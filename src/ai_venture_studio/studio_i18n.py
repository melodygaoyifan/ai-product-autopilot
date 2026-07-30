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
    # --- enterprise posture / trust / codebase panels -------------------
    "gov_posture": {
        "zh": "治理态势 / Governance posture",
        "en": "Governance posture",
    },
    "gov_posture_attention": {
        "zh": "需要处理 / needs attention:",
        "en": "needs attention:",
    },
    "gov_posture_measured": {
        "zh": "已度量 / measured:",
        "en": "measured:",
    },
    "gov_posture_unmeasured": {
        "zh": "尚未配置 / not yet configured:",
        "en": "not yet configured:",
    },
    "gov_posture_note": {
        "zh": "未度量的项显示为灰色，绝不显示为绿色 — 绿色只属于真正度量过的东西。"
              "/ Unmeasured items render grey, never green.",
        "en": "Unmeasured items render grey, never green — green is only "
              "earned by something actually measured.",
    },
    "gov_action_reload": {
        "zh": "本页每次刷新都会重新读取工作区 — 运行命令后刷新即可。"
              "/ This page re-reads the workspace on every reload.",
        "en": "This page re-reads the workspace on every reload — run the "
              "command, then refresh.",
    },
    "gov_edition_effect": {
        "zh": "该命令会写入 .mas/edition.yaml（含指定的闸门负责人）。"
              "/ Writes .mas/edition.yaml with the named gate owner.",
        "en": "This writes .mas/edition.yaml with the named gate owner; "
              "the Governance card fills in from it.",
    },
    "gov_substrate_effect": {
        "zh": "该命令会打印阶梯与起步档案；声明 .mas/substrate-profile.yaml "
              "后此表格生效。/ Prints the ladder; declaring the profile "
              "activates this grid.",
        "en": "Prints the rung-by-rung ladder and a starter profile; "
              "declaring .mas/substrate-profile.yaml activates this grid.",
    },
    "trust_head": {
        "zh": "模型通道与数据流向 / Model door & egress",
        "en": "Model door & egress",
    },
    "trust_note": {
        "zh": "安全评审最先问的问题 — 每次加载从环境与工作区实时读取，"
              "从不显示密钥的值。/ Read live from the environment; never "
              "shows a secret's value.",
        "en": "What a security review asks first — read live from the "
              "environment and workspace on each load; presence only, "
              "never a secret's value.",
    },
    "trust_provider": {
        "zh": "模型通道 / Model door",
        "en": "Model door",
    },
    "trust_auth_env": {
        "zh": "密钥来自环境变量 / key in environment",
        "en": "key in environment",
    },
    "trust_auth_file": {
        "zh": "密钥来自 *_FILE 挂载 / key via *_FILE mount",
        "en": "key via *_FILE secret mount",
    },
    "trust_auth_gateway": {
        "zh": "网关令牌（ANTHROPIC_AUTH_TOKEN + base URL）/ gateway bearer",
        "en": "gateway (ANTHROPIC_AUTH_TOKEN + base URL)",
    },
    "trust_auth_none": {
        "zh": "当前进程看不到任何凭据 / no credential visible",
        "en": "no credential visible to this process",
    },
    "trust_forge": {
        "zh": "代码托管（origin）/ Forge (origin remote)",
        "en": "Forge (origin remote)",
    },
    "trust_forge_none": {
        "zh": "未检测到远端 / none detected",
        "en": "no forge remote detected",
    },
    "trust_egress": {
        "zh": "出网 / Egress",
        "en": "Egress",
    },
    "trust_egress_note": {
        "zh": "遥测不发送任何内容（未配置端点）；完整出网清单见采购包 "
              "network-egress.md。/ Telemetry sends nothing; full outbound "
              "list in the procurement pack.",
        "en": "telemetry sends nothing (no endpoint configured); the "
              "complete outbound-host list ships in the procurement pack "
              "(network-egress.md)",
    },
    "trust_spend": {
        "zh": "本工作区花费 / Spend (this workspace)",
        "en": "Spend (this workspace)",
    },
    "trust_spend_none": {
        "zh": "尚无模型调用记录 / no model calls recorded",
        "en": "no model calls recorded",
    },
    "trust_spend_floor": {
        "zh": "至少 / at least",
        "en": "at least",
    },
    "code_head": {
        "zh": "代码库（avs 读到的）/ Codebase (what avs found)",
        "en": "Codebase (what avs found)",
    },
    "code_none": {
        "zh": "还没有代码地图 — 运行（本地读取，无 LLM、无网络）："
              "/ No codebase map yet — run (local read, no LLM, no network):",
        "en": "No codebase map yet — run (reads the repo locally; no LLM, "
              "no network):",
    },
    "code_unreadable": {
        "zh": "代码地图无法解析 — 重新运行 avs map 。/ Map unreadable — "
              "re-run avs map.",
        "en": "The codebase map is unreadable — re-run avs map.",
    },
    "code_http": {
        "zh": "HTTP 路由 / HTTP routes",
        "en": "HTTP routes",
    },
    "code_entries": {
        "zh": "入口 / entry points",
        "en": "entry points",
    },
    "code_note": {
        "zh": "由 avs map 从代码推导 — 规划器读取它，而不是靠文件名猜测。"
              "/ Derived from the code; the planner reads this instead of "
              "guessing.",
        "en": "Derived from the code by avs map — the planner reads this "
              "instead of guessing from filenames.",
    },
    # --- mode strip + per-mode pages (v0.56) ----------------------------
    "mode_strip_label": {"zh": "视角 / View as:", "en": "View as:"},
    "mode_founder": {"zh": "创始人 / Founder", "en": "Founder"},
    "mode_engineer": {"zh": "工程师 / Engineer", "en": "Engineer"},
    "mode_enterprise": {"zh": "企业 / Enterprise", "en": "Enterprise"},
    "correction_log": {
        "zh": "修正历史 / Correction history",
        "en": "Correction history",
    },
    "title_review": {
        "zh": "评审时间线 / Review timeline",
        "en": "Review timeline",
    },
    "review_verdict": {"zh": "结论 / Verdict", "en": "Verdict"},
    "review_duration": {"zh": "耗时 / Duration", "en": "Duration"},
    "eng_reviews": {
        "zh": "最近的评审 / Recent reviews",
        "en": "Recent reviews",
    },
    "eng_reviews_none": {
        "zh": "还没有评审记录。/ None yet.",
        "en": "None yet.",
    },
    "eng_voter_health": {
        "zh": "评审员健康度 / Voter health",
        "en": "Voter health",
    },
    "eng_voter_cols": {
        "zh": "（次数 · 被阻塞 · 换用备选模型）/ (runs · blocked · substituted)",
        "en": "(runs · blocked · substituted)",
    },
    "gov_ledger_ok": {
        "zh": "链校验通过 / chain verified",
        "en": "chain verified",
    },
    "gov_ledger_broken": {
        "zh": "存证链已损坏，从第 / ATTESTATION CHAIN BROKEN at entry",
        "en": "ATTESTATION CHAIN BROKEN at entry",
    },
    "gov_stages": {
        "zh": "阶段就绪状态 / Stage activation",
        "en": "Stage activation",
    },
    "gov_no_substrate": {
        "zh": "未声明基建档案（.mas/substrate-profile.yaml）— 各阶段按 S0 处理。"
              "运行 avs readiness 查看。/ No substrate profile declared.",
        "en": "No substrate profile declared (.mas/substrate-profile.yaml) — "
              "stages assume S0. Run avs readiness to see the ladder.",
    },
    "gov_dwell": {
        "zh": "闸门停留时间 / Gate dwell",
        "en": "Gate dwell",
    },
    "gov_dwell_median": {
        "zh": "中位停留 / Median dwell",
        "en": "Median dwell",
    },
    "gov_override_rate": {
        "zh": "推翻率 / Override rate",
        "en": "Override rate",
    },
    "gov_automation": {
        "zh": "自动化策略 / Automation policies",
        "en": "Automation policies",
    },
    "gov_armed": {
        "zh": "已启用，授权人 / ARMED by",
        "en": "ARMED by",
    },
    "gov_expires": {
        "zh": "到期 / expires",
        "en": "expires",
    },
    "gov_disarmed": {
        "zh": "未启用（默认）/ disarmed (the default)",
        "en": "disarmed (the default)",
    },
    "gov_policy_error": {
        "zh": "策略文件无效 / POLICY ERROR",
        "en": "POLICY ERROR",
    },
    # --- in-flight and failure pages (v0.57.1) --------------------------
    # --- cost transparency (v0.60) --------------------------------------
    "h_cost": {"zh": "花了多少 / What this cost", "en": "What this cost"},
    "cost_what": {"zh": "这个产品到目前", "en": "This product so far"},
    "cost_own_key": {
        "zh": "这笔费用由你自己的 API key 承担 — 系统从不代你花钱。",
        "en": "Billed to your own API key — the framework never spends money "
              "on your behalf.",
    },
    "title_working": {"zh": "正在处理 / Working…", "en": "Working on it…"},
    "working_lead": {
        "zh": "已经在做了，请不要重复提交。",
        "en": "Already working on this — no need to submit again.",
    },
    "working_hint": {
        "zh": "这一步要调用模型，通常需要几分钟。这个页面会自动刷新。",
        "en": "This step calls the model and usually takes a few minutes. "
              "This page refreshes itself.",
    },
    "working_fdr": {
        "zh": "正在读你的需求并生成计划。",
        "en": "Reading your requirements and making the plan.",
    },
    "working_correct": {
        "zh": "正在处理你的修正。",
        "en": "Working through your correction.",
    },
    "working_feature": {
        "zh": "正在检查这个新功能。",
        "en": "Checking the new feature.",
    },
    "title_failed": {
        "zh": "这一步没成功 / That step did not finish",
        "en": "That step did not finish",
    },
    "failed_lead": {
        "zh": "这一步没有做完。",
        "en": "That step stopped before it finished.",
    },
    "failed_hint": {
        "zh": "你的需求和已有成果都还在，什么都没丢。常见原因：模型的 API key "
              "没设置或额度用完了。可以修好后重试。",
        "en": "Nothing was lost — your requirements and anything already built "
              "are still here. The usual causes are a missing or exhausted "
              "model API key. Fix that and try again.",
    },
    "failed_detail": {
        "zh": "技术细节 / Technical detail",
        "en": "Technical detail",
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
