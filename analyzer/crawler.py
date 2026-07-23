"""
AEO 网页爬取引擎
负责爬取目标网站的 HTML 内容、标题、元数据、结构信息
"""
import re
import random
import time
import httpx
from dataclasses import dataclass, field
from bs4 import BeautifulSoup


@dataclass
class PageData:
    url: str
    title: str = ""
    brand_name: str = ""
    meta_description: str = ""
    h1_texts: list = field(default_factory=list)
    h2_texts: list = field(default_factory=list)
    h3_texts: list = field(default_factory=list)
    all_links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    paragraphs: list = field(default_factory=list)
    body_text: str = ""
    word_count: int = 0
    has_schema: bool = False
    schema_types: list = field(default_factory=list)
    has_faq: bool = False
    faq_items: list = field(default_factory=list)
    has_author_info: bool = False
    has_publish_date: bool = False
    has_about_page_link: bool = False
    has_contact_info: bool = False
    has_comparison_content: bool = False
    has_testimonials: bool = False
    meta_robots: str = ""
    has_viewport_meta: bool = False
    status_code: int = 0
    error: str = ""
    main_content_length: int = 0
    # ===== GEO 技术检查清单相关字段 =====
    canonical_url: str = ""
    robots_txt: str = ""           # 抓取的 robots.txt 内容（抓不到则为空）
    bot_blocked: bool = False      # 是否显式 Disallow 了 GPTBot/Google-Extended/CCBot 等 AI 爬虫
    has_sitemap: bool = False      # 是否能发现 sitemap
    has_breadcrumb: bool = False   # 是否有面包屑导航 / BreadcrumbList schema
    internal_link_count: int = 0
    external_link_count: int = 0
    same_as: list = field(default_factory=list)     # schema sameAs 权威平台
    has_organization_schema: bool = False
    has_faq_schema: bool = False
    has_breadcrumb_schema: bool = False
    has_article_schema: bool = False
    has_howto_schema: bool = False
    response_time_ms: float = 0.0  # 首字节响应耗时（TTFB 近似）
    is_js_rendered: bool = False   # 原始 HTML 内容极少，疑似 JS 渲染（AI 难抓取）
    has_login_wall: bool = False   # 疑似登录墙
    soft_404: bool = False         # 疑似软 404（返回 200 但内容像“未找到”）
    crawl_depth_ok: bool = True    # 关键内容是否无需登录即可访问


