"""
持久化存储（JSON 文件）
- 报告与订单写入磁盘，进程重启/平台休眠后仍可恢复
- 已付款报告长期保留，支持随时下载 Word
- 兼容 Railway / Render 等免费层（单实例即可）
"""
import json
import os
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional


# 数据目录（相对工作目录）
DATA_DIR = os.environ.get("AEO_DATA_DIR", "data")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
ORDERS_DIR = os.path.join(DATA_DIR, "orders")

# 进程内缓存（启动时从磁盘加载）
REPORTS_CACHE: dict[str, dict] = {}
ORDERS_CACHE: dict[str, dict] = {}

# 简单锁，避免并发写入冲突
_LOCK = asyncio.Lock()


def _ensure_dirs():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(ORDERS_DIR, exist_ok=True)


def _report_path(report_id: str) -> str:
    return os.path.join(REPORTS_DIR, f"{report_id}.json")


def _order_path(order_id: str) -> str:
    return os.path.join(ORDERS_DIR, f"{order_id}.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(obj):
    """序列化辅助：dataclass / 不可 JSON 类型先转 dict / str。"""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _load_disk():
    """启动时从磁盘加载全部报告与订单到内存。"""
    _ensure_dirs()
    # 加载报告
    for fname in os.listdir(REPORTS_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(REPORTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            rid = data.get("id")
            if rid:
                REPORTS_CACHE[rid] = data
        except Exception:
            # 单条损坏不影响整体启动
            continue
    # 加载订单
    for fname in os.listdir(ORDERS_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(ORDERS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            oid = data.get("order_id")
            if oid:
                ORDERS_CACHE[oid] = data
        except Exception:
            continue


def _save_report_to_disk(report_id: str, data: dict):
    _ensure_dirs()
    fpath = _report_path(report_id)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=_serialize, indent=2)


def _save_order_to_disk(order_id: str, data: dict):
    _ensure_dirs()
    fpath = _order_path(order_id)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=_serialize, indent=2)


# 启动时加载历史数据
_load_disk()


async def save_report(url: str, page_data, aeo_score, full_report: dict) -> str:
    """保存报告到缓存和磁盘，返回 report_id"""
    report_id = uuid.uuid4().hex[:12]
    record = {
        "id": report_id,
        "url": url,
        "target_title": full_report.get("meta", {}).get("site_name", ""),
        "scores": {
            "total": aeo_score.total_score,
            "grade": aeo_score.grade,
        },
        "full_report": full_report,
        "status": "completed",
        "created_at": _now_iso(),
    }
    async with _LOCK:
        REPORTS_CACHE[report_id] = record
        _save_report_to_disk(report_id, record)
    return report_id


async def get_report(report_id: str) -> Optional[dict]:
    """从缓存获取报告；若内存未命中但磁盘存在，则重新加载。"""
    if report_id in REPORTS_CACHE:
        return REPORTS_CACHE[report_id]
    fpath = _report_path(report_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            REPORTS_CACHE[report_id] = data
            return data
        except Exception:
            return None
    return None


async def create_order(report_id: str, amount: int = 9900) -> dict:
    """创建支付订单（order_id 同时作为微信的 out_trade_no）"""
    order_id = uuid.uuid4().hex[:16]
    record = {
        "order_id": order_id,
        "out_trade_no": order_id,
        "report_id": report_id,
        "amount": amount,
        "status": "pending",
        "created_at": _now_iso(),
        "paid_at": None,
        "transaction_id": None,
    }
    async with _LOCK:
        ORDERS_CACHE[order_id] = record
        _save_order_to_disk(order_id, record)
    return ORDERS_CACHE[order_id]


async def verify_order(order_id: str) -> dict:
    """查询订单状态；内存未命中时回查磁盘。"""
    order = ORDERS_CACHE.get(order_id)
    if not order:
        fpath = _order_path(order_id)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    order = json.load(f)
                ORDERS_CACHE[order_id] = order
            except Exception:
                order = None
    if order:
        return {
            "order_id": order["order_id"],
            "report_id": order["report_id"],
            "amount": order["amount"],
            "status": order["status"],
            "transaction_id": order.get("transaction_id"),
        }
    return {"status": "not_found"}


async def confirm_payment(order_id: str, transaction_id: str = None) -> bool:
    """确认支付成功，更新订单状态并记录微信交易号"""
    async with _LOCK:
        order = ORDERS_CACHE.get(order_id)
        if order and order["status"] == "pending":
            order["status"] = "paid"
            order["paid_at"] = _now_iso()
            if transaction_id:
                order["transaction_id"] = transaction_id
            _save_order_to_disk(order_id, order)
            return True
    return False


async def find_order_by_report(report_id: str, status: Optional[str] = None) -> Optional[dict]:
    """根据 report_id 查找关联订单（用于支付后重载报告等场景）。"""
    for order in ORDERS_CACHE.values():
        if order.get("report_id") == report_id:
            if status is None or order.get("status") == status:
                return order
    # 回查磁盘
    if not os.path.exists(ORDERS_DIR):
        return None
    for fname in os.listdir(ORDERS_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(ORDERS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                order = json.load(f)
            if order.get("report_id") == report_id:
                if status is None or order.get("status") == status:
                    ORDERS_CACHE[order["order_id"]] = order
                    return order
        except Exception:
            continue
    return None
