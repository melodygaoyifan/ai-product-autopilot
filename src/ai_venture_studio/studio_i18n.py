"""Founder Studio strings, per language.

The Studio was written bilingual-with-Chinese-first, because its first users
were 小程序 founders. That is a fine default and a bad ceiling: an
English-speaking founder saw `写下你的产品需求 / Describe your product`, and
the README's product demo could not be shown in English at all.

So every user-facing string lives here, keyed by language:

- `en` is English only, and is the DEFAULT — no bilingual slash, because a
  bilingual UI is a compromise for a mixed audience, not an improvement for
  a single one.
- `zh` is the ORIGINAL bilingual text, character for character. `--lang zh`
  brings back exactly the UI 小程序 founders have been using; the strings
  were not touched, only the default.

There is deliberately no autodetection: guessing a founder's language from a
locale header and getting it wrong is worse than one flag, and the FDR itself
may be written in either language whichever UI they read.
"""

from __future__ import annotations

LANGUAGES = ("zh", "en")
# English is the default (v0.53). The Studio began Chinese-first because its
# first users were 小程序 founders; the repository is public and English-
# speaking, so the default now matches the audience that meets it first.
# `--lang zh` restores the original bilingual UI in full — nothing was
# removed, only the default moved.
DEFAULT_LANGUAGE = "en"

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
        "zh": "所有模块其实都做完了 — 在终端运行 <code>avs preview</code> "
              "查看产品。",
        "en": "Every module actually finished — run <code>autoproduct "
              "preview</code> in the terminal to see the product.",
    },
    "interrupted_resume": {
        "zh": "已完成的模块都保留着，逐个继续就行：",
        "en": "Finished modules are kept. Resume the rest one at a time:",
    },
    # --- studio modes (v0.55) -------------------------------------------
    "h_engineer": {
        "zh": "构建内幕 / Build internals",
        "en": "Build internals",
    },
    "mode_note_engineer": {
        "zh": "工程师模式 — 显示命令行视角的模块 ID 和状态，可用 --mode 切换。"
              " / Engineer mode — switch with --mode.",
        "en": "Engineer mode — task IDs and states as the CLI sees them. "
              "Switch with --mode.",
    },
    "eng_profile": {"zh": "项目类型 / Profile", "en": "Profile"},
    "eng_no_plan": {
        "zh": "还没有计划 — 先写需求。/ No plan yet.",
        "en": "No plan yet — write the FDR first.",
    },
    "eng_cli": {
        "zh": "命令行等价操作 / CLI equivalents",
        "en": "CLI equivalents",
    },
    "eng_cli_body": {
        "zh": "avs retry-task <id> --repo-dir .   # 「重试」按钮\n"
              "avs preview                        # 在本地运行产品\n"
              "avs walkthrough                    # 验收清单\n"
              "avs verify                         # 重新跑检查",
        "en": "avs retry-task <id> --repo-dir .   # the Retry button\n"
              "avs preview                        # run the product locally\n"
              "avs walkthrough                    # acceptance walkthrough\n"
              "avs verify                         # re-run the checks",
    },
    "h_governance": {"zh": "治理 / Governance", "en": "Governance"},
    "mode_note_enterprise": {
        "zh": "企业模式 — 显示当前 edition 的治理设置（.mas/edition.yaml），"
              "可用 --mode 切换。 / Enterprise mode — switch with --mode.",
        "en": "Enterprise mode — what this edition enforces, read from "
              ".mas/edition.yaml. Switch with --mode.",
    },
    "gov_edition": {"zh": "预设 / Edition", "en": "Edition"},
    "gov_rung": {"zh": "基建层级 / Substrate rung", "en": "Substrate rung"},
    "gov_wip": {"zh": "并行上限 / WIP limit", "en": "WIP limit"},
    "gov_weekly": {
        "zh": "每周评审预算（分钟）/ Weekly review minutes",
        "en": "Weekly review budget (minutes)",
    },
    "gov_never": {
        "zh": "永不合并的闸门 / Never-batched gates",
        "en": "Never-batched gates",
    },
    "gov_gate_owner_yes": {
        "zh": "每个闸门都需要指定负责人。/ Named gate owner required.",
        "en": "Every gate requires a named owner.",
    },
    "gov_gate_owner_no": {
        "zh": "闸门不要求指定负责人。/ No gate owner required.",
        "en": "No named gate owner required.",
    },
    "gov_attestations": {
        "zh": "存证记录 / Attestation entries",
        "en": "Attestation ledger entries",
    },
    "gov_no_ledger": {
        "zh": "还没有存证记录 — 尚未进行任何存证。/ No attestation ledger yet.",
        "en": "No attestation ledger yet — nothing has been attested.",
    },
    "gov_no_edition": {
        "zh": "此工作区还没有选择 edition — 运行 avs init --edition "
              "enterprise。/ No edition resolved for this workspace.",
        "en": "No edition resolved for this workspace — run "
              "avs init --edition enterprise.",
    },
    "gov_edition_error": {
        "zh": "edition 文件未通过检查 / Edition file fails lint",
        "en": "The edition file fails lint",
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
