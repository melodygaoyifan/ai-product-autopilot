"""Founder Studio strings, per language.

The Studio was written bilingual-with-Chinese-first, because its first users
were 小程序 founders. That is a fine default and a bad ceiling: an
English-speaking founder saw `写下你的产品需求 / Describe your product`, and
the README's product demo could not be shown in English at all.

So every user-facing string lives here, keyed by language:

- `zh` is the EXISTING bilingual text, character for character. Choosing it
  changes nothing about how the Studio behaves today.
- `en` is English only — no bilingual slash, because a bilingual UI is a
  compromise for a mixed audience, not an improvement for a single one.

`--lang` picks one. There is deliberately no autodetection: guessing a
founder's language from a locale header and getting it wrong is worse than
asking once, and the FDR itself may be in either language regardless of
which UI they read.
"""

from __future__ import annotations

LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"  # unchanged behaviour for existing users

STRINGS: dict[str, dict[str, str]] = {
    # --- page titles ---------------------------------------------------
    "title_describe": {
        "zh": "写下你的产品需求 / Describe your product",
        "en": "Describe your product",
    },
    "title_confirm_plan": {
        "zh": "确认计划 / Confirm the plan",
        "en": "Confirm the plan",
    },
    "title_building": {"zh": "正在搭建 / Building…", "en": "Building…"},
    "title_interrupted": {
        "zh": "搭建中断了 / Build was interrupted",
        "en": "The build was interrupted",
    },
    "title_product": {"zh": "你的产品 / Your product", "en": "Your product"},
    "title_confirm_feature": {
        "zh": "确认新功能 / Confirm the new feature",
        "en": "Confirm the new feature",
    },
    "title_acceptance": {
        "zh": "验收清单 / Acceptance walkthrough",
        "en": "Acceptance walkthrough",
    },
    # --- buttons ------------------------------------------------------
    "btn_check_and_plan": {
        "zh": "检查并生成计划 / Check &amp; make the plan",
        "en": "Check it &amp; make the plan",
    },
    "btn_start_building": {
        "zh": "开始搭建 / Start building",
        "en": "Start building",
    },
    "btn_edit_fdr": {"zh": "改需求 / Edit FDR", "en": "Edit the FDR"},
    "btn_edit_and_restart": {
        "zh": "改需求，重新来 / Edit FDR &amp; start over",
        "en": "Edit the FDR &amp; start over",
    },
    "btn_build_feature": {
        "zh": "开始添加这个功能 / Build this feature",
        "en": "Build this feature",
    },
    "btn_correct": {"zh": "修正 / Correct it", "en": "Correct it"},
    "btn_check_feature": {
        "zh": "检查这个功能 / Check this feature",
        "en": "Check this feature",
    },
    "btn_undo": {
        "zh": "⏪ 回到上一个版本 / Undo last change",
        "en": "⏪ Undo the last change",
    },
    "btn_retry": {"zh": "重试", "en": "Retry"},
    "btn_resume": {"zh": "继续", "en": "Resume"},
    # --- headings and prose -------------------------------------------
    "h_screenshots": {"zh": "页面截图 / Screenshots", "en": "Screenshots"},
    "h_features": {"zh": "功能 / Features", "en": "Features"},
    "h_something_wrong": {
        "zh": "哪里不对？/ Something wrong?",
        "en": "Something wrong?",
    },
    "h_add_feature": {"zh": "添加新功能 / Add a feature", "en": "Add a feature"},
    "link_acceptance": {
        "zh": "📋 验收清单 / Acceptance walkthrough",
        "en": "📋 Acceptance walkthrough",
    },
    "link_back": {"zh": "← 返回 / back", "en": "← Back"},
    "guide_summary": {
        "zh": "怎么写好？/ How to write a good FDR",
        "en": "How to write a good FDR",
    },
    "answer_first": {
        "zh": "请先回答这些问题 / Please answer:",
        "en": "Please answer these first:",
    },
    "planning": {"zh": "正在做计划… / planning…", "en": "planning…"},
    "updates_live": {
        "zh": "个模块 — 实时更新 / updates live.",
        "en": "modules built — updates live.",
    },
    "done_label": {"zh": "已完成", "en": "Done:"},
    "state_done": {"zh": "✅ 已完成", "en": "✅ done"},
    "state_pending_confirm": {"zh": "待确认", "en": "awaiting confirmation"},
    "first_version": {"zh": "(初版)", "en": "(first version)"},
    "correction_hint": {
        "zh": "用你自己的话说 — 小修会直接修好，需求变化会走正规变更。",
        "en": "Say it in your own words. A small fix is repaired directly; a "
              "change of requirements goes through the formal change process.",
    },
    "correction_placeholder": {
        "zh": "例：下单按钮的文字应该是「参加接龙」，不是「提交」。",
        "en": "e.g. the button on the task form should say “Add task”, not "
              "“Submit”.",
    },
    "feature_hint": {
        "zh": "一次只写一个功能或改动 — 越小越准。One feature per FDR — smaller "
              "is better.",
        "en": "One feature or change per FDR — smaller is more accurate.",
    },
    "feature_placeholder": {
        "zh": "例：住户可以取消自己的订单，取消后汇总自动更新。",
        "en": "e.g. anyone can reopen a task they marked done by mistake.",
    },
    "failed_modules": {"zh": "没做成的模块 / Failed modules",
                       "en": "Modules that did not build"},
    "failed_hint": {
        "zh": "可以先不管它们，产品其余部分能用；也可以单独重试：",
        "en": "You can leave them: the rest of the product works. Or retry one "
              "on its own:",
    },
    "interrupted_lead": {
        "zh": "上次搭建没有做完就停了。",
        "en": "The last build stopped before it finished.",
    },
    "interrupted_all_done": {
        "zh": "所有模块其实都做完了 — 在终端运行 <code>autoproduct preview</code> "
              "查看产品。",
        "en": "Every module actually finished — run <code>autoproduct "
              "preview</code> in the terminal to see the product.",
    },
    "interrupted_resume": {
        "zh": "已完成的模块都保留着，逐个继续就行：",
        "en": "Finished modules are kept. Resume the rest one at a time:",
    },
}


def normalize(lang: str | None) -> str:
    """Accept 'en', 'EN', 'en-US'; anything unknown falls back to default."""
    if not lang:
        return DEFAULT_LANGUAGE
    code = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def t(lang: str, key: str) -> str:
    """One string. A missing key is a KeyError on purpose: a Studio page with
    a blank label is worse than a loud failure at startup."""
    return STRINGS[key][normalize(lang)]
