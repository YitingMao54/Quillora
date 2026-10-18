"""华为PC营销软文智能体 - Streamlit界面

视觉体系：深墨底 × 华为红主色 × 暖琥珀点缀，编辑感大字阶 + 斜切线条纹理；
功能逻辑与 agent.pipeline 完全一致，仅重排布局与交互。
"""
from __future__ import annotations

import streamlit as st

from agent import config, llm_providers as lp
from agent.models import Platform, Task, TaskStatus
from agent.pipeline import MarketingAgent, TaskError

st.set_page_config(page_title="华为PC营销软文智能体", page_icon="⚡", layout="wide")

# ============================================================
# 设计系统：CSS
# ============================================================

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --ink: #0F1219;          /* 页面底色 */
  --surface: #171B24;      /* 卡片面 */
  --surface-2: #1E2430;    /* 抬升面 */
  --line: #2A3140;         /* 分隔线 */
  --text: #ECEFF5;
  --text-dim: #9BA6B8;
  --red: #E02020;          /* 华为红 · 主色 */
  --red-deep: #B3121B;
  --ember: #FF7A45;        /* 暖琥珀 · 强调 */
  --amber: #FFB347;
  --ok: #3DDC97;
  --warn: #FFB347;
  --err: #FF5C5C;
  --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* ---------- 全局 ---------- */
.stApp {
  background:
    repeating-linear-gradient(115deg, transparent 0 34px, rgba(255,255,255,.016) 34px 35px),
    radial-gradient(1200px 500px at 85% -10%, rgba(224,32,32,.14), transparent 60%),
    radial-gradient(900px 420px at -10% 110%, rgba(255,122,69,.08), transparent 55%),
    var(--ink);
}
.block-container { max-width: 1180px; padding-top: 2.2rem; }
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #12161E 0%, #0F1219 100%);
  border-right: 1px solid var(--line);
}
@media (min-width: 992px) {
  section[data-testid="stSidebar"] {
    width: 22.5rem !important; min-width: 22.5rem !important; max-width: 22.5rem !important;
  }
}
section[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }
h1, h2, h3, h4 { font-family: "Noto Sans SC", system-ui, sans-serif !important; }
p, li, label, span, div { font-family: "Noto Sans SC", system-ui, sans-serif; }
code, pre, .mono { font-family: var(--mono) !important; }

/* ---------- 主视觉 ---------- */
.hero { position: relative; padding: 2.1rem 2.4rem 2.3rem; margin-bottom: 1.6rem;
  background: linear-gradient(135deg, rgba(224,32,32,.16), rgba(255,122,69,.07) 45%, rgba(30,36,48,.9));
  border: 1px solid rgba(224,32,32,.35); border-left: 6px solid var(--red);
  animation: rise .7s cubic-bezier(.16,1,.3,1) both; }
.hero::after { content: ""; position: absolute; right: -40px; top: -40px; width: 220px; height: 220px;
  background: conic-gradient(from 45deg, rgba(224,32,32,.28), transparent 32%);
  transform: rotate(12deg); pointer-events: none; }
.hero-kicker { display: inline-block; font-family: var(--mono); font-size: .72rem; letter-spacing: .22em;
  color: var(--amber); border: 1px solid rgba(255,179,71,.45); padding: .22rem .7rem; margin-bottom: .9rem; }
.hero-title { font-size: clamp(1.9rem, 4.4vw, 3.15rem); font-weight: 900; line-height: 1.24;
  letter-spacing: -.015em; margin: 0 0 .55rem; overflow-wrap: break-word; padding-bottom: .12em; }
