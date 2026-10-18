"""营销合规规则引擎（规则层，无需LLM即可拦截高风险表达）

覆盖：绝对化用语 / 虚假承诺 / 价格误导 / 无依据对比 / 竞品贬低 / 伪造体验 / 夸大宣传
"""
from __future__ import annotations

from typing import List, Optional

from .models import ComplianceResult, Content, Violation

# 绝对化用语（一票否决）
ABSOLUTE_PATTERNS = [
    "最好", "最佳", "最强", "最轻", "最薄", "最快", "最优", "最先进", "最低价", "最高性价比",
    "第一", "唯一", "独一无二", "完美", "极致", "顶级", "至尊", "首选", "王牌", "巅峰",
    "绝无仅有", "史无前例", "遥遥领先", "稳居第一",
]

# 虚假承诺（一票否决）
PROMISE_PATTERNS = [
    "保证", "百分百", "100%", "永不", "绝对", "必然", "承诺", "零风险", "无与伦比",
    "终身免费", "永不卡顿", "永不断电",
]

# 无依据对比 / 竞品贬低（一票否决）
COMPARISON_PATTERNS = [
    "秒杀", "碾压", "吊打", "完胜", "甩开", "吊打一切", "友商", "杂牌", "不如华为",
]

# 价格误导（高风险）
PRICE_PATTERNS = [
    "原价", "立省", "立减", "仅需", "亏本", "清仓", "跳楼价", "补贴", "返现", "报销",
    "最后一天", "限时抢购", "库存紧张", "错过再无", "骨折价",
]

# 伪造体验（小红书等平台）
FAKE_EXPERIENCE_PATTERNS = [
    "我买了", "我入手", "我用了", "亲测", "用了三天", "用了一周", "用了一个月",
    "作为老用户", "真实体验说", "不吹不黑", "姐妹们冲",
]

# 夸大宣传
EXAGGERATION_PATTERNS = [
    "颠覆", "革命", "黑科技", "重新定义", "划时代", "无所不能", "一骑绝尘",
]

_RULE_GROUPS = [
    ("absolute_claims", "绝对化用语", ABSOLUTE_PATTERNS, "critical"),
    ("false_promise", "虚假承诺", PROMISE_PATTERNS, "critical"),
    ("comparison_without_evidence", "无依据对比/竞品贬低", COMPARISON_PATTERNS, "critical"),
    ("price_misleading", "价格误导", PRICE_PATTERNS, "high"),
    ("fake_experience", "伪造用户体验", FAKE_EXPERIENCE_PATTERNS, "high"),
    ("exaggeration", "夸大宣传", EXAGGERATION_PATTERNS, "medium"),
]

# 伪体验仅在UGC型平台严格拦截
UGC_PLATFORMS = {"小红书"}

_SEVERITY_RISK = {"critical": "法律风险", "high": "平台处罚风险", "medium": "品牌形象风险"}


def _locate(text: str, index: int) -> str:
    """估算命中位置属于标题/第几段"""
    before = text[:index]
    para_no = before.count("\n") + 1
    return f"第{para_no}处"


def rule_check(content: Content, platform: str = "") -> ComplianceResult:
    """对生成内容执行规则层合规检查"""
    blocks: List[tuple] = [("title", content.title or "")]
    if content.intro:
        blocks.append(("intro", content.intro))
    for sec in content.body:
        blocks.append((f"paragraph_{sec.paragraph_id}", sec.content))
    if content.cta:
        blocks.append(("cta", content.cta))
    if content.poster_lines:
        for key, value in content.poster_lines.items():
            blocks.append((f"poster_{key}", "；".join(value) if isinstance(value, list) else str(value)))

    violations: List[Violation] = []
    for category, label, patterns, severity in _RULE_GROUPS:
        if category == "fake_experience" and platform not in UGC_PLATFORMS:
            continue
        for location, text in blocks:
            for pattern in patterns:
                if pattern in text:
                    violations.append(Violation(
                        rule_category=category,
                        location=location,
                        matched_text=pattern,
                        issue=f"{label}：命中「{pattern}」",
                        severity=severity,
                        action="must_remove" if severity == "critical" else "must_correct",
                        correction_suggestion="删除或改为可验证的客观表述",
                    ))

    # 价格/补贴信息统一提示需核实依据
    price_hits = []
    for location, text in blocks:
        for pattern in ("元", "￥", "¥", "价格", "售价"):
            if pattern in text:
                price_hits.append(location)
                break
    if price_hits:
        violations.append(Violation(
            rule_category="price_needs_source",
            location="、".join(sorted(set(price_hits))),
            matched_text="价格相关表述",
            issue="包含价格/金额表述，必须有知识库依据和时间范围，否则视为价格误导",
            severity="high",
            action="needs_confirmation",
            correction_suggestion="补充资料依据，或删除具体价格表述",
        ))

    critical = [v for v in violations if v.severity == "critical"]
    high = [v for v in violations if v.severity == "high"]
    if critical:
        risk_level = "high"
    elif high:
        risk_level = "medium"
    else:
        risk_level = "low"

    return ComplianceResult(
        is_compliant=not critical,
        violations=violations,
        risk_level=risk_level,
        approved_for_publication=not violations,
    )


def check_model_confusion(content: Content, target_model: str,
                          all_models: Optional[List[str]] = None) -> List[Violation]:
    """型号混淆检查：文中出现非目标型号即标记（防相近型号错配）"""
    if not all_models:
        return []
    text = f"{content.title} {content.intro or ''} " + " ".join(s.content for s in content.body)
    text += " " + " ".join(p.caption for p in content.image_placements)
    target_norm = target_model.lower().replace(" ", "")
    violations: List[Violation] = []
    for model in all_models:
        model_norm = model.lower().replace(" ", "")
        if not model_norm or model_norm in target_norm or target_norm in model_norm:
            continue
        if model.lower() in text.lower() or (len(model_norm) > 8 and model_norm in text.lower().replace(" ", "")):
            violations.append(Violation(
                rule_category="model_confusion",
                location="全文",
                matched_text=model,
                issue=f"文中出现非任务型号「{model}」，存在相近型号混淆风险",
                severity="critical",
                action="must_correct",
                correction_suggestion=f"核对并统一替换为任务型号「{target_model}」",
            ))
    return violations
