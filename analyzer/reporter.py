"""
AEO 报告生成器 - 按照用户上传的报告模板格式生成结构化报告
"""
import json
from analyzer.crawler import PageData
from analyzer.scorer import AEOScore, DimScore


def generate_report(url: str, page_data: PageData, aeo_score: AEOScore) -> dict:
    """生成完整的 AEO 分析报告（JSON 结构）"""

    domain = _extract_domain(url)
    site_name = page_data.title or domain

    report = {
        "meta": {
            "url": url,
            "domain": domain,
            "site_name": site_name,
            "total_score": aeo_score.total_score,
            "grade": aeo_score.grade,
            "summary": aeo_score.summary,
        },
        "part1_overview": _build_part1_overview(aeo_score, page_data),
        "part2_advantages": _build_part2_advantages(page_data),
        "part3_problems": _build_part3_problems(page_data, aeo_score),
        "part4_content_opportunities": _build_part4_opportunities(page_data, site_name, domain),
        "part5_priority_pages": _build_part5_priority_pages(page_data, site_name, domain),
        "part6_page_template": _build_part6_template(page_data, site_name, domain),
        "part7_technical_suggestions": _build_part7_technical(page_data, aeo_score),
        "part8_measurement": _build_part8_measurement(site_name, domain),
        "part9_conclusion": _build_part9_conclusion(page_data, aeo_score, site_name, domain),
        "dimension_details": [{
            "name": dim.name,
            "score": dim.score,
            "weight": dim.weight,
            "details": dim.details,
            "suggestions": dim.suggestions,
        } for dim in aeo_score.dimensions],
    }
    return report


def _extract_domain(url: str) -> str:
    import re
    m = re.search(r'https?://([^/]+)', url)
    return m.group(1) if m else url


def _build_part1_overview(aeo_score, page_data):
    dims = aeo_score.dimensions
    items = []
    for dim in dims:
        items.append({
            "name": dim.name,
            "score": dim.score,
            "max_score": 100,
            "weight": int(dim.weight * 100),
            "key_finding": dim.details[0] if dim.details else dim.suggestions[0] if dim.suggestions else "暂无数据",
        })
    return {
        "title": "一、AEO 健康度评分总览",
        "total_score": aeo_score.total_score,
        "grade": aeo_score.grade,
        "summary": aeo_score.summary,
        "dimensions": items,
    }


def _build_part2_advantages(page_data):
    items = []
    idx = 1
    if page_data.title:
        items.append(f"网站有明确的页面标题「{page_data.title[:80]}」，有助于 AI 理解页面主题")
    if page_data.has_schema:
        items.append(f"已部署 Schema 结构化数据（{', '.join(page_data.schema_types[:5])}），有助于 AI 解析页面内容")
    if page_data.has_faq:
        items.append("包含 FAQ 结构，AI 可直接引用问答内容")
    if page_data.has_comparison_content:
        items.append("包含对比类内容，这是 AI 引用偏好最高的内容类型之一")
    if page_data.has_author_info:
        items.append("有作者/团队信息展示，增强 AI 信任度")
    if page_data.has_testimonials:
        items.append("包含用户评价/案例信号，有助于建立可信度")
    if page_data.has_viewport_meta:
        items.append("页面支持响应式设计（Viewport），移动端体验基础良好")
    if page_data.word_count > 1000:
        items.append(f"页面内容丰富（约 {page_data.word_count} 字符），有足够信息供 AI 提取")
    if not items:
        items.append("网站已在线可访问，这是 AEO 优化的基础前提")
    return {"title": "二、网站当前 AEO 优势", "items": items}