.hero-title em { font-style: normal;
  background: linear-gradient(100deg, var(--red) 5%, var(--ember) 55%, var(--amber) 95%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero-sub { color: var(--text-dim); font-size: 1.02rem; line-height: 1.85; max-width: 56rem; }
.hero-sub b { color: var(--text); font-weight: 700; }

/* ---------- 状态徽章 ---------- */
.chips { display: flex; flex-wrap: wrap; gap: .55rem; margin-top: 1.15rem; }
.chip { display: inline-flex; align-items: center; gap: .45rem; padding: .34rem .85rem;
  border: 1px solid var(--line); background: rgba(15,18,25,.72); font-size: .8rem;
  color: var(--text-dim); font-family: var(--mono); letter-spacing: .02em; }
.chip b { color: var(--text); font-weight: 600; }
.chip.on { border-color: rgba(61,220,151,.5); } .chip.on i { background: var(--ok); }
.chip.off { border-color: rgba(255,92,92,.5); } .chip.off i { background: var(--err); }
.chip i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

/* ---------- 特性卡片 ---------- */
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1.2rem 0; }
.f-card { background: var(--surface); border: 1px solid var(--line); border-top: 3px solid var(--red);
  padding: 1.35rem 1.35rem 1.5rem; animation: rise .7s cubic-bezier(.16,1,.3,1) both; }
.f-card:nth-child(2) { animation-delay: .08s; border-top-color: var(--ember); }
.f-card:nth-child(3) { animation-delay: .16s; border-top-color: var(--amber); }
.f-card h4 { margin: 0 0 .5rem; font-size: 1.06rem; font-weight: 900; letter-spacing: .01em; }
.f-card p { margin: 0; color: var(--text-dim); font-size: .88rem; line-height: 1.85; }
.f-icon { font-family: var(--mono); font-size: .72rem; letter-spacing: .2em; color: var(--ember); }

/* ---------- 区块标题 ---------- */
.sec-head { display: flex; align-items: baseline; gap: .85rem; margin: 1.9rem 0 1rem; }
.sec-head::before { content: ""; width: 22px; height: 22px; flex: none;
  background: linear-gradient(135deg, var(--red), var(--ember)); transform: rotate(45deg); align-self: center; }
.sec-head h3 { margin: 0; font-size: 1.32rem; font-weight: 900; letter-spacing: .01em; }
.sec-head span { color: var(--text-dim); font-family: var(--mono); font-size: .74rem; letter-spacing: .18em; }

/* ---------- 执行过程时间线 ---------- */
.timeline { border-left: 2px solid var(--line); margin: .4rem 0 0 .55rem; padding-left: 1.35rem; }
.tl-item { position: relative; padding: .42rem 0 .62rem; animation: rise .5s cubic-bezier(.16,1,.3,1) both; }
.tl-item::before { content: ""; position: absolute; left: -1.63rem; top: .82rem; width: 11px; height: 11px;
  border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 4px rgba(61,220,151,.15); }
.tl-item.warn::before { background: var(--warn); box-shadow: 0 0 0 4px rgba(255,179,71,.15); }
.tl-item.error::before { background: var(--err); box-shadow: 0 0 0 4px rgba(255,92,92,.15); }
.tl-name { font-weight: 700; font-size: .96rem; }
.tl-name .ms { font-family: var(--mono); font-size: .72rem; color: var(--amber); margin-left: .55rem; }
.tl-detail { color: var(--text-dim); font-size: .82rem; line-height: 1.75; margin-top: .15rem; }

/* ---------- 软文排版 ---------- */
.article-title { font-size: 1.65rem; font-weight: 900; line-height: 1.35; margin: .3rem 0 .8rem;
  padding-left: 1rem; border-left: 5px solid var(--red); }
.article-intro { color: var(--amber); font-size: 1.02rem; line-height: 1.9; margin-bottom: 1rem; }
.article-body p { line-height: 2.05; font-size: 1rem; margin: .85rem 0; }
.fact-ref { font-family: var(--mono); font-size: .72rem; color: var(--ember); letter-spacing: .04em; }
.cta-box { margin-top: 1.25rem; padding: 1rem 1.35rem; background: rgba(224,32,32,.12);
  border: 1px solid rgba(224,32,32,.4); border-left: 5px solid var(--red); font-weight: 700; }
.tag { display: inline-block; margin: .18rem .32rem .18rem 0; padding: .22rem .72rem;
  background: rgba(255,122,69,.13); border: 1px solid rgba(255,122,69,.4); color: var(--amber);
  font-family: var(--mono); font-size: .76rem; }

/* ---------- 图片方案卡 ---------- */
.img-card { display: flex; gap: 1rem; background: var(--surface); border: 1px solid var(--line);
  padding: .95rem; margin: .65rem 0; transition: transform .25s cubic-bezier(.16,1,.3,1), border-color .25s; }
.img-card:hover { transform: translateY(-3px); border-color: rgba(224,32,32,.55); }
.img-card img { width: 168px; max-height: 128px; object-fit: cover; border: 1px solid var(--line); }
.img-meta { font-size: .84rem; line-height: 1.95; color: var(--text-dim); }
.img-meta b { color: var(--text); }

/* ---------- 核验判定卡 ---------- */
.verdict-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: .9rem; margin: .8rem 0 1.15rem; }
.verdict { padding: 1.05rem 1.15rem; background: var(--surface); border: 1px solid var(--line); }
.verdict .k { font-family: var(--mono); font-size: .7rem; letter-spacing: .18em; color: var(--text-dim); }
.verdict .v { font-size: 1.32rem; font-weight: 900; margin: .28rem 0 .12rem; }
.verdict .v.pass { color: var(--ok); } .verdict .v.fail { color: var(--err); }
.verdict .s { font-family: var(--mono); font-size: .72rem; color: var(--amber); }
.violation { padding: .62rem .95rem; margin: .42rem 0; background: rgba(255,92,92,.08);
  border-left: 4px solid var(--err); font-size: .85rem; line-height: 1.8; }
