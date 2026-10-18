"""Agent主管线

标准流程（赛题四·二）：
场景解析 → 平台策略 → ima资料与图片检索 → 事实点提取 → 图文编排 → 软文生成
→ 事实与图片核验 → 合规检查 → 导出
"""
from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional

from . import compliance, prompts
from .knowledge import SOURCE_LABELS, KnowledgeSource
from .llm_client import LLMClient
from .models import (
    ComplianceResult, Content, ContentResult, ContentSection, ExecutionTrace,
    Fact, FactCheckResult, ImageAsset, ImageCheckResult, ImagePlacement,
    Platform, Strategy, Task, TaskParseResult, TaskStatus, Violation,
)

# 平台图片数量要求（赛题三·三）
PLATFORM_IMAGE_RANGE = {
    Platform.WECHAT_ARTICLE: (2, 4),
    Platform.XIAOHONGSHU: (3, 6),
    Platform.WECHAT_MOMENT: (1, 3),
    Platform.STORE_POSTER: (1, 1),
}

PLATFORM_KEYWORDS = {
    "公众号": Platform.WECHAT_ARTICLE,
    "小红书": Platform.XIAOHONGSHU,
    "朋友圈": Platform.WECHAT_MOMENT,
    "门店朋友圈": Platform.WECHAT_MOMENT,
    "海报": Platform.STORE_POSTER,
    "门店海报": Platform.STORE_POSTER,
}

AUDIENCE_KEYWORDS = ["大学新生", "学生", "家长", "职场", "商务", "出差", "创作者", "设计",
                     "摄影", "视频", "家庭", "换新", "企业", "采购", "团队", "门店"]


class TaskError(ValueError):
    """任务无法执行（型号歧义/信息不全），携带追问文案"""


def _fill(template: str, **kwargs: str) -> str:
    """填充提示词占位符（__TOKEN__），避免与JSON花括号冲突"""
    for key, value in kwargs.items():
        template = template.replace(f"__{key.upper()}__", str(value))
    return template


