"""文件夹扫描 / 结构化入库 / 来源解析 单元测试"""
from pathlib import Path

import pytest

from agent import config
from agent.enrich.scanner import scan_folder
from agent.enrich.store import EnrichStore
from agent.knowledge import SOURCE_LABELS, KnowledgeSource

# 与运行时同一套解析逻辑：LOCAL_KB_ROOT → 上级目录 → 仓库内置 knowledge-base/
KB_ROOT = Path(config.LOCAL_KB_ROOT)
SAMPLE_DIR = KB_ROOT / "P1-产品参数库" / "02-MateBook-Windows" / "MateBook X系列"

# 依赖知识库的用例：知识库未就位时跳过，其余用例仍照常执行
requires_kb = pytest.mark.skipif(
    not SAMPLE_DIR.is_dir(),
    reason=f"缺少 P1-P8 知识库（{KB_ROOT}），可用 LOCAL_KB_ROOT 指向知识库根目录",
)


@requires_kb
def test_scan_folder_finds_model_and_urls():
    result = scan_folder(str(SAMPLE_DIR),
                         known_models=["HUAWEI MateBook X Pro 酷睿 Ultra 微绒典藏版"])
    assert result.ok
    assert "HUAWEI MateBook X Pro 酷睿 Ultra 微绒典藏版" in result.models
    info = result.models["HUAWEI MateBook X Pro 酷睿 Ultra 微绒典藏版"]
    assert info["count"] > 0 and info["urls"], "应提取到官网链接"


def test_scan_folder_error_feedback():
    bad = scan_folder("/路径不存在-测试")
    assert not bad.ok and bad.error


@requires_kb
def test_scan_skips_asset_urls():
    result = scan_folder(str(SAMPLE_DIR))
    for info in result.models.values():
        for url in info["urls"]:
            assert not url.lower().endswith((".jpg", ".png", ".pdf"))


def test_store_roundtrip(tmp_path):
    store = EnrichStore(tmp_path)
    entry = {"model": "TEST-1", "folder": "/tmp/f", "local_files": ["a.md"],
             "crawled": {"model": "TEST-1", "pages": [{"url": "https://x", "ok": True}]}}
    path = store.save_product(entry)
    assert path.exists()
    loaded = store.load_product("TEST-1")
    assert loaded and loaded["local_files"] == ["a.md"]
    assert "TEST-1" in store.list_models()


def test_parse_sources():
    assert KnowledgeSource._parse_sources("auto") == ["ima", "local"]
    assert KnowledgeSource._parse_sources("local") == ["local"]
    assert KnowledgeSource._parse_sources("ima,local,enrich") == ["ima", "local", "enrich"]
    assert KnowledgeSource._parse_sources("乱填") == ["local"]
    assert set(SOURCE_LABELS) == {"ima", "local", "enrich"}


@requires_kb
def test_local_only_search_no_network():
    ks = KnowledgeSource()
    ks.initialize("local")
    assert ks.sources == ["local"]
    facts = ks.search_facts("HUAWEI MateBook Pro", "屏幕 续航", limit=5)
    assert facts and all(f.source_path for f in facts), "事实必须带来源"
