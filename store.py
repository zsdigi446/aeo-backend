"""
持久化存储
- 优先使用 Supabase Postgres（配置 SUPABASE_URL / SUPABASE_KEY 时启用）
- 未配置或 Supabase 不可用时，回退到本地 JSON 文件（data/）
- 已付款报告长期保留，支持随时下载 Word

Supabase 使用 service_role key（服务端专用，绕过 RLS），不要在前端暴露。
表结构（在 Supabase SQL Editor 执行）：
  create table reports (
    id text primary key,
    url text,
    target_title text,
    scores jsonb,
    full_report jsonb,
    status text,
    created_at timestamptz default now()
  );
  create table orders (
    order_id text primary key,
    out_trade_no text,
    report_id text references reports(id),
    amount int,
    status text,
    created_at timestamptz default now(),
    paid_at timestamptz,
    transaction_id text
  );
"""
import json
import os
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx


# ========================= 配置 =========================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
_SB_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)

# 磁盘回退目录
DATA_DIR = os.environ.get("AEO_DATA_DIR", "data")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
ORDERS_DIR = os.path.join(DATA_DIR, "orders")

# 进程内缓存（热读取 + 减少数据库压力）
REPORTS_CACHE: dict[str, dict] = {}
ORDERS_CACHE: dict[str, dict] = {}

# 并发写锁
_LOCK = asyncio.Lock()

# Supabase 异步 HTTP 客户端
_http_client: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=15)
    return _http_client


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ========================= 磁盘回退 =========================
def _ensure_dirs():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(ORDERS_DIR, exist_ok=True)


def _report_path(report_id: str) -> str:
    return os.path.join(REPORTS_DIR, f"{report_id}.json")


def _order_path(order_id: str) -> str:
    return os.path.join(ORDERS_DIR, f"{order_id}.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_disk():
    """启动时从磁盘加载全部报告与订单到内存（仅作回退用）。"""
    _ensure_dirs()
    for fname in os.listdir(REPORTS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(REPORTS_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("id"):
                REPORTS_CACHE[data["id"]] = data
        except Exception:
            continue
    for fname in os.listdir(ORDERS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(ORDERS_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("order_id"):
                ORDERS_CACHE[data["order_id"]] = data
        except Exception:
            continue


def _save_report_to_disk(report_id: str, data: dict):
    _ensure_dirs()
    with open(_report_path(report_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_order_to_disk(order_id: str, data: dict):
    _ensure_dirs()
    with open(_order_path(order_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_load_disk()


# ========================= Supabase 辅助 =========================
async def _sb_get_report(report_id: str) -> Optional[dict]:
    r = await _client().get(
        f"{SUPABASE_URL}/rest/v1/reports",
        params={"id": f"eq.{report_id}", "select": "*"},
        headers=_sb_headers(),
    )
    rows = r.json()
    return rows[0] if isinstance(rows, list) and rows else None


async def _sb_insert_report(record: dict):
    await _client().post(
        f"{SUPABASE_URL}/rest/v1/reports",
        json=record,
        headers=_sb_headers(),
    )


async def _sb_get_order(order_id: str) -> Optional[dict]:
    r = await _client().get(
        f"{SUPABASE_URL}/rest/v1/orders",
        params={"order_id": f"eq.{order_id}", "select": "*"},
        headers=_sb_headers(),
    )
    rows = r.json()
    return rows[0] if isinstance(rows, list) and rows else None


async def _sb_insert_order(record: dict):
    await _client().post(
        f"{SUPABASE_URL}/rest/v1/orders",
        json=record,
        headers=_sb_headers(),
    )


async def _sb_update_order(order_id: str, patch: dict):
    await _client().patch(
        f"{SUPABASE_URL}/rest/v1/orders",
        params={"order_id": f"eq.{order_id}"},
        json=patch,
        headers=_sb_headers(),
    )


# ========================= 公共接口 =========================
async def save_report(url: str, page_data, aeo_score, full_report: dict) -> str:
    """保存报告（Supabase 优先，失败回退磁盘），返回 report_id。"""
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
        if _SB_ENABLED:
            try:
                await _sb_insert_report(record)
            except Exception:
                # Supabase 不可用时回退磁盘，保证报告不丢
                _save_report_to_disk(report_id, record)
        else:
            _save_report_to_disk(report_id, record)
    return report_id


async def get_report(report_id: str) -> Optional[dict]:
    """获取报告：内存 → Supabase → 磁盘。"""
    if report_id in REPORTS_CACHE:
        return REPORTS_CACHE[report_id]
    if _SB_ENABLED:
        try:
            data = await _sb_get_report(report_id)
            if data:
                REPORTS_CACHE[report_id] = data
                return data
        except Exception:
            pass
    # 磁盘回退
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
    """创建支付订单（order_id 同时作为微信的 out_trade_no）。"""
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
        if _SB_ENABLED:
            try:
                await _sb_insert_order(record)
            except Exception:
                _save_order_to_disk(order_id, record)
        else:
            _save_order_to_disk(order_id, record)
    return ORDERS_CACHE[order_id]


async def verify_order(order_id: str) -> dict:
    """查询订单状态：内存 → Supabase → 磁盘。"""
    order = ORDERS_CACHE.get(order_id)
    if order is None and _SB_ENABLED:
        try:
            order = await _sb_get_order(order_id)
            if order:
                ORDERS_CACHE[order_id] = order
        except Exception:
            order = None
    if order is None and os.path.exists(_order_path(order_id)):
        try:
            with open(_order_path(order_id), "r", encoding="utf-8") as f:
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
    """确认支付成功，更新订单状态并记录微信交易号。"""
    patch = {
        "status": "paid",
        "paid_at": _now_iso(),
    }
    if transaction_id:
        patch["transaction_id"] = transaction_id
    async with _LOCK:
        order = ORDERS_CACHE.get(order_id)
        if order and order["status"] == "pending":
            order.update(patch)
            if _SB_ENABLED:
                try:
                    await _sb_update_order(order_id, patch)
                except Exception:
                    _save_order_to_disk(order_id, order)
            else:
                _save_order_to_disk(order_id, order)
            return True
    return False


async def find_order_by_report(report_id: str, status: Optional[str] = None) -> Optional[dict]:
    """根据 report_id 查找关联订单（支付后重载报告等场景）。"""
    for order in ORDERS_CACHE.values():
        if order.get("report_id") == report_id:
            if status is None or order.get("status") == status:
                return order
    if _SB_ENABLED:
        try:
            r = await _client().get(
                f"{SUPABASE_URL}/rest/v1/orders",
                params={"report_id": f"eq.{report_id}", "select": "*"},
                headers=_sb_headers(),
            )
            for order in r.json():
                ORDERS_CACHE[order["order_id"]] = order
                if status is None or order.get("status") == status:
                    return order
        except Exception:
            pass
    if os.path.exists(ORDERS_DIR):
        for fname in os.listdir(ORDERS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(ORDERS_DIR, fname), "r", encoding="utf-8") as f:
                    order = json.load(f)
                if order.get("report_id") == report_id:
                    if status is None or order.get("status") == status:
                        ORDERS_CACHE[order["order_id"]] = order
                        return order
            except Exception:
                continue
    return None
