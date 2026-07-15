"""
AEO 五维评分引擎
基于爬取的页面数据进行 AEO 健康度评分
"""
import re
from dataclasses import dataclass, field
from analyzer.crawler import PageData


@dataclass
class DimScore:
    name: str
    score: int
    weight: float
    details: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)


@dataclass
class AEOScore:
    total_score: int
    dimensions: list
    summary: str
    grade: str


class AEOScorer:
    WEIGHTS = {
        "content_structure": 0.30,
        "semantic_coverage": 0.25,
        "credibility": 0.20,
        "technical_basis": 0.15,
        "page_experience": 0.10,
    }

    def score(self, d: PageData) -> AEOScore:
        dims = [
            self._score_content_structure(d),
            self._score_semantic_coverage(d),
            self._score_credibility(d),
            self._score_technical_basis(d),
            self._score_page_experience(d),
        ]
        total = round(sum(x.score * x.weight for x in dims))
        return AEOScore(total_score=total, dimensions=dims, summary=self._summary(total, dims), grade=self._grade(total))

    def _score_content_structure(self, d: PageData) -> DimScore:
        score, details, suggestions = 0, [], []

        if d.h1_texts:
            score += 10; details.append("✅ 页面有 H1 标题")
            if len(d.h1_texts) == 1: score += 5; details.append("✅ H1 数量合理（1个）")
            else: suggestions.append("建议只保留 1 个 H1 标题，避免 AI 困惑")
        else: suggestions.append("缺少 H1 标题，AI 无法快速判断页面主题")

        if d.h2_texts:
            score += 10; details.append(f"✅ 页面有 {len(d.h2_texts)} 个 H2 子标题")
            q_h2 = [h for h in d.h2_texts if "?" in h or "？" in h]
            if q_h2: score += 5; details.append(f"✅ 发现 {len(q_h2)} 个问题式 H2 标题（AI 偏好）")
            else: suggestions.append("建议将部分 H2 改为问题式标题，更容易被 AI 匹配")
        else: suggestions.append("缺少 H2 子标题，建议按「问题-回答」结构组织内容")

        if d.h3_texts: score += 3; details.append(f"✅ 页面有 {len(d.h3_texts)} 个 H3 小标题")
        else: suggestions.append("建议增加 H3 小标题，细化内容层次")

        if d.has_faq:
            score += 15; details.append("✅ 检测到 FAQ 结构")
            if d.faq_items: score += 5; details.append(f"✅ FAQ 包含 {len(d.faq_items)} 个问答项")
        else: suggestions.append("建议添加 FAQ 板块，FAQ 是 AI 引用率最高的内容格式之一")

        if d.paragraphs:
            avg_len = sum(len(p) for p in d.paragraphs) / len(d.paragraphs)
            if 50 < avg_len < 500: score += 10; details.append("✅ 段落长度适中，适合 AI 读取")
            elif avg_len <= 50: score += 5; suggestions.append("段落偏短，信息密度可能不足")
            else: score += 5; suggestions.append("段落偏长，建议拆分为更小的语义块")
            if len(d.paragraphs) >= 5: score += 5; details.append(f"✅ 页面内容较丰富（{len(d.paragraphs)} 段）")
            else: suggestions.append("页面内容较少，AI 可引用的信息量不足")
        else: suggestions.append("页面缺少有效文本段落，AI 无内容可引用")

        if d.has_comparison_content: score += 10; details.append("✅ 检测到对比/比较类内容")
        else: suggestions.append("建议增加对比类内容（如 A vs B、优缺点对比），AI 偏好引用对比信息")

        if d.paragraphs and len(d.paragraphs[0]) < 300: score += 10; details.append("✅ 开头段落简洁，符合「直接回答」模式")
        elif d.paragraphs: score += 5; suggestions.append("开头段落较长，建议在前 100 字内给出核心答案")

        def_pats = [r"是[一种个]", r"指的是", r"定义", r"is\s+a\s", r"refers to"]
        for p in d.paragraphs[:3]:
            for pat in def_pats:
                if re.search(pat, p, re.I): score += 10; details.append("✅ 包含定义/解释式内容，适合 AI 直接引用"); break

        return DimScore(name="内容结构", score=min(score, 100), weight=self.WEIGHTS["content_structure"], details=details, suggestions=suggestions)

    def _score_semantic_coverage(self, d: PageData) -> DimScore:
        score, details, suggestions = 0, [], []
        all_headings = d.h1_texts + d.h2_texts + d.h3_texts
        all_text = " ".join(all_headings + d.paragraphs).lower()

        q_count = sum(1 for h in all_headings if "?" in h or "？" in h)
        if q_count >= 5: score += 25; details.append(f"✅ 发现 {q_count} 个问题式标题，语义覆盖较好")
        elif q_count >= 2: score += 15; details.append(f"✅ 发现 {q_count} 个问题式标题"); suggestions.append("建议将更多小标题改为用户真实会问的问题格式")
        elif q_count >= 1: score += 8; suggestions.append("问题式标题偏少，建议增加到 5 个以上")
        else: suggestions.append("缺少问题式标题，建议围绕用户真实问题重写标题结构")

        scenario_kw = ["如果你", "适用于", "适合", "场景", "情况", "比如", "例如", "when you", "for those who", "use case", "scenario", "example", "团队", "企业", "个人", "新手", "专业"]
        sc_count = sum(1 for kw in scenario_kw if kw in all_text)
        if sc_count >= 5: score += 25; details.append("✅ 场景描述丰富，覆盖多种使用情境")
        elif sc_count >= 2: score += 15; details.append(f"✅ 包含 {sc_count} 个场景关键词"); suggestions.append("建议增加更多具体使用场景描述")
        else: score += 5; suggestions.append("严重缺少使用场景描述，建议按「Persona + 场景 + 问题」公式补充")

        persona_kw = ["新手", "小白", "初学者", "专业", "团队", "企业", "个人", "小型", "大型", "营销", "技术", "创始人", "beginner", "expert", "team", "enterprise", "small business", "startup", "founder", "marketer", "developer", "freelancer", "solo", "agency"]
        p_count = sum(1 for kw in persona_kw if kw in all_text)
        if p_count >= 4: score += 20; details.append(f"✅ 覆盖 {p_count} 种人群关键词")
        elif p_count >= 1: score += 10; suggestions.append("建议明确不同目标人群（如按 B2C/B2B 细分），让 AI 知道「在跟谁说话」")
        else: suggestions.append("缺少明确的目标人群描述，AI 难以判断内容适合谁")

        funnel_top = sum(1 for kw in ["什么是", "是什么", "介绍", "了解", "what is", "guide", "beginner"] if kw in all_text)
        funnel_mid = sum(1 for kw in ["对比", "比较", "哪个好", "区别", "vs", "compare", "alternative"] if kw in all_text)
        funnel_bottom = sum(1 for kw in ["适合我吗", "价格", "购买", "试用", "review", "pricing"] if kw in all_text)
        funnel_hits = sum(1 for x in [funnel_top > 0, funnel_mid > 0, funnel_bottom > 0] if x)
        if funnel_hits >= 2: score += 20; details.append(f"✅ 覆盖 {funnel_hits} 个决策阶段（Top/Mid/Bottom）")
        elif funnel_hits == 1: score += 10; suggestions.append("建议覆盖更多决策阶段内容")
        else: score += 5; suggestions.append("缺少明确的决策阶段内容")

        return DimScore(name="语义覆盖", score=min(score, 100), weight=self.WEIGHTS["semantic_coverage"], details=details, suggestions=suggestions)

    def _score_credibility(self, d: PageData) -> DimScore:
        score, details, suggestions = 0, [], []

        if d.has_author_info: score += 25; details.append("✅ 检测到作者/团队信息")
        else: suggestions.append("建议添加作者信息和背景介绍，增强 AI 信任度")

        if d.has_publish_date: score += 20; details.append("✅ 检测到发布日期")
        else: suggestions.append("建议添加内容发布时间，AI 更信任有明确时间的内容")

        if d.has_about_page_link: score += 15; details.append("✅ 有关于/团队页面链接")
        else: suggestions.append("建议添加关于我们页面，介绍公司和团队背景")

        if d.has_contact_info: score += 10; details.append("✅ 有联系方式")
        else: suggestions.append("建议添加联系信息，增强可信度")

        if d.has_testimonials: score += 15; details.append("✅ 检测到用户评价/案例")
        else: suggestions.append("建议添加真实用户案例、评价或数据引用")

        text = d.body_text.lower()
        data_pats = [r"数据", r"报告", r"研究", r"调查", r"统计", r"data", r"report", r"study", r"survey"]
        if any(re.search(p, text, re.I) for p in data_pats): score += 15; details.append("✅ 检测到数据/研究引用")
        else: suggestions.append("建议引用行业数据或研究报告增强权威性")

        return DimScore(name="可信度", score=min(score, 100), weight=self.WEIGHTS["credibility"], details=details, suggestions=suggestions)

    def _score_technical_basis(self, d: PageData) -> DimScore:
        score, details, suggestions = 0, [], []

        if d.has_schema: score += 25; details.append(f"✅ 检测到 Schema 标记（{', '.join(d.schema_types[:3])}）")
        else: suggestions.append("建议添加 Schema 结构化数据标记（Product/FAQPage/Article/Organization 等）")

        if d.meta_description:
            score += 15
            if 50 <= len(d.meta_description) <= 160: score += 5; details.append("✅ Meta Description 长度合理")
            else: suggestions.append("Meta Description 长度建议在 50-160 字符之间")
        else: suggestions.append("缺少 Meta Description，建议添加")

        if d.h1_texts: score += 15; details.append("✅ 有 H1 标题（SEO 基础）")
        else: suggestions.append("缺少 H1 标签")

        if d.h2_texts: score += 10; details.append("✅ 标题层级结构完整")
        else: suggestions.append("缺少 H2 标签，标题层级不完整")

        if "noindex" not in d.meta_robots.lower(): score += 10; details.append("✅ 页面可被索引")
        else: score += 5; suggestions.append("页面设置了 noindex，AI 和搜索引擎无法收录")

        if d.status_code == 200: score += 10; details.append("✅ HTTP 状态正常")
        else: suggestions.append(f"HTTP 状态码 {d.status_code} 异常")

        all_headings = d.h1_texts + d.h2_texts + d.h3_texts
        if len(all_headings) >= 5: score += 10; details.append("✅ 内容层次丰富")

        return DimScore(name="技术基础", score=min(score, 100), weight=self.WEIGHTS["technical_basis"], details=details, suggestions=suggestions)

    def _score_page_experience(self, d: PageData) -> DimScore:
        score, details, suggestions = 0, [], []

        if d.has_viewport_meta: score += 25; details.append("✅ 设置了 Viewport（响应式设计）")
        else: suggestions.append("建议添加 Viewport meta 标签，适配移动端")

        images_with_alt = [img for img in d.images if img.get("alt")]
        if d.images:
            alt_ratio = len(images_with_alt) / len(d.images)
            if alt_ratio > 0.7: score += 20; details.append(f"✅ {len(images_with_alt)}/{len(d.images)} 图片有 Alt 文本")
            elif alt_ratio > 0.3: score += 10; suggestions.append(f"仅 {len(images_with_alt)}/{len(d.images)} 图片有 Alt 文本")
            else: suggestions.append("大部分图片缺少 Alt 文本")
        else: score += 10

        if d.main_content_length > 500: score += 20; details.append("✅ 主内容量充足")
        elif d.main_content_length > 100: score += 10; suggestions.append("页面主内容偏少")
        else: score += 5; suggestions.append("页面内容过少，AI 可引用信息不足")

        if d.word_count < 100000: score += 15; details.append("✅ 页面大小适中")
        else: score += 5; suggestions.append("页面内容过大，可能影响加载速度")

        nav_count = len([l for l in d.all_links if l["text"] in ["Home", "首页", "Menu", "导航"]])
        if nav_count < 50: score += 20; details.append("✅ 导航结构清晰")
        else: score += 10; suggestions.append("导航链接较多，建议简化以减少 AI 抓取干扰")

        return DimScore(name="页面体验", score=min(score, 100), weight=self.WEIGHTS["page_experience"], details=details, suggestions=suggestions)

    def _grade(self, total: int) -> str:
        if total >= 85: return "A"
        elif total >= 70: return "B"
        elif total >= 55: return "C"
        elif total >= 40: return "D"
        return "F"

    def _summary(self, total: int, dims: list) -> str:
        best = max(dims, key=lambda x: x.score)
        worst = min(dims, key=lambda x: x.score)
        return f"网站 AEO 综合评分 {total}/100（{self._grade(total)} 级），表现最好的维度是「{best.name}」({best.score}分)，最需改进的维度是「{worst.name}」({worst.score}分)。"
