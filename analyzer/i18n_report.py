"""
报告语言翻译模块（后端侧）

策略（与前端已验证的实现一一对应）：
1) 先按中文分号「；」把多建议/多分句拆开，逐句翻译后再用 "; " 拼接
   —— 解决「一句话只匹配一个模式」导致后半句残留中文的问题
2) 每个子句先查 EXACT 精确字典；查不到再尝试 SKELETONS 骨架正则
   （正则捕获 site_name / 数字 / 维度名 等变量，再回填英文模板）
3) 维度名、等级文本、Persona 名用专门的映射表
4) 术语层（章节标题、表头、分组名、衡量维度名、Part9 overview/action/summary）单独映射

覆盖范围：与 analyzer/scorer.py、analyzer/reporter.py 的模板一一对应。
中文（zh-CN）为规范存储格式；调用方按需传 lang 取得对应语言。
"""

import re

# ---------------------------------------------------------------------------
# 维度中文名 -> 英文名（用于「维度名」内嵌在句子里的情况）
# ---------------------------------------------------------------------------
DIM_NAME_EN = {
    '内容结构': 'Content Structure',
    '语义覆盖': 'Semantic Coverage',
    '可信度': 'Credibility',
    '技术基础': 'Technical Basis',
    '页面体验': 'Page Experience',
}

# ---------------------------------------------------------------------------
# 结论等级文本
# ---------------------------------------------------------------------------
LEVEL_EN = {
    '基础不错': 'has a solid foundation',
    '有一定基础，但还有较大提升空间': 'has some foundation but significant room for improvement',
    '需要系统性的 AEO 优化': 'needs systematic AEO optimization',
}

# ---------------------------------------------------------------------------
# Persona 中文名 -> 英文名（固定枚举）
# ---------------------------------------------------------------------------
PERSONA_EN = {
    # 电商/零售
    '第一次购买的新用户': 'First-time buyer',
    '预算敏感的消费者': 'Budget-conscious consumer',
    '注重品质的专业用户': 'Quality-focused pro user',
    '给他人买礼物的用户': 'Gift buyer',
    '回头客/老用户': 'Returning customer',
    '移动端浏览用户': 'Mobile browser',
    # SaaS/软件
    '小团队/初创公司创始人': 'Small team / startup founder',
    '企业采购决策者': 'Enterprise procurement decision-maker',
    '从竞品切换的用户': 'User switching from competitors',
    '技术评估者/开发者': 'Technical evaluator / developer',
    '非技术背景的部门主管': 'Non-technical department lead',
    '自由职业者/个人用户': 'Freelancer / individual user',
    # 内容/媒体
    '信息搜索者': 'Information seeker',
    '深度学习者': 'Deep learner',
    '内容创作者': 'Content creator',
    # 服务/咨询
    '有明确需求的客户': 'Client with clear needs',
    '在比较服务商的客户': 'Client comparing providers',
    '预算有限的客户': 'Budget-limited client',
    '第一次使用服务的客户': 'First-time service client',
    # 默认
    '潜在客户': 'Potential customer',
    '对比中的用户': 'User comparing options',
    '即将决策的用户': 'User about to decide',
    '老用户': 'Existing user',
}

