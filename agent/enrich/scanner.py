"""文件夹扫描器：识别产品相关文件并提取产品标识与官方URL

支持任意本地文件夹；按文件名/正文识别华为PC产品型号，
并抓取文件中记录的官网来源链接，供官网爬取模块使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# 文本类文件才做内容解析（图片等仅计数）
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".html", ".htm"}
SKIP_DIRS = {"__pycache__", ".git", "venv", "node_modules", ".venv"}
MAX_FILES = 3000            # 单次扫描文件上限（防超大目录拖垮）
MAX_READ_BYTES = 200_000    # 单文件读取上限

# 产品标识提取
MODEL_PATTERNS = [
    re.compile(r"HUAWEI\s+MateBook[\s\S]{0,24}?(?=[\s,，。;；、|｜/）)]|$)"),
    re.compile(r"MateBook[\sA-Za-z0-9\u4e00-\u9fff]{0,20}"),
    re.compile(r"华为(?:擎云|MateBook)[A-Za-z0-9\u4e00-\u9fff\s]{0,16}"),
]
URL_PATTERN = re.compile(r"https?://consumer\.huawei\.com[^\s\)\"'<>，,]*")
ASSET_URL_PATTERN = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|mp4|pdf|zip)(\?|$)", re.I)
SLUG_MODEL_MAP = {
    "matebook-pro-harmonyos": "HUAWEI MateBook Pro",
    "matebook-pro-s": "HUAWEI MateBook Pro S",
    "matebook-fold": "HUAWEI MateBook Fold 非凡大师",
    "matebook-x-pro-ultra": "HUAWEI MateBook X Pro 酷睿 Ultra 微绒典藏版",
    "matebook-14-harmonyos": "HUAWEI MateBook 14（鸿蒙版）",
    "matebook-14-2024": "HUAWEI MateBook 14 酷睿 Ultra",
    "matebook-14-2025": "HUAWEI MateBook 14 酷睿 Ultra",
    "matebook-d14-2024": "HUAWEI MateBook D 14 2024",
    "matebook-d16-2024": "HUAWEI MateBook D 16 2024",
    "matebook-d16-se-2024": "HUAWEI MateBook D 16 SE 版 2024",
    "matebook-gt-14": "HUAWEI MateBook GT 14",
}


def normalize_model(raw: str) -> str:
    """清洗型号文本"""
    text = re.sub(r"\s+", " ", raw).strip(" .·-—_")
    text = re.sub(r"(产品事实|卖点与限制|图片索引|来源清单|资料|图)$", "", text).strip()
    return text


@dataclass
class ScanResult:
    folder: str = ""
    ok: bool = False
    error: str = ""
    files: List[Dict] = field(default_factory=list)          # {path, suffix, size, models, urls}
    models: Dict[str, Dict] = field(default_factory=dict)    # 型号 -> {files, urls, slugs}
    total_files: int = 0
    text_files: int = 0
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "folder": self.folder, "ok": self.ok, "error": self.error,
            "models": self.models, "total_files": self.total_files,
            "text_files": self.text_files, "skipped": self.skipped,
            "files": self.files[:200],
        }


def scan_folder(folder: str, known_models: Optional[List[str]] = None) -> ScanResult:
    """扫描文件夹，提取产品标识（型号）与官方URL"""
    result = ScanResult(folder=folder)
    root = Path(folder).expanduser()
    if not folder.strip():
        result.error = "未填写文件夹路径"
        return result
    if not root.exists():
        result.error = f"文件夹不存在：{folder}"
        return result
    if not root.is_dir():
        result.error = f"路径不是文件夹：{folder}"
        return result

    known = [normalize_model(m) for m in (known_models or [])]
    scanned = 0
    for path in sorted(root.rglob("*")):
        if scanned >= MAX_FILES:
            result.skipped.append(f"文件数超过上限{MAX_FILES}，其余未扫描")
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        scanned += 1
        result.total_files += 1
        entry: Dict = {"path": str(path.relative_to(root)), "suffix": path.suffix.lower(),
                       "size": path.stat().st_size, "models": [], "urls": []}

        # 文件名中的型号线索（如 hwpc_matebook-pro-harmonyos_xxx.jpg）
        name_l = path.name.lower()
        for slug, model in SLUG_MODEL_MAP.items():
            if slug.replace("-", "") in name_l.replace("-", "").replace("_", ""):
                entry["models"].append(model)

        if path.suffix.lower() in TEXT_SUFFIXES:
            result.text_files += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:MAX_READ_BYTES]
            except Exception as e:
                result.skipped.append(f"{entry['path']} 读取失败: {e}")
                result.files.append(entry)
                continue
            for url in URL_PATTERN.findall(text):
                if ASSET_URL_PATTERN.search(url):
                    continue        # 跳过图片等资源链接，只留产品页面
                if url not in entry["urls"]:
                    entry["urls"].append(url)
            found = _extract_models(text, known)
            for m in found:
                if m not in entry["models"]:
                    entry["models"].append(m)

        for model in entry["models"]:
            bucket = result.models.setdefault(model, {"files": [], "urls": [], "count": 0})
            bucket["count"] += 1
            if entry["path"] not in bucket["files"]:
                bucket["files"].append(entry["path"])
            for u in entry["urls"]:
                if u not in bucket["urls"]:
                    bucket["urls"].append(u)
        result.files.append(entry)

    if not result.models:
        result.error = "未在该文件夹中识别到产品型号（可检查文件内容是否包含型号字样）"
    result.ok = bool(result.models)
    return result


def _extract_models(text: str, known: List[str]) -> List[str]:
    """从正文提取产品标识：精确匹配已知型号优先，其次通用模式"""
    found: List[str] = []
    text_flat = re.sub(r"\s+", " ", text)
    for model in known:
        if model and model.lower() in text_flat.lower():
            found.append(model)
    if found:
        return found
    for pattern in MODEL_PATTERNS:
        for raw in pattern.findall(text):
            model = normalize_model(raw)
            if 3 < len(model) <= 42 and model not in found:
                found.append(model)
    return found[:5]