def _build_part3_problems(page_data, aeo_score):
    problems = []
    idx = 1

    # 从评分维度中提取问题
    for dim in aeo_score.dimensions:
        if dim.score < 60:
            problems.append({
                "id": idx,
                "title": f"问题 {idx}：{dim.name}维度评分较低（{dim.score}分）",
                "detail": "；".join(dim.suggestions[:3]) if dim.suggestions else f"「{dim.name}」需要重点优化",
            })
            idx += 1

    if not page_data.has_schema:
        problems.append({
            "id": idx, "title": f"问题 {idx}：缺少 Schema 结构化数据",
            "detail": "网站未检测到 JSON-LD 格式的结构化数据。Schema 是 AI 理解页面内容的关键信号，建议添加 Organization、Product、FAQPage、Article 等类型的 Schema 标记。"
        }); idx += 1

    if not page_data.has_faq:
        problems.append({
            "id": idx, "title": f"问题 {idx}：缺少 FAQ 板块",
            "detail": "FAQ 是 AI 引用率最高的内容格式之一。建议在核心页面添加问答结构，直接回答用户最关心的问题。"
        }); idx += 1

    if not page_data.has_comparison_content:
        problems.append({
            "id": idx, "title": f"问题 {idx}：缺少对比类内容",
            "detail": "AI 非常偏好引用对比内容（A vs B、优缺点、适用场景对比）。建议创建竞品对比、方案对比等页面。"
        }); idx += 1

    if page_data.h2_texts and not any("?" in h or "？" in h for h in page_data.h2_texts):
        problems.append({
            "id": idx, "title": f"问题 {idx}：标题缺乏问题式结构",
            "detail": "当前 H2 标题以陈述为主，缺少问题式标题。AI 更偏好能直接匹配用户问题的标题结构。"
        }); idx += 1

    if not problems:
        problems.append({
            "id": 1, "title": "网站整体表现良好",
            "detail": "各项指标基本达标，建议进一步深化语义场景覆盖和对比内容建设。"
        })

    return {"title": "三、当前最大 AEO 问题", "problems": problems}


def _build_part4_opportunities(page_data, site_name, domain):
    industry = _guess_industry(page_data)
    scenarios = _generate_scenarios(site_name, domain, industry)

    return {
        "title": "四、Persona × Funnel × Use Case 内容机会",
        "description": f"基于 {site_name} 的行业特点和现有内容，以下是推荐的 AI 语义场景覆盖矩阵：",
        "scenarios": scenarios,
    }


def _build_part5_priority_pages(page_data, site_name, domain):
    industry = _guess_industry(page_data)
    pages = _generate_priority_pages(site_name, domain, industry)

    return {
        "title": "五、最值得优先做的 AEO 页面",
        "description": "以下页面按优先级分为四组，建议按顺序逐步实施：",
        "groups": [
            {"name": "第一组：对比类页面", "pages": pages[:5]},
            {"name": "第二组：适合/不适合类页面", "pages": pages[5:10]},
            {"name": "第三组：场景/用例页面", "pages": pages[10:15]},
            {"name": "第四组：FAQ/知识库页面", "pages": pages[15:20]},
        ],
        "top5": pages[:5],
    }


def _build_part6_template(page_data, site_name, domain):
    industry = _guess_industry(page_data)
    example = _generate_template_example(site_name, domain, industry)
    return {
        "title": "六、页面重构模板",
        "description": "以下是一个示例页面结构，展示如何将普通产品/服务页面改造成 AI 友好的「决策答案页」：",
        "example": example,
    }


def _build_part7_technical(page_data, aeo_score):
    items = []
    if not page_data.has_schema:
        items.append("为核心页面添加 Product、FAQPage、Breadcrumb、Organization、Article 等结构化数据标记")
    if not page_data.has_viewport_meta:
        items.append("添加 Viewport Meta 标签，确保移动端适配")
    if not page_data.meta_description:
        items.append("为每个页面添加独特的 Meta Description（50-160 字符）")
    items.extend([
        "在首页、分类页和产品页首屏增加「直接回答型摘要」，让 AI 更快抓取核心信息",
        "减少重复导航和促销文本对主内容抓取的干扰，让核心信息更靠前",
        "优化图片 Alt 文本，使用具体、自然的描述而非只重复产品名",
        "为博客和内容页统一添加作者信息、更新时间和数据来源",
        "将信任信号（评价、保障、退换政策）做成可读文本模块，而非仅用图标展示",
        "优化页面加载速度，确保移动端 PageSpeed 评分 ≥ 70",
    ])
    return {"title": "七、技术与抓取层面建议", "items": items}