class MarketingAgent:
    """华为PC营销软文智能体"""

    def __init__(self, llm: Optional[LLMClient] = None,
                 knowledge: Optional[KnowledgeSource] = None):
        self._llm = llm
        self.knowledge = knowledge or KnowledgeSource()
        self.kb_status: Dict = {}

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    # ==================================================
    # 初始化：账号与知识库连接
    # ==================================================

    def initialize(self, source_mode: str = "auto") -> Dict:
        """识别当前账号配置、连接指定共享知识库；返回脱敏状态

        source_mode: auto（ima优先）/ ima（强制在线）/ local（仅本地数据）
        """
        from . import config
        self.kb_status = self.knowledge.initialize(source_mode)
        return {
            "llm": {
                "configured": config.llm_configured(),
                "base_url": config.LLM_BASE_URL,
                "model": config.LLM_MODEL,
                "key_masked": config.mask_secret(config.LLM_API_KEY),
            },
            "ima": {
                "configured": config.ima_configured(),
                "kb_name": config.IMA_KNOWLEDGE_BASE_NAME,
                "source": self.kb_status.get("source"),
                "reason": self.kb_status.get("reason"),
                "mode": self.kb_status.get("mode"),
                "key_masked": config.mask_secret(config.IMA_API_KEY),
                "client_id_masked": config.mask_secret(config.IMA_CLIENT_ID),
            },
            "knowledge": self.kb_status,
        }

    @staticmethod
    def source_label(knowledge_source: str) -> str:
        """把来源标记（如 ima+local / ima,local）转为可读标签"""
        parts = [p for p in re.split(r"[,+|、\s]+", knowledge_source or "") if p]
        return " + ".join(SOURCE_LABELS.get(s, s) for s in parts) or "—"

    # ==================================================
    # 1. 任务解析与追问
    # ==================================================

    def _candidate_models(self, user_input: str) -> List[str]:
        text = user_input.lower().replace(" ", "")
        tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", text) if len(t) >= 3]
        hits = []
        for model in self.knowledge.local.list_models():
            key = model.lower().replace(" ", "").replace("华为", "").replace("huawei", "")
            if not key:
                continue
            if key in text or text in key or any(t in key for t in tokens):
                hits.append(model)
        return hits

    def parse_task(self, user_input: str) -> TaskParseResult:
        """解析自然语言任务；信息不足时生成追问"""
        candidates = self._candidate_models(user_input)
        try:
            data = self.llm.generate_json(
                _fill(prompts.TASK_PARSE_PROMPT,
                      user_input=user_input,
                      candidates=json.dumps(candidates, ensure_ascii=False)),
                system=prompts.SYSTEM_PROMPT,
                temperature=0.2,
            )
        except Exception:
            data = self._parse_task_fallback(user_input, candidates)

        status = data.get("status", "INCOMPLETE")
        parsed = data.get("parsed_task") or {}
        matched = data.get("matched_candidate") or parsed.get("product") or ""

        # 型号归一化到知识库精确型号
        model = ""
        if matched:
            resolved = self.knowledge.resolve_model(matched)
            model = resolved[0] if len(resolved) == 1 else matched

        if status == "AMBIGUOUS" or (matched and not model):
            return TaskParseResult(
                status=TaskStatus.AMBIGUOUS,
                follow_up_question=data.get("follow_up_question") or
                f"知识库中有多个相近型号：{candidates}，请确认具体型号。",
                candidates=candidates,
            )

        if status == "COMPLETE" and parsed:
            try:
                task = Task(
                    product=model or parsed.get("product", ""),
                    target_audience=parsed.get("target_audience", ""),
                    scenario=parsed.get("scenario"),
                    platform=Platform(parsed.get("platform")),
                    content_goal=parsed.get("content_goal"),
                    special_requirements=parsed.get("special_requirements") or [],
                )
                return TaskParseResult(status=TaskStatus.COMPLETE, parsed_task=task)
            except Exception:
                status = "INCOMPLETE"

        return TaskParseResult(
            status=TaskStatus.INCOMPLETE,
            missing_fields=data.get("missing_fields") or [],
            follow_up_question=data.get("follow_up_question") or
            "请补充：产品型号、目标人群、使用场景和发布平台。",
        )

    def _parse_task_fallback(self, user_input: str, candidates: List[str]) -> Dict:
        """无LLM时的规则解析兜底"""
        missing = []
        platform = ""
        for kw, p in PLATFORM_KEYWORDS.items():
            if kw in user_input:
                platform = p.value
                break
        if not platform:
            missing.append("platform")
        audience = next((a for a in AUDIENCE_KEYWORDS if a in user_input), "")
        if not audience:
            missing.append("target_audience")
        if len(candidates) != 1:
            missing.append("product")
        if missing:
            return {
                "status": "INCOMPLETE",
                "missing_fields": missing,
                "follow_up_question": f"为了生成内容，请补充：{', '.join(missing)}（平台可选公众号/小红书/门店朋友圈/门店海报）。",
            }
        return {
            "status": "COMPLETE",
            "parsed_task": {
                "product": candidates[0], "target_audience": audience,
                "scenario": None, "platform": platform,
                "content_goal": None, "special_requirements": [],
            },
        }

    # ==================================================
    # 2. 主执行流程
    # ==================================================

    def execute(self, task: Task) -> ContentResult:
        trace = ExecutionTrace(task_id=task.task_id)

        # --- 步骤1：场景解析（含型号归一化） ---
        t0 = time.perf_counter()
        resolved = self.knowledge.resolve_model(task.product)
        if len(resolved) != 1:
            raise TaskError(
                f"型号「{task.product}」无法唯一定位（候选：{resolved or '无'}），"
                f"请提供更精确的型号后重新生成。")
        task.product = resolved[0]
        trace.add("场景解析", detail=f"型号归一化为「{task.product}」；人群={task.target_audience}；"
                  f"场景={task.scenario}；平台={task.platform.value}",
                  duration_ms=int((time.perf_counter() - t0) * 1000))

        # --- 步骤2：平台策略 ---
        t0 = time.perf_counter()
        business_docs = self.knowledge.search_business_docs(
            task.target_audience, task.scenario or "", task.product)
        business_digest = "\n".join(
            f"- 《{d['title']}》：{d['excerpt'][:200]}" for d in business_docs) or "（无）"
        spec_preview = self.knowledge.search_facts(task.product, "屏幕 性能 续航 重量 接口", limit=3)
        strategy_data = self.llm.generate_json(
            _fill(prompts.STRATEGY_PROMPT,
                  task=prompts.format_task(task),
                  facts_digest=prompts.format_facts(spec_preview),
                  business_digest=business_digest),
            system=prompts.SYSTEM_PROMPT,
            temperature=0.5,
        )
        strategy = Strategy(
            audience_analysis=strategy_data.get("audience_analysis", {}),
            content_strategy=strategy_data.get("content_strategy", {}),
            platform_adaptation=strategy_data.get("platform_adaptation", {}),
        )
        trace.add("平台策略", detail=f"切入点：{strategy.content_strategy.get('angle', '')}",
                  duration_ms=int((time.perf_counter() - t0) * 1000))

        # --- 步骤3：ima资料与图片检索 ---
        t0 = time.perf_counter()
        query = f"{task.target_audience} {task.scenario or ''} {strategy.content_strategy.get('angle', '')}"
        facts = self.knowledge.search_facts(task.product, query, limit=10)
        images = self.knowledge.search_images(task.product, query, limit=8)
        # 来源标注按"实际命中"而非"配置项"生成，避免把兜底数据标成ima
        actual_source = self._actual_source(facts)
        source_note = self.source_label(actual_source)
        trace.add("资料与图片检索", status="ok" if facts else "warn",
                  detail=f"来源：{source_note}；事实点{len(facts)}条；图片{len(images)}张",
                  duration_ms=int((time.perf_counter() - t0) * 1000),
                  facts=len(facts), images=len(images))

        # --- 步骤4：事实点提取 ---
        trace.add("事实点提取", detail="已建立事实点ID（F编号）与来源映射，供生成引用与核验",
                  facts=[f.fact_id for f in facts])

        # --- 步骤5：图文编排与软文生成 ---
        t0 = time.perf_counter()
        content_data = self.llm.generate_json(
            _fill(prompts.CONTENT_PROMPT,
                  platform=task.platform.value,
                  strategy=json.dumps(strategy_data, ensure_ascii=False),
                  facts=prompts.format_facts(facts),
                  images=prompts.format_images(images),
                  task=prompts.format_task(task)),
            system=prompts.SYSTEM_PROMPT,
            temperature=0.7,
        )
        content = _parse_content(content_data)
        trace.add("图文软文生成", detail=f"标题：{content.title}",
                  duration_ms=int((time.perf_counter() - t0) * 1000),
                  paragraphs=len(content.body), images_planned=len(content.image_placements))

        # --- 步骤6：图片核验 ---
        t0 = time.perf_counter()
        image_check = self._check_images(content, images, task)
        trace.add("图片型号核验",
                  status="ok" if image_check.is_consistent else "warn",
                  detail=f"核验{len(image_check.checked_images)}张；"
                         f"问题{len(image_check.violations)}项",
                  duration_ms=int((time.perf_counter() - t0) * 1000))

        # --- 步骤7：事实核验 ---
        t0 = time.perf_counter()
        fact_check = self._check_facts(content, facts, task)
        trace.add("事实核验",
                  status="ok" if fact_check.is_verified else "warn",
                  detail=f"置信度{fact_check.confidence_score:.2f}；"
                         f"无依据/待确认{len(fact_check.violations) + len(fact_check.unverified_items)}项",
                  duration_ms=int((time.perf_counter() - t0) * 1000))

        # --- 步骤8：合规检查 ---
        t0 = time.perf_counter()
        compliance_result = self._check_compliance(content, task)
        trace.add("合规检查",
                  status="ok" if compliance_result.is_compliant else "warn",
                  detail=f"风险等级：{compliance_result.risk_level}；"
                         f"命中{len(compliance_result.violations)}项",
                  duration_ms=int((time.perf_counter() - t0) * 1000))

        # --- 步骤9：导出 ---
        trace.add("导出", detail="已生成统一输出格式Markdown与JSON",
                  knowledge_source=source_note)

        return ContentResult(
            task=task, strategy=strategy, facts=facts, images=images,
            content=content, fact_check=fact_check, image_check=image_check,
            compliance=compliance_result,
            knowledge_source=actual_source,
            trace=trace,
        )

    def _actual_source(self, facts: List[Fact]) -> str:
        """按事实点来源路径判定实际数据来源（http=ima在线，本地路径=本地同源）"""
        if not facts:
            return self.knowledge.active
        online = any(f.source_path.startswith("http") for f in facts)
        offline = any(not f.source_path.startswith("http") for f in facts)
        if online and offline:
            return "ima+local"
        return "ima" if online else "local"

    # ==================================================
    # 核验
    # ==================================================

    def _check_images(self, content: Content, images: List[ImageAsset],
                      task: Task) -> ImageCheckResult:
        """图片核验：来源存在、型号一致、数量符合平台、说明完整"""
        by_id = {img.image_id: img for img in images}
        low, high = PLATFORM_IMAGE_RANGE.get(task.platform, (0, 9))
        violations: List[Violation] = []
        checked: List[Dict] = []

        for place in content.image_placements:
            img = by_id.get(place.image_id)
            if img is None:
                violations.append(Violation(
                    rule_category="image_missing", location=place.position,
                    matched_text=place.image_id,
                    issue=f"引用的图片 {place.image_id} 不在检索结果中",
                    severity="critical", action="must_remove",
                    correction_suggestion="从检索到的图片中重新选择"))
                continue
            checked.append({"image_id": place.image_id, "file_name": img.file_name,
                            "model": img.product_model, "position": place.position})
            if img.product_model and img.product_model != task.product:
                violations.append(Violation(
                    rule_category="image_mismatch", location=place.position,
                    matched_text=img.file_name,
                    issue=f"图片型号「{img.product_model}」与任务型号「{task.product}」不一致",
                    severity="critical", action="must_remove",
                    correction_suggestion="更换为任务型号的图片"))
            if not place.caption or not place.source:
                violations.append(Violation(
                    rule_category="image_meta_missing", location=place.position,
                    matched_text=img.file_name,
                    issue="图片缺少说明或来源",
                    severity="medium", action="must_correct",
                    correction_suggestion="补充图片来源与图片说明"))

        count = len(content.image_placements)
        if count < low:
            violations.append(Violation(
                rule_category="image_count", location="全文", matched_text=f"{count}张",
                issue=f"{task.platform.value}要求{low}-{high}张图，当前{count}张",
                severity="high", action="must_correct",
                correction_suggestion=f"补充到{low}-{high}张型号一致的图片"))
        elif count > high:
            violations.append(Violation(
                rule_category="image_count", location="全文", matched_text=f"{count}张",
                issue=f"{task.platform.value}要求{low}-{high}张图，当前{count}张",
                severity="high", action="must_correct",
                correction_suggestion=f"精简到{low}-{high}张"))

        return ImageCheckResult(
            is_consistent=not any(v.severity == "critical" for v in violations),
            violations=violations, checked_images=checked)

    def _check_facts(self, content: Content, facts: List[Fact],
                     task: Task) -> FactCheckResult:
        """事实核验：LLM逐项核对 + 型号混淆规则检查"""
        try:
            data = self.llm.generate_json(
                _fill(prompts.FACT_CHECK_PROMPT,
                      content=_content_to_text(content),
                      facts=prompts.format_facts(facts),
                      product_model=task.product),
                system=prompts.SYSTEM_PROMPT,
                temperature=0.2,
            )
            violations = [_parse_violation(v) for v in data.get("violations", [])]
            unverified = data.get("unverified_items", []) or []
            checked = data.get("checked_claims", []) or []
            confidence = float(data.get("confidence_score", 0.9))
        except Exception as e:
            violations = [Violation(rule_category="fact_check_failed", issue=f"事实核验执行失败: {e}",
                                    severity="high", action="needs_confirmation")]
            unverified, checked, confidence = [], [], 0.5

        # 型号混淆规则检查（防相近型号错配）
        violations += compliance.check_model_confusion(
            content, task.product, self.knowledge.local.list_models())

        critical = [v for v in violations if v.severity in ("critical", "high")]
        return FactCheckResult(
            is_verified=not critical,
            checked_claims=checked,
            violations=violations,
            unverified_items=unverified,
            confidence_score=confidence,
        )

    def _check_compliance(self, content: Content, task: Task) -> ComplianceResult:
        """合规检查：规则引擎 + LLM语义复核"""
        result = compliance.rule_check(content, task.platform.value)
        try:
            data = self.llm.generate_json(
                _fill(prompts.COMPLIANCE_PROMPT,
                      content=_content_to_text(content), platform=task.platform.value),
                system=prompts.SYSTEM_PROMPT,
                temperature=0.2,
            )
            seen = {v.matched_text for v in result.violations}
            for v in data.get("violations", []):
                parsed = _parse_violation(v)
                if parsed.matched_text not in seen:
                    result.violations.append(parsed)
                    seen.add(parsed.matched_text)
            if data.get("risk_level") == "high":
                result.risk_level = "high"
            if data.get("approved_for_publication") is False:
                result.approved_for_publication = False
        except Exception:
            pass  # 规则层结果保留，不因LLM失败而中断

        critical = [v for v in result.violations if v.severity in ("critical", "high")]
        if critical:
            result.is_compliant = False
            result.approved_for_publication = False
            result.risk_level = "high" if any(v.severity == "critical" for v in critical) else "medium"
        return result

    # ==================================================
    # 3. 修改与重新生成
    # ==================================================

    def regenerate(self, result: ContentResult, modification: str) -> ContentResult:
        """根据临时要求（删减/换渠道/替换卖点等）重新生成"""
        task = result.task.model_copy(deep=True)
        task.special_requirements = task.special_requirements + [f"临时修改要求：{modification}"]
        if any(kw in modification for kw in PLATFORM_KEYWORDS):
            for kw, platform in PLATFORM_KEYWORDS.items():
                if kw in modification:
                    task.platform = platform
                    break
        return self.execute(task)

    # ==================================================
    # 4. 导出：统一输出格式
    # ==================================================

    def export_markdown(self, result: ContentResult) -> str:
        """赛题四·四 统一输出格式（字段与题目要求逐项对齐）

        一、场景判断  目标人群 / 使用场景 / 用户问题 / 内容目标 / 平台
        二、知识库依据 产品型号 / 事实点 / 资料标题
        三、图文软文  标题 / 导语 / 正文 / 行动引导；图片名称 / 来源 / 插入位置 / 图片说明
        四、核验结果  产品事实 / 图片型号 / 合规 / 待确认信息
        """
        task, content = result.task, result.content
        lines: List[str] = []
        lines.append("# 华为PC营销图文软文 · 统一输出格式\n")

        # ---------- 一、场景判断 ----------
        lines.append("## 一、场景判断")
        lines.append(f"- 目标人群：{task.target_audience}")
        lines.append(f"- 使用场景：{task.scenario or '（未指定）'}")
        pain = "、".join(result.strategy.audience_analysis.get("pain_points", []) or []) or "—"
        lines.append(f"- 用户问题：{pain}")
        lines.append(f"- 内容目标：{task.content_goal or result.strategy.content_strategy.get('angle') or '—'}")
        lines.append(f"- 平台：{task.platform.value}")
        lines.append("")

        # ---------- 二、知识库依据 ----------
        lines.append("## 二、知识库依据")
        lines.append(f"- 资料来源：{self.source_label(result.knowledge_source)}")
        lines.append(f"- 产品型号：{task.product}")
        lines.append("- 事实点：")
        if result.facts:
            for f in result.facts:
                lines.append(f"  - [{f.fact_id}]（{f.fact_type}）{f.content}")
                lines.append(f"    - 资料标题：{f.source_title}")
                lines.append(f"    - 来源：{f.source_path}")
        else:
            lines.append("  - （无事实点）")
        lines.append("")

        # ---------- 三、图文软文 ----------
        lines.append("## 三、图文软文")
        lines.append(f"- 标题：{content.title}")
        lines.append(f"- 导语：{content.intro or '（无）'}")
        lines.append("- 正文：")
        if content.poster_lines:
            pl = content.poster_lines
            lines.append(f"  - 主标题：{pl.get('main_title', '')}")
            lines.append(f"  - 副标题：{pl.get('subtitle', '')}")
            for sp in pl.get("selling_points", []):
                lines.append(f"  - 卖点：{sp}")
            if pl.get("activity_note"):
                lines.append(f"  - 活动说明：{pl['activity_note']}")
        for sec in content.body:
            lines.append(f"  - {sec.paragraph_id}. {sec.content}")
            if sec.supporting_facts:
                lines.append(f"    - 事实依据：{'、'.join(sec.supporting_facts)}")
        if content.hashtags:
            lines.append(f"  - 平台标签：{' '.join(content.hashtags)}")
        lines.append(f"- 行动引导：{content.cta or '（无）'}")
        lines.append("- 图片：")
        by_id = {img.image_id: img for img in result.images}
        if content.image_placements:
            for p in content.image_placements:
                img = by_id.get(p.image_id)
                lines.append(f"  - 图片名称：{img.file_name if img else p.image_id}（{p.image_id}）")
                lines.append(f"    - 来源：{p.source or (img.source_page if img else '—')}")
                lines.append(f"    - 插入位置：{p.position}")
                lines.append(f"    - 图片说明：{p.caption}" + (f"（{p.reason}）" if p.reason else ""))
        else:
            lines.append("  - （无配图）")
        lines.append("")

        # ---------- 四、核验结果 ----------
        lines.append("## 四、核验结果")
        fc, ic, cp = result.fact_check, result.image_check, result.compliance
        lines.append(f"- 产品事实：{'通过' if fc.is_verified else '未通过'}（置信度 {fc.confidence_score:.2f}）")
        for v in fc.violations:
            lines.append(f"  - [{v.severity}] {v.location}：{v.issue or v.rule_category}")
        lines.append(f"- 图片型号：{'通过' if ic.is_consistent else '未通过'}")
        for v in ic.violations:
            lines.append(f"  - [{v.severity}] {v.location}：{v.issue or v.rule_category}")
        lines.append(f"- 合规：{'通过' if cp.is_compliant else '未通过'}（风险等级 {cp.risk_level}）")
        for v in cp.violations:
            lines.append(f"  - [{v.severity}] {v.location}「{v.matched_text}」：{v.issue or v.rule_category}")
        lines.append("- 待确认信息：")
        if fc.unverified_items:
            for item in fc.unverified_items:
                lines.append(f"  - {item}")
        else:
            lines.append("  - （无）")
        return "\n".join(lines)

    def export_json(self, result: ContentResult) -> str:
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


