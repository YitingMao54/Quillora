"""结构化存储：爬取数据与本地文件夹信息关联映射、统一入库

存储布局（data/enriched/）：
  index.json               总索引：型号 -> {folder, files, pages, updated_at}
  <型号slug>/product.json  该型号的完整结构化数据（本地文件映射 + 官网页数据）
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .. import config


def _slug(model: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff-]+", "_", model).strip("_") or "unknown"


class EnrichStore:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else (config.PROJECT_ROOT / "data" / "enriched")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def index_path(self) -> Path:
        return self.data_dir / "index.json"

    def load_index(self) -> Dict:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"products": {}}

    def save_product(self, entry: Dict) -> Path:
        """入库一个型号的结构化数据，并更新总索引

        entry 结构：
          {model, folder, local_files: [...], crawled: {model, pages: [...]}, notes: [...]}
        """
        model = entry.get("model", "")
        slug = _slug(model)
        target_dir = self.data_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        entry = dict(entry)
        entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
        target = target_dir / "product.json"
        target.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

        index = self.load_index()
        index.setdefault("products", {})[model] = {
            "slug": slug,
            "folder": entry.get("folder", ""),
            "local_files": len(entry.get("local_files", [])),
            "pages_ok": sum(1 for p in entry.get("crawled", {}).get("pages", []) if p.get("ok")),
            "pages_total": len(entry.get("crawled", {}).get("pages", [])),
            "updated_at": entry["updated_at"],
            "path": str(target),
        }
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def load_product(self, model: str) -> Optional[Dict]:
        index = self.load_index()
        info = index.get("products", {}).get(model)
        if not info:
            return None
        try:
            return json.loads(Path(info["path"]).read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_models(self) -> List[str]:
        return list(self.load_index().get("products", {}).keys())
