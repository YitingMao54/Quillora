"""产品数据增强服务：扫描 → 官网爬取 → 结构化入库（编排 + 日志反馈）"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional

from .. import config
from .crawler import CrawlerConfig, OfficialSiteCrawler
from .scanner import ScanResult, scan_folder
from .store import EnrichStore

LOG_DIR = config.PROJECT_ROOT / "data" / "logs"
LOG_FILE = LOG_DIR / "enrich.log"

_logger = logging.getLogger("enrich")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _logger.addHandler(_fh)


def _display_path(path) -> str:
    """对外展示用路径：相对项目根目录，避免把本机绝对路径带进报告"""
    try:
        return str(path.relative_to(config.PROJECT_ROOT))
    except (ValueError, AttributeError):
        return str(path)


class EnrichService:
    """独立于主生成流程的可选增强服务（模块化隔离）"""

    def __init__(self, crawler_config: Optional[CrawlerConfig] = None,
                 store: Optional[EnrichStore] = None):
        self.crawler = OfficialSiteCrawler(crawler_config)
        self.store = store or EnrichStore()
        self.messages: Deque[Dict] = deque(maxlen=200)   # UI展示用日志

    # ---------- 日志 ----------

    def _log(self, level: str, text: str) -> None:
        self.messages.append({"time": datetime.now().strftime("%H:%M:%S"),
                              "level": level, "text": text})
        getattr(_logger, level.lower(), _logger.info)("%s", text)

    def logs(self) -> List[Dict]:
        return list(self.messages)

    # ---------- 1. 扫描 ----------

    def scan(self, folder: str, known_models: Optional[List[str]] = None) -> Dict:
        self._log("info", f"开始扫描文件夹：{folder}")
        result: ScanResult = scan_folder(folder, known_models)
        if result.error:
            self._log("error", f"扫描异常：{result.error}")
        self._log("info", f"扫描完成：共{result.total_files}个文件，文本文件{result.text_files}个，"
                          f"识别型号{len(result.models)}个")
        for model, info in result.models.items():
            self._log("info", f"识别到产品：{model}（关联文件{info['count']}个，官网链接{len(info['urls'])}条）")
        for s in result.skipped:
            self._log("warning", s)
        return result.to_dict()

    # ---------- 2. 官网爬取 + 入库 ----------

    def crawl_and_store(self, scan_data: Dict, models: Optional[List[str]] = None) -> Dict:
        """按扫描结果抓取官网数据并结构化入库"""
        report = {"ok": True, "results": [], "errors": []}
        if not scan_data.get("ok"):
            msg = "扫描结果无效，无法执行官网抓取"
            self._log("error", msg)
            return {"ok": False, "results": [], "errors": [msg]}

        target_models = models or list(scan_data.get("models", {}).keys())
        for model in target_models:
            info = scan_data.get("models", {}).get(model)
            if not info:
                report["errors"].append(f"型号「{model}」不在扫描结果中，已跳过")
                continue
            urls = info.get("urls", [])
            if not urls:
                msg = f"型号「{model}」未在本地文件中找到官网链接，无法抓取（可先在文件中补充来源URL）"
                self._log("warning", msg)
                report["errors"].append(msg)
                continue

            self._log("info", f"开始抓取「{model}」官网数据（{len(urls)}条链接，"
                              f"限速{self.crawler.config.rate_limit_sec}s/次）")
            crawled = self.crawler.fetch_product(model, urls)
            ok_pages = [p for p in crawled["pages"] if p.get("ok")]
            for p in crawled["pages"]:
                if p.get("ok"):
                    self._log("info", f"抓取成功：{p['url']}（标题：{p.get('title') or '无'}）")
                else:
                    self._log("warning", f"抓取失败：{p['url']} -> {p.get('error')}")

            entry = {
                "model": model,
                "folder": scan_data.get("folder", ""),
                "local_files": info.get("files", []),
                "crawled": crawled,
                "notes": [f"本地文件{info.get('count', 0)}个与官网数据已关联映射"],
            }
            path = self.store.save_product(entry)
            self._log("info", f"已入库：{model}（成功页面{len(ok_pages)}/"
                              f"{len(crawled['pages'])}）→ {path.name}")
            report["results"].append({"model": model, "pages_ok": len(ok_pages),
                                      "pages_total": len(crawled["pages"]),
                                      "stored_path": _display_path(path)})

        report["ok"] = bool(report["results"])
        return report
