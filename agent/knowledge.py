"""统一知识检索层：优先ima OpenAPI，本地P1-P8知识库兜底

两种来源均返回 Fact / ImageAsset，并保留来源记录（依据可追溯）。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from . import config
from .ima_client import ImaAPIError, ImaClient
from .local_kb import LocalKnowledgeBase
from .models import Fact, ImageAsset


SOURCE_LABELS = {
    "ima": "ima在线知识库",
    "local": "本地同源知识库（P1-P8）",
    "enrich": "增强库（官网爬取）",
}


class KnowledgeSource:
    """知识与图片检索入口（支持多来源合并）

    source_mode 支持多来源组合，如 "ima,local" / "ima,local,enrich"：
      - "ima"    ：ima在线知识库
      - "local"  ：本地P1-P8同源数据
      - "enrich" ：产品数据增强库（官网爬取入库）
    兼容旧值："auto"=ima+local，单值 "ima"/"local" 同前。
    """

    def __init__(self, prefer_ima: bool = True, source_mode: str = "auto"):
        self.local = LocalKnowledgeBase(config.LOCAL_KB_ROOT)
        self.ima: Optional[ImaClient] = None
        self.kb_id: Optional[str] = None
        self.sources: List[str] = ["ima", "local"]
        self.active: str = "ima+local"
        self.active_reason: str = ""
        self.prefer_ima = prefer_ima
        self.source_mode = source_mode

    @staticmethod
    def _parse_sources(mode: Optional[str]) -> List[str]:
        if not mode or mode == "auto":
            return ["ima", "local"]
        if mode in SOURCE_LABELS:
            return [mode]
        parts = [p.strip() for p in re.split(r"[,+|、\s]+", mode) if p.strip()]
        picked = [p for p in parts if p in SOURCE_LABELS]
        return picked or ["local"]

    @property
    def active_label(self) -> str:
        return " + ".join(SOURCE_LABELS.get(s, s) for s in self.active.split("+")) or "—"

    def initialize(self, source_mode: Optional[str] = None) -> Dict:
        """连接/装载所选数据来源；多来源合并，记录各来源状态"""
        if source_mode:
            self.source_mode = source_mode
        sources = self._parse_sources(self.source_mode)
        notes: List[str] = []

        self.local.load()
        status: Dict = {"source": "", "source_label": "", "reason": "", "mode": self.source_mode,
                        "sources": sources, "models": len(self.local.list_models()),
                        "kb_name": config.IMA_KNOWLEDGE_BASE_NAME}

        if "ima" in sources:
            if config.ima_configured():
                try:
                    self.ima = ImaClient()
                    self.kb_id = self.ima.find_knowledge_base(config.IMA_KNOWLEDGE_BASE_NAME)
                    notes.append("ima在线知识库已连接")
                except ImaAPIError as e:
                    notes.append(f"⚠ ima连接失败，临时用本地数据补位：{e}")
                    if "local" not in sources:
                        sources.append("local")
                    self.ima = None
            else:
                notes.append("⚠ 未配置ima凭证，临时用本地数据补位")
                if "local" not in sources:
                    sources.append("local")
                self.ima = None
        if "local" in sources:
            notes.append(f"本地数据就绪（{status['models']}个型号）")
        if "enrich" in sources:
            try:
                from .enrich.store import EnrichStore
                n = len(EnrichStore().list_models())
                notes.append(f"增强库就绪（{n}个型号）" if n else "⚠ 增强库为空，可在增强面板爬取入库")
            except Exception as e:
                notes.append(f"⚠ 增强库读取失败：{e}")

        self.sources = sources
        self.active = "+".join(sources)
        self.active_reason = "；".join(notes)
        status.update(source=self.active, source_label=self.active_label,
                      sources=sources, reason=self.active_reason)
        return status

    # ---------- 型号识别 ----------

    def resolve_model(self, product_query: str) -> List[str]:
        """识别精确型号；返回多个命中表示相近型号歧义，需追问"""
        return self.local.resolve_model(product_query)

    # ---------- 事实检索 ----------

    def search_facts(self, product_model: str, query: str, limit: int = 8) -> List[Fact]:
        """按所选来源检索事实点，轮转合并去重（保证多来源均有代表）"""
        buckets: List[List[Fact]] = []
        if "ima" in self.sources and self.ima and self.kb_id:
            try:
                items = self.ima.search_knowledge(self.kb_id, f"{product_model} {query}", limit=limit)
                if items:
                    buckets.append(self._ima_items_to_facts(items, product_model))
            except Exception:
                pass  # ima检索失败/配额用尽时由其他来源补位，不中断生成
        if "local" in self.sources:
            buckets.append(self.local.search_facts(product_model, query, limit=limit))
        if "enrich" in self.sources:
            buckets.append(self._enriched_facts(product_model, query, limit))

        # 轮转交错合并：多来源时各来源事实交替出现，避免单一来源占满配额
        merged: List[Fact] = []
        for i in range(max((len(b) for b in buckets), default=0)):
            for b in buckets:
                if i < len(b):
                    merged.append(b[i])

        seen: set = set()
        facts: List[Fact] = []
        for f in merged:
            key = f.content[:60]
            if key not in seen:
                seen.add(key)
                facts.append(f)
        facts = facts[:limit]
        for i, fact in enumerate(facts, 1):
            fact.fact_id = f"F{i:02d}"
        return facts

    def _enriched_facts(self, product_model: str, query: str, limit: int) -> List[Fact]:
        """从产品数据增强库（官网爬取入库）读取事实点"""
        try:
            from .enrich.store import EnrichStore
            data = EnrichStore().load_product(product_model)
        except Exception:
            return []
        if not data:
            return []
        facts: List[Fact] = []
        for page in data.get("crawled", {}).get("pages", []):
            if not page.get("ok"):
                continue
            text = f"{page.get('description', '')} {page.get('text_excerpt', '')}".strip()
            if not text:
                continue
            title = page.get("title") or "官网产品页"
            facts.append(Fact(
                fact_id="",
                fact_type="feature",
                content=f"【官网·{title}】{text[:600]}",
                product_model=product_model,
                source_title=title,
                source_path=page.get("url", ""),
            ))
            if len(facts) >= limit:
                break
        return facts

    def _ima_items_to_facts(self, items: List[Dict], product_model: str) -> List[Fact]:
        """把ima检索命中（media_id/title/highlight_content）转为可追溯事实点"""
        facts: List[Fact] = []
        for i, item in enumerate(items, 1):
            content = (item.get("highlight_content") or item.get("content")
                       or item.get("summary") or "")
            title = item.get("title") or "ima资料"
            if not content:
                continue
            # 原文访问信息（URL类媒体），失败不影响事实点生成
            source = f"ima知识库 media_id={item.get('media_id', '')}"
            try:
                media = self.ima.get_media_info(item.get("media_id", "")) if self.ima else {}
                url = (media.get("url_info") or {}).get("url", "")
                if url:
                    source = url
            except Exception:
                pass
            facts.append(Fact(
                fact_id=f"F{i:02d}",
                fact_type="feature",
                content=f"【{title}】{content[:600]}",
                product_model=product_model,
                source_title=title,
                source_path=source,
            ))
        return facts

    # ---------- 图片检索 ----------

    def search_images(self, product_model: str, query: str = "", limit: int = 6) -> List[ImageAsset]:
        # 图片要求型号一致、来源可查，本地检索表包含ima同源的官网图片URL与来源页
        return self.local.search_images(product_model, query, limit=limit)

    # ---------- 场景资料 ----------

    def search_business_docs(self, audience: str, scenario: str,
                             product_model: str = "", limit: int = 3) -> List[Dict]:
        return self.local.search_business_docs(audience, scenario, product_model, limit)

    # ---------- 目录浏览（搜索为空时回退） ----------

    def browse_catalog(self, limit: int = 50) -> List[Dict]:
        if self.active == "ima" and self.ima and self.kb_id:
            try:
                return self.ima.browse_catalog(self.kb_id, limit)
            except ImaAPIError:
                pass
        return self.local.browse_catalog(limit)
