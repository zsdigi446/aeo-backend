"""
AEO 报告生成器 v2
基于 AEO Expert 方法论，输出专家级诊断报告（对齐 Bailey & Coco 风格）

报告结构（九部分）：
一、核心结论 — 有人情味的战略判断
二、网站当前 AEO 优势 — 具体洞察
三、当前最大 AEO 问题 — 商业级诊断
四、内容类型覆盖分析 — 对比/替代方案/场景/FAQ 覆盖
五、Persona × Funnel × Use Case 内容机会矩阵
六、最值得优先做的 AEO 页面
七、页面重构模板
八、技术与抓取层面建议
九、AEO 效果衡量方式
"""

from analyzer.crawler import PageData
from analyzer.scorer import AEOScore, DimScore


def generate_report(url: str, page_data: PageData, aeo_score: AEOScore) -> dict:
    domain = _extract_domain(url)
    brand_name = page_data.brand_name or _extract_brand_from_domain(domain)
    site_name = brand_name
    industry = _guess_industry(page_data)

    report = {
        "meta": {
            "url": url,
            "domain": domain,
            "site_name": site_name,
            "total_score": aeo_score.total_score,
            "grade": aeo_score.grade,
            "summary": aeo_score.summary,
            "industry": industry,
        },
        "part1_core_judgment": _build_part1_core_judgment(aeo_score, page_data, site_name),
        "part2_advantages": _build_part2_advantages(aeo_score, page_data, site_name),
        "part3_problems": _build_part3_problems(aeo_score, page_data, site_name),
        "part4_content_coverage": _build_part4_content_coverage(aeo_score, page_data, site_name),
        "part5_opportunities": _build_part5_opportunities(page_data, site_name, domain, industry),
        "part6_priority_pages": _build_part6_priority_pages(page_data, site_name, domain, industry),
        "part7_page_template": _build_part7_template(page_data, site_name, domain, industry),
        "part8_technical": _build_part8_technical(aeo_score, page_data, site_name),
        "part9_measurement": _build_part9_measurement(site_name, domain, industry),
        "part10_geo_checklist": _build_part10_geo_checklist(aeo_score, page_data, site_name),
        "geo_checklist": aeo_score.geo_checklist,
        "dimension_details": [{
            "name": dim.name,
            "score": dim.score,
            "weight": dim.weight,
            "details": dim.details,
            "suggestions": dim.suggestions,
        } for dim in aeo_score.dimensions],
    }
    return report


# ============================================================================
# Part 1: 核心结论
# ============================================================================
def _build_part1_core_judgment(aeo_score, page_data, site_name):
    dims = aeo_score.dimensions
    best = max(dims, key=lambda x: x.score)
    worst = min(dims, key=lambda x: x.score)
    decision_dim = next((x for x in dims if x.name == "对比与决策内容"), None)
    cred_dim = next((x for x in dims if x.name == "可信度信号"), None)
    content_dim = next((x for x in dims if x.name == "内容结构"), None)

    total = aeo_score.total_score
    grade = aeo_score.grade

    # 生成有人情味的判断
    if total >= 65:
        level_judgment = f"{site_name} 的品牌基础不错，已经具备一定的 AI 可读性。"
        if decision_dim and decision_dim.score < 40:
            level_judgment += " 但从 AEO/GEO 角度看，网站目前更像展示窗口，还不是「AI 容易引用的决策答案库」。最大的短板不是没有内容，而是缺少能直接回答用户购买问题的决策型内容。"
    elif total >= 40:
        level_judgment = f"{site_name} 有一定基础，但距离「AI 愿意推荐的答案库」还有明显差距。"
        if decision_dim and decision_dim.score < 30:
            level_judgment += " 网站缺少对比内容、适合/不适合边界和场景描述——这些正是 AI 引用时最需要的信号。"
    else:
        level_judgment = f"{site_name} 目前对 AI 几乎是「不可见的」——AI 很难从中提取可引用的答案。几乎所有维度都需要系统性建设。"

    # 维度总结
    dim_summary = []
    for dim in dims:
        if dim.score >= 70:
            dim_summary.append(f"「{dim.name}」表现较好（{dim.score}分）")
        elif dim.score >= 40:
            dim_summary.append(f"「{dim.name}」有提升空间（{dim.score}分）")
        else:
            dim_summary.append(f"「{dim.name}」急需改进（{dim.score}分）")

    # 优先行动建议
    if total >= 65:
        priority_action = f"建议优先补充对比类内容和适合/不适合边界，让 AI 在用户问「选哪个」「适合谁」时能引用你。当前最值得投入的是「{worst.name}」维度。"
    elif total >= 40:
        priority_action = f"建议从「{worst.name}」({worst.score}分)和内容结构重构开始，然后系统性地补充对比内容和 FAQ。"
    else:
        priority_action = f"建议从最基础的步骤开始：添加问题式标题、补充对比内容、建立可信度信号。核心突破口是「{worst.name}」维度。"

    return {
        "title": "一、核心结论",
        "overview_score": f"网站 AEO 综合评分：{total}/100（{grade} 级）",
        "summary": aeo_score.summary,
        "judgment": level_judgment,
        "dimension_summary": dim_summary,
        "priority_action": priority_action,
        "dimensions": [{
            "name": dim.name,
            "score": dim.score,
            "max_score": 100,
            "weight": int(dim.weight * 100),
            "key_finding": dim.details[0] if dim.details else (dim.suggestions[0] if dim.suggestions else "暂无数据"),
        } for dim in dims],
    }


