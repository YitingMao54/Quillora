"""ima OpenAPI 客户端

按官方 ima-skill（ima_api.cjs + knowledge-base/references/api.md）的接口约定封装：
A search_knowledge_base  按名称查找知识库（SearchedKnowledgeBaseInfo：id/name）
B get_knowledge_list     浏览目录（knowledge_list / next_cursor / is_end，搜索为空时回退）
C search_knowledge       按产品型号和任务搜索资料（info_list：media_id/title/highlight_content）
D get_media_info         按 media_id 获取原文或访问链接

认证头（与官方 ima_api.cjs 一致）：
  ima-openapi-clientid / ima-openapi-apikey / ima-openapi-ctx: skill_version=...
响应包装：{"code": 0, "msg": "success", "data": {...}}，code≠0 时直接采用 msg。

凭证（IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY）仅从环境变量读取，
不得写入源码、仓库、截图或演示画面。
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Dict, List, Optional

import httpx

from . import config

SKILL_VERSION = "1.1.10"

# 响应缓存：知识库内容在比赛期间相对静态，缓存可显著节省接口配额
_CACHE_PATH = config.PROJECT_ROOT / "data" / "cache" / "ima_cache.json"
_MEDIA_TTL = 1800          # get_media_info 的临时访问链接缓存30分钟
_OTHERS_TTL = None         # 目录/检索结果长期缓存（知识库静态）


class ImaAPIError(RuntimeError):
    """ima接口调用失败"""


class ImaQuotaExceeded(ImaAPIError):
    """ima接口当日资料获取次数已达上限"""


class ImaClient:
    def __init__(self, client_id: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, timeout: float = 20.0):
        self.client_id = client_id or config.IMA_CLIENT_ID
        self.api_key = api_key or config.IMA_API_KEY
        self.base_url = (base_url or config.IMA_BASE_URL).rstrip("/")
        self.timeout = timeout

    @property
    def headers(self) -> Dict[str, str]:
        # 完整密钥不出现在日志/输出中
        return {
            "ima-openapi-clientid": self.client_id,
            "ima-openapi-apikey": self.api_key,
            "ima-openapi-ctx": f"skill_version={SKILL_VERSION}",
            "Content-Type": "application/json",
        }

    # ---------- 响应缓存（节省接口配额） ----------

    @staticmethod
    def _cache_key(path: str, payload: Dict) -> str:
        raw = f"{path}|{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _cache_load() -> Dict:
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _cache_save(cache: Dict) -> None:
        try:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass  # 缓存写入失败不影响主流程

    def _post(self, path: str, payload: Dict, cache_ttl: Optional[int] = _OTHERS_TTL) -> Dict:
        key = self._cache_key(path, payload)
        cache = self._cache_load()
        entry = cache.get(key)
        if entry and (cache_ttl is None or time.time() - entry.get("at", 0) < cache_ttl):
            return entry["data"]

        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise ImaAPIError(f"ima接口返回异常: HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise ImaAPIError(f"ima接口连接失败: {e}") from e

        if not isinstance(data, dict):
            raise ImaAPIError("ima接口返回格式异常")
        code = data.get("code", data.get("ret", 0))
        if code not in (0, "0", None):
            msg = data.get("msg", "")
            if code in (220021, "220021"):
                raise ImaQuotaExceeded(f"ima接口配额已用尽：{msg}")
            raise ImaAPIError(f"ima接口业务错误: code={code} msg={msg}")

        result = data.get("data", {}) or {}
        cache[key] = {"at": time.time(), "data": result}
        self._cache_save(cache)
        return result

    # ---------- A. 查找知识库 ----------

    def search_knowledge_base(self, query: str, limit: int = 20) -> List[Dict]:
        data = self._post("openapi/wiki/v1/search_knowledge_base",
                          {"query": query, "cursor": "", "limit": limit})
        items = data.get("info_list", []) or []
        # 文档字段为 id/name，实测可能为 kb_id/kb_name，统一归一化
        normalized = []
        for item in items:
            normalized.append({
                "id": item.get("id") or item.get("kb_id") or "",
                "name": item.get("name") or item.get("kb_name") or "",
                "raw": item,
            })
        return normalized

    def find_knowledge_base(self, name: str) -> str:
        """按名称查找知识库，返回kb_id"""
        infos = self.search_knowledge_base(name)
        for item in infos:
            if item["name"] == name or name in item["name"]:
                return item["id"]
        if infos and infos[0]["id"]:
            return infos[0]["id"]
        raise ImaAPIError(f"找不到知识库: {name}")

    # ---------- B. 浏览目录 ----------

    def get_knowledge_list(self, kb_id: str, cursor: str = "", limit: int = 20,
                           folder_id: str = "") -> Dict:
        """浏览知识库目录；搜索为空时必须用此接口回退"""
        payload = {"knowledge_base_id": kb_id, "cursor": cursor, "limit": limit}
        if folder_id:
            payload["folder_id"] = folder_id
        return self._post("openapi/wiki/v1/get_knowledge_list", payload)

    def browse_catalog(self, kb_id: str, limit: int = 50,
                       max_folders: int = 60) -> List[Dict]:
        """递归浏览知识库目录（文件夹节点 media_id 以 folder_ 开头，需继续下钻）"""
        items: List[Dict] = []
        queue: List[str] = [""]           # 待访问 folder_id，"" = 根目录
        folders_visited = 0
        while queue and len(items) < limit and folders_visited < max_folders:
            folder_id = queue.pop(0)
            folders_visited += 1
            cursor = ""
            while True:
                data = self.get_knowledge_list(kb_id, cursor=cursor, limit=50,
                                               folder_id=folder_id)
                batch = data.get("knowledge_list", []) or []
                for it in batch:
                    media_id = it.get("media_id", "") or ""
                    if media_id.startswith("folder_"):
                        queue.append(media_id)
                    items.append(it)
                    if len(items) >= limit:
                        return items
                if data.get("is_end") or not batch:
                    break
                cursor = data.get("next_cursor", "") or ""
                if not cursor:
                    break
        return items[:limit]

    # ---------- C. 搜索资料 ----------

    def search_knowledge(self, kb_id: str, query: str, limit: int = 10) -> List[Dict]:
        items: List[Dict] = []
        cursor = ""
        while len(items) < limit:
            data = self._post("openapi/wiki/v1/search_knowledge",
                              {"knowledge_base_id": kb_id, "query": query,
                               "cursor": cursor, "limit": limit})
            batch = data.get("info_list", []) or []
            items.extend(batch)
            if data.get("is_end") or not batch:
                break
            cursor = data.get("next_cursor", "") or ""
            if not cursor:
                break
        return items[:limit]

    # ---------- D. 获取资料原文/媒体 ----------

    def get_media_info(self, media_id: str) -> Dict:
        return self._post("openapi/wiki/v1/get_media_info", {"media_id": media_id},
                          cache_ttl=_MEDIA_TTL)

    # ---------- 连接自检（界面展示用） ----------

    def health_check(self) -> Dict:
        """核查知识库名称、连接状态和接口返回；不含完整密钥。

        为节省接口配额，不做全量目录遍历：目录数在已缓存时展示，
        并用一次轻量检索确认内容可读。
        """
        result = {"configured": bool(self.client_id and self.api_key),
                  "kb_name": config.IMA_KNOWLEDGE_BASE_NAME,
                  "connected": False, "kb_id": "", "item_count": 0,
                  "item_count_source": "未统计", "error": ""}
        if not result["configured"]:
            result["error"] = "未配置 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY"
            return result
        try:
            kb_id = self.find_knowledge_base(config.IMA_KNOWLEDGE_BASE_NAME)
            result["kb_id"] = kb_id
            self.search_knowledge(kb_id, "产品", limit=1)   # 轻量探活
            result["connected"] = True
            cached = self._cache_load()
            result["item_count"] = sum(
                1 for e in cached.values()
                if isinstance(e.get("data"), dict) and e["data"].get("knowledge_list"))
            result["item_count_source"] = "缓存统计" if cached else "未遍历（节省配额）"
        except ImaQuotaExceeded as e:
            result["error"] = f"{e}（已缓存结果仍可使用）"
            result["connected"] = bool(result["kb_id"])
        except ImaAPIError as e:
            result["error"] = str(e)
        return result
