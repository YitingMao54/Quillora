"""合规规则引擎单元测试"""
from agent.compliance import check_model_confusion, rule_check
from agent.models import Content, ContentSection, Platform


def _content(title="测试标题", body="这是正文内容。", **kw):
    return Content(title=title, intro=kw.get("intro"),
                   body=[ContentSection(paragraph_id=1, content=body)],
                   cta=kw.get("cta", "到店体验"))


def test_clean_content_passes():
    result = rule_check(_content(), Platform.WECHAT_ARTICLE.value)
    assert result.is_compliant
    assert result.risk_level == "low"


def test_absolute_word_flagged():
    result = rule_check(_content(body="这是最好的屏幕。"), Platform.WECHAT_ARTICLE.value)
    assert not result.is_compliant
    assert any(v.matched_text == "最好" for v in result.violations)


def test_false_promise_flagged():
    result = rule_check(_content(body="保证永不卡顿，百分百满意。"), Platform.WECHAT_ARTICLE.value)
    words = {v.matched_text for v in result.violations}
    assert "保证" in words and "百分百" in words and "永不" in words


def test_price_misleading_flagged():
    result = rule_check(_content(body="立省500元，仅需999！"), Platform.WECHAT_ARTICLE.value)
    assert any(v.rule_category == "price_misleading" for v in result.violations)


def test_fake_experience_only_on_ugc_platform():
    body = "我用了一个月，真的好用。"
    xhs = rule_check(_content(body=body), Platform.XIAOHONGSHU.value)
    wechat = rule_check(_content(body=body), Platform.WECHAT_ARTICLE.value)
    assert any(v.rule_category == "fake_experience" for v in xhs.violations)
    assert not any(v.rule_category == "fake_experience" for v in wechat.violations)


def test_price_without_source_needs_confirmation():
    result = rule_check(_content(body="售价7999元。"), Platform.WECHAT_ARTICLE.value)
    assert any(v.rule_category == "price_needs_source" for v in result.violations)
    assert result.approved_for_publication is False


def test_model_confusion_detected():
    content = _content(body="比 HUAWEI MateBook D 14 2024 更适合学生。")
    violations = check_model_confusion(
        content, "HUAWEI MateBook Pro",
        ["HUAWEI MateBook Pro", "HUAWEI MateBook D 14 2024"])
    assert any(v.rule_category == "model_confusion" for v in violations)


def test_model_confusion_not_triggered_for_target():
    content = _content(body="HUAWEI MateBook Pro 重量 970g。")
    violations = check_model_confusion(
        content, "HUAWEI MateBook Pro", ["HUAWEI MateBook Pro", "HUAWEI MateBook Pro S"])
    assert not violations