# ============================================================================
# Part 2: 当前 AEO 优势
# ============================================================================
def _build_part2_advantages(aeo_score, page_data, site_name):
    items = []
    dims = aeo_score.dimensions

    # 从各维度提取高分项作为优势
    content_dim = next((x for x in dims if x.name == "内容结构"), None)
    cred_dim = next((x for x in dims if x.name == "可信度信号"), None)
    tech_dim = next((x for x in dims if x.name == "技术基础"), None)
    exp_dim = next((x for x in dims if x.name == "页面体验"), None)
    decision_dim = next((x for x in dims if x.name == "对比与决策内容"), None)

    idx = 1

    # 内容结构优势
    if content_dim and content_dim.score >= 50:
        if page_data.h1_texts:
            items.append(f"{idx}. 页面有明确的标题结构（H1: 「{page_data.h1_texts[0][:60]}」），有助于 AI 理解页面主题")
            idx += 1
        q_headings = [h for h in (page_data.h1_texts + page_data.h2_texts + page_data.h3_texts)
                       if "?" in h or "？" in h]
        if q_headings:
            items.append(f"{idx}. 已有 {len(q_headings)} 个问题式标题，说明内容已经开始向「用户问题」方向靠拢")
            idx += 1
        if page_data.has_faq:
            items.append(f"{idx}. 包含 FAQ 结构，AI 可直接引用问答内容——这是 AEO 引用率最高的格式之一")
            idx += 1

    # 可信度优势
    if cred_dim and cred_dim.score >= 50:
        if page_data.has_author_info:
            items.append(f"{idx}. 有作者/团队信息展示，增强 AI 信任度")
            idx += 1
        if page_data.has_publish_date:
            items.append(f"{idx}. 内容有明确的发布时间，AI 更信任有时效性信号的内容")
            idx += 1
        if page_data.has_testimonials:
            items.append(f"{idx}. 包含用户评价/案例信号，有助于建立可信度")
            idx += 1
        if page_data.has_about_page_link:
            items.append(f"{idx}. 有关于/团队页面，为 AI 提供品牌背景信息")
            idx += 1
        if page_data.has_contact_info:
            items.append(f"{idx}. 有联系信息，增强可信度")
            idx += 1

    # 决策内容优势
    if decision_dim and decision_dim.score >= 30:
        if page_data.has_comparison_content:
            items.append(f"{idx}. 包含对比类内容——这是 AI 引用偏好最高的内容类型之一")
            idx += 1

    # 技术基础优势
    if tech_dim and tech_dim.score >= 50:
        if page_data.has_schema:
            items.append(f"{idx}. 已部署 Schema 结构化数据（{', '.join(page_data.schema_types[:3])}），有助于 AI 解析页面内容")
            idx += 1
        if page_data.h1_texts and page_data.h2_texts:
            items.append(f"{idx}. 标题层级结构完整（H1+H2），内容组织清晰")
            idx += 1

    # 页面体验优势
    if exp_dim and exp_dim.score >= 50:
        if page_data.has_viewport_meta:
            items.append(f"{idx}. 页面支持响应式设计（Viewport），移动端体验良好")
            idx += 1
        if page_data.main_content_length > 500:
            items.append(f"{idx}. 主内容量充足（约 {page_data.main_content_length} 字符），有足够信息供 AI 提取")
            idx += 1

    if not items:
        items.append("网站已在线可访问，这是 AEO 优化的基础前提。建议从内容结构重构开始，逐步建立 AI 友好的内容体系。")

    return {"title": "二、网站当前 AEO 优势", "items": items}