# ---------------------------------------------------------------------------
# 精确字典：整句（或整段，不含变量）直接映射
# ---------------------------------------------------------------------------
EXACT = {
    # ===== Scorer: 内容结构 =====
    '✅ 页面有 H1 标题': '✅ Page has an H1 title',
    '✅ H1 数量合理（1个）': '✅ H1 count is appropriate (1)',
    '建议只保留 1 个 H1 标题，避免 AI 困惑': 'Keep only 1 H1 title to avoid confusing AI',
    '缺少 H1 标题，AI 无法快速判断页面主题': 'Missing H1 title; AI cannot quickly determine the page topic',
    '✅ 检测到 FAQ 结构': '✅ FAQ structure detected',
    '建议添加 FAQ 板块，FAQ 是 AI 引用率最高的内容格式之一': 'Add a FAQ section — FAQ is one of the content formats AI cites most often',
    '✅ 段落长度适中，适合 AI 读取': '✅ Paragraph length is moderate, suitable for AI reading',
    '段落偏短，信息密度可能不足': 'Paragraphs are short; information density may be insufficient',
    '段落偏长，建议拆分为更小的语义块': 'Paragraphs are long; consider splitting into smaller semantic blocks',
    '页面内容较少，AI 可引用的信息量不足': 'Page content is thin; not enough information for AI to cite',
    '页面缺少有效文本段落，AI 无内容可引用': 'Page lacks valid text paragraphs; AI has nothing to cite',
    '✅ 检测到对比/比较类内容': '✅ Comparison-type content detected',
    '建议增加对比类内容（如 A vs B、优缺点对比），AI 偏好引用对比信息': 'Add comparison content (e.g., A vs B, pros/cons); AI prefers citing comparisons',
    '✅ 开头段落简洁，符合「直接回答」模式': '✅ Opening paragraph is concise, fits the "direct answer" pattern',
    '开头段落较长，建议在前 100 字内给出核心答案': 'Opening paragraph is long; provide the core answer within the first 100 characters',
    '✅ 包含定义/解释式内容，适合 AI 直接引用': '✅ Contains definition/explanatory content, suitable for direct AI citation',
    '建议将更多小标题改为用户真实会问的问题格式': 'Turn more subheadings into the questions users actually ask',
    '问题式标题偏少，建议增加到 5 个以上': 'Too few question-style headings; aim for 5 or more',
    '缺少问题式标题，建议围绕用户真实问题重写标题结构': "Missing question-style headings; rewrite the heading structure around users' real questions",
    '缺少 H2 子标题，建议按「问题-回答」结构组织内容': 'Missing H2 subheadings; organize content in a "question–answer" structure',
    '建议增加 H3 小标题，细化内容层次': 'Add H3 subheadings to refine the content hierarchy',
    '建议将部分 H2 改为问题式标题，更容易被 AI 匹配': 'Turn some H2s into question-style headings to match AI queries more easily',

    # ===== Scorer: 语义覆盖 =====
    '✅ 场景描述丰富，覆盖多种使用情境': '✅ Rich scenario descriptions covering multiple use cases',
    '建议增加更多具体使用场景描述': 'Add more concrete usage scenario descriptions',
    '严重缺少使用场景描述，建议按「Persona + 场景 + 问题」公式补充': 'Severely lacking scenario descriptions; add them using the "Persona + Scenario + Question" formula',
    '建议明确不同目标人群（如按 B2C/B2B 细分），让 AI 知道「在跟谁说话」': 'Define distinct target audiences (e.g., B2C/B2B segments) so AI knows "who it is talking to"',
    '缺少明确的目标人群描述，AI 难以判断内容适合谁': "Missing clear target-audience description; AI struggles to judge who the content is for",
    '建议覆盖更多决策阶段内容': 'Cover more decision-stage content',
    '缺少明确的决策阶段内容': 'Missing clear decision-stage content',

    # ===== Scorer: 可信度 =====
    '✅ 检测到作者/团队信息': '✅ Author/team information detected',
    '建议添加作者信息和背景介绍，增强 AI 信任度': 'Add author info and bio to increase AI trust',
    '✅ 检测到发布日期': '✅ Publish date detected',
    '建议添加内容发布时间，AI 更信任有明确时间的内容': 'Add content publish time; AI trusts time-stamped content more',
    '✅ 有关于/团队页面链接': '✅ Has About/team page link',
    '建议添加关于我们页面，介绍公司和团队背景': 'Add an About Us page introducing the company and team',
    '✅ 有联系方式': '✅ Has contact information',
    '建议添加联系信息，增强可信度': 'Add contact info to boost credibility',
    '✅ 检测到用户评价/案例': '✅ User reviews/cases detected',
    '建议添加真实用户案例、评价或数据引用': 'Add real user cases, reviews, or data citations',
    '✅ 检测到数据/研究引用': '✅ Data/research citation detected',
    '建议引用行业数据或研究报告增强权威性': 'Cite industry data or research reports to strengthen authority',

    # ===== Scorer: 技术基础 =====
    '✅ 有 H1 标题（SEO 基础）': '✅ Has H1 title (SEO basics)',
    '缺少 H1 标签': 'Missing H1 tag',
    '✅ 标题层级结构完整': '✅ Heading hierarchy is complete',
    '缺少 H2 标签，标题层级不完整': 'Missing H2 tags; heading hierarchy incomplete',
    '✅ 页面可被索引': '✅ Page is indexable',
    '页面设置了 noindex，AI 和搜索引擎无法收录': 'Page has noindex set; AI and search engines cannot index it',
    '✅ HTTP 状态正常': '✅ HTTP status is normal',
    '✅ 内容层次丰富': '✅ Content hierarchy is rich',
    '建议添加 Schema 结构化数据标记（Product/FAQPage/Article/Organization 等）': 'Add Schema structured-data markup (Product/FAQPage/Article/Organization, etc.)',
    '✅ Meta Description 长度合理': '✅ Meta Description length is reasonable',
    'Meta Description 长度建议在 50-160 字符之间': 'Recommended Meta Description length is 50–160 characters',
    '缺少 Meta Description，建议添加': 'Missing Meta Description; add one',
    '大部分图片缺少 Alt 文本': 'Most images are missing Alt text',

    # ===== Scorer: 页面体验 =====
    '✅ 设置了 Viewport（响应式设计）': '✅ Viewport set (responsive design)',
    '建议添加 Viewport meta 标签，适配移动端': 'Add a Viewport meta tag for mobile adaptation',
    '✅ 主内容量充足': '✅ Main content volume is sufficient',
    '页面主内容偏少': 'Main content is thin',
    '页面内容过少，AI 可引用信息不足': 'Page content is too little; insufficient for AI citation',
    '✅ 页面大小适中': '✅ Page size is moderate',
    '页面内容过大，可能影响加载速度': 'Page content is too large; may affect load speed',
    '✅ 导航结构清晰': '✅ Navigation structure is clear',
    '导航链接较多，建议简化以减少 AI 抓取干扰': 'Too many nav links; simplify to reduce AI crawl interference',

    # ===== Part 2 优势 (无变量的条目) =====
    '包含 FAQ 结构，AI 可直接引用问答内容': 'Contains FAQ structure; AI can directly cite Q&A content',
    '包含对比类内容，这是 AI 引用偏好最高的内容类型之一': 'Contains comparison content — one of the content types AI prefers to cite most',
    '有作者/团队信息展示，增强 AI 信任度': "Shows author/team info, increasing AI trust",
    '包含用户评价/案例信号，有助于建立可信度': 'Contains user-review/case signals, helping build credibility',
    '页面支持响应式设计（Viewport），移动端体验基础良好': 'Page supports responsive design (Viewport); solid mobile experience',
    '网站已在线可访问，这是 AEO 优化的基础前提': 'The site is online and accessible — the basic prerequisite for AEO optimization',

    # ===== Part 3 固定问题描述 =====
    '网站未检测到 JSON-LD 格式的结构化数据。Schema 是 AI 理解页面内容的关键信号，建议添加 Organization、Product、FAQPage、Article 等类型的 Schema 标记。':
        'No JSON-LD structured data detected on the site. Schema is a key signal for AI to understand page content; add Organization, Product, FAQPage, Article and similar Schema markup.',
    'FAQ 是 AI 引用率最高的内容格式之一。建议在核心页面添加问答结构，直接回答用户最关心的问题。':
        "FAQ is one of the content formats AI cites most often. Add a Q&A structure to core pages to directly answer users' most pressing questions.",
    'AI 非常偏好引用对比内容（A vs B、优缺点、适用场景对比）。建议创建竞品对比、方案对比等页面。':
        'AI strongly prefers citing comparison content (A vs B, pros/cons, use-case comparisons). Create competitor-comparison and solution-comparison pages.',
    '当前 H2 标题以陈述为主，缺少问题式标题。AI 更偏好能直接匹配用户问题的标题结构。':
        'Current H2 headings are mostly statements, lacking question-style headings. AI prefers heading structures that directly match user questions.',
    '各项指标基本达标，建议进一步深化语义场景覆盖和对比内容建设。':
        'All metrics are basically up to standard; further deepen semantic scenario coverage and comparison content.',
    '网站整体表现良好': 'The site performs well overall',

    # ===== Part 4 / 6 结构层级名 =====
    '开头摘要': 'Opening Summary',
    '对比表': 'Comparison Table',
    '常见问题 (FAQ)': 'FAQ',
    '真实用户案例': 'Real User Cases',

    # ===== Part 6 描述 =====
    '以下是一个示例页面结构，展示如何将普通产品/服务页面改造成 AI 友好的「决策答案页」：':
        'Below is a sample page structure showing how to turn an ordinary product/service page into an AI-friendly "decision answer page":',

    # ===== Part 7 技术建议 (无变量) =====
    '为核心页面添加 Product、FAQPage、Breadcrumb、Organization、Article 等结构化数据标记':
        'Add structured-data markup (Product, FAQPage, Breadcrumb, Organization, Article, etc.) to core pages',
    '添加 Viewport Meta 标签，确保移动端适配': 'Add a Viewport Meta tag to ensure mobile adaptation',
    '为每个页面添加独特的 Meta Description（50-160 字符）': 'Add a unique Meta Description (50–160 chars) to every page',
    '在首页、分类页和产品页首屏增加「直接回答型摘要」，让 AI 更快抓取核心信息':
        'Add a "direct-answer summary" above the fold on the homepage, category and product pages so AI captures core info faster',
    '减少重复导航和促销文本对主内容抓取的干扰，让核心信息更靠前':
        'Reduce repetitive nav and promo text that interferes with main-content crawling; keep core info further up',
    '优化图片 Alt 文本，使用具体、自然的描述而非只重复产品名':
        'Optimize image Alt text with specific, natural descriptions rather than just repeating the product name',
    '为博客和内容页统一添加作者信息、更新时间和数据来源':
        'Uniformly add author info, update time, and data sources to blog and content pages',
    '将信任信号（评价、保障、退换政策）做成可读文本模块，而非仅用图标展示':
        'Turn trust signals (reviews, guarantees, return policies) into readable text modules, not just icons',
    '优化页面加载速度，确保移动端 PageSpeed 评分 ≥ 70':
        'Optimize page load speed; ensure mobile PageSpeed score ≥ 70',

    # ===== Part 8 维度描述 =====
    '每月测试 5-10 个核心问题，检查品牌是否出现在 AI 推荐答案中':
        'Test 5–10 core questions monthly; check whether the brand appears in AI-recommended answers',
    '在 ChatGPT、Perplexity、Gemini 等工具中测试 10-15 个问题，对比竞品出现频率':
        'Test 10–15 questions in tools like ChatGPT, Perplexity, Gemini; compare competitor mention frequency',
    '直接问 AI 关于品牌的问题，检查回答是否准确、完整':
        'Ask AI directly about the brand; check whether answers are accurate and complete',

    # ===== Part 9 结论 =====
    '核心建议：不要把网站仅仅当作展示窗口，而要把它升级为「AI 决策答案库」——在足够多的具体问题里，让 AI 知道什么时候应该推荐你。':
        "Core recommendation: don't treat your website merely as a showcase — upgrade it into an \"AI Decision Answer Library\" so that, across enough specific questions, AI knows when to recommend you.",

    # ===== 其他 =====
    '暂无数据': 'No data available',
    '以下页面按优先级分为四组，建议按顺序逐步实施：': 'The following pages are grouped into four priority tiers; implement them in order:',
    '网站目前在多个维度都有提升空间，建议从内容结构重构和 Schema 部署开始，逐步建立 AI 友好的内容体系。':
        'The site has room to improve across multiple dimensions; start with content-structure restructuring and Schema deployment to gradually build an AI-friendly content system.',
}


