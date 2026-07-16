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
                    resp = await client.get(url)
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
                    self._extract_basic_info(soup, data)
                    self._extract_headings(soup, data)
                    self._extract_links(soup, data)
                    self._extract_images(soup, data)
                    self._extract_content(soup, data)
                    self._extract_schema(soup, data)
                    self._extract_faq(soup, data)
                    self._extract_credibility(soup, data)
                    self._extract_comparison(soup, data)
                    self._extract_meta(soup, data)
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
        meta_desc = soup.find("meta", attrs={"name": "description"})
        data.meta_description = meta_desc.get("content", "") if meta_desc else ""

    def _extract_headings(self, soup, data):
        data.h1_texts = [h.get_text(strip=True) for h in soup.find_all("h1")]
        data.h2_texts = [h.get_text(strip=True) for h in soup.find_all("h2")]
        data.h3_texts = [h.get_text(strip=True) for h in soup.find_all("h3")]

    def _extract_links(self, soup, data):
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            data.all_links.append({"text": text, "href": href})
            if re.search(r"about|关于|团队|team", text, re.I) or re.search(r"about|about-us", href, re.I):
                data.has_about_page_link = True
            if re.search(r"contact|联系", text, re.I) or re.search(r"contact|contact-us", href, re.I):
                data.has_contact_info = True

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
                    for item in items:
                        if isinstance(item, dict):
                            data.schema_types.append(item.get("@type", "Unknown"))
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
