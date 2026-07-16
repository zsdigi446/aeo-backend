"""
AEO/GEO 五维评分引擎 v2
基于 AEO Expert 方法论：不是 SEO 规则检查，而是评估"AI 是否会把此页面当成合理答案"

五维：
1. 内容结构 (30%) — 问题式标题、开头直接回答、H1-H3 层级、FAQ、段落可读性
2. 对比与决策内容 (25%) — 对比、替代方案、适合/不适合边界、决策阶段、场景关键词
3. 可信度信号 (20%) — 作者、案例/评价、数据来源、第三方外链、更新时间
4. 技术基础 (15%) — Schema、Meta Description、索引、sitemap 信号、加载速度
5. 页面体验 (10%) — Viewport、图片 Alt、内容量、弹窗、导航
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
    # 新增：核心结论（有人情味的战略判断）
    core_judgment: str = ""
    # 新增：内容类型覆盖分析
    content_type_coverage: dict = field(default_factory=dict)


class AEOScorer:
    WEIGHTS = {
        "content_structure": 0.30,
        "decision_content": 0.25,
        "credibility": 0.20,
        "technical_basis": 0.15,
        "page_experience": 0.10,
    }

    def score(self, d: PageData) -> AEOScore:
        dims = [
            self._score_content_structure(d),
            self._score_decision_content(d),
            self._score_credibility(d),
            self._score_technical_basis(d),
            self._score_page_experience(d),
        ]
        total = round(sum(x.score * x.weight for x in dims))
        grade = self._grade(total)
        summary = self._summary(total, grade, dims)
        core_judgment = self._core_judgment(total, grade, dims, d)
        content_type_coverage = self._content_type_coverage(d)

        return AEOScore(
            total_score=total,
            dimensions=dims,
            summary=summary,
            grade=grade,
            core_judgment=core_judgment,
            content_type_coverage=content_type_coverage,
        )

    # ========================================================================
    # 维度一：内容结构 (30%)
    # ========================================================================
    def _score_content_structure(self, d: PageData) -> DimScore:
        score = 0
        details = []
        suggestions = []

        all_headings = d.h1_texts + d.h2_texts + d.h3_texts
        all_text = " ".join(all_headings + d.paragraphs)

        # 1. H1 标题（基础）
        if d.h1_texts:
            score += 10
            details.append("✅ 页面有 H1 标题")
            if len(d.h1_texts) == 1:
                score += 5
                details.append("✅ H1 数量合理（1个）")
            else:
                suggestions.append("建议只保留 1 个 H1 标题，避免 AI 困惑")
        else:
            suggestions.append("缺少 H1 标题，AI 无法快速判断页面主题")

        # 2. 问题式标题比例（核心指标）
        q_headings = [h for h in all_headings if "?" in h or "？" in h]
        total_headings = len(all_headings) if all_headings else 1
        q_ratio = len(q_headings) / total_headings

        if q_ratio >= 0.3:
            score += 25
            details.append(f"✅ {len(q_headings)}/{total_headings} 标题是问题式标题（比例 {q_ratio:.0%}），AI 偏好此结构")
        elif q_ratio >= 0.1:
            score += 12
            details.append(f"✅ {len(q_headings)} 个问题式标题")
            suggestions.append("建议将更多标题改为用户真实会问的问题格式，目标比例 ≥ 30%")
        elif q_headings:
            score += 5
            suggestions.append(f"仅有 {len(q_headings)} 个问题式标题，建议增加到 5 个以上")
        else:
            suggestions.append("缺少问题式标题——这是 AEO 最关键的信号。建议围绕用户真实问题重写标题结构")

        # 3. H2/H3 层级
        if d.h2_texts:
            score += 5
            details.append(f"✅ 页面有 {len(d.h2_texts)} 个 H2 子标题")
        else:
            suggestions.append("缺少 H2 子标题，建议按「问题-回答」结构组织内容")

        if d.h3_texts:
            score += 3
            details.append(f"✅ 页面有 {len(d.h3_texts)} 个 H3 小标题")
        else:
            suggestions.append("建议增加 H3 小标题，细化内容层次")

        # 4. FAQ 结构
        if d.has_faq:
            score += 15
            details.append("✅ 检测到 FAQ 结构——这是 AI 引用率最高的内容格式之一")
            if d.faq_items:
                score += 3
                details.append(f"✅ FAQ 包含 {len(d.faq_items)} 个问答项")
        else:
            suggestions.append("建议添加 FAQ 板块，FAQ 是 AI 引用率最高的内容格式之一")

        # 5. 段落可读性
        if d.paragraphs:
            avg_len = sum(len(p) for p in d.paragraphs) / len(d.paragraphs)
            if 50 < avg_len < 500:
                score += 8
                details.append("✅ 段落长度适中，适合 AI 读取")
            elif avg_len <= 50:
                score += 3
                suggestions.append("段落偏短，信息密度可能不足")
            else:
                score += 3
                suggestions.append("段落偏长，建议拆分为更小的语义块（AI 偏好 50-500 字段落）")
            if len(d.paragraphs) >= 8:
                score += 5
                details.append(f"✅ 页面内容较丰富（{len(d.paragraphs)} 段）")
            elif len(d.paragraphs) >= 3:
                score += 2
            else:
                suggestions.append("页面内容较少，AI 可引用的信息量不足")
        else:
            suggestions.append("页面缺少有效文本段落，AI 无内容可引用")

        # 6. 开头直接回答（前 100 字是否给出核心答案）
        if d.paragraphs and len(d.paragraphs[0]) < 300:
            score += 10
            details.append("✅ 开头段落简洁，符合「直接回答」模式")
        elif d.paragraphs:
            score += 4
            suggestions.append("开头段落较长，建议在前 100 字内给出核心答案")

        # 7. 定义/解释式内容
        def_pats = [r"是[一种个]", r"指的是", r"定义", r"is\s+a\s", r"refers to"]
        for p in d.paragraphs[:3]:
            for pat in def_pats:
                if re.search(pat, p, re.I):
                    score += 8
                    details.append("✅ 包含定义/解释式内容，适合 AI 直接引用")
                    break
            else:
                continue
            break

        return DimScore(name="内容结构", score=min(score, 100), weight=self.WEIGHTS["content_structure"],
                        details=details, suggestions=suggestions)

    # ========================================================================
    # 维度二：对比与决策内容 (25%) — AEO 方法论核心维度
    # ========================================================================
    def _score_decision_content(self, d: PageData) -> DimScore:
        score = 0
        details = []
        suggestions = []

        all_headings = d.h1_texts + d.h2_texts + d.h3_texts
        all_text = " ".join(all_headings + d.paragraphs).lower()

        # 1. 对比内容（最高优先级）
        if d.has_comparison_content:
            score += 30
            details.append("✅ 检测到对比/比较类内容——这是 AI 引用偏好最高的内容类型")
        else:
            suggestions.append("强烈建议增加对比类内容（A vs B、优缺点对比）——这是 AEO 最快见效的切入口")

        # 2. 替代方案关键词
        alt_kw = ["替代", "alternative", "instead of", "rather than", "不同于", "另一个选择"]
        if any(kw in all_text for kw in alt_kw):
            score += 15
            details.append("✅ 包含替代方案相关内容，AI 在回答对比类问题时更可能引用")

        # 3. 适合/不适合边界（AI 最喜欢引用的内容类型）
        fit_kw = ["适合", "不适合", "建议使用", "不建议", "best for", "not for", "ideal for",
                   "who should", "who shouldn't", "适用于", "不适用于"]
        fit_count = sum(1 for kw in fit_kw if kw in all_text)
        if fit_count >= 3:
            score += 20
            details.append(f"✅ 包含 {fit_count} 个「适合/不适合」信号，AI 偏好边界清晰的内容")
        elif fit_count >= 1:
            score += 8
            suggestions.append("建议增加「适合谁/不适合谁」的明确表述，AI 非常喜欢引用边界清晰的内容")
        else:
            suggestions.append("缺少「适合/不适合」边界内容——这是 AEO 最容易被忽视但 AI 最喜欢引用的信号")

        # 4. 场景关键词（Persona + Use Case）
        scenario_kw = ["如果你", "适用于", "适合", "场景", "情况", "比如", "例如",
                        "when you", "for those who", "use case", "scenario", "example",
                        "团队", "企业", "个人", "新手", "专业", "小型", "大型"]
        sc_count = sum(1 for kw in scenario_kw if kw in all_text)
        if sc_count >= 5:
            score += 15
            details.append(f"✅ 场景描述丰富（{sc_count} 个场景关键词），覆盖多种使用情境")
        elif sc_count >= 2:
            score += 8
            details.append(f"✅ 包含 {sc_count} 个场景关键词")
            suggestions.append("建议增加更多具体使用场景描述（Persona + 场景 + 问题）")
        else:
            score += 2
            suggestions.append("严重缺少使用场景描述，建议按「Persona + 场景 + 问题」公式补充")

        # 5. 决策阶段覆盖（Top/Mid/Bottom）
        funnel_top = sum(1 for kw in ["什么是", "是什么", "介绍", "了解", "what is", "guide", "beginner",
                                       "入门", "新手"] if kw in all_text)
        funnel_mid = sum(1 for kw in ["对比", "比较", "哪个好", "区别", "vs", "compare", "alternative",
                                       "替代", "优缺点", "pros and cons"] if kw in all_text)
        funnel_bottom = sum(1 for kw in ["适合我吗", "价格", "购买", "试用", "定价", "review", "pricing",
                                          "案例", "评价", "testimonial", "多少钱"] if kw in all_text)
        funnel_hits = sum(1 for x in [funnel_top > 0, funnel_mid > 0, funnel_bottom > 0] if x)
        if funnel_hits >= 3:
            score += 15
            details.append("✅ 覆盖全部 3 个决策阶段（Top/Mid/Bottom）")
        elif funnel_hits == 2:
            score += 10
            details.append(f"✅ 覆盖 {funnel_hits} 个决策阶段")
            suggestions.append("建议补充缺失的决策阶段内容")
        elif funnel_hits == 1:
            score += 4
            suggestions.append("仅覆盖 1 个决策阶段，建议扩展到 Top/Mid/Bottom 全漏斗")
        else:
            suggestions.append("缺少明确的决策阶段内容，AI 难以判断内容适合哪个阶段的用户")

        # 6. 对比表/表格
        import bs4
        if hasattr(d, '_soup'):
            table_count = len(d._soup.find_all("table")) if d._soup else 0
        else:
            table_count = 0
        if table_count >= 2:
            score += 5
            details.append(f"✅ 页面有 {table_count} 个表格，结构化数据对 AI 更友好")

        return DimScore(name="对比与决策内容", score=min(score, 100), weight=self.WEIGHTS["decision_content"],
                        details=details, suggestions=suggestions)

    # ========================================================================
    # 维度三：可信度信号 (20%) — AI 可读的信任要素
    # ========================================================================
    def _score_credibility(self, d: PageData) -> DimScore:
        score = 0
        details = []
        suggestions = []

        # 1. 作者/团队信息
        if d.has_author_info:
            score += 25
            details.append("✅ 检测到作者/团队信息——AI 可读取的信任信号")
        else:
            suggestions.append("建议添加作者信息和背景介绍，AI 更信任有明确作者的内容")

        # 2. 发布日期/更新时间
        if d.has_publish_date:
            score += 20
            details.append("✅ 检测到发布日期/更新时间")
        else:
            suggestions.append("建议添加内容发布时间，AI 更信任有明确时间戳的内容")

        # 3. 关于/团队页面
        if d.has_about_page_link:
            score += 15
            details.append("✅ 有关于/团队页面链接")
        else:
            suggestions.append("建议添加关于我们页面，介绍公司和团队背景")

        # 4. 联系方式
        if d.has_contact_info:
            score += 10
            details.append("✅ 有联系方式")
        else:
            suggestions.append("建议添加联系信息，增强可信度")

        # 5. 用户评价/案例
        if d.has_testimonials:
            score += 15
            details.append("✅ 检测到用户评价/案例信号")
        else:
            suggestions.append("建议添加真实用户案例、评价或数据引用——这是 AI 判断可信度的关键信号")

        # 6. 数据/研究引用
        text = d.body_text.lower()
        data_pats = [r"数据", r"报告", r"研究", r"调查", r"统计", r"data", r"report", r"study", r"survey",
                      r"根据", r"according to", r"来源", r"source"]
        if any(re.search(p, text, re.I) for p in data_pats):
            score += 15
            details.append("✅ 检测到数据/研究引用")
        else:
            suggestions.append("建议引用行业数据或研究报告增强权威性")

        return DimScore(name="可信度信号", score=min(score, 100), weight=self.WEIGHTS["credibility"],
                        details=details, suggestions=suggestions)

    # ========================================================================
    # 维度四：技术基础 (15%)
    # ========================================================================
    def _score_technical_basis(self, d: PageData) -> DimScore:
        score = 0
        details = []
        suggestions = []

        # 1. Schema 结构化数据
        if d.has_schema:
            score += 30
            types_str = ", ".join(d.schema_types[:3]) if d.schema_types else "已部署"
            details.append(f"✅ 检测到 Schema 标记（{types_str}）")
        else:
            suggestions.append("建议添加 Schema 结构化数据标记（Organization/Product/FAQPage/Article 等）——这是 AI 理解页面的关键信号")

        # 2. Meta Description
        if d.meta_description:
            score += 15
            if 50 <= len(d.meta_description) <= 160:
                score += 5
                details.append("✅ Meta Description 长度合理（50-160 字符）")
            else:
                suggestions.append("Meta Description 长度建议在 50-160 字符之间")
        else:
            suggestions.append("缺少 Meta Description，建议添加")

        # 3. H1 标题（SEO 基础）
        if d.h1_texts:
            score += 15
            details.append("✅ 有 H1 标题（SEO 基础）")
        else:
            suggestions.append("缺少 H1 标签")

        # 4. 标题层级完整性
        if d.h2_texts:
            score += 10
            details.append("✅ 标题层级结构完整（H1+H2）")
        else:
            suggestions.append("缺少 H2 标签，标题层级不完整")

        # 5. 可索引性
        if "noindex" not in d.meta_robots.lower():
            score += 10
            details.append("✅ 页面可被索引")
        else:
            score += 3
            suggestions.append("页面设置了 noindex，AI 和搜索引擎无法收录")

        # 6. HTTP 状态
        if d.status_code == 200:
            score += 10
            details.append("✅ HTTP 状态正常（200）")
        else:
            suggestions.append(f"HTTP 状态码 {d.status_code} 异常")

        # 7. 内容层次丰富度
        all_headings = d.h1_texts + d.h2_texts + d.h3_texts
        if len(all_headings) >= 5:
            score += 5
            details.append("✅ 内容层次丰富（≥5 个标题）")

        return DimScore(name="技术基础", score=min(score, 100), weight=self.WEIGHTS["technical_basis"],
                        details=details, suggestions=suggestions)

    # ========================================================================
    # 维度五：页面体验 (10%)
    # ========================================================================
    def _score_page_experience(self, d: PageData) -> DimScore:
        score = 0
        details = []
        suggestions = []

        # 1. Viewport（响应式）
        if d.has_viewport_meta:
            score += 25
            details.append("✅ 设置了 Viewport（响应式设计）")
        else:
            suggestions.append("建议添加 Viewport meta 标签，适配移动端")

        # 2. 图片 Alt 文本
        images_with_alt = [img for img in d.images if img.get("alt")]
        if d.images:
            alt_ratio = len(images_with_alt) / len(d.images)
            if alt_ratio > 0.7:
                score += 20
                details.append(f"✅ {len(images_with_alt)}/{len(d.images)} 图片有 Alt 文本（{alt_ratio:.0%}）")
            elif alt_ratio > 0.3:
                score += 10
                suggestions.append(f"仅 {len(images_with_alt)}/{len(d.images)} 图片有 Alt 文本（{alt_ratio:.0%}）")
            else:
                suggestions.append("大部分图片缺少 Alt 文本，AI 无法理解图片内容")
        else:
            score += 10

        # 3. 主内容量
        if d.main_content_length > 1000:
            score += 20
            details.append("✅ 主内容量充足（>1000 字符）")
        elif d.main_content_length > 300:
            score += 10
            suggestions.append("页面主内容偏少，AI 可引用信息有限")
        else:
            score += 3
            suggestions.append("页面内容过少，AI 可引用信息严重不足")

        # 4. 页面大小
        if d.word_count < 100000:
            score += 15
            details.append("✅ 页面大小适中")
        else:
            score += 5
            suggestions.append("页面内容过大，可能影响加载速度（PageSpeed 移动端建议 ≥70）")

        # 5. 导航清晰度
        nav_count = len([l for l in d.all_links
                          if l["text"] in ["Home", "首页", "Menu", "导航", "Products", "产品",
                                            "Services", "服务", "About", "关于", "Contact", "联系"]])
        if nav_count < 30:
            score += 20
            details.append("✅ 导航结构清晰")
        else:
            score += 8
            suggestions.append("导航链接较多，建议简化以减少 AI 抓取干扰")

        return DimScore(name="页面体验", score=min(score, 100), weight=self.WEIGHTS["page_experience"],
                        details=details, suggestions=suggestions)

    # ========================================================================
    # 辅助方法
    # ========================================================================
    def _grade(self, total: int) -> str:
        if total >= 80:
            return "A"
        elif total >= 65:
            return "B"
        elif total >= 50:
            return "C"
        elif total >= 35:
            return "D"
        return "F"

    def _summary(self, total: int, grade: str, dims: list) -> str:
        best = max(dims, key=lambda x: x.score)
        worst = min(dims, key=lambda x: x.score)
        return (f"网站 AEO 综合评分 {total}/100（{grade} 级），"
                f"表现最好的维度是「{best.name}」({best.score}分)，"
                f"最需改进的维度是「{worst.name}」({worst.score}分)。")

    def _core_judgment(self, total: int, grade: str, dims: list, d: PageData) -> str:
        """生成有人情味的战略判断（对齐 Bailey & Coco 报告风格）"""
        best = max(dims, key=lambda x: x.score)
        worst = min(dims, key=lambda x: x.score)
        decision = next((x for x in dims if x.name == "对比与决策内容"), None)
        credibility = next((x for x in dims if x.name == "可信度信号"), None)
        content = next((x for x in dims if x.name == "内容结构"), None)
        site_name = d.title or "该网站"

        parts = []

        if total >= 65:
            parts.append(f"{site_name} 的 AEO 基础不错，品牌信息和内容结构已经具备一定的 AI 可读性。")
            if decision and decision.score < 50:
                parts.append(f"但从 AEO 角度看，最大的短板是「对比与决策内容」——网站目前更像展示窗口，还不是 AI 容易引用的决策答案库。")
            parts.append(f"建议优先补充对比类内容和适合/不适合边界，让 AI 在用户问「选哪个」「适合谁」时能引用你。")
        elif total >= 40:
            parts.append(f"{site_name} 有一定基础，但距离「AI 愿意推荐的答案库」还有明显差距。")
            if worst:
                parts.append(f"最需要改进的是「{worst.name}」维度（{worst.score}分）。")
            if decision and decision.score < 40:
                parts.append("网站缺少对比内容、适合/不适合边界和场景描述——这些正是 AI 引用时最需要的信号。")
            parts.append("建议从内容结构重构和对比内容建设开始，逐步建立 AI 友好的内容体系。")
        else:
            parts.append(f"{site_name} 目前对 AI 几乎是「不可见的」——AI 很难从中提取可引用的答案。")
            parts.append(f"几乎所有维度都需要系统性建设，尤其是「{worst.name}」（{worst.score}分）。")
            parts.append("建议从最基础的步骤开始：添加问题式标题、补充对比内容、建立可信度信号。")

        return "".join(parts)

    def _content_type_coverage(self, d: PageData) -> dict:
        """分析内容类型覆盖情况（对齐内容优先级表）"""
        all_headings = d.h1_texts + d.h2_texts + d.h3_texts
        all_text = " ".join(all_headings + d.paragraphs).lower()

        return {
            "comparison": d.has_comparison_content,
            "alternatives": any(kw in all_text for kw in ["替代", "alternative", "instead of", "rather than"]),
            "best_for_persona": any(kw in all_text for kw in ["适合", "best for", "ideal for", "who should"]),
            "not_suitable": any(kw in all_text for kw in ["不适合", "不建议", "not for", "who shouldn't"]),
            "pricing_roi": any(kw in all_text for kw in ["价格", "定价", "pricing", "roi", "多少钱", "成本"]),
            "use_case": any(kw in all_text for kw in ["场景", "用例", "use case", "workflow", "如果你"]),
            "case_study": d.has_testimonials,
            "faq": d.has_faq,
        }