def _build_part8_measurement(site_name, domain):
    return {
        "title": "八、AEO 效果衡量方式",
        "description": f"建议为 {site_name} 建立 AI Answer Share 监测机制，每月固定测试一组核心 prompt，关注三个维度：",
        "dimensions": [
            {
                "name": "AI 可见度",
                "description": "每月测试 5-10 个核心问题，检查品牌是否出现在 AI 推荐答案中",
                "prompts": [
                    f"{site_name} 是什么？",
                    f"{site_name} 好用吗？",
                    f"{site_name} 适合什么类型的用户？",
                    f"{site_name} 和竞品有什么区别？",
                ]
            },
            {
                "name": "引用份额",
                "description": "在 ChatGPT、Perplexity、Gemini 等工具中测试 10-15 个问题，对比竞品出现频率",
                "prompts": [
                    f"最好的[{_guess_industry(page_data=None)}]工具/产品推荐",
                    f"{site_name} vs 竞品 哪个好？",
                    f"适合小团队的[{_guess_industry(page_data=None)}]方案",
                ]
            },
            {
                "name": "品牌叙事准确度",
                "description": "直接问 AI 关于品牌的问题，检查回答是否准确、完整",
                "prompts": [
                    f"What is {site_name}?",
                    f"What are the pros and cons of {site_name}?",
                    f"Who is {site_name} best for?",
                    f"What problems does {site_name} solve?",
                ]
            },
        ],
    }


def _build_part9_conclusion(page_data, aeo_score, site_name, domain):
    grade = aeo_score.grade
    total = aeo_score.total_score
    worst = min(aeo_score.dimensions, key=lambda x: x.score)
    best = max(aeo_score.dimensions, key=lambda x: x.score)

    if total >= 70:
        level_text = "基础不错"
        action = f"当前最需要改进的是「{worst.name}」维度，同时建议深化「{best.name}」的优势，建立更完整的 AI 答案素材库。"
    elif total >= 50:
        level_text = "有一定基础，但还有较大提升空间"
        action = f"建议优先优化「{worst.name}」({worst.score}分)和内容结构，然后系统性地补充对比内容和 FAQ。"
    else:
        level_text = "需要系统性的 AEO 优化"
        action = f"网站目前在多个维度都有提升空间，建议从内容结构重构和 Schema 部署开始，逐步建立 AI 友好的内容体系。"

    return {
        "title": "九、最终判断",
        "overview": f"{site_name} 的 AEO {level_text}，总分 {total}/100（{grade} 级）。",
        "action": action,
        "summary": f"核心建议：不要把网站仅仅当作展示窗口，而要把它升级为「AI 决策答案库」——在足够多的具体问题里，让 AI 知道什么时候应该推荐你。",
    }


def _guess_industry(page_data):
    """根据页面内容猜测行业"""
    if page_data is None:
        return "通用"
    text = (page_data.title + " " + " ".join(page_data.h2_texts) + " " + page_data.body_text[:500]).lower()
    if any(kw in text for kw in ["shop", "buy", "product", "price", "cart", "sale", "产品", "购买"]):
        return "电商/零售"
    if any(kw in text for kw in ["saas", "software", "api", "platform", "软件", "平台"]):
        return "SaaS/软件"
    if any(kw in text for kw in ["blog", "article", "news", "博客", "新闻"]):
        return "内容/媒体"
    if any(kw in text for kw in ["service", "consult", "agency", "服务", "咨询"]):
        return "服务/咨询"
    return "通用"


