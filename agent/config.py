"""配置管理：所有密钥经环境变量注入，不写入源码"""
import os
from pathlib import Path
from typing import Union

from dotenv import load_dotenv

# 加载项目根目录下的 .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ===== LLM（OpenAI兼容接口） =====
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

# ===== ima OpenAPI =====
IMA_CLIENT_ID = os.getenv("IMA_OPENAPI_CLIENTID", "")
IMA_API_KEY = os.getenv("IMA_OPENAPI_APIKEY", "")
IMA_KNOWLEDGE_BASE_NAME = os.getenv("IMA_KNOWLEDGE_BASE_NAME", "任德耀新建华为PC知识库")
IMA_BASE_URL = os.getenv("IMA_BASE_URL", "https://ima.qq.com")

# ===== 本地知识库兜底 =====
def _resolve_local_kb_root() -> Path:
    """定位 P1-P8 知识库根目录

    优先级：LOCAL_KB_ROOT 环境变量 → 项目上级目录（开发时的实时知识库）
    → 仓库内置的 knowledge-base/（随仓库分发的公开快照）。
    这样单独克隆仓库也能直接跑，本地开发则始终读最新知识库。
    """
    env = os.getenv("LOCAL_KB_ROOT", "").strip()
    if env:
        p = Path(env).expanduser()
        return (PROJECT_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    external = PROJECT_ROOT.parent
    if (external / "P1-产品参数库").is_dir():
        return external
    bundled = PROJECT_ROOT / "knowledge-base"
    if (bundled / "P1-产品参数库").is_dir():
        return bundled
    return external


LOCAL_KB_ROOT = _resolve_local_kb_root()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def ima_configured() -> bool:
    """是否已配置ima接口凭证"""
    return bool(IMA_CLIENT_ID and IMA_API_KEY)


def llm_configured() -> bool:
    """是否已配置LLM接口凭证"""
    return bool(LLM_API_KEY)


def mask_secret(secret: str) -> Union[bool, str]:
    """脱敏展示密钥：只显示是否存在，不显示完整内容"""
    if not secret:
        return False
    return f"{secret[:3]}***{secret[-2:]}" if len(secret) > 8 else "***"


# 前端填写入口 -> 模块全局变量 / 环境变量名 的映射
_OVERRIDE_FIELDS = {
    "LLM_API_KEY": "LLM_API_KEY",
    "LLM_BASE_URL": "LLM_BASE_URL",
    "LLM_MODEL": "LLM_MODEL",
    "IMA_CLIENT_ID": "IMA_OPENAPI_CLIENTID",
    "IMA_API_KEY": "IMA_OPENAPI_APIKEY",
}


def apply_overrides(**kwargs) -> None:
    """应用前端填写的凭证/配置（只接受映射内的字段，空值表示不覆盖）"""
    g = globals()
    for key, env_name in _OVERRIDE_FIELDS.items():
        value = kwargs.get(key)
        if value:
            g[key] = value
            os.environ[env_name] = value


def save_dotenv(**kwargs) -> None:
    """把凭证持久化到本地 .env（已被 .gitignore 排除，不会进入仓库）"""
    env_path = PROJECT_ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for key, env_name in _OVERRIDE_FIELDS.items():
        value = kwargs.get(key)
        if not value:
            continue
        new_line = f"{env_name}={value}"
        replaced = False
        for i, line in enumerate(lines):
            if line.split("=", 1)[0].strip() == env_name:
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
