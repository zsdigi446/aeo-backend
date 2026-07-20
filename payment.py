"""
支付接口 - 微信支付（Native 扫码 + H5）+ 模拟支付兜底

- PC 端：create_order(device="pc") → 返回 code_url，前端渲染二维码
- 移动端：create_order(device="mobile") → 返回 h5_url，前端跳转调起微信
- 未配置微信密钥时：自动回退到模拟支付（前端显示模拟按钮）
"""
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import store
from wechat_pay import WechatPayClient

router = APIRouter(prefix="/payment", tags=["payment"])

# 价格：完整报告 + Word 下载（单位：分），可被环境变量覆盖
PAY_AMOUNT = int(os.environ.get("WX_PAY_AMOUNT", "9900"))
PRODUCT_DESC = os.environ.get("WX_PRODUCT_DESC", "AEO网站完整分析报告")


class CreateOrderRequest(BaseModel):
    report_id: str
    amount: int = PAY_AMOUNT
    device: str = "pc"  # "pc" | "mobile"


class SimulatePayRequest(BaseModel):
    order_id: str


def _get_client_ip(request: Request) -> str:
    """从代理链中取真实客户端 IP（H5 支付需要）"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("/create")
async def create_order(req: CreateOrderRequest, request: Request):
    """创建支付订单，返回二维码/跳转链接（真实微信或模拟）"""
    report = await store.get_report(req.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    amount = req.amount if req.amount > 0 else PAY_AMOUNT
    order = await store.create_order(req.report_id, amount)
    out_trade_no = order["order_id"]

    # 真实微信支付
    if WechatPayClient.is_enabled():
        try:
            client = WechatPayClient()
            if req.device.lower() == "mobile":
                # H5 支付：返回 h5_url，前端跳转调起微信
                client_ip = _get_client_ip(request)
                redirect = f"https://aeo.miubox.cn/report/{req.report_id}?paid=1"
                h5_url = client.create_h5_order(out_trade_no, PRODUCT_DESC, amount, client_ip, redirect)
                return {
                    "success": True,
                    "order_id": out_trade_no,
                    "amount": amount,
                    "amount_yuan": amount / 100,
                    "status": order["status"],
                    "is_wechat": True,
                    "pay_type": "h5",
                    "h5_url": h5_url,
                    "qr_note": "正在跳转到微信支付…",
                }
            else:
                # Native 扫码支付
                code_url = client.create_native_order(out_trade_no, PRODUCT_DESC, amount)
                return {
                    "success": True,
                    "order_id": out_trade_no,
                    "amount": amount,
                    "amount_yuan": amount / 100,
                    "status": order["status"],
                    "is_wechat": True,
                    "pay_type": "native",
                    "code_url": code_url,
                    "qr_note": "请使用微信「扫一扫」扫描二维码完成支付",
                }
        except Exception as e:
            # 真实支付下单异常，回退模拟模式，避免用户卡死
            return {
                "success": True,
                "order_id": out_trade_no,
                "amount": amount,
                "amount_yuan": amount / 100,
                "status": order["status"],
                "is_wechat": False,
                "error": str(e),
                "qr_note": "支付通道暂时不可用，已切换为演示模式",
            }

    # 模拟支付模式（未配置微信密钥）
    return {
        "success": True,
        "order_id": out_trade_no,
        "amount": amount,
        "amount_yuan": amount / 100,
        "status": order["status"],
        "is_wechat": False,
        "qr_note": "演示模式：点击下方按钮模拟支付成功",
    }


@router.get("/verify/{order_id}")
async def verify_payment(order_id: str):
    """查询支付状态（前端轮询用）"""
    order = await store.verify_order(order_id)
    if order.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"success": True, "order_id": order_id, "status": order["status"]}


@router.post("/simulate-pay")
async def simulate_pay(req: SimulatePayRequest):
    """模拟支付成功（仅用于演示 / 未配置微信密钥时）"""
    ok = await store.confirm_payment(req.order_id)
    if not ok:
        raise HTTPException(status_code=400, detail="订单不存在或已支付")
    return {"success": True, "message": "支付成功！"}


@router.post("/wechat/callback")
async def wechat_callback(request: Request):
    """微信支付结果回调通知（统一下单时配置的 WX_PAY_NOTIFY_URL）

    微信回调头为小写（wechatpay-signature 等），wechatpayv3 已兼容 FastAPI。
    验签失败返回 FAIL，让微信按策略重试；成功返回 SUCCESS。
    """
    headers = dict(request.headers)
    body = await request.body()
    try:
        client = WechatPayClient()
        data = client.parse_callback(headers, body)
    except Exception:
        return {"code": "FAIL", "message": "签名验证失败"}

    resource = data.get("resource", {})
    out_trade_no = resource.get("out_trade_no")
    transaction_id = resource.get("transaction_id")
    trade_state = resource.get("trade_state")

    if trade_state == "SUCCESS" and out_trade_no:
        await store.confirm_payment(out_trade_no, transaction_id)
        return {"code": "SUCCESS", "message": "成功"}

    # 非成功状态（如 CLOSED/REFUND）也返回 SUCCESS，避免微信重复重试
    return {"code": "SUCCESS", "message": "已接收"}
