"""
AEO 分析工具 - FastAPI 主入口（无状态模式，适配 Railway 等免费休眠层）
"""
import json
import io
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from analyzer.crawler import Crawler
from analyzer.scorer import AEOScorer
from analyzer.reporter import generate_report
import store
from payment import router as payment_router

# 前端构建产物目录（Vercel 部署时后端不 serve 前端，此处仅沙箱/单实例方便）
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 无状态模式：无需初始化数据库
    yield

app = FastAPI(title="AEO Analyzer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(payment_router)

crawler = Crawler(timeout=15)
scorer = AEOScorer()


class AnalyzeRequest(BaseModel):
    url: str


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """分析 URL 的 AEO 健康度"""
    url = req.url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    # 爬取
    page_data = await crawler.crawl(url)
    if page_data.error:
        raise HTTPException(status_code=400, detail=f"无法访问目标网站：{page_data.error}")

    # 评分
    aeo_score = scorer.score(page_data)

    # 生成报告
    report = generate_report(url, page_data, aeo_score)

    # 保存到内存缓存（无状态，重启后需重新分析）
    report_id = await store.save_report(url, page_data, aeo_score, report)

    return {
        "success": True,
        "report_id": report_id,
        "total_score": aeo_score.total_score,
        "grade": aeo_score.grade,
        "site_name": report["meta"]["site_name"],
    }


@app.get("/api/report/{report_id}")
async def get_report(report_id: str, type: str = Query("free", pattern="^(free|full)$")):
    """获取报告内容
    - type=free: 返回前 1/3 内容（免费）
    - type=full: 返回完整内容（需验证支付）
    """
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在或已过期（请重新分析）")

    full = report["full_report"]
    if type == "full":
        return {"success": True, "data": full, "is_full": True}

    # 免费版：返回前 3 部分
    free_keys = ["meta", "part1_overview", "part2_advantages", "part3_problems", "dimension_details"]
    free_data = {k: full[k] for k in free_keys if k in full}
    free_data["meta"] = full.get("meta", {})
    return {
        "success": True,
        "data": free_data,
        "is_full": False,
        "total_parts": 9,
        "free_parts": 3,
        "message": "这是免费版本，包含前 3 部分内容。支付后可查看完整 9 部分报告并下载 Word 版本。",
    }


@app.get("/api/report/{report_id}/word")
async def download_word(report_id: str):
    """下载 Word 版报告"""
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在或已过期（请重新分析）")

    from word_generator import generate_word
    doc_bytes = generate_word(report["full_report"])
    site_name = report["full_report"]["meta"]["site_name"].replace(" ", "_")[:30]
    # ASCII 安全的文件名，避免编码问题
    ascii_name = "AEO_Report"
    filename = f"{ascii_name}_{report_id[:8]}.docx"

    return StreamingResponse(
        io.BytesIO(doc_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ===== 前端静态文件服务（生产模式） =====
# 如果前端已构建（dist 存在），由后端统一提供页面，避免额外端口依赖
if os.path.exists(FRONTEND_DIST) and os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
    # 挂载静态资源（assets 等）
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA 路由回退：非 /api 路径都返回 index.html"""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        index_file = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index_file)
