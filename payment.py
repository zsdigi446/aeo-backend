"""
支付接口 - 预留真实支付接口，当前支持模拟支付
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import store

router = APIRouter(prefix="/api/payment", tags=["payment"])


class CreateOrderRequest(BaseModel):
    report_id: str
    amount: int = 199  # 单位：分


class SimulatePayRequest(BaseModel):
    order_id: str


@router.post("/create")
async def create_order(req: CreateOrderRequest):
    """创建支付订单，返回订单信息和支付二维码（当前为模拟）"""
    report = await store.get_report(req.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    order = await store.create_order(req.report_id, req.amount)
    return {
        "success": True,
        "order_id": order["order_id"],
        "amount": order["amount"],
        "amount_yuan": order["amount"] / 100,
        "status": order["status"],
        "qr_note": "请扫描二维码支付（当前为模拟支付，点击「模拟支付成功」按钮即可）",
    }


@router.get("/verify/{order_id}")
async def verify_payment(order_id: str):
    """查询支付状态"""
    order = await store.verify_order(order_id)
    if order.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"success": True, "order_id": order_id, "status": order["status"]}


@router.post("/simulate-pay")
async def simulate_pay(req: SimulatePayRequest):
    """模拟支付成功（仅用于演示/开发环境）"""
    ok = await store.confirm_payment(req.order_id)
    if not ok:
        raise HTTPException(status_code=400, detail="订单不存在或已支付")
    return {"success": True, "message": "支付成功！"}


@router.post("/callback")
async def payment_callback(request: dict):
    """真实支付回调接口（预留）
    
    接收第三方支付平台（微信/支付宝/Stripe）的回调通知。
    需要验证签名后更新订单状态。
    """
    # TODO: 实现签名验证
    # TODO: 更新订单状态
    return {"code": "SUCCESS", "message": "回调已接收"}
