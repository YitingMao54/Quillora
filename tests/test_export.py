"""统一输出格式导出测试（对齐赛题四·四）"""
from agent.models import (
    ComplianceResult, Content, ContentResult, ContentSection, Fact,
    FactCheckResult, ImageAsset, ImageCheckResult, ImagePlacement,
    Platform, Strategy, Task,
)
from agent.pipeline import MarketingAgent

REQUIRED = [
    "一、场景判断", "目标人群：", "使用场景：", "用户问题：", "内容目标：", "平台：",
    "二、知识库依据", "产品型号：", "事实点：", "资料标题：",
    "三、图文软文", "标题：", "导语：", "正文：", "行动引导：",
    "图片名称：", "来源：", "插入位置：", "图片说明：",
    "四、核验结果", "产品事实：", "图片型号：", "合规：", "待确认信息：",
]


def _result(knowledge_source="ima,local") -> ContentResult:
    return ContentResult(
        task=Task(product="HUAWEI MateBook Pro", target_audience="大学新生",
                  scenario="开学季", platform=Platform.XIAOHONGSHU, content_goal="种草"),
        strategy=Strategy(audience_analysis={"pain_points": ["移动学习"]},
                          content_strategy={"angle": "开学移动学习"}),
        facts=[Fact(fact_id="F01", fact_type="spec", content="重量：970 g",
                    product_model="HUAWEI MateBook Pro",
                    source_title="产品事实", source_path="P1/产品事实.md")],
        images=[ImageAsset(image_id="I01", file_name="a.jpg",
                           product_model="HUAWEI MateBook Pro", source_page="华为官网")],
        content=Content(title="标题", intro="导语",
                        body=[ContentSection(paragraph_id=1, content="正文内容。",
                                             supporting_facts=["F01"])],
                        image_placements=[ImagePlacement(
                            image_id="I01", position="after_title",
                            caption="外观图", reason="首图", source="华为官网")],
                        cta="到店体验", hashtags=["#开学季"]),
        fact_check=FactCheckResult(is_verified=True, unverified_items=["接口清单"]),
        image_check=ImageCheckResult(is_consistent=True),
        compliance=ComplianceResult(is_compliant=True),
        knowledge_source=knowledge_source,
    )


def test_unified_format_fields_complete():
    md = MarketingAgent(llm=object()).export_markdown(_result())
    missing = [f for f in REQUIRED if f not in md]
    assert not missing, f"缺少题目要求字段: {missing}"


def test_source_label_multi():
    md = MarketingAgent(llm=object()).export_markdown(_result("ima,local"))
    assert "ima在线知识库 + 本地P1-P8数据" in md


def test_fact_content_not_truncated():
    long_fact = "重量：970 g " + "详细参数说明" * 50
    r = _result()
    r.facts[0].content = long_fact
    md = MarketingAgent(llm=object()).export_markdown(r)
    assert "详细参数说明" * 20 in md, "事实点应输出完整内容，不得截断"


def test_unverified_items_rendered():
    md = MarketingAgent(llm=object()).export_markdown(_result())
    assert "接口清单" in md