# ============================================================================
# Part 3: 当前最大 AEO 问题
# ============================================================================
def _build_part3_problems(aeo_score, page_data, site_name):
    problems = []
    dims = aeo_score.dimensions
    idx = 1

    decision_dim = next((x for x in dims if x.name == "对比与决策内容"), None)
    content_dim = next((x for x in dims if x.name == "内容结构"), None)
    cred_dim = next((x for x in dims if x.name == "可信度信号"), None)

    # 问题 1：对比与决策内容不足（AEO 方法论最核心的问题）
    if decision_dim and decision_dim.score < 40:
        detail_parts = []
        if not page_data.has_comparison_content:
            detail_parts.append("网站目前缺少对比类内容。AI 在回答「XX vs YY」「哪个更适合」类问题时，几乎不可能引用你的网站。对比内容是 AEO 最快见效的切入口，建议创建竞品对比、方案对比、适用场景对比等页面。")
        if not any(kw in " ".join(page_data.h1_texts + page_data.h2_texts + page_data.paragraphs).lower()
                   for kw in ["适合", "不适合", "best for", "not for"]):
            detail_parts.append("缺少「适合谁/不适合谁」的明确表述。AI 非常偏好引用边界清晰的内容——明确告诉 AI 你的产品在什么场景下是最佳选择、什么情况下不建议使用。")
        if not any(kw in " ".join(page_data.h1_texts + page_data.h2_texts + page_data.paragraphs).lower()
                   for kw in ["场景", "用例", "use case", "workflow", "如果你"]):
            detail_parts.append("缺少具体使用场景描述。建议按「Persona + 场景 + 问题」公式补充，让 AI 知道在什么语境下应该推荐你。")

        problems.append({
            "id": idx,
            "title": f"问题 {idx}：对比与决策内容严重不足（{decision_dim.score}分）——AEO 最核心的短板",
            "detail": "".join(detail_parts) if detail_parts else "对比与决策内容维度需要系统性建设。",
        })
        idx += 1

    # 问题 2：内容偏展示而非决策答案
    if content_dim and content_dim.score < 60:
        detail_parts = []
        q_headings = [h for h in (page_data.h1_texts + page_data.h2_texts + page_data.h3_texts)
                       if "?" in h or "？" in h]
        total_headings = len(page_data.h1_texts + page_data.h2_texts + page_data.h3_texts)
        if total_headings > 0 and len(q_headings) / total_headings < 0.2:
            detail_parts.append(f"当前 {total_headings} 个标题中仅 {len(q_headings)} 个是问题式标题。AI 更偏好能直接匹配用户问题的标题结构。建议将至少 30% 的标题改为用户真实会问的问题格式。")
        if not page_data.has_faq:
            detail_parts.append("缺少 FAQ 板块。FAQ 是 AI 引用率最高的内容格式之一，建议在核心页面添加问答结构。")

        if detail_parts:
            problems.append({
                "id": idx,
                "title": f"问题 {idx}：内容结构偏「展示型」而非「决策答案型」（{content_dim.score}分）",
                "detail": "".join(detail_parts),
            })
            idx += 1

    # 问题 3：可信度信号不足
    if cred_dim and cred_dim.score < 60:
        missing = []
        if not page_data.has_author_info:
            missing.append("作者/团队信息")
        if not page_data.has_publish_date:
            missing.append("发布时间/更新时间")
        if not page_data.has_about_page_link:
            missing.append("关于我们页面")
        if not page_data.has_testimonials:
            missing.append("用户案例/评价")
        if missing:
            problems.append({
                "id": idx,
                "title": f"问题 {idx}：可信度信号对 AI 不够可读（{cred_dim.score}分）",
                "detail": f"缺少以下 AI 可读取的信任信号：{'、'.join(missing)}。AI 不像人类能通过设计感判断可信度，它更依赖结构化信号。建议每篇重要内容都加上：作者信息 + 公司背景 + 数据来源 + 更新时间。",
            })
            idx += 1

    # 从各维度提取低分项作为补充问题
    for dim in dims:
        if dim.score < 40 and dim.suggestions:
            # 只取尚未被上述问题覆盖的维度
            if dim.name == "对比与决策内容" and decision_dim and decision_dim.score < 40:
                continue  # 已在问题 1 覆盖
            if dim.name == "内容结构" and content_dim and content_dim.score < 60:
                continue  # 已在问题 2 覆盖
            if dim.name == "可信度信号" and cred_dim and cred_dim.score < 60:
                continue  # 已在问题 3 覆盖

            problems.append({
                "id": idx,
                "title": f"问题 {idx}：{dim.name}维度评分较低（{dim.score}分）",
                "detail": "；".join(dim.suggestions[:4]) if dim.suggestions else f"「{dim.name}」需要重点优化",
            })
            idx += 1

    # 补充：缺少 Schema（技术基础维度）
    if not page_data.has_schema:
        problems.append({
            "id": idx,
            "title": f"问题 {idx}：缺少 Schema 结构化数据",
            "detail": "网站未检测到 JSON-LD 格式的结构化数据。Schema 是 AI 理解页面内容的关键信号，建议添加 Organization、Product、FAQPage、Article 等类型的 Schema 标记。",
        })
        idx += 1

    if not problems:
        problems.append({
            "id": 1,
            "title": "网站整体表现良好",
            "detail": "各项指标基本达标，建议进一步深化语义场景覆盖和对比内容建设，持续监测 AI 可见度和引用份额。",
        })

    return {"title": "三、当前最大 AEO 问题", "problems": problems}