.violation.low { background: rgba(255,179,71,.08); border-left-color: var(--warn); }

/* ---------- 侧栏 ---------- */
.side-title { font-family: var(--mono); font-size: .72rem; letter-spacing: .26em;
  color: var(--ember); margin: 1.5rem 0 .55rem; text-transform: uppercase; }
.side-title:first-of-type { margin-top: .3rem; }

/* ---------- 按钮 / 输入 ---------- */
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: linear-gradient(100deg, var(--red-deep), var(--red) 55%, var(--ember)) !important;
  border: none !important; font-weight: 800 !important; letter-spacing: .06em; height: 3rem;
  transition: filter .2s, transform .2s cubic-bezier(.16,1,.3,1); }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
  filter: brightness(1.12); transform: translateY(-2px); }
.stButton > button { transition: transform .2s cubic-bezier(.16,1,.3,1), border-color .2s; }
.stButton > button:hover { transform: translateY(-2px); border-color: var(--red); }
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div {
  border-color: var(--line) !important; background: var(--surface) !important; }
.stTextInput input:focus, .stTextArea textarea:focus { border-color: var(--red) !important; }

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] { gap: .4rem; border-bottom: 2px solid var(--line); }
.stTabs [data-baseweb="tab"] { padding: .68rem 1.25rem; border-radius: 0 !important;
  font-weight: 700; letter-spacing: .03em; color: var(--text-dim); }
.stTabs [aria-selected="true"] { color: var(--text) !important;
  background: linear-gradient(180deg, transparent 55%, rgba(224,32,32,.28)) !important;
  border-bottom: 3px solid var(--red) !important; }

/* ---------- 信息条 ---------- */
.info-strip { display: flex; gap: .8rem; align-items: center; padding: .85rem 1.15rem;
  background: var(--surface-2); border: 1px solid var(--line); border-left: 4px solid var(--amber);
  color: var(--text-dim); font-size: .87rem; line-height: 1.8; margin: .75rem 0; }

/* ---------- 任务工作台：大控件 ---------- */
div[data-testid="stForm"] { border: 1px solid var(--line); border-top: 3px solid var(--red);
  background: var(--surface); padding: 1.35rem 1.55rem .55rem; }
div[data-testid="stTextArea"] textarea { font-size: 1.04rem !important; line-height: 1.95 !important; }
div[data-baseweb="select"] > div { min-height: 2.85rem; }
div[data-testid="stTextInput"] input { min-height: 2.75rem; font-size: .98rem; }
label, .stRadio label, .stCheckbox label { font-size: .92rem !important; font-weight: 600; }

/* ---------- 动效 ---------- */
@keyframes rise { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}

