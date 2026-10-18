"""数据模型：任务、策略、事实、图片、内容、核验结果"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    WECHAT_ARTICLE = "公众号"
    XIAOHONGSHU = "小红书"
    WECHAT_MOMENT = "门店朋友圈"
    STORE_POSTER = "门店海报"


class TaskStatus(str, Enum):
    INCOMPLETE = "INCOMPLETE"   # 信息不足，需追问
    COMPLETE = "COMPLETE"       # 信息完整，可生成
    AMBIGUOUS = "AMBIGUOUS"     # 型号/信息有歧义，需澄清


class Task(BaseModel):
    """营销内容生成任务"""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    product: str                       # 产品型号（精确型号）
    target_audience: str               # 目标人群
    scenario: Optional[str] = None     # 使用场景
    platform: Platform                 # 发布平台
    content_goal: Optional[str] = None # 内容目标
    special_requirements: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class TaskParseResult(BaseModel):
    """任务解析结果（含追问）"""
    status: TaskStatus
    parsed_task: Optional[Task] = None
    missing_fields: List[str] = Field(default_factory=list)
    follow_up_question: Optional[str] = None
    candidates: List[str] = Field(default_factory=list)  # 型号歧义候选


class Strategy(BaseModel):
    """场景与平台内容策略"""
    audience_analysis: Dict = Field(default_factory=dict)   # 人群/问题/购买阶段
    content_strategy: Dict = Field(default_factory=dict)    # 切入点/优先卖点/语气
    platform_adaptation: Dict = Field(default_factory=dict) # 标题/篇幅/结构/图片数/引导


class Fact(BaseModel):
    """知识库事实点（可追溯）"""
    fact_id: str
    fact_type: str = "spec"          # spec / feature / benefit / limit / policy
    content: str                     # 事实内容
    product_model: str = ""          # 归属型号
    source_title: str = ""           # 资料标题
    source_path: str = ""            # 来源文件/链接
    confidence: float = 1.0


class ImageAsset(BaseModel):
    """图片素材（来自ima/知识库）"""
    image_id: str
    file_name: str = ""
    url: str = ""                    # 原始图片URL
    local_path: str = ""             # 本地文件路径（演示用）
    product_model: str = ""          # 图片归属型号（核验关键）
    description: str = ""            # 画面说明
    source_page: str = ""            # 来源页面
    suggested_use: str = ""          # 建议用途


class ImagePlacement(BaseModel):
    """图文编排：图片插入方案"""
    image_id: str
    position: str = ""               # 如 after_title / after_paragraph_2
    caption: str = ""                # 图片说明
    reason: str = ""                 # 选择理由
    source: str = ""                 # 来源


class ContentSection(BaseModel):
    paragraph_id: int
    content: str
    supporting_facts: List[str] = Field(default_factory=list)
    reasoning: str = ""


class Content(BaseModel):
    """生成的图文软文"""
    title: str
    intro: Optional[str] = None
    body: List[ContentSection] = Field(default_factory=list)
    image_placements: List[ImagePlacement] = Field(default_factory=list)
    cta: str = ""
    hashtags: List[str] = Field(default_factory=list)
    poster_lines: Optional[Dict] = None   # 门店海报：主标题/副标题/卖点/活动说明


class Violation(BaseModel):
    """核验/合规问题"""
    rule_category: str
    location: str = ""
    matched_text: str = ""
    issue: str = ""
    severity: str = "medium"         # critical / high / medium / low
    action: str = "needs_confirmation"  # must_remove / must_correct / needs_confirmation / suggestion
    correction_suggestion: str = ""


class FactCheckResult(BaseModel):
    """事实核验结果"""
    is_verified: bool = True
    checked_claims: List[Dict] = Field(default_factory=list)
    violations: List[Violation] = Field(default_factory=list)
    unverified_items: List[str] = Field(default_factory=list)  # 待人工确认
    confidence_score: float = 1.0


class ComplianceResult(BaseModel):
    """合规检查结果"""
    is_compliant: bool = True
    violations: List[Violation] = Field(default_factory=list)
    risk_level: str = "low"
    approved_for_publication: bool = True


class ImageCheckResult(BaseModel):
    """图片核验结果"""
    is_consistent: bool = True
    violations: List[Violation] = Field(default_factory=list)
    checked_images: List[Dict] = Field(default_factory=list)


class StepTrace(BaseModel):
    """执行过程追踪"""
    step: str
    status: str = "ok"               # ok / warn / error / skipped
    detail: str = ""
    duration_ms: int = 0
    data_summary: Dict = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    task_id: str
    steps: List[StepTrace] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)

    def add(self, step: str, status: str = "ok", detail: str = "",
            duration_ms: int = 0, **data_summary) -> None:
        self.steps.append(StepTrace(
            step=step, status=status, detail=detail,
            duration_ms=duration_ms, data_summary=data_summary,
        ))


class ContentResult(BaseModel):
    """完整生成结果（统一输出格式的数据底座）"""
    task: Task
    strategy: Strategy
    facts: List[Fact] = Field(default_factory=list)
    images: List[ImageAsset] = Field(default_factory=list)
    content: Content
    fact_check: FactCheckResult = Field(default_factory=FactCheckResult)
    image_check: ImageCheckResult = Field(default_factory=ImageCheckResult)
    compliance: ComplianceResult = Field(default_factory=ComplianceResult)
    knowledge_source: str = "ima"    # ima / local
    trace: Optional[ExecutionTrace] = None
    created_at: datetime = Field(default_factory=datetime.now)