# ============================================================================
# Part 4: 内容类型覆盖分析
# ============================================================================
def _build_part4_content_coverage(aeo_score, page_data, site_name):
    cov = aeo_score.content_type_coverage

    content_types = [
        {
            "type": "对比内容 (A vs B)",
            "covered": cov.get("comparison", False),
            "priority": "最高",
            "description": "AI 引用偏好最高的内容类型。帮用户在「选哪个」时获得明确指引。",
        },
        {
            "type": "替代方案 (Alternatives)",
            "covered": cov.get("alternatives", False),
            "priority": "最高",
            "description": "AI 在回答「XX 有哪些替代方案」时直接引用。",
        },
        {
            "type": "适合/不适合边界",
            "covered": cov.get("best_for_persona", False) or cov.get("not_suitable", False),
            "priority": "最高",
            "description": "边界清晰的内容 AI 最喜欢引用——明确告诉 AI 谁该用、谁不该用。",
        },
        {
            "type": "定价/ROI 内容",
            "covered": cov.get("pricing_roi", False),
            "priority": "高",
            "description": "强转化内容，AI 在用户问「值不值」「多少钱」时引用。",
        },
        {
            "type": "场景/用例内容",
            "covered": cov.get("use_case", False),
            "priority": "高",
            "description": "具体使用场景让 AI 知道「什么情况下该推荐你」。",
        },
        {
            "type": "案例/评价",
            "covered": cov.get("case_study", False),
            "priority": "高",
            "description": "建立 AI 信任度的关键信号。",
        },
        {
            "type": "FAQ",
            "covered": cov.get("faq", False),
            "priority": "高",
            "description": "AI 引用率最高的内容格式之一。",
        },
    ]

    covered_count = sum(1 for ct in content_types if ct["covered"])
    total_count = len(content_types)

    return {
        "title": "四、内容类型覆盖分析",
        "description": f"{site_name} 当前覆盖了 {covered_count}/{total_count} 种 AEO 核心内容类型。以下是各类型的覆盖情况和优先级建议：",
        "covered_count": covered_count,
        "total_count": total_count,
        "content_types": content_types,
    }