# ==================================================
# 内部工具
# ==================================================

def _parse_content(data: Dict) -> Content:
    body = []
    for i, sec in enumerate(data.get("body") or [], 1):
        body.append(ContentSection(
            paragraph_id=sec.get("paragraph_id", i),
            content=sec.get("content", ""),
            supporting_facts=sec.get("supporting_facts") or [],
            reasoning=sec.get("reasoning", ""),
        ))
    placements = []
    for p in data.get("image_placements") or []:
        placements.append(ImagePlacement(
            image_id=str(p.get("image_id", "")),
            position=str(p.get("position", "")),
            caption=p.get("caption", ""),
            reason=p.get("reason", ""),
            source=p.get("source", ""),
        ))
    return Content(
        title=data.get("title", ""),
        intro=data.get("intro") or None,
        body=body,
        image_placements=placements,
        cta=data.get("cta", ""),
        hashtags=data.get("hashtags") or [],
        poster_lines=data.get("poster_lines") or None,
    )


def _parse_violation(data: Dict) -> Violation:
    return Violation(
        rule_category=data.get("rule_category", "unknown"),
        location=data.get("location", ""),
        matched_text=data.get("matched_text", ""),
        issue=data.get("issue") or data.get("problem", ""),
        severity=data.get("severity", "medium"),
        action=data.get("action", "needs_confirmation"),
        correction_suggestion=data.get("correction_suggestion", ""),
    )


def _content_to_text(content: Content) -> str:
    parts = [f"标题：{content.title}"]
    if content.intro:
        parts.append(f"导语：{content.intro}")
    for sec in content.body:
        parts.append(f"段落{sec.paragraph_id}：{sec.content}")
    if content.poster_lines:
        parts.append(f"海报文案：{json.dumps(content.poster_lines, ensure_ascii=False)}")
    parts.append(f"行动引导：{content.cta}")
    return "\n".join(parts)