# ---------------------------------------------------------------------------
# 骨架正则：捕获 site_name / 数字 / 维度名 等变量再回填英文模板
# 注意顺序：更具体的模式放在更通用模式之前
# 每个元素为 (Pattern, 替换串 或 接收 match 的回调函数)
# ---------------------------------------------------------------------------
SKELETONS = [
    # ---- 总览 summary（含维度名） ----
    (re.compile(r'^网站 AEO 综合评分 (\d+)/100（([A-F]) 级），表现最好的维度是「(.+?)」\((\d+)分\)，最需改进的维度是「(.+?)」\((\d+)分\)。$'),
     lambda m: f"Website AEO overall score {m.group(1)}/100 (Grade {m.group(2)}). "
                f"Best-performing dimension: {DIM_NAME_EN.get(m.group(3), m.group(3))} ({m.group(4)}); "
                f"dimension most needing improvement: {DIM_NAME_EN.get(m.group(5), m.group(5))} ({m.group(6)})."),

    # ---- Part 3 问题标题 ----
    (re.compile(r'^问题 (\d+)：(.+?)维度评分较低（(\d+)分）$'),
     lambda m: f"Issue {m.group(1)}: {DIM_NAME_EN.get(m.group(2), m.group(2))} dimension scores low ({m.group(3)}/100)"),
    (re.compile(r'^问题 (\d+)：缺少 Schema 结构化数据$'),
     lambda m: f"Issue {m.group(1)}: Missing Schema structured data"),
    (re.compile(r'^问题 (\d+)：缺少 FAQ 板块$'),
     lambda m: f"Issue {m.group(1)}: Missing FAQ section"),
    (re.compile(r'^问题 (\d+)：缺少对比类内容$'),
     lambda m: f"Issue {m.group(1)}: Missing comparison content"),
    (re.compile(r'^问题 (\d+)：标题缺乏问题式结构$'),
     lambda m: f"Issue {m.group(1)}: Headings lack question-style structure"),
    # 兼容已做前缀替换的情况
    (re.compile(r'^Issue (\d+):(.+?)维度评分较低（(\d+)分）$'),
     lambda m: f"Issue {m.group(1)}: {DIM_NAME_EN.get(m.group(2), m.group(2))} dimension scores low ({m.group(3)}/100)"),
    (re.compile(r'^Issue (\d+):缺少 Schema 结构化数据$'),
     lambda m: f"Issue {m.group(1)}: Missing Schema structured data"),
    (re.compile(r'^Issue (\d+):缺少 FAQ 板块$'),
     lambda m: f"Issue {m.group(1)}: Missing FAQ section"),
    (re.compile(r'^Issue (\d+):缺少对比类内容$'),
     lambda m: f"Issue {m.group(1)}: Missing comparison content"),
    (re.compile(r'^Issue (\d+):标题缺乏问题式结构$'),
     lambda m: f"Issue {m.group(1)}: Headings lack question-style structure"),

    # ---- Part 4 描述 ----
    (re.compile(r'^基于 (.+?) 的行业特点和现有内容，以下是推荐的 AI 语义场景覆盖矩阵：$'),
     lambda m: f"Based on {m.group(1)}'s industry profile and existing content, here is the recommended AI semantic scenario coverage matrix:"),

    # ---- Part 4 use_case ----
    (re.compile(r'^第一次了解 (.+?)$'), lambda m: f"First time learning about {m.group(1)}"),
    (re.compile(r'^在 (.+?) 和竞品之间选择$'), lambda m: f"Choosing between {m.group(1)} and competitors"),
    (re.compile(r'^需要确认是否适合自己$'), lambda m: "Need to confirm if it fits them"),
    (re.compile(r'^想了解更多功能或场景$'), lambda m: "Want to learn more features or scenarios"),
    (re.compile(r'^不了解产品怎么选，需要购买指南$'), lambda m: "Not sure how to choose; needs a buying guide"),
    (re.compile(r'^想确认性价比，和竞品比较$'), lambda m: "Want to confirm value for money; comparing with competitors"),
    (re.compile(r'^关心材质、工艺、售后保障$'), lambda m: "Cares about material, craftsmanship, after-sales"),
    (re.compile(r'^不知道该买什么，需要礼物推荐$'), lambda m: "Not sure what to buy; needs gift recommendations"),
    (re.compile(r'^想了解新品、升级或补充购买$'), lambda m: "Wants to learn about new products, upgrades"),
    (re.compile(r'^碎片时间浏览，需要快速了解$'), lambda m: "Browsing in spare time; needs a quick overview"),
    (re.compile(r'^预算有限，需要性价比高的工具$'), lambda m: "Limited budget; needs a cost-effective tool"),
    (re.compile(r'^关心安全性、集成能力、ROI$'), lambda m: "Cares about security, integration, ROI"),
    (re.compile(r'^觉得现有工具太贵或不好用$'), lambda m: "Finds current tool too expensive or hard to use"),
    (re.compile(r'^关心 API、文档、技术架构$'), lambda m: "Cares about API, docs, tech architecture"),
    (re.compile(r'^需要简单易用的工具，不想学复杂系统$'), lambda m: "Needs an easy-to-use tool, no complex systems"),
    (re.compile(r'^需要个人能负担的方案$'), lambda m: "Needs an affordable personal plan"),
    (re.compile(r'^想了解某个话题或概念$'), lambda m: "Wants to understand a topic or concept"),
    (re.compile(r'^需要系统性的知识体系$'), lambda m: "Needs a systematic knowledge base"),
    (re.compile(r'^寻找可引用的权威来源$'), lambda m: "Looking for authoritative citable sources"),
    (re.compile(r'^需要确认服务是否适合自己的情况$'), lambda m: "Needs to confirm if the service fits their situation"),
    (re.compile(r'^在几家服务商之间比较$'), lambda m: "Comparing several service providers"),
    (re.compile(r'^关心价格和服务范围$'), lambda m: "Cares about price and service scope"),
    (re.compile(r'^不了解服务流程和预期效果$'), lambda m: "Unfamiliar with service process and expected outcomes"),

    # ---- Part 4 ai_question ----
    (re.compile(r'^(.+?) 是什么？靠谱吗？$'), lambda m: f"What is {m.group(1)}? Is it trustworthy?"),
    (re.compile(r'^(.+?) 和竞品比哪个好？$'), lambda m: f"Is {m.group(1)} better than its competitors?"),
    (re.compile(r'^(.+?) 适合我吗？$'), lambda m: f"Is {m.group(1)} right for me?"),
    (re.compile(r'^(.+?) 还有什么用法？$'), lambda m: f"What else can you do with {m.group(1)}?"),
    (re.compile(r'^(.+?) 的产品适合新手吗？怎么选？$'), lambda m: f"Is {m.group(1)}'s product good for beginners? How to choose?"),
    (re.compile(r'^(.+?) 和竞品比哪个更值得买？$'), lambda m: f"Is {m.group(1)} or its competitors more worth buying?"),
    (re.compile(r'^(.+?) 的产品质量怎么样？有什么保障？$'), lambda m: f"How is {m.group(1)}'s product quality? Any guarantees?"),
    (re.compile(r'^(.+?) 适合送礼吗？有什么推荐？$'), lambda m: f"Is {m.group(1)} good for gifts? Any recommendations?"),
    (re.compile(r'^(.+?) 有什么新品推荐？$'), lambda m: f"Any new product recommendations from {m.group(1)}?"),
    (re.compile(r'^(.+?) 是什么品牌？靠谱吗？$'), lambda m: f"What brand is {m.group(1)}? Is it trustworthy?"),
    (re.compile(r'^(.+?) 适合小团队吗？价格贵不贵？$'), lambda m: f"Is {m.group(1)} good for small teams? Pricey?"),
    (re.compile(r'^(.+?) 企业版有什么功能？安全吗？$'), lambda m: f"What features does {m.group(1)} Enterprise have? Is it secure?"),
    (re.compile(r'^(.+?) 和 XX 比哪个好？迁移麻烦吗？$'), lambda m: f"Is {m.group(1)} better than XX? Is migration difficult?"),
    (re.compile(r'^(.+?) 有 API 吗？技术文档全吗？$'), lambda m: f"Does {m.group(1)} have an API? Are the docs complete?"),
    (re.compile(r'^(.+?) 容易上手吗？需要技术背景吗？$'), lambda m: f"Is {m.group(1)} easy to learn? Need a technical background?"),
    (re.compile(r'^(.+?) 有免费版或个人版吗？$'), lambda m: f"Does {m.group(1)} have a free or personal plan?"),
    (re.compile(r'^(.+?) 上的信息可信吗？$'), lambda m: f"Is the information on {m.group(1)} credible?"),
    (re.compile(r'^(.+?) 有哪些深度内容？$'), lambda m: f"What in-depth content does {m.group(1)} offer?"),
    (re.compile(r'^(.+?) 的内容可以引用吗？$'), lambda m: f"Can {m.group(1)}'s content be cited?"),
    (re.compile(r'^(.+?) 适合我的情况吗？$'), lambda m: f"Is {m.group(1)} right for my situation?"),
    (re.compile(r'^(.+?) 和 XX 服务有什么区别？$'), lambda m: f"What's the difference between {m.group(1)} and XX's service?"),
    (re.compile(r'^(.+?) 的价格是多少？值不值？$'), lambda m: f"What is {m.group(1)}'s pricing? Is it worth it?"),
    (re.compile(r'^(.+?) 的服务流程是怎样的？$'), lambda m: f"What is {m.group(1)}'s service process?"),

    # ---- Part 4 page（具体行业，放在通用「关于」之前） ----
    (re.compile(r'^(.+?) 新手购买指南$'), lambda m: f"{m.group(1)} Beginner Buying Guide"),
    (re.compile(r'^(.+?) vs 竞品：性价比对比$'), lambda m: f"{m.group(1)} vs Competitors: Value Comparison"),
    (re.compile(r'^(.+?) 品质与售后详解$'), lambda m: f"{m.group(1)} Quality & After-sales Explained"),
    (re.compile(r'^(.+?) 礼物选购指南$'), lambda m: f"{m.group(1)} Gift Buying Guide"),
    (re.compile(r'^(.+?) 新品与升级指南$'), lambda m: f"{m.group(1)} New & Upgrade Guide"),
    (re.compile(r'^关于 (.+?)：品牌故事与承诺$'), lambda m: f"About {m.group(1)}: Brand Story & Promise"),
    (re.compile(r'^(.+?) 小团队方案$'), lambda m: f"{m.group(1)} Small Team Plan"),
    (re.compile(r'^(.+?) 企业方案与安全$'), lambda m: f"{m.group(1)} Enterprise Plan & Security"),
    (re.compile(r'^(.+?) vs 竞品对比$'), lambda m: f"{m.group(1)} vs Competitor Comparison"),
    (re.compile(r'^(.+?) 技术文档与 API$'), lambda m: f"{m.group(1)} Docs & API"),
    (re.compile(r'^(.+?) 快速上手指南$'), lambda m: f"{m.group(1)} Quick Start Guide"),
    (re.compile(r'^(.+?) 个人/免费方案$'), lambda m: f"{m.group(1)} Personal/Free Plan"),
    (re.compile(r'^关于 (.+?)：编辑方针与可信度$'), lambda m: f"About {m.group(1)}: Editorial Policy & Credibility"),
    (re.compile(r'^(.+?) 内容导航与专题$'), lambda m: f"{m.group(1)} Content Navigation & Topics"),
    (re.compile(r'^(.+?) 引用与合作指南$'), lambda m: f"{m.group(1)} Citation & Partnership Guide"),
    (re.compile(r'^(.+?) 服务适用场景$'), lambda m: f"{m.group(1)} Service Use Cases"),
    (re.compile(r'^(.+?) vs 竞品服务对比$'), lambda m: f"{m.group(1)} vs Competitor Services"),
    (re.compile(r'^(.+?) 定价与价值说明$'), lambda m: f"{m.group(1)} Pricing & Value"),
    (re.compile(r'^(.+?) 服务流程与案例$'), lambda m: f"{m.group(1)} Service Process & Cases"),
    (re.compile(r'^(.+?) vs 竞品$'), lambda m: f"{m.group(1)} vs Competitors"),
    (re.compile(r'^(.+?) 适合什么人群$'), lambda m: f"Who {m.group(1)} is best for"),
    (re.compile(r'^(.+?) 进阶指南$'), lambda m: f"{m.group(1)} Advanced Guide"),
    (re.compile(r'^关于 (.+?) 你需要知道的一切$'), lambda m: f"Everything You Need to Know About {m.group(1)}"),
    (re.compile(r'^关于 (.+?)$'), lambda m: f"About {m.group(1)}"),

    # ---- Part 5 优先页面（20 个模板） ----
    (re.compile(r'^(.+?) vs 竞品方案：全面对比$'), lambda m: f"{m.group(1)} vs Competitors: Full Comparison"),
    (re.compile(r'^(.+?) 适合什么样的用户？$'), lambda m: f"Who is {m.group(1)} best for?"),
    (re.compile(r'^(.+?) 的优缺点分析$'), lambda m: f"{m.group(1)} Pros & Cons Analysis"),
    (re.compile(r'^(.+?) 定价是否合理？价值分析$'), lambda m: f"Is {m.group(1)}'s pricing reasonable? Value analysis"),
    (re.compile(r'^什么时候应该选择 (.+?)？$'), lambda m: f"When should you choose {m.group(1)}?"),
    (re.compile(r'^什么时候不建议使用 (.+?)？$'), lambda m: f"When should you avoid {m.group(1)}?"),
    (re.compile(r'^(.+?) 入门指南：新用户必读$'), lambda m: f"{m.group(1)} Beginner Guide: Must-read"),
    (re.compile(r'^(.+?) 和替代方案的区别$'), lambda m: f"{m.group(1)} vs Alternatives"),
    (re.compile(r'^(.+?) 最常被问到的 20 个问题$'), lambda m: f"Top 20 Questions About {m.group(1)}"),
    (re.compile(r'^(.+?) 使用技巧与最佳实践$'), lambda m: f"{m.group(1)} Tips & Best Practices"),
    (re.compile(r'^(.+?) 的用户真实评价与案例$'), lambda m: f"{m.group(1)} Real User Reviews & Cases"),
    (re.compile(r'^如何最大化 (.+?) 的价值？$'), lambda m: f"How to Maximize {m.group(1)}'s Value?"),
    (re.compile(r'^(.+?) 适合小团队/个人吗？$'), lambda m: f"Is {m.group(1)} good for small teams/individuals?"),
    (re.compile(r'^(.+?) 的安全性与数据保护$'), lambda m: f"{m.group(1)} Security & Data Protection"),
    (re.compile(r'^(.+?) 的更新与未来规划$'), lambda m: f"{m.group(1)} Updates & Roadmap"),
    (re.compile(r'^从 XX 迁移到 (.+?) 的指南$'), lambda m: f"Guide: Migrating from XX to {m.group(1)}"),
    (re.compile(r'^(.+?) 与其他工具/服务的集成$'), lambda m: f"{m.group(1)} Integrations with Other Tools/Services"),
    (re.compile(r'^(.+?) 的隐藏功能与高级用法$'), lambda m: f"{m.group(1)} Hidden Features & Advanced Usage"),
    (re.compile(r'^选择 (.+?) 的 10 个理由$'), lambda m: f"10 Reasons to Choose {m.group(1)}"),
    (re.compile(r'^(.+?) 适合什么样的用户？完整指南$'), lambda m: f"{m.group(1)} Complete Guide: Who It's Best For"),

    # ---- Part 6 模板示例 ----
    (re.compile(r'^直接回答：(.+?) 最适合\[某类人群\]，尤其是当他们\[遇到什么情况\]时。但如果\[某种限制\]，可能不一定是最佳选择。$'),
     lambda m: f"Direct answer: {m.group(1)} is best for [a certain audience], especially when they [encounter a situation]. "
                f"But if [some limitation], it may not be the best choice."),
    (re.compile(r'^什么样的用户最适合 (.+?)？$'), lambda m: f"Who is {m.group(1)} best for?"),
    (re.compile(r'^什么情况下不建议使用 (.+?)？$'), lambda m: f"When should you avoid using {m.group(1)}?"),
    (re.compile(r'^(.+?) 和替代方案怎么选？$'), lambda m: f"How to choose between {m.group(1)} and alternatives?"),
    (re.compile(r'^从适合人群、价格、上手难度、核心优势等维度对比$'),
     lambda m: "Compare across dimensions: audience fit, price, ease of use, core advantages"),
    (re.compile(r'^对于【目标人群】，如果他们正在【具体场景】下遇到【具体问题】，那么 (.+?) 是一个合适选择，因为它可以【解决方式】。它尤其适合【更具体情况】，但如果【某种限制】，可能不一定是最佳选择。$'),
     lambda m: f"For [target audience], if they are facing [specific scenario] and encountering [specific problem], "
                f"then {m.group(1)} is a suitable choice because it can [solution]. "
                f"It's especially good for [more specific case], but if [some limitation], it may not be the best choice."),

    # ---- Part 8 描述 & prompts ----
    (re.compile(r'^建议为 (.+?) 建立 AI Answer Share 监测机制，每月固定测试一组核心 prompt，关注三个维度：$'),
     lambda m: f"Set up an AI Answer Share monitoring mechanism for {m.group(1)}, "
                f"testing a fixed set of core prompts monthly and watching three dimensions:"),
    (re.compile(r'^(.+?) 是什么？$'), lambda m: f"What is {m.group(1)}?"),
    (re.compile(r'^(.+?) 好用吗？$'), lambda m: f"Is {m.group(1)} easy to use?"),
    (re.compile(r'^(.+?) 适合什么类型的用户？$'), lambda m: f"What type of users is {m.group(1)} for?"),
    (re.compile(r'^(.+?) 和竞品有什么区别？$'), lambda m: f"What's the difference between {m.group(1)} and competitors?"),
    (re.compile(r'^最好的\[通用\]工具/产品推荐$'), lambda m: "[General] tool/product recommendations"),
    (re.compile(r'^(.+?) vs 竞品 哪个好？$'), lambda m: f"{m.group(1)} vs competitors: which is better?"),
    (re.compile(r'^适合小团队的\[通用\]方案$'), lambda m: "[General] solutions for small teams"),

    # ---- Part 9 结论 ----
    (re.compile(r'^当前最需要改进的是「(.+?)」维度，同时建议深化「(.+?)」的优势，建立更完整的 AI 答案素材库。$'),
     lambda m: f"The most urgent improvement is the '{DIM_NAME_EN.get(m.group(1), m.group(1))}' dimension, "
                f"while deepening the strength of '{DIM_NAME_EN.get(m.group(2), m.group(2))}' "
                f"to build a richer AI answer asset library."),
    (re.compile(r'^建议优先优化「(.+?)」\((\d+)分\)和内容结构，然后系统性地补充对比内容和 FAQ。$'),
    lambda m: "Prioritize optimizing '" + DIM_NAME_EN.get(m.group(1), m.group(1)) + "' (" + m.group(2) + ") and content structure, then systematically add comparison content and FAQ."),
    (re.compile(r'^(.+?) 的 AEO (.+?)，总分 (\d+)/100（([A-F]) 级）。$'),
     lambda m: f"{m.group(1)}'s AEO {LEVEL_EN.get(m.group(2), m.group(2))}, total score {m.group(3)}/100 (Grade {m.group(4)})."),

    # ---- 带数字的 scorer 模板 ----
    (re.compile(r'^✅ 页面有 (\d+) 个 H2 子标题$'), lambda m: f"✅ Page has {m.group(1)} H2 subheadings"),
    (re.compile(r'^✅ 发现 (\d+) 个问题式 H2 标题（AI 偏好）$'), lambda m: f"✅ Found {m.group(1)} question-style H2 headings (AI-preferred)"),
    (re.compile(r'^✅ 页面有 (\d+) 个 H3 小标题$'), lambda m: f"✅ Page has {m.group(1)} H3 subheadings"),
    (re.compile(r'^✅ FAQ 包含 (\d+) 个问答项$'), lambda m: f"✅ FAQ contains {m.group(1)} Q&A items"),
    (re.compile(r'^✅ 页面内容较丰富（(\d+) 段）$'), lambda m: f"✅ Page content is fairly rich ({m.group(1)} paragraphs)"),
    (re.compile(r'^✅ 发现 (\d+) 个问题式标题，语义覆盖较好$'), lambda m: f"✅ Found {m.group(1)} question-style headings; semantic coverage is good"),
    (re.compile(r'^✅ 发现 (\d+) 个问题式标题$'), lambda m: f"✅ Found {m.group(1)} question-style headings"),
    (re.compile(r'^✅ 包含 (\d+) 个场景关键词$'), lambda m: f"✅ Contains {m.group(1)} scenario keywords"),
    (re.compile(r'^✅ 覆盖 (\d+) 种人群关键词$'), lambda m: f"✅ Covers {m.group(1)} audience-keyword types"),
    (re.compile(r'^✅ 覆盖 (\d+) 个决策阶段（Top/Mid/Bottom）$'), lambda m: f"✅ Covers {m.group(1)} decision stages (Top/Mid/Bottom)"),
    (re.compile(r'^✅ 检测到 Schema 标记（(.+?)）$'), lambda m: f"✅ Schema markup detected ({m.group(1)})"),
    (re.compile(r'^✅ (\d+)/(\d+) 图片有 Alt 文本$'), lambda m: f"✅ {m.group(1)}/{m.group(2)} images have Alt text"),
    (re.compile(r'^仅 (\d+)/(\d+) 图片有 Alt 文本$'), lambda m: f"Only {m.group(1)}/{m.group(2)} images have Alt text"),
    (re.compile(r'^HTTP 状态码 (\d+) 异常$'), lambda m: f"HTTP status code {m.group(1)} is abnormal"),

    # ---- 带变量的 Part 2 优势 ----
    (re.compile(r'^网站有明确的页面标题「(.+?)」，有助于 AI 理解页面主题$'),
     lambda m: f'Site has a clear page title "{m.group(1)}", helping AI understand the page topic'),
    (re.compile(r'^已部署 Schema 结构化数据（(.+?)），有助于 AI 解析页面内容$'),
     lambda m: f"Schema structured data deployed ({m.group(1)}), helping AI parse page content"),
    (re.compile(r'^页面内容丰富（约 (\d+) 字符），有足够信息供 AI 提取$'),
     lambda m: f"Page content is rich (~{m.group(1)} chars), enough information for AI to extract"),
]


