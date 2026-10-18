"""本地知识库兜底检索：直接检索P1-P8华为PC知识库文件

当ima OpenAPI未配置或不可用时使用，保证开发调试与演示不中断。
检索结果保留来源（文件路径/资料标题），满足"保留依据"要求。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .models import Fact, ImageAsset

# 业务主题词 -> 用于匹配资料章节/参数列
TOPIC_KEYWORDS = {
    "屏幕": ["屏幕", "显示屏", "分辨率", "亮度", "刷新率", "OLED", "色准", "护眼"],
    "性能": ["处理器", "CPU", "芯片", "内存", "性能", "存储", "显卡"],
    "续航": ["电池", "续航", "充电", "电源", "mAh", "Wh"],
    "便携": ["重量", "尺寸", "厚度", "轻薄", "便携", "mm"],
    "接口": ["接口", "USB", "Type-C", "HDMI", "扩展"],
    "协同": ["多屏协同", "超级终端", "协同", "流转", "共享", "碰一碰"],
    "AI": ["AI", "小艺", "智慧", "慧记", "深度研究"],
    "安全": ["安全", "隐私", "指纹", "加密", "防窥"],
    "摄像头": ["摄像头", "视频会议", "美颜"],
    "音频": ["扬声器", "麦克风", "音频", "降噪"],
    "键盘": ["键盘", "触控板", "触屏"],
    "系统": ["操作系统", "Windows", "HarmonyOS", "Linux"],
    "价格": ["价格", "售价", "定价", "元"],
    "售后": ["售后", "保修", "服务", "质保"],
}


def _split_sections(text: str) -> List[Tuple[str, str]]:
    """按二级标题切分Markdown为(标题, 内容)列表"""
    sections: List[Tuple[str, str]] = []
    current_title, current_lines = "概述", []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def _score(text: str, query: str) -> int:
    """简单关键词打分：命中业务主题词/查询词加分"""
    score = 0
    text_lower = text.lower()
    for token in re.split(r"[\s,，。、/|+]+", query):
        if len(token) >= 2 and token.lower() in text_lower:
            score += 3
    for topic, words in TOPIC_KEYWORDS.items():
        if topic in query:
            for w in words:
                if w.lower() in text_lower:
                    score += 2
    return score


class LocalKnowledgeBase:
    """本地P1-P8知识库检索器（懒加载索引）"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.p1 = self.root / "P1-产品参数库"
        self._model_index: Dict[str, Dict] = {}     # 型号 -> {facts_path, selling_path, dir}
        self._spec_matrix: List[Dict] = []           # 全型号参数联合矩阵行
        self._images: List[Dict] = []                # 全部图片联合检索表行
        self._loaded = False

    # ---------- 加载 ----------

    def load(self) -> None:
        if self._loaded:
            return
        self._load_model_index()
        self._load_spec_matrix()
        self._load_images()
        self._loaded = True

    def _load_model_index(self) -> None:
        if not self.p1.exists():
            return
        for facts_path in self.p1.rglob("产品事实.md"):
            model_dir = facts_path.parent
            model_name = self._model_name_from_facts(facts_path) or model_dir.name
            selling = model_dir / "卖点与限制.md"
            self._model_index[model_name] = {
                "dir": model_dir,
                "facts_path": facts_path,
                "selling_path": selling if selling.exists() else None,
                "image_csv": model_dir / "图片索引.csv" if (model_dir / "图片索引.csv").exists() else None,
            }

    @staticmethod
    def _model_name_from_facts(path: Path) -> str:
        try:
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
        except Exception:
            return ""
        m = re.match(r"#\s*(.+?)\s*-\s*产品事实", first_line)
        return m.group(1).strip() if m else ""

    def _load_spec_matrix(self) -> None:
        matrix = self.p1 / "00-全库横向索引" / "全型号参数联合矩阵.csv"
        if not matrix.exists():
            return
        with matrix.open(encoding="utf-8-sig") as f:
            self._spec_matrix = list(csv.DictReader(f))

    def _load_images(self) -> None:
        table = self.p1 / "00-全库横向索引" / "全部图片联合检索表.csv"
        if not table.exists():
            return
        with table.open(encoding="utf-8-sig") as f:
            self._images = list(csv.DictReader(f))

    # ---------- 型号识别（防混淆） ----------

    def resolve_model(self, product_query: str) -> List[str]:
        """把用户输入的型号解析为知识库中的精确型号；多命中=歧义需追问"""
        self.load()
        q = product_query.strip().lower().replace("华为", "").replace("huawei", "").strip()
        if not q:
            return []
        exact = [m for m in self._model_index if q == m.lower().replace("huawei", "").strip()]
        if exact:
            return exact
        contains = [
            m for m in self._model_index
            if q in m.lower() or m.lower().replace("huawei", "").strip() in q
        ]
        return contains

    def list_models(self) -> List[str]:
        self.load()
        return sorted(self._model_index.keys())

    # ---------- 事实检索 ----------

    def search_facts(self, product_model: str, query: str, limit: int = 8) -> List[Fact]:
        """按型号+任务检索事实点，全部带来源"""
        self.load()
        facts: List[Tuple[int, Fact]] = []
        info = self._model_index.get(product_model)

        # 1. 参数联合矩阵：结构化规格事实
        for row in self._spec_matrix:
            if row.get("型号", "").strip() == product_model:
                for column, value in row.items():
                    if column in ("型号", "本地事实源") or not value:
                        continue
                    score = _score(f"{column} {value}", query) + (1 if column in query else 0)
                    facts.append((score, Fact(
                        fact_id="",
                        fact_type="spec",
                        content=f"{column}：{value}",
                        product_model=product_model,
                        source_title=f"全型号参数联合矩阵 · {product_model}",
                        source_path=row.get("本地事实源", ""),
                    )))
                break

        # 2. 产品事实.md / 卖点与限制.md 章节
        if info:
            for key, fact_type in (("facts_path", "feature"), ("selling_path", "benefit")):
                path = info.get(key)
                if not path or not Path(path).exists():
                    continue
                text = Path(path).read_text(encoding="utf-8")
                for title, body in _split_sections(text):
                    if not body:
                        continue
                    score = _score(f"{title} {body[:400]}", query)
                    facts.append((score, Fact(
                        fact_id="",
                        fact_type=fact_type,
                        content=f"【{title}】{body[:600]}",
                        product_model=product_model,
                        source_title=f"{product_model} · {Path(path).stem}",
                        source_path=str(path),
                    )))

        # 命中优先，未命中事实作为背景补充；保证生成始终有事实依据可引用
        facts.sort(key=lambda x: -x[0])
        result = [f for _, f in facts[:limit]]
        for i, fact in enumerate(result, 1):
            fact.fact_id = f"F{i:02d}"
        return result

    # ---------- 图片检索 ----------

    def search_images(self, product_model: str, query: str = "", limit: int = 6) -> List[ImageAsset]:
        """按型号检索图片；只返回型号一致的图片（防错配）"""
        self.load()
        matched: List[Tuple[int, Dict]] = []
        for row in self._images:
            if row.get("产品型号", "").strip() != product_model:
                continue
            score = _score(row.get("画面说明", ""), query) if query else 1
            matched.append((score, row))
        matched.sort(key=lambda x: -x[0])

        assets: List[ImageAsset] = []
        for i, (_, row) in enumerate(matched[:limit], 1):
            local_dir = self.root / row.get("本地目录", "")
            local_path = local_dir / row.get("文件名", "")
            if not local_path.exists():
                local_path = local_dir / "images" / row.get("文件名", "")
            assets.append(ImageAsset(
                image_id=f"I{i:02d}",
                file_name=row.get("文件名", ""),
                url=row.get("原始图片URL", ""),
                local_path=str(local_path) if local_path.exists() else "",
                product_model=row.get("产品型号", ""),
                description=row.get("画面说明", "") or row.get("官网图片说明", ""),
                source_page=row.get("页面来源", "") or row.get("来源页面", ""),
                suggested_use=row.get("建议用途", ""),
            ))
        return assets

    # ---------- 场景与卖点资料 ----------

    def search_business_docs(self, audience: str, scenario: str, product_model: str = "",
                             limit: int = 3) -> List[Dict]:
        """检索P8客户场景库/P2卖点话术库中与人群场景相关的资料片段（带来源）"""
        self.load()
        query = f"{audience} {scenario}"
        candidates = []
        for base in (self.root / "P8-客户场景库", self.root / "P2-卖点话术库"):
            if not base.exists():
                continue
            for md in base.rglob("*.md"):
                score = _score(md.stem, query)
                if score <= 0:
                    continue
                text = md.read_text(encoding="utf-8")[:3000]
                score += _score(text[:800], query)
                if product_model and product_model.lower() in text.lower():
                    score += 2
                candidates.append((score, {
                    "title": md.stem,
                    "path": str(md),
                    "excerpt": text[:500],
                }))
        candidates.sort(key=lambda x: -x[0])
        return [c for _, c in candidates[:limit]]

    # ---------- 目录浏览（对应 get_knowledge_list 回退） ----------

    def browse_catalog(self, limit: int = 50) -> List[Dict]:
        """浏览知识库目录结构"""
        self.load()
        items: List[Dict] = []
        for base in sorted(self.root.glob("P*")):
            if not base.is_dir():
                continue
            items.append({"id": base.name, "name": base.name, "type": "folder", "path": str(base)})
            for sub in sorted(base.iterdir()):
                if sub.is_dir() and len(items) < limit:
                    items.append({"id": f"{base.name}/{sub.name}", "name": sub.name,
                                  "type": "folder", "path": str(sub)})
        return items[:limit]
