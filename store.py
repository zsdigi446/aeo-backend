"""
无状态内存存储 - 适配 Railway 等免费休眠层
报告与订单存于进程内存，重启后清空（用户重新分析即可）
避免 SQLite 在休眠层丢数据的问题
"""
import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional


# 进程内缓存（单实例足够，Railway 免费层默认单实例）
REPORTS_CACHE: dict[str, dict] = {}
ORDERS_CACHE: dict[str, dict] = {}

# 简单锁，避免并发写入冲突
_LOCK = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def save_report(url: str, page_data, aeo_score, full_report: dict) -> str:
    """保存报告到内存缓存，返回 report_id"""
    report_id = uuid.uuid4().hex[:12]
    async with _LOCK:
        REPORTS_CACHE[report_id] = {
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
    return report_id


async def get_report(report_id: str) -> Optional[dict]:
    """从缓存获取报告，不存在返回 None"""
    return REPORTS_CACHE.get(report_id)


async def create_order(report_id: str, amount: int = 9900) -> dict:
    """创建支付订单（order_id 同时作为微信的 out_trade_no）"""
    order_id = uuid.uuid4().hex[:16]
    async with _LOCK:
        ORDERS_CACHE[order_id] = {
            "order_id": order_id,
            "out_trade_no": order_id,
            "report_id": report_id,
            "amount": amount,
            "status": "pending",
            "created_at": _now_iso(),
            "paid_at": None,
            "transaction_id": None,
        }
    return ORDERS_CACHE[order_id]


async def verify_order(order_id: str) -> dict:
    """查询订单状态"""
    order = ORDERS_CACHE.get(order_id)
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
            return True
    return False
