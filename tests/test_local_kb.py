"""本地知识库检索：型号识别（防混淆）与图片型号一致性"""
from pathlib import Path

import pytest

from agent import config
from agent.local_kb import LocalKnowledgeBase

# 与运行时同一套解析逻辑：LOCAL_KB_ROOT → 上级目录 → 仓库内置 knowledge-base/
KB_ROOT = Path(config.LOCAL_KB_ROOT)

# 知识库未就位时（例如只拷了代码）跳过，而不是误报失败
pytestmark = pytest.mark.skipif(
    not (KB_ROOT / "P1-产品参数库").is_dir(),
    reason=f"缺少 P1-P8 知识库（{KB_ROOT}），可用 LOCAL_KB_ROOT 指向知识库根目录",
)


def _kb() -> LocalKnowledgeBase:
    kb = LocalKnowledgeBase(KB_ROOT)
    kb.load()
    return kb


def test_models_indexed():
    kb = _kb()
    models = kb.list_models()
    assert len(models) >= 5
    assert "HUAWEI MateBook Pro" in models


def test_resolve_exact_model():
    kb = _kb()
    assert kb.resolve_model("HUAWEI MateBook Pro") == ["HUAWEI MateBook Pro"]


def test_resolve_ambiguous_model():
    """相近型号必须返回多候选（防 D 16 与 D 16 SE 混淆）"""
    kb = _kb()
    hits = kb.resolve_model("D 16")
    assert len(hits) >= 2


def test_resolve_unknown_model():
    kb = _kb()
    assert kb.resolve_model("MateBook 999 不存在") == []


def test_images_model_consistent():
    kb = _kb()
    images = kb.search_images("HUAWEI MateBook Pro", "外观", limit=5)
    assert images
    assert all(i.product_model == "HUAWEI MateBook Pro" for i in images)
    assert all(i.source_page for i in images), "图片必须带来源页"


def test_facts_carry_sources():
    kb = _kb()
    facts = kb.search_facts("HUAWEI MateBook Pro", "屏幕", limit=5)
    assert facts
    assert all(f.source_title and f.source_path for f in facts)