def _generate_scenarios(site_name, domain, industry):
    """根据行业生成 Persona × Funnel × Use Case 矩阵"""
    templates = {
        "电商/零售": [
            {"persona": "第一次购买的新用户", "funnel": "Mid / Bottom", "use_case": f"不了解产品怎么选，需要购买指南", "ai_question": f"{site_name} 的产品适合新手吗？怎么选？", "page": f"{site_name} 新手购买指南"},
            {"persona": "预算敏感的消费者", "funnel": "Mid", "use_case": "想确认性价比，和竞品比较", "ai_question": f"{site_name} 和竞品比哪个更值得买？", "page": f"{site_name} vs 竞品：性价比对比"},
            {"persona": "注重品质的专业用户", "funnel": "Bottom", "use_case": "关心材质、工艺、售后保障", "ai_question": f"{site_name} 的产品质量怎么样？有什么保障？", "page": f"{site_name} 品质与售后详解"},
            {"persona": "给他人买礼物的用户", "funnel": "Top / Mid", "use_case": "不知道该买什么，需要礼物推荐", "ai_question": f"{site_name} 适合送礼吗？有什么推荐？", "page": f"{site_name} 礼物选购指南"},
            {"persona": "回头客/老用户", "funnel": "Bottom", "use_case": "想了解新品、升级或补充购买", "ai_question": f"{site_name} 有什么新品推荐？", "page": f"{site_name} 新品与升级指南"},
            {"persona": "移动端浏览用户", "funnel": "Top / Mid", "use_case": "碎片时间浏览，需要快速了解", "ai_question": f"{site_name} 是什么品牌？靠谱吗？", "page": f"关于 {site_name}：品牌故事与承诺"},
        ],
        "SaaS/软件": [
            {"persona": "小团队/初创公司创始人", "funnel": "Mid", "use_case": f"预算有限，需要性价比高的工具", "ai_question": f"{site_name} 适合小团队吗？价格贵不贵？", "page": f"{site_name} 小团队方案"},
            {"persona": "企业采购决策者", "funnel": "Bottom", "use_case": "关心安全性、集成能力、ROI", "ai_question": f"{site_name} 企业版有什么功能？安全吗？", "page": f"{site_name} 企业方案与安全"},
            {"persona": "从竞品切换的用户", "funnel": "Mid", "use_case": "觉得现有工具太贵或不好用", "ai_question": f"{site_name} 和 XX 比哪个好？迁移麻烦吗？", "page": f"{site_name} vs 竞品对比"},
            {"persona": "技术评估者/开发者", "funnel": "Top / Mid", "use_case": "关心 API、文档、技术架构", "ai_question": f"{site_name} 有 API 吗？技术文档全吗？", "page": f"{site_name} 技术文档与 API"},
            {"persona": "非技术背景的部门主管", "funnel": "Top", "use_case": "需要简单易用的工具，不想学复杂系统", "ai_question": f"{site_name} 容易上手吗？需要技术背景吗？", "page": f"{site_name} 快速上手指南"},
            {"persona": "自由职业者/个人用户", "funnel": "Mid / Bottom", "use_case": "需要个人能负担的方案", "ai_question": f"{site_name} 有免费版或个人版吗？", "page": f"{site_name} 个人/免费方案"},
        ],
        "内容/媒体": [
            {"persona": "信息搜索者", "funnel": "Top", "use_case": "想了解某个话题或概念", "ai_question": f"{site_name} 上的信息可信吗？", "page": f"关于 {site_name}：编辑方针与可信度"},
            {"persona": "深度学习者", "funnel": "Mid", "use_case": "需要系统性的知识体系", "ai_question": f"{site_name} 有哪些深度内容？", "page": f"{site_name} 内容导航与专题"},
            {"persona": "内容创作者", "funnel": "Mid / Bottom", "use_case": "寻找可引用的权威来源", "ai_question": f"{site_name} 的内容可以引用吗？", "page": f"{site_name} 引用与合作指南"},
        ],
        "服务/咨询": [
            {"persona": "有明确需求的客户", "funnel": "Bottom", "use_case": "需要确认服务是否适合自己的情况", "ai_question": f"{site_name} 适合我的情况吗？", "page": f"{site_name} 服务适用场景"},
            {"persona": "在比较服务商的客户", "funnel": "Mid", "use_case": "在几家服务商之间比较", "ai_question": f"{site_name} 和 XX 服务有什么区别？", "page": f"{site_name} vs 竞品服务对比"},
            {"persona": "预算有限的客户", "funnel": "Mid / Bottom", "use_case": "关心价格和服务范围", "ai_question": f"{site_name} 的价格是多少？值不值？", "page": f"{site_name} 定价与价值说明"},
            {"persona": "第一次使用服务的客户", "funnel": "Top", "use_case": "不了解服务流程和预期效果", "ai_question": f"{site_name} 的服务流程是怎样的？", "page": f"{site_name} 服务流程与案例"},
        ],
    }

    default = [
        {"persona": "潜在客户", "funnel": "Top", "use_case": f"第一次了解 {site_name}", "ai_question": f"{site_name} 是什么？靠谱吗？", "page": f"关于 {site_name}"},
        {"persona": "对比中的用户", "funnel": "Mid", "use_case": f"在 {site_name} 和竞品之间选择", "ai_question": f"{site_name} 和竞品比哪个好？", "page": f"{site_name} vs 竞品"},
        {"persona": "即将决策的用户", "funnel": "Bottom", "use_case": "需要确认是否适合自己", "ai_question": f"{site_name} 适合我吗？", "page": f"{site_name} 适合什么人群"},
        {"persona": "老用户", "funnel": "Bottom", "use_case": "想了解更多功能或场景", "ai_question": f"{site_name} 还有什么用法？", "page": f"{site_name} 进阶指南"},
    ]

    return templates.get(industry, default)