/* ---------- 响应式 ---------- */
@media (max-width: 900px) {
  .grid3, .verdict-row { grid-template-columns: 1fr; }
  .hero { padding: 1.55rem 1.35rem 1.75rem; }
  .hero::after { display: none; }
  .img-card { flex-direction: column; }
  .img-card img { width: 100%; max-height: 210px; }
  .block-container { padding-top: 1.2rem; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def _img_src(asset) -> str:
    """图片渲染源：本地文件转base64内嵌（浏览器无法直接读本地路径），否则用原始URL"""
    if asset is None:
        return ""
    if asset.local_path:
        from pathlib import Path
        import base64
        import mimetypes
        p = Path(asset.local_path)
        if p.exists() and p.stat().st_size < 5_000_000:
            mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64}"
    return asset.url or ""

PLATFORM_OPTIONS = {
    "公众号": Platform.WECHAT_ARTICLE,
    "小红书": Platform.XIAOHONGSHU,
    "门店朋友圈": Platform.WECHAT_MOMENT,
    "门店海报": Platform.STORE_POSTER,
}
AUDIENCES = ["大学新生", "职场人士", "内容创作者", "家庭用户", "企业采购", "门店到访顾客"]
SCENARIOS = ["开学季", "移动办公", "内容创作", "家庭换新", "企业采购", "新品首发", "节日营销", "门店到访"]


@st.cache_resource
def get_agent() -> MarketingAgent:
    return MarketingAgent()


agent = get_agent()

# ============================================================
# 侧边栏：模型与凭证 + 任务输入
# ============================================================

with st.sidebar:
    st.markdown('<div class="side-title">MODEL · 模型与凭证</div>', unsafe_allow_html=True)
    st.caption("选厂商和模型，填对应 API Key 即可使用；密钥只留本机，界面不回显。")

    provider = st.selectbox("模型厂商", lp.provider_names(),
                            help="均为OpenAI兼容接口，选择后自动带出接口地址")
    model_options = lp.models_of(provider) or []
    if model_options:
        model_name = st.selectbox("模型", model_options)
    else:
        model_name = st.text_input("模型名（自定义）", value=config.LLM_MODEL,
                                   placeholder="如 glm-4-plus / qwen-max")
    base_url = st.text_input("接口地址（Base URL）", value=lp.base_url_of(provider) or config.LLM_BASE_URL)
    st.caption(f"💡 {lp.note_of(provider)}")

    # 每个厂商专属的API Key输入框（切换厂商互不覆盖）
    if "llm_keys" not in st.session_state:
        st.session_state["llm_keys"] = {}
    provider_key = st.text_input(
        f"{provider} · API Key", type="password",
        key=f"key_input_{provider}", placeholder="粘贴该模型的 API Key",
        help="每个厂商独立保存，切换厂商不会丢失已填写的Key",
    )
    if provider_key.strip():
        st.session_state["llm_keys"][provider] = provider_key.strip()

    with st.expander("ima 凭证（可选，赛题知识库）", expanded=not config.ima_configured()):
        st.caption("可在此直接修改ima凭证；留空表示保持现有配置不变。")
        ima_hint = "已配置（留空保持不变）" if config.ima_configured() else "粘贴 ima Client ID"
        ima_key_hint = "已配置（留空保持不变）" if config.ima_configured() else "粘贴 ima API Key"
        ima_cid = st.text_input("ima Client ID", type="password", key="ima_cid", placeholder=ima_hint)
        ima_key = st.text_input("ima API Key", type="password", key="ima_key", placeholder=ima_key_hint)

    persist = st.checkbox("保存到本地 .env（已被 .gitignore 排除）", value=True)
    if st.button("⚡ 保存并应用", type="primary", use_container_width=True):
        key_to_apply = st.session_state["llm_keys"].get(provider, "").strip()
        if not key_to_apply:
            st.warning(f"请先填写 {provider} 的 API Key")
        else:
            overrides = {
                "LLM_API_KEY": key_to_apply,
                "LLM_BASE_URL": base_url.strip(),
                "LLM_MODEL": model_name.strip(),
                "IMA_CLIENT_ID": (st.session_state.get("ima_cid") or "").strip(),
                "IMA_API_KEY": (st.session_state.get("ima_key") or "").strip(),
            }
            config.apply_overrides(**overrides)
            if persist:
                config.save_dotenv(**overrides)
            st.session_state["active_llm"] = {"provider": provider, "model": model_name.strip()}
            get_agent.clear()
            st.session_state.pop("kb_status", None)
            st.session_state.pop("result", None)
            st.success(f"已启用 {provider} · {model_name}" + ("，并写入 .env" if persist else ""))
            st.rerun()

    active = st.session_state.get("active_llm")
    if active:
        st.markdown(
            f'<div class="chips"><span class="chip on"><i></i>当前模型 <b>{active["provider"]} · {active["model"]}</b></span></div>',
            unsafe_allow_html=True)

    st.markdown('<div class="side-title">SOURCE · 数据来源（可多选）</div>', unsafe_allow_html=True)
    SOURCE_OPTIONS = {"ima在线知识库": "ima", "本地P1-P8数据": "local", "增强库（官网爬取）": "enrich"}
    picked = st.pills(
        "数据来源（可多选组合）", list(SOURCE_OPTIONS.keys()),
        selection_mode="multi", default=["ima在线知识库", "本地P1-P8数据"],
        key="source_pills", label_visibility="collapsed",
        help="可多选：生成时同时从勾选的来源检索并合并事实；选「增强库」可打开官网爬取面板")
    if picked:
        source_mode = ",".join(SOURCE_OPTIONS[p] for p in picked)
    else:
        st.warning("至少选择一个数据来源，已默认使用本地数据")
        source_mode = "local"
    st.session_state["enrich_enabled"] = "增强库（官网爬取）" in picked

    st.markdown('<div class="side-title">STATUS · 账号与知识库</div>', unsafe_allow_html=True)
    if st.button("连接/刷新状态", use_container_width=True):
        st.session_state.pop("kb_status", None)
    # 数据来源切换后强制重新连接
    if st.session_state.get("kb_status_mode") != source_mode:
        st.session_state["kb_status_mode"] = source_mode
        st.session_state.pop("kb_status", None)
    status = st.session_state.get("kb_status")
    if status is None:
        try:
            status = agent.initialize(source_mode=source_mode)
            st.session_state["kb_status"] = status
        except Exception as e:
            st.error(f"初始化失败：{e}")
            status = {}
    if status:
        ima = status.get("ima", {})
        st.markdown(
            f'<div class="chips">'
            f'<span class="chip {"on" if ima.get("source") else "off"}"><i></i>资料来源 <b>'
            f'{agent.source_label(ima.get("source", ""))}</b></span>'
            f'<span class="chip {"on" if ima.get("configured") else "off"}"><i></i>ima凭证 <b>'
            f'{"已配置" if ima.get("configured") else "未配置"}</b></span>'
            f'</div>', unsafe_allow_html=True)
        st.caption(f"知识库：{ima.get('kb_name')}｜{ima.get('reason')}")

# ============================================================
# 主区域
# ============================================================

# ---------- 主视觉 ----------
llm_on = config.llm_configured()
kb_src = st.session_state.get("kb_status", {}).get("ima", {}).get("source", "")
st.markdown(f"""
<div class="hero">
  <div class="hero-kicker">HUAWEI PC · MARKETING AGENT</div>
  <div class="hero-title">把门店业务规则做进Agent的<br><em>华为PC营销软文智能体</em></div>
  <div class="hero-sub">自研Agent负责<b>理解人群场景</b>、<b>匹配平台规则</b>、<b>组织图文内容</b>，
  并在交付前完成<b>事实核验</b>与<b>营销合规检查</b>；产品事实与图片来自ima共享知识库，全程可追溯。</div>
  <div class="chips">
    <span class="chip {'on' if llm_on else 'off'}"><i></i>LLM <b>{'已配置 · ' + config.LLM_MODEL if llm_on else '待配置'}</b></span>
    <span class="chip {'on' if kb_src else 'off'}"><i></i>资料来源 <b>{agent.source_label(kb_src) if kb_src else '待连接'}</b></span>
    <span class="chip on"><i></i>流程 <b>九步闭环</b></span>
    <span class="chip on"><i></i>核验 <b>事实 / 图片 / 合规</b></span>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------- 任务工作台（主区域，大尺寸交互） ----------
st.markdown('<div class="sec-head"><h3>任务工作台</h3><span>TASK WORKBENCH</span></div>',
            unsafe_allow_html=True)
input_mode = st.radio("输入方式", ["自然语言任务（支持追问）", "表单直接填写"],
                      horizontal=True, label_visibility="collapsed")

if input_mode == "自然语言任务（支持追问）":
    user_input = st.text_area(
        "描述你的营销任务",
        placeholder="例：为准备开学购机的大学新生生成小红书图文，兼顾学习、携带和续航",
        height=150,
    )
    nb1, nb2 = st.columns([1, 5])
    with nb1:
        parse_clicked = st.button("🔍 解析任务", use_container_width=True)
    with nb2:
        if parse_clicked:
            if not user_input.strip():
                st.warning("请输入任务描述")
            else:
                with st.spinner("解析任务中..."):
                    parse_result = agent.parse_task(user_input)
                st.session_state["parse_result"] = parse_result

parse_result = st.session_state.get("parse_result")
if parse_result is not None:
    if parse_result.status == TaskStatus.COMPLETE:
        t = parse_result.parsed_task
        st.success("任务信息完整，可点击下方「生成图文软文」")
        st.markdown(
            f'<div class="info-strip">📌 <b>{t.product}</b>｜{t.target_audience}｜'
            f'{t.scenario or "—"}｜{t.platform.value}</div>', unsafe_allow_html=True)
    else:
        # ---------- 追问面板：把追问变成可点选/可填写的选项 ----------
        qtext = parse_result.follow_up_question or "信息不足，请补充以下信息"
        st.markdown(f'<div class="info-strip">💬 {qtext}</div>', unsafe_allow_html=True)

        # 核心三项（机型/平台/内容目标）始终给出选项；其余按追问内容动态补充
        ask: set = {"product", "platform", "content_goal"}
        field_hints = {
            "target_audience": ["人群", "谁"],
            "scenario": ["场景"],
            "special_requirements": ["卖点", "回避", "要求", "重点"],
        }
        for field, hints in field_hints.items():
            if any(h in qtext for h in hints) or field in (parse_result.missing_fields or []):
                ask.add(field)
        if parse_result.status == TaskStatus.AMBIGUOUS:
            ask.add("product")

        models = agent.knowledge.local.list_models()
        answers: dict = {}
        if "product" in ask:
            opts = parse_result.candidates or models
            if opts:
                answers["product"] = st.selectbox(
                    "① 具体机型（点选即可）", opts, key="ask_product",
                    help="相近型号配置不同，请选精确型号")
            else:
                answers["product"] = st.text_input("① 具体机型", key="ask_product_text")
        a1, a2 = st.columns(2)
        if "platform" in ask:
            answers["platform"] = a1.radio(
                "② 发布平台", list(PLATFORM_OPTIONS.keys()), horizontal=True, key="ask_platform")
        if "content_goal" in ask:
            answers["content_goal"] = a2.radio(
                "③ 内容目标", ["种草", "引导到店", "引导私信咨询", "转发", "暂不指定"],
                horizontal=True, key="ask_goal")
        a3, a4 = st.columns(2)
        if "target_audience" in ask:
            answers["target_audience"] = a3.selectbox("目标人群", AUDIENCES, key="ask_audience")
        if "scenario" in ask:
            answers["scenario"] = a4.selectbox("使用场景", SCENARIOS, key="ask_scenario")
        if "special_requirements" in ask:
            answers["special_requirements"] = st.text_input(
                "重点卖点 / 需回避内容（可选）", key="ask_special",
                placeholder="如：突出多屏协同；避免提到价格")

        b1, b2, _ = st.columns([1.3, 1.3, 3])
        fill_clicked = b1.button("✅ 填入任务表单", use_container_width=True)
        direct_clicked = b2.button("⚡ 填入并直接生成", use_container_width=True, type="primary")
        if fill_clicked or direct_clicked:
            if answers.get("product"):
                st.session_state["f_product"] = answers["product"]
            if answers.get("platform"):
                st.session_state["f_platform"] = answers["platform"]
            if answers.get("target_audience"):
                st.session_state["f_audience"] = answers["target_audience"]
            if answers.get("scenario"):
                st.session_state["f_scenario"] = answers["scenario"]
            if "content_goal" in answers:
                st.session_state["f_goal"] = "" if answers["content_goal"] == "暂不指定" else answers["content_goal"]
            if "special_requirements" in answers:
                st.session_state["f_special"] = answers["special_requirements"]
            if direct_clicked:
                st.session_state["direct_generate"] = True
                st.success("已填入，正在生成...")
            else:
                st.success("已填入下方任务表单，可继续调整后点击「生成图文软文」")

with st.form("task_form"):
    models = agent.knowledge.local.list_models()
    product = st.selectbox("产品型号（知识库精确型号）", models, key="f_product") if models \
        else st.text_input("产品型号", key="f_product_text")
    f1, f2, f3 = st.columns(3)
    audience = f1.selectbox("目标人群", AUDIENCES, key="f_audience")
    scenario = f2.selectbox("使用场景", SCENARIOS, key="f_scenario")
    platform_name = f3.selectbox("发布平台", list(PLATFORM_OPTIONS.keys()), key="f_platform")
    f4, f5 = st.columns([2, 3])
    content_goal = f4.text_input("内容目标（可选）", placeholder="种草 / 到店 / 咨询 / 转发", key="f_goal")
    special = f5.text_input("特殊要求（可选）", placeholder="如：突出多屏协同；避免提到价格", key="f_special")
    submitted = st.form_submit_button("🚀 生成图文软文", use_container_width=True, type="primary")

if st.session_state.pop("direct_generate", False):
    submitted = True

if submitted:
    try:
        if "kb_status" not in st.session_state:
            st.session_state["kb_status"] = agent.initialize(
                source_mode=st.session_state.get("kb_status_mode", "auto"))
        task = Task(
            product=product,
            target_audience=audience,
            scenario=scenario,
            platform=PLATFORM_OPTIONS[platform_name],
            content_goal=content_goal or None,
            special_requirements=[special] if special else [],
        )
        with st.spinner("正在执行：场景解析 → 平台策略 → 检索 → 生成 → 核验 → 合规检查..."):
            result = agent.execute(task)
        st.session_state["result"] = result
        st.session_state.pop("parse_result", None)
    except TaskError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"执行失败：{e}")

result = st.session_state.get("result")

if result is None:
    st.markdown("""
<div class="sec-head"><h3>能力全景</h3><span>CAPABILITIES</span></div>
<div class="grid3">
  <div class="f-card"><div class="f-icon">01 / SCENE</div><h4>场景实质变化</h4>
  <p>识别人群、问题、购买阶段与内容目标；换场景后切入点与卖点排序随之改变，不是套模板。</p></div>
  <div class="f-card"><div class="f-icon">02 / FACT</div><h4>知识库驱动</h4>
  <p>产品事实与图片来自ima共享知识库（同源本地兜底），型号精确匹配，每条声明可追溯来源。</p></div>
  <div class="f-card"><div class="f-icon">03 / VERIFY</div><h4>三重核验</h4>
  <p>事实核验 + 图片型号核验 + 营销合规检查；绝对化用语、价格误导、型号混淆自动拦截。</p></div>
</div>
<div class="info-strip">👈 在上方「任务工作台」填写任务，然后点击 <b>🚀 生成图文软文</b>；
首次使用请先在左侧「MODEL · 模型与凭证」选择模型并填入 API Key。</div>
""", unsafe_allow_html=True)
else:
    task, content = result.task, result.content

    # ---------- 执行过程 ----------
    st.markdown('<div class="sec-head"><h3>执行过程追踪</h3><span>EXECUTION TRACE</span></div>',
                unsafe_allow_html=True)
    if result.trace:
        items = []
        for i, step in enumerate(result.trace.steps):
            icon = {"ok": "✅", "warn": "⚠️", "error": "❌", "skipped": "⏭️"}.get(step.status, "✅")
            cls = {"warn": "warn", "error": "error"}.get(step.status, "")
            ms = f'<span class="ms">{step.duration_ms}ms</span>' if step.duration_ms else ""
            items.append(
                f'<div class="tl-item {cls}" style="animation-delay:{i * 0.05:.2f}s">'
                f'<div class="tl-name">{icon} {step.step}{ms}</div>'
                f'<div class="tl-detail">{step.detail or ""}</div></div>')
        st.markdown(f'<div class="timeline">{"".join(items)}</div>', unsafe_allow_html=True)

    tab_strategy, tab_content, tab_check, tab_export = st.tabs(
        ["📊 场景与策略", "📄 图文软文", "✅ 核验结果", "📤 导出与修改"])

    # ---------- 策略 ----------
    with tab_strategy:
        st.markdown('<div class="sec-head"><h3>一、场景判断</h3><span>SCENE</span></div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f'<div class="info-strip">🎯 目标人群 <b>{task.target_audience}</b>｜场景 <b>{task.scenario}</b><br>'
                f'📱 平台 <b>{task.platform.value}</b></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(
                f'<div class="info-strip">💻 产品 <b>{task.product}</b><br>'
                f'📚 依据 <b>{agent.source_label(result.knowledge_source)}</b></div>',
                unsafe_allow_html=True)
        st.markdown("**人群分析**")
        st.json(result.strategy.audience_analysis, expanded=False)
        st.markdown("**内容策略**")
        st.json(result.strategy.content_strategy, expanded=False)
        st.markdown("**平台适配**")
        st.json(result.strategy.platform_adaptation, expanded=False)

    # ---------- 内容 ----------
    with tab_content:
        st.markdown(f'<div class="article-title">{content.title}</div>', unsafe_allow_html=True)
        if content.intro:
            st.markdown(f'<div class="article-intro">{content.intro}</div>', unsafe_allow_html=True)
        if content.poster_lines:
            st.markdown(f"**主标题**：{content.poster_lines.get('main_title', '')}")
            st.markdown(f"**副标题**：{content.poster_lines.get('subtitle', '')}")
            for sp in content.poster_lines.get("selling_points", []):
                st.markdown(f"- {sp}")
            if content.poster_lines.get("activity_note"):
                st.info(content.poster_lines["activity_note"])
        body_html = "".join(
            f"<p>{sec.content}"
            + (f'<br><span class="fact-ref">依据：{"、".join(sec.supporting_facts)}</span>'
               if sec.supporting_facts else "")
            + "</p>"
            for sec in content.body)
        st.markdown(f'<div class="article-body">{body_html}</div>', unsafe_allow_html=True)
        if content.hashtags:
            st.markdown("".join(f'<span class="tag">{t}</span>' for t in content.hashtags),
                        unsafe_allow_html=True)
        st.markdown(f'<div class="cta-box">💡 {content.cta}</div>', unsafe_allow_html=True)

        st.markdown('<div class="sec-head"><h3>配图方案</h3><span>IMAGE PLAN</span></div>',
                    unsafe_allow_html=True)
        by_id = {img.image_id: img for img in result.images}
        for p in content.image_placements:
            img = by_id.get(p.image_id)
            src = _img_src(img)
            img_tag = f'<img src="{src}" alt="{p.image_id}">' if src else '<div class="img-card">（无预览）</div>'
            st.markdown(
                f'<div class="img-card">{img_tag}<div class="img-meta">'
                f'<b>{img.file_name if img else p.image_id}</b>（{p.image_id}）<br>'
                f'来源：{p.source or (img.source_page if img else "—")}<br>'
                f'插入位置：{p.position}<br>'
                f'说明：{p.caption}<br>'
                f'理由：{p.reason}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="sec-head"><h3>知识库依据</h3><span>EVIDENCE</span></div>',
                    unsafe_allow_html=True)
        for f in result.facts:
            with st.expander(f"[{f.fact_id}] {f.content[:40]}..."):
                st.write(f.content)
                st.caption(f"来源：{f.source_title}｜{f.source_path}")

    # ---------- 核验 ----------
    with tab_check:
        fc, ic, cp = result.fact_check, result.image_check, result.compliance
        st.markdown(f"""
<div class="verdict-row">
  <div class="verdict"><div class="k">FACT CHECK</div>
    <div class="v {'pass' if fc.is_verified else 'fail'}">{'通过' if fc.is_verified else '未通过'}</div>
    <div class="s">置信度 {fc.confidence_score:.2f}</div></div>
  <div class="verdict"><div class="k">IMAGE CHECK</div>
    <div class="v {'pass' if ic.is_consistent else 'fail'}">{'通过' if ic.is_consistent else '未通过'}</div>
    <div class="s">核验 {len(ic.checked_images)} 张</div></div>
  <div class="verdict"><div class="k">COMPLIANCE</div>
    <div class="v {'pass' if cp.is_compliant else 'fail'}">{'通过' if cp.is_compliant else '未通过'}</div>
    <div class="s">风险等级 {cp.risk_level}</div></div>
</div>""", unsafe_allow_html=True)

        for name, violations in (("事实核验问题", fc.violations),
                                 ("图片核验问题", ic.violations),
                                 ("合规问题", cp.violations)):
            if violations:
                st.markdown(f"**{name}**")
                for v in violations:
                    low = "low" if v.severity in ("low", "medium") else ""
                    st.markdown(
                        f'<div class="violation {low}"><b>[{v.severity}]</b> {v.location}'
                        f'「{v.matched_text}」 {v.issue}'
                        + (f'<br>建议：{v.correction_suggestion}' if v.correction_suggestion else "")
                        + "</div>", unsafe_allow_html=True)
        if fc.unverified_items:
            st.markdown("**待确认信息**")
            for item in fc.unverified_items:
                st.markdown(f"- {item}")

    # ---------- 导出与修改 ----------
    with tab_export:
        markdown_text = agent.export_markdown(result)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📥 下载统一输出格式（Markdown）", markdown_text,
                               file_name=f"{task.product}_{task.platform.value}_{task.target_audience}.md",
                               mime="text/markdown", use_container_width=True)
        with c2:
            st.download_button("📥 下载完整JSON（含核验与来源）", agent.export_json(result),
                               file_name=f"{task.task_id}.json", mime="application/json",
                               use_container_width=True)
        st.code(markdown_text, language="markdown")

        st.divider()
        st.markdown('<div class="sec-head"><h3>临时修改并重新生成</h3><span>REGENERATE</span></div>',
                    unsafe_allow_html=True)
        modification = st.text_input("修改要求", placeholder="如：删掉第二段 / 换成公众号 / 换成突出屏幕")
        if st.button("重新生成", type="primary"):
            if not modification.strip():
                st.warning("请输入修改要求")
            else:
                with st.spinner("按修改要求重新生成..."):
                    st.session_state["result"] = agent.regenerate(result, modification)
                st.rerun()

# ============================================================
# 可选模块：产品数据增强（默认关闭，模块化隔离，不影响主流程）
# ============================================================
if st.session_state.get("enrich_enabled"):
    from agent.enrich.ui import render_enrich_module
    render_enrich_module()
