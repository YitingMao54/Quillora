"""产品数据增强模块 · Streamlit界面（仅在功能开关打开时渲染）"""
from __future__ import annotations

from typing import List

import streamlit as st

from .. import config
from .service import EnrichService

LEVEL_ICON = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}


@st.cache_resource
def _service() -> EnrichService:
    return EnrichService()


def render_enrich_module() -> None:
    """主区域面板：文件夹入口 / 扫描 / 官网爬取 / 日志"""
    st.markdown('<div class="sec-head"><h3>产品数据增强（可选）</h3><span>DATA ENRICHMENT</span></div>',
                unsafe_allow_html=True)
    st.caption("选择任意本地文件夹 → 自动识别产品型号 → 合规抓取官网产品详情 → 与本地文件关联入库。"
               "功能默认关闭，不开启时不产生任何爬取请求。")

    svc = _service()

    c1, c2 = st.columns([3, 1])
    with c1:
        default_folder = str(config.LOCAL_KB_ROOT / "P1-产品参数库")
        folder = st.text_input("本地数据源文件夹路径", value=st.session_state.get("enrich_folder", default_folder),
                               key="enrich_folder",
                               placeholder="如 /Users/xxx/Documents/产品资料")
    with c2:
        st.write("")
        st.write("")
        scan_clicked = st.button("🔍 扫描文件夹", use_container_width=True)

    if scan_clicked:
        with st.spinner("扫描中..."):
            known = [str(m) for m in _local_models()]
            scan_data = svc.scan(folder, known_models=known)
        st.session_state["enrich_scan"] = scan_data

    scan_data = st.session_state.get("enrich_scan")
    if scan_data is None:
        st.info("填写文件夹路径后点击「扫描文件夹」开始。")
    elif not scan_data.get("ok"):
        st.error(f"扫描失败：{scan_data.get('error')}")
    else:
        st.success(f"扫描完成：共 {scan_data['total_files']} 个文件（文本 {scan_data['text_files']} 个），"
                   f"识别到 {len(scan_data['models'])} 个产品型号")
        models = list(scan_data["models"].keys())
        selected = st.multiselect("选择要抓取官网数据的型号（默认全部）", models, default=models,
                                  key="enrich_models")
        st.markdown("**识别结果**")
        for model, info in scan_data["models"].items():
            st.markdown(
                f'<div class="info-strip">💻 <b>{model}</b>｜关联本地文件 {info["count"]} 个｜'
                f'官网链接 {len(info["urls"])} 条</div>', unsafe_allow_html=True)
            with st.expander(f"查看「{model}」的文件与链接"):
                for f in info["files"][:10]:
                    st.write(f"- {f}")
                for u in info["urls"][:10]:
                    st.write(f"- {u}")

        crawl_clicked = st.button("🚀 抓取官网数据并入库", type="primary",
                                  use_container_width=True)
        if crawl_clicked:
            if not selected:
                st.warning("请至少选择一个型号")
            else:
                with st.spinner("正在按限速策略抓取官网数据（每请求间隔≥2秒，失败自动重试）..."):
                    report = svc.crawl_and_store(scan_data, selected)
                st.session_state["enrich_report"] = report

        report = st.session_state.get("enrich_report")
        if report is not None:
            if report.get("results"):
                st.success(f"完成：{len(report['results'])} 个型号已入库")
                for r in report["results"]:
                    st.markdown(
                        f'<div class="info-strip">📦 <b>{r["model"]}</b>｜官网页面成功 '
                        f'{r["pages_ok"]}/{r["pages_total"]}｜已保存 {r["stored_path"]}</div>',
                        unsafe_allow_html=True)
            for err in report.get("errors", []):
                st.warning(err)
            if not report.get("results") and not report.get("errors"):
                st.error("抓取未完成，请查看下方日志定位原因")

    # ---------- 运行日志 ----------
    st.markdown("**运行日志**（同时写入 data/logs/enrich.log）")
    logs = svc.logs()
    if not logs:
        st.caption("暂无日志")
    else:
        for m in logs[-25:]:
            icon = LEVEL_ICON.get(m["level"], "ℹ️")
            st.markdown(f"`{m['time']}` {icon} {m['text']}")


def _local_models() -> List[str]:
    """尽量从本地知识库拿已知精确型号做匹配优先级（失败不影响功能）"""
    try:
        from ..local_kb import LocalKnowledgeBase
        return LocalKnowledgeBase(config.LOCAL_KB_ROOT).list_models()
    except Exception:
        return []
