"""官方网站数据爬取模块（合规优先）

- 遵守 robots.txt：不允许的路径直接跳过并记录
- 请求频率控制：默认每个请求间隔 ≥2 秒（同域串行）
- 异常重试：网络/5xx/429 指数退避重试，最多3次
- 超时控制与清晰错误信息；仅发起 GET 请求，不绕过任何站点限制
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib import robotparser
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("enrich.crawler")

DEFAULT_UA = ("HuaweiPcMarketingAgent/1.0 (course-project; "
              "local research use; polite crawler)")


@dataclass
class CrawlerConfig:
    rate_limit_sec: float = 2.0     # 相邻请求最小间隔
    max_retries: int = 3            # 重试次数
    backoff_base: float = 2.0       # 退避基数（秒），指数增长
    timeout_sec: float = 15.0
    max_pages_per_model: int = 3    # 每个型号最多抓取页面数
    user_agent: str = DEFAULT_UA


class _TextExtractor(HTMLParser):
    """提取标题 / meta描述 / 标题层级 / 正文摘要"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings: List[str] = []
        self._text_parts: List[str] = []
        self._in_title = False
        self._in_heading: Optional[str] = None
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag in ("script", "style"):
            self._in_script = True
        elif tag in ("h1", "h2", "h3"):
            self._in_heading = tag
        elif tag == "meta":
            name = (attrs_d.get("name") or attrs_d.get("property") or "").lower()
            if name in ("description", "og:description") and attrs_d.get("content"):
                self.description = self.description or attrs_d["content"]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("script", "style"):
            self._in_script = False
        elif tag in ("h1", "h2", "h3"):
            self._in_heading = None

    def handle_data(self, data):
        text = data.strip()
        if not text or self._in_script:
            return
        if self._in_title:
            self.title += text
        if self._in_heading:
            self.headings.append(f"{self._in_heading}: {text}")
        if len(self._text_parts) < 400:
            self._text_parts.append(text)

    def summary(self, limit: int = 1500) -> str:
        return " ".join(self._text_parts)[:limit]


class OfficialSiteCrawler:
    """官网产品页爬取器（限速 + 重试 + robots合规）"""

    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.config = config or CrawlerConfig()
        self._robots_cache: Dict[str, Optional[robotparser.RobotFileParser]] = {}
        self._last_request_at: Dict[str, float] = {}

    # ---------- robots.txt ----------

    def _robots(self, url: str) -> Optional[robotparser.RobotFileParser]:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots_cache:
            return self._robots_cache[origin]
        rp = robotparser.RobotFileParser()
        try:
            with httpx.Client(timeout=self.config.timeout_sec,
                              headers={"User-Agent": self.config.user_agent}) as client:
                resp = client.get(f"{origin}/robots.txt")
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp = None     # 无robots.txt视作无特殊限制
        except Exception as e:
            logger.warning("robots.txt 获取失败（按无限制处理）: %s", e)
            rp = None
        self._robots_cache[origin] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._robots(url)
        return rp.can_fetch(self.config.user_agent, url) if rp else True

    # ---------- 限速 ----------

    def _throttle(self, url: str) -> None:
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        last = self._last_request_at.get(origin, 0.0)
        wait = self.config.rate_limit_sec - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at[origin] = time.time()

    # ---------- 抓取 ----------

    def fetch_url(self, url: str) -> Dict:
        """抓取单个URL（含限速/重试/robots检查），返回结构化结果"""
        result: Dict = {"url": url, "ok": False, "status": 0, "title": "",
                        "description": "", "headings": [], "text_excerpt": "",
                        "fetched_at": datetime.now().isoformat(timespec="seconds"), "error": ""}
        if not self.allowed(url):
            result["error"] = "robots.txt 不允许抓取该路径（已跳过，合规要求）"
            logger.info("robots 禁止: %s", url)
            return result

        last_error = ""
        for attempt in range(1, self.config.max_retries + 1):
            self._throttle(url)
            try:
                with httpx.Client(timeout=self.config.timeout_sec,
                                  headers={"User-Agent": self.config.user_agent,
                                           "Accept-Language": "zh-CN,zh;q=0.9"},
                                  follow_redirects=True) as client:
                    resp = client.get(url)
                if resp.status_code == 200:
                    parser = _TextExtractor()
                    parser.feed(resp.text)
                    result.update(ok=True, status=200, title=parser.title.strip(),
                                  description=parser.description.strip(),
                                  headings=parser.headings[:30],
                                  text_excerpt=parser.summary())
                    logger.info("抓取成功: %s (%d bytes)", url, len(resp.text))
                    return result
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}"
                    retry_after = min(int(resp.headers.get("Retry-After", "0") or 0), 30)
                    time.sleep(retry_after or self.config.backoff_base ** attempt)
                    continue
                result.update(status=resp.status_code,
                              error=f"HTTP {resp.status_code}（不重试）")
                logger.warning("抓取失败: %s -> %s", url, result["error"])
                return result
            except httpx.HTTPError as e:
                last_error = f"网络异常: {e}"
                logger.warning("第%d次尝试失败 %s: %s", attempt, url, e)
                time.sleep(self.config.backoff_base ** attempt)

        result["error"] = f"重试{self.config.max_retries}次仍失败：{last_error}"
        return result

    def fetch_product(self, model: str, urls: List[str]) -> Dict:
        """抓取某型号的官方页面（去重、限量），返回统一结构"""
        unique_urls: List[str] = []
        for u in urls:
            if u not in unique_urls:
                unique_urls.append(u)
        pages = [self.fetch_url(u) for u in unique_urls[: self.config.max_pages_per_model]]
        return {"model": model, "pages": pages, "fetched_at": datetime.now().isoformat(timespec="seconds")}