# ---------------------------------------------------------------------------
# 术语层：章节标题 / 分组名 / 衡量维度名（精确映射）
# ---------------------------------------------------------------------------
TITLE_EN = {
    '一、AEO 健康度评分总览': 'I. AEO Health Score Overview',
    '二、网站当前 AEO 优势': 'II. Current AEO Strengths',
    '三、当前最大 AEO 问题': 'III. Top AEO Issues',
    '四、Persona × Funnel × Use Case 内容机会': 'IV. Persona × Funnel × Use Case Content Opportunities',
    '五、最值得优先做的 AEO 页面': 'V. Top-Priority AEO Pages to Build',
    '六、页面重构模板': 'VI. Page Restructuring Template',
    '七、技术与抓取层面建议': 'VII. Technical & Crawl Recommendations',
    '八、AEO 效果衡量方式': 'VIII. AEO Effect Measurement Methods',
    '九、最终判断': 'IX. Final Verdict',
}
GROUP_NAME_EN = {
    '第一组：对比类页面': 'Group 1: Comparison Pages',
    '第二组：适合/不适合类页面': 'Group 2: Best For / Not For Pages',
    '第三组：场景/用例页面': 'Group 3: Scenario / Use-Case Pages',
    '第四组：FAQ/知识库页面': 'Group 4: FAQ / Knowledge Base Pages',
}
MEASURE_DIM_EN = {
    'AI 可见度': 'AI Visibility',
    '引用份额': 'Citation Share',
    '品牌叙事准确度': 'Brand Narrative Accuracy',
}


