"""LLM客户端：OpenAI兼容接口（OpenAI / DeepSeek / 通义等）"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from openai import OpenAI

from . import config


class LLMError(RuntimeError):
    """LLM调用失败"""


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None, timeout: float = 120.0):
        self.api_key = api_key or config.LLM_API_KEY
        self.base_url = base_url or config.LLM_BASE_URL
        self.model = model or config.LLM_MODEL
        if not self.api_key:
            raise LLMError("未配置 LLM_API_KEY，请在 .env 中填写 OpenAI 兼容接口凭证")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=timeout)

    def generate(self, prompt: str, system: Optional[str] = None,
                 temperature: float = 0.7, json_mode: bool = False) -> str:
        messages: List[Dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"LLM调用失败: {e}") from e
        content = resp.choices[0].message.content or ""
        return content

    def generate_json(self, prompt: str, system: Optional[str] = None,
                      temperature: float = 0.5) -> Dict:
        """生成并解析JSON；解析失败时剥离代码块重试一次"""
        raw = self.generate(prompt, system=system, temperature=temperature, json_mode=True)
        try:
            return _extract_json(raw)
        except ValueError:
            retry_prompt = f"{prompt}\n\n注意：只输出一个合法的JSON对象，不要输出任何其他文字或代码块标记。"
            raw = self.generate(retry_prompt, system=system, temperature=temperature, json_mode=False)
            return _extract_json(raw)


def _extract_json(text: str) -> Dict:
    """从模型输出中稳健提取JSON对象"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("输出中未找到JSON对象")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}") from e
