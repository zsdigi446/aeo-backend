"""
微信支付 v3 封装（Native 扫码支付 + H5 支付）

所有敏感配置从环境变量读取，不写死在代码中，也不提交到 git。
需在部署平台（Render）配置以下环境变量：
  WX_PAY_ENABLED    true 启用真实微信支付；false/未设置走模拟支付
  WX_MCH_ID         微信商户号
  WX_APP_ID         已绑定商户号的 AppID（公众号/小程序）
  WX_API_V3_KEY     APIv3 密钥（32 位）
  WX_SERIAL_NO      商户 API 证书序列号
  WX_PRIVATE_KEY    商户 API 私钥（apiclient_key.pem 全文，Render 支持多行粘贴）
  WX_PAY_NOTIFY_URL 公网回调地址，如 https://aeo-backend.onrender.com/payment/wechat/callback
"""
import os
from wechatpayv3 import WeChatPay, WeChatPayType


class WechatPayClient:
    """微信支付客户端封装（单例式，按需初始化）"""

    @staticmethod
    def is_enabled() -> bool:
        """是否启用真实微信支付：WX_PAY_ENABLED=true 且关键配置齐全"""
        enabled = os.environ.get("WX_PAY_ENABLED", "false").lower() == "true"
        configured = all([
            os.environ.get("WX_MCH_ID"),
            os.environ.get("WX_APP_ID"),
            os.environ.get("WX_API_V3_KEY"),
            os.environ.get("WX_SERIAL_NO"),
            os.environ.get("WX_PRIVATE_KEY"),
        ])
        return enabled and configured

    def __init__(self):
        self.mchid = os.environ["WX_MCH_ID"]
        self.appid = os.environ["WX_APP_ID"]
        self.apiv3_key = os.environ["WX_API_V3_KEY"]
        self.serial_no = os.environ["WX_SERIAL_NO"]
        self.private_key = os.environ["WX_PRIVATE_KEY"]
        self.notify_url = os.environ.get("WX_PAY_NOTIFY_URL", "")
        self.wxpay = WeChatPay(
            wechatpay_type=WeChatPayType.NATIVE,  # 仅作为默认类型，实际按 pay_type 覆盖
            mchid=self.mchid,
            private_key=self.private_key,
            cert_serial_no=self.serial_no,
            appid=self.appid,
            apiv3_key=self.apiv3_key,
            notify_url=self.notify_url,
        )

    def create_native_order(self, out_trade_no: str, description: str, total: int) -> str:
        """Native 扫码支付统一下单，返回 code_url（前端据此生成二维码）"""
        resp = self.wxpay.pay(
            description=description,
            out_trade_no=out_trade_no,
            amount={"total": total, "currency": "CNY"},
            pay_type=WeChatPayType.NATIVE,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"微信下单失败({resp.status_code}): {data}")
        code_url = data.get("code_url")
        if not code_url:
            raise RuntimeError(f"微信下单未返回 code_url: {data}")
        return code_url

    def create_h5_order(self, out_trade_no: str, description: str, total: int,
                        client_ip: str = "127.0.0.1", redirect_url: str = None) -> str:
        """H5 支付统一下单，返回 h5_url（前端跳转直接调起微信）"""
        scene_info = {
            "payer_client_ip": client_ip,
            "h5_info": {
                "type": "Wap",
                "app_name": "AEO分析报告",
                "app_url": "https://aeo.miubox.cn",
            },
        }
        resp = self.wxpay.pay(
            description=description,
            out_trade_no=out_trade_no,
            amount={"total": total, "currency": "CNY"},
            scene_info=scene_info,
            pay_type=WeChatPayType.H5,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"微信下单失败({resp.status_code}): {data}")
        h5_url = data.get("h5_url")
        if not h5_url:
            raise RuntimeError(f"微信下单未返回 h5_url: {data}")
        # 拼接支付完成后的回跳地址（需为已配置的 H5 支付域名）
        if redirect_url:
            from urllib.parse import quote
            sep = "&" if "?" in h5_url else "?"
            h5_url = f"{h5_url}{sep}redirect_url={quote(redirect_url, safe='')}"
        return h5_url

    def parse_callback(self, headers: dict, body) -> dict:
        """验签并解密微信回调，返回解密后的通知数据。验签失败抛异常。"""
        result = self.wxpay.callback(headers, body)
        if not result:
            raise RuntimeError("微信回调验签失败")
        return result

    def query_order(self, out_trade_no: str) -> dict:
        """查询订单状态（兜底用，前端轮询也可直接查内存订单）"""
        resp = self.wxpay.query(out_trade_no=out_trade_no)
        return resp.json()