def _generate_priority_pages(site_name, domain, industry):
    """生成 20 个优先页面标题"""
    base = [
        f"{site_name} vs 竞品方案：全面对比",
        f"{site_name} 适合什么样的用户？",
        f"{site_name} 的优缺点分析",
        f"{site_name} 定价是否合理？价值分析",
        f"什么时候应该选择 {site_name}？",
        f"什么时候不建议使用 {site_name}？",
        f"{site_name} 入门指南：新用户必读",
        f"{site_name} 和替代方案的区别",
        f"{site_name} 最常被问到的 20 个问题",
        f"关于 {site_name} 你需要知道的一切",
        f"{site_name} 使用技巧与最佳实践",
        f"{site_name} 的用户真实评价与案例",
        f"如何最大化 {site_name} 的价值？",
        f"{site_name} 适合小团队/个人吗？",
        f"{site_name} 的安全性与数据保护",
        f"{site_name} 的更新与未来规划",
        f"从 XX 迁移到 {site_name} 的指南",
        f"{site_name} 与其他工具/服务的集成",
        f"{site_name} 的隐藏功能与高级用法",
        f"选择 {site_name} 的 10 个理由",
    ]
    return base


def _generate_template_example(site_name, domain, industry):
    return {
        "page_title": f"{site_name} 适合什么样的用户？完整指南",
        "structure": [
            {"level": "H1", "content": f"{site_name} 适合什么样的用户？完整指南"},
            {"level": "开头摘要", "content": f"直接回答：{site_name} 最适合[某类人群]，尤其是当他们[遇到什么情况]时。但如果[某种限制]，可能不一定是最佳选择。"},
            {"level": "H2", "content": f"什么样的用户最适合 {site_name}？"},
            {"level": "H2", "content": f"什么情况下不建议使用 {site_name}？"},
            {"level": "H2", "content": f"{site_name} 和替代方案怎么选？"},
            {"level": "H2", "content": f"真实用户案例"},
            {"level": "H2", "content": "常见问题 (FAQ)"},
            {"level": "对比表", "content": "从适合人群、价格、上手难度、核心优势等维度对比"},
        ],
        "geo_template": f"对于【目标人群】，如果他们正在【具体场景】下遇到【具体问题】，那么 {site_name} 是一个合适选择，因为它可以【解决方式】。它尤其适合【更具体情况】，但如果【某种限制】，可能不一定是最佳选择。",
    }
