"""A confirmation the founder cannot read is worse than none."""
from ai_venture_studio.upstream.autopilot import _confirm_system, fdr_language

EN = "A shared task list for the two of us running a small studio. No logins."
ZH = "小区团购接龙：团长发起接龙写商品和价格，住户下单选数量。"


def test_an_english_fdr_gets_english_headings():
    assert fdr_language(EN) == "en"
    prompt = _confirm_system(EN)
    assert "What will be built" in prompt
    # The demonstration must not contradict the instruction: with Chinese
    # headings in the prompt, a real live run came back Chinese-first over an
    # entirely English FDR.
    assert not any("一" <= ch <= "鿿" for ch in prompt), (
        "an English FDR was shown Chinese headings to copy"
    )


def test_a_chinese_fdr_keeps_the_bilingual_headings():
    assert fdr_language(ZH) == "zh"
    prompt = _confirm_system(ZH)
    assert "会做什么" in prompt and "What will be built" in prompt


def test_a_mixed_fdr_counts_as_chinese():
    """One CJK sentence means the founder reads Chinese."""
    assert fdr_language(EN + " 不需要登录。") == "zh"


def test_both_call_sites_build_the_prompt_from_the_fdr():
    import inspect

    from ai_venture_studio.upstream import autopilot

    src = inspect.getsource(autopilot)
    assert "system=_CONFIRM_SYSTEM" not in src, (
        "a call site still uses the hardcoded-bilingual prompt"
    )
    assert src.count("system=_confirm_system(fdr_text)") == 2