# ---------------------------------------------------------------------------
# Word 生成器专用字典（报告字典之外、Word 里硬编码的字符串）
# ---------------------------------------------------------------------------
WORD_I18N = {
    'zh-CN': {
        'report_title_suffix': 'AEO / GEO 优化分析报告',
        'subtitle': '基于"AI 是否会把它当成合理答案"的优化建议方案',
        'analysis_target': '分析对象：',
        'prelim_score': '初步 AEO 评分',
        'overview_score': '网站 AEO 综合评分：{}（{} 级）',
        'th_dimension': '维度',
        'th_weight': '权重',
        'th_score': '评分',
        'th_key_finding': '关键发现',
        'sc_persona': 'Persona',
        'sc_funnel': 'Funnel',
        'sc_use_case': 'Use Case',
        'sc_ai_question': 'AI 可能遇到的问题',
        'sc_recommended_page': '建议页面',
        'top5_label': '优先级最高的 5 篇：',
        'example_page_label': '示例页面：',
        'geo_template_label': 'GEO/AEO 内容模板',
        'sep': '、',
        'free_message': '这是免费版本，包含前 3 部分内容。支付后可查看完整 9 部分报告并下载 Word 版本。',
    },
    'en-US': {
        'report_title_suffix': 'AEO / GEO Optimization Report',
        'subtitle': 'Optimization recommendations based on "whether AI treats this as a reasonable answer"',
        'analysis_target': 'Analyzed site: ',
        'prelim_score': 'Preliminary AEO Score',
        'overview_score': 'Website AEO overall score: {} (Grade {})',
        'th_dimension': 'Dimension',
        'th_weight': 'Weight',
        'th_score': 'Score',
        'th_key_finding': 'Key Finding',
        'sc_persona': 'Persona',
        'sc_funnel': 'Funnel',
        'sc_use_case': 'Use Case',
        'sc_ai_question': 'Likely AI Question',
        'sc_recommended_page': 'Recommended Page',
        'top5_label': 'Top 5 Priority Pages: ',
        'example_page_label': 'Example Page: ',
        'geo_template_label': 'GEO/AEO Content Template',
        'sep': ', ',
        'free_message': 'This is the free version, containing the first 3 parts. After payment you can view the full 9-part report and download the Word version.',
    },
}