class Crawler:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/124.0.2478.80",
    ]

    def __init__(self, timeout: int = 15, max_retries: int = 3, retry_delay: float = 2.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _headers(self) -> dict:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

    async def crawl(self, url: str) -> PageData:
        data = PageData(url=url)
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers=self._headers(),
                    verify=False,
                ) as client:
                    t0 = time.monotonic()
                    resp = await client.get(url)
                    data.response_time_ms = round((time.monotonic() - t0) * 1000, 1)
                    data.status_code = resp.status_code
                    # 对 429/503/502/504 等限流或临时错误进行重试
                    if resp.status_code in (429, 503, 502, 504, 408) and attempt < self.max_retries - 1:
                        wait = self.retry_delay * (2 ** attempt) + random.uniform(0, 1)
                        time.sleep(wait)
                        continue
                    if resp.status_code >= 400:
                        data.error = f"HTTP {resp.status_code}"
                        if resp.status_code == 429:
                            data.error = "HTTP 429：目标网站请求过于频繁，请稍后重试"
                        return data
                    html = resp.text
                    soup = BeautifulSoup(html, "lxml")
                    data._soup = soup
                    self._extract_basic_info(soup, data)
                    self._extract_headings(soup, data)
                    self._extract_links(soup, data, url)
                    self._extract_images(soup, data)
                    self._extract_content(soup, data)
                    self._extract_schema(soup, data)
                    self._extract_faq(soup, data)
                    self._extract_credibility(soup, data)
                    self._extract_comparison(soup, data)
                    self._extract_meta(soup, data)
                    self._extract_geo_heuristics(soup, data, url, html)
                    # 抓取 robots.txt 与 sitemap（尽力而为，失败不影响主流程）
                    await self._extract_robots_and_sitemap(client, url, data)
                    return data
            except httpx.TimeoutException:
                data.error = "请求超时"
                last_exception = "timeout"
            except httpx.ConnectError:
                data.error = "无法连接到目标网站"
                last_exception = "connect"
            except Exception as e:
                data.error = str(e)
                last_exception = e
            # 非 429 类异常也按指数退避重试
            if attempt < self.max_retries - 1:
                wait = self.retry_delay * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
        return data

    def _extract_basic_info(self, soup, data):
        data.title = soup.title.string.strip() if soup.title else ""
        data.brand_name = self._extract_brand_name(soup, data.title)
        meta_desc = soup.find("meta", attrs={"name": "description"})
        data.meta_description = meta_desc.get("content", "") if meta_desc else ""

    def _extract_brand_name(self, soup, title: str) -> str:
        """优先从页面元数据中提取品牌名，避免使用域名作为品牌名。"""
        # 1. og:site_name
        og_site = soup.find("meta", attrs={"property": "og:site_name"})
        if og_site and og_site.get("content", "").strip():
            return self._clean_brand(og_site["content"])

        # 2. application-name
        app_name = soup.find("meta", attrs={"name": "application-name"})
        if app_name and app_name.get("content", "").strip():
            return self._clean_brand(app_name["content"])

        # 3. Organization / Brand schema
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                ld = json.loads(script.string or "{}")
                if isinstance(ld, dict):
                    if ld.get("@type") in ("Organization", "Brand") and ld.get("name"):
                        return self._clean_brand(ld["name"])
                    # 有时 Organization 在 @graph 里
                    graph = ld.get("@graph", [])
                    if isinstance(graph, list):
                        for item in graph:
                            if item.get("@type") in ("Organization", "Brand") and item.get("name"):
                                return self._clean_brand(item["name"])
            except Exception:
                pass

        # 4. 从 title 中提取品牌名
        if title:
            brand = self._extract_brand_from_title(title)
            if brand:
                return self._clean_brand(brand)

        # 5. 从 logo 图片 alt 文本中推断
        for img in soup.find_all("img"):
            alt = (img.get("alt", "") or "").strip()
            src = (img.get("src", "") or "").lower()
            if alt and len(alt) <= 40 and not any(w in alt.lower() for w in ["banner", "hero", "slide", "icon", "avatar"]):
                return self._clean_brand(alt)
            if "logo" in src:
                # 从文件名提取，如 logo-petkit.png -> petkit
                name = re.sub(r'.*[\\/]', '', src)
                name = re.sub(r'\.(png|jpg|jpeg|svg|webp|gif).*', '', name, flags=re.I)
                name = re.sub(r'[\-_]?logo[\-_]?', '', name, flags=re.I)
                if name:
                    return self._clean_brand(name)

        return ""

    def _extract_brand_from_title(self, title: str) -> str:
        """从 title 中推断品牌名，处理 '品牌 | 描述' 和 '描述 | 品牌' 两种格式。"""
        separators = [" | ", " - ", " — ", " – ", ": ", " · ", " / ", " \\ "]
        candidates = []
        for sep in separators:
            if sep in title:
                parts = [p.strip() for p in title.split(sep) if p.strip()]
                for p in parts:
                    candidates.append(p)

        # 去重并保持顺序
        seen = set()
        unique = []
        for c in candidates:
            if c.lower() not in seen:
                seen.add(c.lower())
                unique.append(c)

        def brand_score(text: str) -> int:
            if not text or len(text) > 40:
                return -1000
            score = 0
            words = text.split()
            if 1 <= len(words) <= 3:
                score += 30
            # 全大写且较长的字符串通常是公司全称，降低权重
            if text.isupper():
                score += 20 if len(text) <= 15 else -10
            elif words and all(w[0].isupper() for w in words if w):
                score += 15
            generic = ["bed", "car", "seat", "cover", "product", "products", "home",
                       "shop", "store", "buy", "official", "site", "website", "online",
                       "welcome", "best"]
            for w in words:
                if w.lower().strip("s") in generic:
                    score -= 25
            # 过长或包含法人后缀的，更可能是公司名而非品牌/产品名
            if len(text) > 20:
                score -= 15
            if len(text) > 30:
                score -= 20
            legal_words = ["ltd", "limited", "inc", "llc", "corp", "corporation",
                           "company", "co", "group", "有限公司", "公司"]
            lower_text = text.lower()
            if any(w in lower_text for w in legal_words):
                score -= 25
            return score

        unique.sort(key=brand_score, reverse=True)
        return unique[0] if unique and brand_score(unique[0]) > 0 else ""

    def _clean_brand(self, text: str) -> str:
        """清理品牌名：去掉法人后缀、首尾空白、截断过长文本，尽量保留产品/品牌名。"""
        if not text:
            return ""
        text = text.strip()
        # 如果包含换行或明显是段落，则不适合做品牌名
        if "\n" in text or len(text) > 80:
            return ""
        # 去掉末尾常见标语词
        text = re.sub(r'[\s]*[-|—–:][\s]*.*$', '', text)
        # 去掉常见公司/法人实体后缀（中英）
        suffix_patterns = [
            r'\bLTD\.?\s*,?\s*(CO\.?|COMPANY|LIMITED)?\b',
            r'\bLIMITED\b', r'\bINC\.?\b', r'\bLLC\b', r'\bL\.L\.C\.?\b',
            r'\bCORP\.?\b', r'\bCORPORATION\b', r'\bGROUP\b',
            r'有限公司$', r'股份有限公司$', r'有限责任公司$', r'公司$',
            r'\bLTD\b', r'\bCO\b',
        ]
        for pat in suffix_patterns:
            text = re.sub(pat, '', text, flags=re.I)
        # 清理残留标点和前后空格
        text = re.sub(r'^[\s,，.;:·]+|[\s,，.;:·]+$', '', text)
        if len(text) < 2:
            return ""
        return text[:60]

    def _extract_headings(self, soup, data):
        data.h1_texts = [h.get_text(strip=True) for h in soup.find_all("h1")]
        data.h2_texts = [h.get_text(strip=True) for h in soup.find_all("h2")]
        data.h3_texts = [h.get_text(strip=True) for h in soup.find_all("h3")]

    def _extract_links(self, soup, data, url: str = ""):
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower() if url else ""
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            data.all_links.append({"text": text, "href": href})
            if re.search(r"about|关于|团队|team", text, re.I) or re.search(r"about|about-us", href, re.I):
                data.has_about_page_link = True
            if re.search(r"contact|联系", text, re.I) or re.search(r"contact|contact-us", href, re.I):
                data.has_contact_info = True
            # 内/外链统计（用于语义化内链评估）
            low = href.lower()
            if low.startswith("http"):
                if domain and domain in low:
                    data.internal_link_count += 1
                else:
                    data.external_link_count += 1
            elif low.startswith("#") or low.startswith("javascript:") or low.startswith("mailto:") or low.startswith("tel:"):
                pass
            else:
                data.internal_link_count += 1
            # 面包屑导航检测
            cls = " ".join(a.get("class", [])).lower()
            par = a.parent
            par_cls = " ".join(par.get("class", [])).lower() if par else ""
            if "breadcrumb" in cls or "breadcrumb" in par_cls or a.get("aria-label", "").lower() == "breadcrumb":
                data.has_breadcrumb = True

    def _extract_images(self, soup, data):
        for img in soup.find_all("img"):
            data.images.append({"src": img.get("src", ""), "alt": img.get("alt", "")})

    def _extract_content(self, soup, data):
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        paragraphs = []
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 20:
                paragraphs.append(text)
        data.paragraphs = paragraphs
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main:
            data.body_text = main.get_text(separator=" ", strip=True)
            data.word_count = len(data.body_text)
            data.main_content_length = len(data.body_text)

    def _extract_schema(self, soup, data):
        schemas = soup.find_all("script", type="application/ld+json")
        if schemas:
            data.has_schema = True
            import json as _json
            for s in schemas:
                try:
                    sc = _json.loads(s.string)
                    items = sc if isinstance(sc, list) else [sc]
                    # 支持 @graph 嵌套
                    if isinstance(sc, dict) and isinstance(sc.get("@graph"), list):
                        items = items + sc["@graph"]
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        t = item.get("@type", "Unknown")
                        if isinstance(t, list):
                            for tt in t:
                                data.schema_types.append(tt)
                        else:
                            data.schema_types.append(t)
                        tset = set(t) if isinstance(t, list) else {t}
                        if "Organization" in tset or "Brand" in tset:
                            data.has_organization_schema = True
                        if "FAQPage" in tset or "QAPage" in tset:
                            data.has_faq_schema = True
                        if "BreadcrumbList" in tset:
                            data.has_breadcrumb_schema = True
                            data.has_breadcrumb = True
                        if "Article" in tset or "BlogPosting" in tset or "NewsArticle" in tset:
                            data.has_article_schema = True
                        if "HowTo" in tset:
                            data.has_howto_schema = True
                        # sameAs 权威平台
                        sa = item.get("sameAs")
                        if isinstance(sa, list):
                            data.same_as.extend([str(x) for x in sa if x])
                        elif isinstance(sa, str) and sa:
                            data.same_as.append(sa)
                except Exception:
                    pass

    def _extract_faq(self, soup, data):
        all_headings = [h.get_text(strip=True).lower() for h in soup.find_all(["h1", "h2", "h3", "h4"])]
        faq_indicators = ["faq", "常见问题", "frequently asked", "q&a", "问答"]
        for heading in all_headings:
            for ind in faq_indicators:
                if ind in heading:
                    data.has_faq = True
                    break
        import json as _json
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                sc = _json.loads(s.string)
                items = sc if isinstance(sc, list) else [sc]
                for item in items:
                    if item.get("@type") in ("FAQPage", "QAPage"):
                        data.has_faq = True
            except Exception:
                pass

    def _extract_credibility(self, soup, data):
        text = data.body_text.lower()
        author_pats = [r"author[:\s]+", r"作者[：:]", r"by\s+[A-Z][a-z]+", r"written by", r"posted by"]
        for pat in author_pats:
            if re.search(pat, text, re.I):
                data.has_author_info = True
                break
        linkedin = soup.find_all("a", href=re.compile(r"linkedin\.com", re.I))
        if linkedin:
            data.has_author_info = True
        time_elems = soup.find_all(["time", "meta"])
        for elem in time_elems:
            if elem.get("datetime") or elem.get("content"):
                data.has_publish_date = True
                break
        pub_meta = soup.find("meta", property="article:published_time")
        if pub_meta:
            data.has_publish_date = True
        test_pats = ["testimonial", "review", "case study", "客户评价", "用户评价", "案例", "好评"]
        for pat in test_pats:
            if re.search(pat, text, re.I):
                data.has_testimonials = True
                break

    def _extract_comparison(self, soup, data):
        text = data.body_text.lower()
        comp_pats = [r"vs\.?\s", r"versus", r"对比", r"比较", r"哪个更好", r"alternative", r"替代", r"difference between", r"pros and cons", r"优缺点"]
        for pat in comp_pats:
            if re.search(pat, text, re.I):
                data.has_comparison_content = True
                break
        if len(soup.find_all("table")) >= 2:
            data.has_comparison_content = True

    def _extract_meta(self, soup, data):
        robots = soup.find("meta", attrs={"name": "robots"})
        data.meta_robots = robots.get("content", "") if robots else ""
        viewport = soup.find("meta", attrs={"name": "viewport"})
        data.has_viewport_meta = viewport is not None
        # canonical URL
        canon = soup.find("link", attrs={"rel": "canonical"})
        if canon and canon.get("href"):
            data.canonical_url = canon["href"].strip()
        else:
            # 某些站点用 alternate canonical
            alt = soup.find("link", attrs={"rel": lambda r: r and "canonical" in str(r).lower()})
            if alt and alt.get("href"):
                data.canonical_url = alt["href"].strip()

    def _extract_geo_heuristics(self, soup, data, url: str, html: str):
        """GEO 启发式：JS 渲染、登录墙、软 404、面包屑兜底。"""
        text_len = len(data.body_text or "")
        # JS 渲染启发式：原始 HTML 几乎无正文（疑似 SPA，AI 难以直接抓取到内容）
        if text_len < 200 and len(html) > 5000:
            data.is_js_rendered = True
        # 登录墙启发式：出现登录/注册但无实质内容
        low = (data.body_text or "").lower()
        login_kw = ["sign in", "log in", "login", "登录", "注册", "sign up", "请先登录"]
        if any(k in low for k in login_kw) and text_len < 400:
            data.has_login_wall = True
            data.crawl_depth_ok = False
        # 软 404 启发式：状态码 200 但内容像“未找到”
        notfound_kw = ["404", "not found", "页面不存在", "找不到页面", "page not found", "已删除", "不存在的页面"]
        if data.status_code == 200 and any(k in low for k in notfound_kw) and text_len < 600:
            data.soft_404 = True
        # 面包屑兜底：nav/ol/ul 含 “首页 >” 或 breadcrumb 文本
        if not data.has_breadcrumb:
            for nav in soup.find_all(["nav", "ol", "ul"]):
                cls = " ".join(nav.get("class", [])).lower()
                txt = nav.get_text(" ", strip=True)
                if "breadcrumb" in cls or ("首页" in txt and ">" in txt):
                    data.has_breadcrumb = True
                    break

    async def _extract_robots_and_sitemap(self, client, url: str, data: PageData):
        """抓取 robots.txt 与 sitemap（尽力而为）。"""
        from urllib.parse import urlparse
        try:
            base = "{uri.scheme}://{uri.netloc}".format(uri=urlparse(url))
        except Exception:
            return
        # 1) robots.txt
        try:
            r = await client.get(base + "/robots.txt", timeout=8)
            if r.status_code == 200 and r.text:
                data.robots_txt = r.text
                low = r.text.lower()
                # 显式 Disallow 了主流 AI 爬虫 -> 判定为屏蔽
                ai_bots = ["gptbot", "google-extended", "ccbot", "applebot", "bingbot", "facebookbot"]
                blocked = False
                # 简单解析：每个 bot 段后的 Disallow
                import io
                cur = None
                for line in r.text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    k, v = k.strip().lower(), v.strip()
                    if k == "user-agent":
                        cur = v
                    elif k == "disallow":
                        if cur in ai_bots and v:
                            blocked = True
                        # 通配 * 且 disallow 非空
                        if cur == "*" and v and any(b in ai_bots for b in []):
                            pass
                # 若 * 段全局 Disallow: / 也会拦截 AI 爬虫
                if "user-agent: *" in low and "disallow: /" in low.replace(" ", ""):
                    blocked = True
                data.bot_blocked = blocked
                # sitemap 行
                if "sitemap:" in low:
                    data.has_sitemap = True
        except Exception:
            pass
        # 2) 尝试常见 sitemap 路径
        if not data.has_sitemap:
            for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap.xml.gz"):
                try:
                    r = await client.get(base + path, timeout=8, follow_redirects=True)
                    if r.status_code == 200 and ("<urlset" in r.text or "<sitemapindex" in r.text):
                        data.has_sitemap = True
                        break
                except Exception:
                    continue
