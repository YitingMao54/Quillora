"""产品数据增强模块（可选功能，默认关闭）

文件夹扫描 → 产品标识提取 → 官网合规爬取 → 结构化入库 → 日志反馈。
与主生成流程完全隔离：不被 agent.pipeline 引用，仅由界面按需启用。
"""
from .service import EnrichService
from .store import EnrichStore
from .crawler import CrawlerConfig, OfficialSiteCrawler
from .scanner import scan_folder, ScanResult

__all__ = ["EnrichService", "EnrichStore", "CrawlerConfig", "OfficialSiteCrawler",
           "scan_folder", "ScanResult"]