# ============================================================================
# Part 5: Persona × Funnel × Use Case 内容机会矩阵
# ============================================================================
def _build_part5_opportunities(page_data, site_name, domain, industry):
    scenarios = _generate_scenarios(site_name, domain, industry)

    return {
        "title": "五、Persona × Funnel × Use Case 内容机会",
        "description": f"基于 {site_name} 的行业特点（{industry}）和现有内容，以下是推荐的 AI 语义场景覆盖矩阵。每个场景对应一个真实用户可能向 AI 提问的情境：",
        "scenarios": scenarios,
    }


# ============================================================================
# Part 6: 最值得优先做的 AEO 页面
# ============================================================================
def _build_part6_priority_pages(page_data, site_name, domain, industry):
    pages = _generate_priority_pages(site_name, domain, industry)

    groups = [
        {"name": "第一组：对比类页面（最快见效）", "pages": pages[:5]},
        {"name": "第二组：适合/不适合类页面", "pages": pages[5:10]},
        {"name": "第三组：场景/用例页面", "pages": pages[10:15]},
        {"name": "第四组：FAQ/知识库页面", "pages": pages[15:20]},
    ]

    return {
        "title": "六、最值得优先做的 AEO 页面",
        "description": "以下页面按优先级分为四组，建议按顺序逐步实施。对比类内容是最快见效的切入口：",
        "groups": groups,
        "top5": pages[:5],
    }


# ============================================================================
# Part 7: 页面重构模板
# ============================================================================
def _build_part7_template(page_data, site_name, domain, industry):
    example = _generate_template_example(site_name, domain, industry)

    return {
        "title": "七、页面重构模板",
        "description": "以下是一个示例页面结构，展示如何将普通产品/服务页面改造成 AI 友好的「决策答案页」。核心原则：开头直接回答 + 问题式小标题 + 对比表 + 适合/不适合 + FAQ + 数据来源 + 作者背景 + 更新时间。",
        "example": example,
    }


# ============================================================================
# Part 8: 技术与抓取层面建议
# ============================================================================
def _build_part8_technical(aeo_score, page_data, site_name):
    """第八部分：基于 GEO 技术检查清单的逐项技术建议（通过/未通过）。"""
    geo = aeo_score.geo_checklist
    sections = geo.get("sections", []) if geo else []

    # 把清单中未通过/需人工验证的项转成可执行建议
    items = []
    for s in sections:
        if s["status"] == "pass":
            continue
        if s["status"] == "manual":
            items.append(f"【需人工验证】{s['name']}：{s['suggestions'][0] if s['suggestions'] else ''}")
            continue
        # fail：列出关键发现 + 第一条建议
        head = s["findings"][0] if s["findings"] else ""
        sug = s["suggestions"][0] if s["suggestions"] else ""
        items.append(f"【{s['name']}】{head} → 建议：{sug}")

    # 兜底通用建议（确保不空洞）
    if not page_data.has_schema:
        items.append("为核心页面添加 Product、FAQPage、Breadcrumb、Organization、Article 等 JSON-LD 结构化数据——这是 AI 理解页面的关键信号")
    items.extend([
        "在首页、分类页和产品页首屏增加「直接回答型摘要」，让 AI 更快抓取核心信息",
        "将信任信号（评价、保障、退换政策）做成可读文本模块，而非仅用图标展示",
        "优化页面加载速度，确保 TTFB < 800ms、移动端体验良好",
        "提交并维护 sitemap，确认 robots.txt 未误拦截 AI 爬虫（GPTBot / Google-Extended / CCBot）",
        "修复 404、优化站内语义化内链结构",
    ])

    passed = geo.get("passed_count", 0)
    auto = geo.get("auto_count", 0)
    geo_score = geo.get("geo_score", 0)
    summary = (f"GEO 技术检查：自动可检测的 {auto} 个大类中，{passed} 项通过，"
               f"技术合规分约 {geo_score}/100。以下为待改进项：") if geo else "技术与抓取层面建议"

    return {"title": "八、GEO 技术检查与抓取层面建议", "summary": summary, "items": items}