def _translate_clause(c: str) -> str:
    if not c:
        return c
    if c in EXACT:
        return EXACT[c]
    for pat, rep in SKELETONS:
        if pat.search(c):
            if callable(rep):
                return pat.sub(rep, c)
            return pat.sub(rep, c)
    return c


def translate_string(s) -> str:
    if not s or not isinstance(s, str):
        return s
    if '；' in s:
        return '; '.join(_translate_clause(x.strip()) for x in s.split('；'))
    return _translate_clause(s)


def translate_persona(name: str) -> str:
    return PERSONA_EN.get(name, name)


def translate_report(report: dict, lang: str) -> dict:
    """对完整报告做语言翻译。lang='zh-CN' 时原样返回（存储规范为中文）。"""
    if lang == 'zh-CN' or not report:
        return report

    r = {k: (dict(v) if isinstance(v, dict) else v) for k, v in report.items()}

    # meta.summary
    if r.get('meta', {}).get('summary'):
        r['meta']['summary'] = translate_string(r['meta']['summary'])

    # ---- Part 1 ----
    p1 = r.get('part1_overview')
    if p1:
        if p1.get('title') in TITLE_EN:
            p1['title'] = TITLE_EN[p1['title']]
        if p1.get('summary'):
            p1['summary'] = translate_string(p1['summary'])
        if p1.get('dimensions'):
            p1['dimensions'] = [
                {
                    **d,
                    'name': DIM_NAME_EN.get(d.get('name', ''), d.get('name', '')),
                    'key_finding': translate_string(d.get('key_finding', '')),
                }
                for d in p1['dimensions']
            ]

    # ---- Part 2 ----
    p2 = r.get('part2_advantages')
    if p2:
        if p2.get('title') in TITLE_EN:
            p2['title'] = TITLE_EN[p2['title']]
        if p2.get('items'):
            p2['items'] = [translate_string(it) for it in p2['items']]

    # ---- Part 3 ----
    p3 = r.get('part3_problems')
    if p3:
        if p3.get('title') in TITLE_EN:
            p3['title'] = TITLE_EN[p3['title']]
        if p3.get('problems'):
            new_problems = []
            for p in p3['problems']:
                np = dict(p)
                np['title'] = translate_string(p.get('title', ''))
                np['detail'] = translate_string(p.get('detail', ''))
                new_problems.append(np)
            p3['problems'] = new_problems

    # ---- Part 4 ----
    p4 = r.get('part4_content_opportunities')
    if p4:
        if p4.get('title') in TITLE_EN:
            p4['title'] = TITLE_EN[p4['title']]
        if p4.get('description'):
            p4['description'] = translate_string(p4['description'])
        if p4.get('scenarios'):
            p4['scenarios'] = [
                {
                    **sc,
                    'persona': translate_persona(sc.get('persona', '')),
                    'use_case': translate_string(sc.get('use_case', '')),
                    'ai_question': translate_string(sc.get('ai_question', '')),
                    'page': translate_string(sc.get('page', '')),
                }
                for sc in p4['scenarios']
            ]

    # ---- Part 5 ----
    p5 = r.get('part5_priority_pages')
    if p5:
        if p5.get('title') in TITLE_EN:
            p5['title'] = TITLE_EN[p5['title']]
        if p5.get('description'):
            p5['description'] = translate_string(p5['description'])
        if p5.get('groups'):
            p5['groups'] = [
                {
                    **g,
                    'name': GROUP_NAME_EN.get(g.get('name', ''), g.get('name', '')),
                    'pages': [translate_string(pg) for pg in g.get('pages', [])],
                }
                for g in p5['groups']
            ]
        if p5.get('top5'):
            p5['top5'] = [translate_string(pg) for pg in p5['top5']]

    # ---- Part 6 ----
    p6 = r.get('part6_page_template')
    if p6:
        if p6.get('title') in TITLE_EN:
            p6['title'] = TITLE_EN[p6['title']]
        if p6.get('description'):
            p6['description'] = translate_string(p6['description'])
        ex = p6.get('example')
        if ex:
            ex['page_title'] = translate_string(ex.get('page_title', ''))
            if ex.get('structure'):
                ex['structure'] = [
                    {
                        **item,
                        'level': translate_string(item.get('level', '')),
                        'content': translate_string(item.get('content', '')),
                    }
                    for item in ex['structure']
                ]
            ex['geo_template'] = translate_string(ex.get('geo_template', ''))

    # ---- Part 7 ----
    p7 = r.get('part7_technical_suggestions')
    if p7:
        if p7.get('title') in TITLE_EN:
            p7['title'] = TITLE_EN[p7['title']]
        if p7.get('items'):
            p7['items'] = [translate_string(it) for it in p7['items']]

    # ---- Part 8 ----
    p8 = r.get('part8_measurement')
    if p8:
        if p8.get('title') in TITLE_EN:
            p8['title'] = TITLE_EN[p8['title']]
        if p8.get('description'):
            p8['description'] = translate_string(p8['description'])
        if p8.get('dimensions'):
            p8['dimensions'] = [
                {
                    **d,
                    'name': MEASURE_DIM_EN.get(d.get('name', ''), d.get('name', '')),
                    'description': translate_string(d.get('description', '')),
                    'prompts': [translate_string(p) for p in d.get('prompts', [])] if d.get('prompts') else d.get('prompts'),
                }
                for d in p8['dimensions']
            ]

    # ---- Part 9 ----
    p9 = r.get('part9_conclusion')
    if p9:
        if p9.get('title') in TITLE_EN:
            p9['title'] = TITLE_EN[p9['title']]
        p9['overview'] = translate_string(p9.get('overview', ''))
        p9['action'] = translate_string(p9.get('action', ''))
        p9['summary'] = translate_string(p9.get('summary', ''))

    # ---- dimension_details ----
    if r.get('dimension_details'):
        r['dimension_details'] = [
            {
                **d,
                'name': DIM_NAME_EN.get(d.get('name', ''), d.get('name', '')),
                'details': [translate_string(x) for x in d.get('details', [])] if d.get('details') else d.get('details'),
                'suggestions': [translate_string(x) for x in d.get('suggestions', [])] if d.get('suggestions') else d.get('suggestions'),
            }
            for d in r['dimension_details']
        ]

    return r
