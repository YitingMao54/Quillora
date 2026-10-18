"""主流LLM厂商/模型目录（全部为OpenAI兼容接口）

前端模型选择下拉与专属API Key配置据此渲染；选择厂商后自动带出Base URL。
"""
from __future__ import annotations

from typing import Dict, List

PROVIDERS: Dict[str, Dict] = {
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-5.6", "gpt-5.5", "gpt-5.1-mini", "gpt-4.1"],
        "note": "2026旗舰 GPT-5.6，通用能力最强",
    },
    "DeepSeek 深度求索": {
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro", "deepseek-v4-flash"],
        "note": "V4系列；deepseek-chat 恒指向最新版",
    },
    "通义千问（阿里百炼）": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.8-max", "qwen3.7-max", "qwen-plus", "qwen-long"],
        "note": "Qwen3.8/3.7 旗舰系列",
    },
    "智谱 GLM": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.3", "glm-5.1", "glm-4.7", "glm-4-air"],
        "note": "GLM-5.3 旗舰（2026-08发布）",
    },
    "Kimi（月之暗面）": {
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3", "kimi-latest", "moonshot-v1-128k"],
        "note": "K3 旗舰，长上下文见长",
    },
    "豆包（火山方舟）": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-seed-2.1-pro", "doubao-seed-2.1-lite", "doubao-seed-evolving"],
        "note": "Seed 2.1 旗舰（2026-09发布）",
    },
    "文心（百度千帆）": {
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-5.0-turbo", "ernie-4.5-turbo", "ernie-x1-pro"],
        "note": "文心5.0系列",
    },
    "MiniMax": {
        "base_url": "https://api.minimax.chat/v1",
        "models": ["MiniMax-M3", "MiniMax-Text-02", "abab6.5s-chat"],
        "note": "M3 旗舰（2026）",
    },
    "自定义（OpenAI兼容）": {
        "base_url": "",
        "models": [],
        "note": "任意OpenAI兼容服务，手动填写Base URL与模型名",
    },
}


def provider_names() -> List[str]:
    return list(PROVIDERS.keys())


def models_of(provider: str) -> List[str]:
    return list(PROVIDERS.get(provider, {}).get("models", []))


def base_url_of(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("base_url", "")


def note_of(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("note", "")