def _build_part10_geo_checklist(aeo_score, page_data, site_name):
    """第十部分：GEO 技术检查清单（11 大类完整呈现，供前端/Word 展示）。"""
    geo = aeo_score.geo_checklist
    if not geo:
        return {"title": "十、GEO 技术检查清单", "sections": []}
    sections_out = []
    for s in geo.get("sections", []):
        sections_out.append({
            "key": s["key"],
            "name": s["name"],
            "status": s["status"],          # pass / fail / manual
            "score": s["score"],
            "findings": s["findings"],
            "suggestions": s["suggestions"],
        })
    return {
        "title": "十、GEO 技术检查清单（AI / LLM 引用优化）",
        "principle": geo.get("principle", ""),
        "passed_count": geo.get("passed_count", 0),
        "auto_count": geo.get("auto_count", 0),
        "geo_score": geo.get("geo_score", 0),
        "sections": sections_out,
    }


# ============================================================================
# Part 9: AEO 效果衡量方式
# ============================================================================
def _build_part9_measurement(site_name, domain, industry):
    return {
        "title": "九、AEO 效果衡量方式",
        "description": f"建议为 {site_name} 建立 AI Answer Share 监测机制，每月固定测试一组核心 prompt，从三个维度跟踪 AEO 优化效果：",
        "dimensions": [
            {
                "name": "1. AI 可见度",
                "description": "每月测试 5-10 个核心问题，检查品牌是否出现在 AI 推荐答案中",
                "prompts": [
                    f"{site_name} 是什么？",
                    f"{site_name} 好用吗？",
                    f"{site_name} 适合什么类型的用户？",
                    f"{site_name} 和竞品有什么区别？",
                ],
            },
            {
                "name": "2. 引用份额",
                "description": "在 ChatGPT、Perplexity、Gemini 等工具中测试 10-15 个问题，对比竞品出现频率",
                "prompts": [
                    f"最好的[{industry}]工具/产品推荐",
                    f"{site_name} vs 竞品 哪个好？",
                    f"适合小团队的[{industry}]方案",
                    f"{site_name} 有哪些替代方案？",
                ],
            },
            {
                "name": "3. 品牌叙事准确度",
                "description": "直接问 AI 关于品牌的问题，检查回答是否准确、完整",
                "prompts": [
                    f"What is {site_name}?",
                    f"What are the pros and cons of {site_name}?",
                    f"Who is {site_name} best for?",
                    f"What problems does {site_name} solve?",
                ],
            },
        ],
    }


# ============================================================================
# 辅助函数
# ============================================================================
def _extract_domain(url: str) -> str:
    m = __import__('re').search(r'https?://([^/]+)', url)
    return m.group(1) if m else url


def _extract_brand_from_domain(domain: str) -> str:
    """从域名中提取候选品牌名（去掉 www 和常见 TLD）。"""
    import re
    d = re.sub(r'^www\.', '', domain, flags=re.I)
    d = re.sub(r'\.(com|net|org|co\.\w+|io|ai|app|shop|store|cn|us|uk|eu|jp|kr|de|fr)(/.*)?$', '', d, flags=re.I)
    return d.strip() or domain


def _guess_industry(page_data):
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
    templates = {
        "电商/零售": [
            {"persona": "第一次购买的新用户", "funnel": "Mid / Bottom",
             "use_case": "不了解产品怎么选，需要购买指南",
             "ai_question": f"{site_name} 的产品适合新手吗？怎么选？",
             "page": f"{site_name} 新手购买指南"},
            {"persona": "预算敏感的消费者", "funnel": "Mid",
             "use_case": "想确认性价比，和竞品比较",
             "ai_question": f"{site_name} 和竞品比哪个更值得买？",
             "page": f"{site_name} vs 竞品：性价比对比"},
            {"persona": "注重品质的专业用户", "funnel": "Bottom",
             "use_case": "关心材质、工艺、售后保障",
             "ai_question": f"{site_name} 的产品质量怎么样？有什么保障？",
             "page": f"{site_name} 品质与售后详解"},
            {"persona": "给他人买礼物的用户", "funnel": "Top / Mid",
             "use_case": "不知道该买什么，需要礼物推荐",
             "ai_question": f"{site_name} 适合送礼吗？有什么推荐？",
             "page": f"{site_name} 礼物选购指南"},
        ],
        "SaaS/软件": [
            {"persona": "小团队/初创公司创始人", "funnel": "Mid",
             "use_case": "预算有限，需要性价比高的工具",
             "ai_question": f"{site_name} 适合小团队吗？价格贵不贵？",
             "page": f"{site_name} 小团队方案"},
            {"persona": "企业采购决策者", "funnel": "Bottom",
             "use_case": "关心安全性、集成能力、ROI",
             "ai_question": f"{site_name} 企业版有什么功能？安全吗？",
             "page": f"{site_name} 企业方案与安全"},
            {"persona": "从竞品切换的用户", "funnel": "Mid",
             "use_case": "觉得现有工具太贵或不好用",
             "ai_question": f"{site_name} 和 XX 比哪个好？迁移麻烦吗？",
             "page": f"{site_name} vs 竞品对比"},
            {"persona": "自由职业者/个人用户", "funnel": "Mid / Bottom",
             "use_case": "需要个人能负担的方案",
             "ai_question": f"{site_name} 有免费版或个人版吗？",
             "page": f"{site_name} 个人/免费方案"},
        ],
        "内容/媒体": [
            {"persona": "信息搜索者", "funnel": "Top",
             "use_case": "想了解某个话题或概念",
             "ai_question": f"{site_name} 上的信息可信吗？",
             "page": f"关于 {site_name}：编辑方针与可信度"},
            {"persona": "深度学习者", "funnel": "Mid",
             "use_case": "需要系统性的知识体系",
             "ai_question": f"{site_name} 有哪些深度内容？",
             "page": f"{site_name} 内容导航与专题"},
        ],
        "服务/咨询": [
            {"persona": "有明确需求的客户", "funnel": "Bottom",
             "use_case": "需要确认服务是否适合自己的情况",
             "ai_question": f"{site_name} 适合我的情况吗？",
             "page": f"{site_name} 服务适用场景"},
            {"persona": "在比较服务商的客户", "funnel": "Mid",
             "use_case": "在几家服务商之间比较",
             "ai_question": f"{site_name} 和 XX 服务有什么区别？",
             "page": f"{site_name} vs 竞品服务对比"},
        ],
    }

    default = [
        {"persona": "潜在客户", "funnel": "Top",
         "use_case": f"第一次了解 {site_name}",
         "ai_question": f"{site_name} 是什么？靠谱吗？",
         "page": f"关于 {site_name}"},
        {"persona": "对比中的用户", "funnel": "Mid",
         "use_case": f"在 {site_name} 和竞品之间选择",
         "ai_question": f"{site_name} 和竞品比哪个好？",
         "page": f"{site_name} vs 竞品"},
        {"persona": "即将决策的用户", "funnel": "Bottom",
         "use_case": "需要确认是否适合自己",
         "ai_question": f"{site_name} 适合我吗？",
         "page": f"{site_name} 适合什么人群"},
        {"persona": "老用户", "funnel": "Bottom",
         "use_case": "想了解更多功能或场景",
         "ai_question": f"{site_name} 还有什么用法？",
         "page": f"{site_name} 进阶指南"},
    ]

    return templates.get(industry, default)


def _generate_priority_pages(site_name, domain, industry):
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
            {"level": "开头摘要",
             "content": f"直接回答：{site_name} 最适合[某类人群]，尤其是当他们[遇到什么情况]时。但如果[某种限制]，可能不一定是最佳选择。"},
            {"level": "H2", "content": f"什么样的用户最适合 {site_name}？"},
            {"level": "H2", "content": f"什么情况下不建议使用 {site_name}？"},
            {"level": "H2", "content": f"{site_name} 和替代方案怎么选？"},
            {"level": "H2", "content": "真实用户案例"},
            {"level": "H2", "content": "常见问题 (FAQ)"},
            {"level": "对比表", "content": "从适合人群、价格、上手难度、核心优势等维度对比"},
        ],
        "geo_template": (
            f"对于【目标人群】，如果他们正在【具体场景】下遇到【具体问题】，"
            f"那么 {site_name} 是一个合适选择，因为它可以【解决方式】。"
            f"它尤其适合【更具体情况】，但如果【某种限制】，可能不一定是最佳选择。"
        ),
        "eight_elements": [
            "✅ 开头直接回答",
            "✅ 问题式小标题",
            "✅ 对比表",
            "✅ 适合/不适合人群",
            "✅ FAQ",
            "✅ 数据来源",
            "✅ 作者/公司背景",
            "✅ 更新时间",
        ],
    }
