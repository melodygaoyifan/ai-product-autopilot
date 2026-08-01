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
    # Named _modules_ explicitly: this used to be "failed_hint", the same key
    # the error page uses further down, so the later definition silently won
    # and this card told founders their API key was missing.
    "failed_modules_hint": {
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
    # --- the production loop: take it live / it's broken / housekeeping --
    "title_live": {
        "zh": "上线 / Take it live",
        "en": "Take it live",
    },
    "link_live": {
        "zh": "上线（部署与检查）/ Take it live",
        "en": "Take it live",
    },
    "live_run": {
        "zh": "在服务器上运行 / Run it on a server",
        "en": "Run it on a server",
    },
    "live_run_hint": {
        "zh": "把这个文件夹放到服务器上（内网虚拟机即可），装好 Python，"
              "运行这一条命令 — 和每次验证用的完全相同：/ Copy this folder "
              "to the server, install Python, run this one command:",
        "en": "Copy this folder to the server (an internal VM is fine), "
              "install Python, and run this one command — the same one "
              "every build verification used:",
    },
    "live_run_note": {
        "zh": "PORT 环境变量决定端口；数据文件随文件夹一起走。/ PORT picks "
              "the port; the data file travels with the folder.",
        "en": "The PORT environment variable picks the port; the data "
              "file travels with the folder.",
    },
    "live_persistence": {
        "zh": "数据存储 / Your data",
        "en": "Your data",
    },
    "live_local_db": {
        "zh": "本地数据库已就绪：/ Local database provisioned:",
        "en": "Local database provisioned:",
    },
    "live_no_services": {
        "zh": "尚未登记任何存储服务。/ No storage service registered yet.",
        "en": "No storage service registered yet.",
    },
    "live_cloud_steps": {
        "zh": "云数据库开通步骤（SERVICES.md）/ Cloud database steps",
        "en": "Cloud database steps (SERVICES.md)",
    },
    "btn_cloud_guide": {
        "zh": "生成云数据库指南 / Write the cloud guide",
        "en": "Write the cloud database guide",
    },
    "live_no_catalog": {
        "zh": "此产品类型没有引导式云服务目录 — 数据存储是产品自身设计的一部分"
              "（见 FDR 与 design.md）。/ No guided cloud catalog for this "
              "profile; storage is part of the product's own design.",
        "en": "No guided cloud catalog for this profile — the data store "
              "is part of the product's own design (see the FDR and "
              "design.md).",
    },
    "btn_cloud_guide_again": {
        "zh": "重新生成指南 / Rewrite the guide",
        "en": "Rewrite the guide",
    },
    "live_guide_effect": {
        "zh": "会写入 SERVICES.md：按你的产品类型给出白话开通步骤，"
              "凭据放入保管库，绝不进入代码或提示词。/ Writes SERVICES.md "
              "with plain-language steps; credentials go to the vault.",
        "en": "Writes SERVICES.md — plain-language setup steps for your "
              "product type; credentials go in the vault, never into code "
              "or prompts.",
    },
    "live_boundary": {
        "zh": "谁来按部署按钮 / Who presses the deploy button",
        "en": "Who presses the deploy button",
    },
    "live_boundary_note": {
        "zh": "avs 从不自行部署上线。自动化部署的机关存在，但默认解除武装 — "
              "由一位署名的人写下限期策略后才生效（ADR-031）。在那之前，"
              "按钮是你的。/ avs never deploys on its own; automation stays "
              "disarmed until a named human arms a policy.",
        "en": "avs never deploys to production on its own. The automation "
              "exists but stays disarmed until a named human writes an "
              "attributed, expiring policy (ADR-031). Until then, the "
              "button is yours — which is the point.",
    },
    "live_verify": {
        "zh": "它现在在线吗？ / Is it answering right now?",
        "en": "Is it answering right now?",
    },
    "live_never_checked": {
        "zh": "还没检查过 — 填入你部署后的网址试试。/ Never checked — paste "
              "your deployed URL.",
        "en": "Never checked — paste the URL where you put it.",
    },
    "btn_check_live": {
        "zh": "检查 / Check",
        "en": "Check",
    },
    "house_head": {
        "zh": "日常维护 / Housekeeping",
        "en": "Housekeeping",
    },
    "house_never": {
        "zh": "清扫角色还没运行过 — 运行：/ The sweep role has not run yet:",
        "en": "The sweep role has not run yet — run:",
    },
    "house_unreadable": {
        "zh": "清扫摘要无法解析。/ The sweep digest is unreadable.",
        "en": "The sweep digest is unreadable.",
    },
    "house_clean": {
        "zh": "上次清扫：无事可做（已记录，不是沉默）。/ Last sweep: clean "
              "pass, recorded.",
        "en": "Last sweep: nothing to tidy — a recorded clean pass, not "
              "silence.",
    },
    "house_items": {
        "zh": "项待处理 / item(s) queued",
        "en": "item(s) queued",
    },
    "house_actionable": {
        "zh": "项可自动处理（人工晋升后）/ actionable",
        "en": "actionable within the cap",
    },
    "house_note": {
        "zh": "由清扫角色从框架队列收集；升级动作永远由人晋升。/ Harvested "
              "by the sweep role; promotion is always a human decision.",
        "en": "Harvested by the sweep role from the framework's own "
              "queues; promoting it to act is always a human decision.",
    },
    "btn_run_sweep": {
        "zh": "现在做一次维护检查 / Run a housekeeping check",
        "en": "Run a housekeeping check",
    },
    "house_run_note": {
        "zh": "SW0 只报告，不改动任何东西；对某项采取行动永远是人的晋升决定。"
              "/ Report-only at SW0; acting on an item is a human promotion.",
        "en": "Report-only at rung SW0 — nothing is changed; acting on an "
              "item is always a human promotion decision.",
    },
    "btn_evidence": {
        "zh": "导出 Gate-R 证据包 / Export the Gate-R evidence bundle",
        "en": "Export the Gate-R evidence bundle",
    },
    "title_evidence": {
        "zh": "证据包 / Evidence bundle",
        "en": "Evidence bundle",
    },
    "evidence_written": {
        "zh": "证据包已写入 / Evidence bundle written",
        "en": "Evidence bundle written",
    },
    "evidence_note": {
        "zh": "逐条列出这次评审的闸门与结论 — 由人附到 CAB/变更申请上；"
              "Studio 从不代为提交。/ Line-by-line gate record for the CAB "
              "submission; a human attaches it, the Studio never submits.",
        "en": "The line-by-line gate record for a CAB/change submission — "
              "a human attaches it; the Studio never submits anything "
              "anywhere.",
    },
    "gov_deploys": {
        "zh": "部署评审（Gate 5）/ Deploy reviews (Gate 5)",
        "en": "Deploy reviews (Gate 5)",
    },
    "gov_no_deploys": {
        "zh": "还没有部署评审 — 运行：/ None yet — run:",
        "en": "None yet — run:",
    },
    "gov_deploys_note": {
        "zh": "建议，从不执行：deploy-execute 在有署名限期策略之前保持解除武装。"
              "/ Recommendations only; deploy-execute stays disarmed.",
        "en": "Recommendations, never executions — deploy-execute stays "
              "disarmed until a named, expiring policy arms it.",
    },
    "h_broken": {
        "zh": "产品出故障了？ / Is it broken?",
        "en": "Is it broken?",
    },
    "inc_hint": {
        "zh": "用你自己的话描述故障（什么坏了、从什么时候开始、影响谁）。"
              "系统会分诊、找根因，并在可能时提出修复 — 修复和其他改动一样"
              "要过评审。/ Describe the failure in your own words; it will "
              "be triaged and root-caused.",
        "en": "Describe the failure in your own words — what broke, since "
              "when, who it affects. It gets triaged and root-caused; a "
              "proposed fix re-enters review like any other change.",
    },
    "inc_placeholder": {
        "zh": "例如：从今天早上开始，提交新申请的按钮点了没反应。/ e.g. since "
              "this morning, submitting a new request does nothing.",
        "en": "e.g. since this morning, clicking “submit a request” does "
              "nothing and no request shows up.",
    },
    "btn_incident": {
        "zh": "分诊这个故障 / Triage it",
        "en": "Triage it",
    },
    "title_incident": {
        "zh": "故障分诊 / Incident triage",
        "en": "Incident triage",
    },
    "inc_head": {
        "zh": "分诊结果 / What the triage found",
        "en": "What the triage found",
    },
    "inc_hypothesis": {
        "zh": "根因假设 / Likely cause",
        "en": "Likely cause",
    },
    "inc_next": {
        "zh": "建议动作 / Suggested next step",
        "en": "Suggested next step",
    },
    "inc_v_low": {
        "zh": "已记录 — 优先级不高，暂不需要动作。/ Logged — low priority.",
        "en": "Logged — low priority, nothing urgent to do.",
    },
    "inc_v_cause": {
        "zh": "找到了可能的原因。/ A likely cause was found.",
        "en": "A likely cause was found.",
    },
    "inc_v_escalate": {
        "zh": "需要人来看 — 系统没能自动定位原因。/ Needs a human — the "
              "cause could not be pinned down automatically.",
        "en": "This needs a human — the cause could not be pinned down "
              "automatically.",
    },
    "inc_saved_at": {
        "zh": "完整的技术记录已保存，交给维护这个产品的人即可：/ The full "
              "technical record is saved here — hand it to whoever "
              "maintains the product:",
        "en": "The full technical record is saved here — hand it to "
              "whoever maintains the product:",
    },
    "btn_try_fix": {
        "zh": "尝试修复（会进评审）/ Attempt the fix",
        "en": "Attempt the fix",
    },
    "inc_fix_note": {
        "zh": "点击即批准一次修复尝试；产出的改动会像任何 PR 一样重新进入"
              "代码评审，绝不直接上线。/ The click approves one attempt; "
              "the change re-enters review, never straight to production.",
        "en": "Your click approves one fix attempt; the resulting change "
              "re-enters code review like any PR — never straight to "
              "production.",
    },
    "title_fix": {
        "zh": "修复尝试 / Fix attempt",
        "en": "Fix attempt",
    },
    "fix_head": {
        "zh": "修复尝试结果 / How the attempt went",
        "en": "How the attempt went",
    },
    "fix_branch": {
        "zh": "分支 / branch",
        "en": "branch",
    },
    "fix_files": {
        "zh": "改动文件 / files changed",
        "en": "files changed",
    },
    "pre_head": {
        "zh": "可以开工了吗？ / Ready to build?",
        "en": "Ready to build?",
    },
    "pre_note": {
        "zh": "一个团队今天就能用它构建软件所需的每一项 — 实时读取，"
              "未就绪的项附上确切的修复命令。/ Every prerequisite for a "
              "team to build software today — read live; each gap carries "
              "its exact fix.",
        "en": "Every prerequisite for a team to build software today — "
              "read live from the environment, git, and the forge CLI; "
              "each gap carries its exact fix.",
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
    # --- the spend guard (cost + cap, on the pages where money is decided) --
    "h_spend_guard": {
        "zh": "花费与上限 / Spending &amp; cap",
        "en": "Spending &amp; cap",
    },
    "cap_month_line": {
        "zh": "本月（{month}）已花 {spent}，上限 {cap}。",
        "en": "This month ({month}): {spent} of your {cap} cap.",
    },
    "cap_no_spend": {
        "zh": "本月还没有产生费用。",
        "en": "No model calls yet this month.",
    },
    "cap_none_warn": {
        "zh": "还没有设定每月花费上限。意外账单几乎都来自没有上限的自动运行 —— "
              "设一个：到达后构建会在模块之间暂停，什么都不会丢，随时可以调高。",
        "en": "No monthly spending cap is set. Surprise bills come from "
              "letting an agent run with no ceiling — set one: when it is "
              "reached, builds pause between modules, nothing is lost, and "
              "you can raise it any time.",
    },
    "cap_over_note": {
        "zh": "已到上限：构建在模块之间暂停了。没有任何东西丢失 —— 调高上限即可继续。",
        "en": "The cap is reached: builds are paused between modules. Nothing "
              "is lost — raise the cap to continue.",
    },
    "cap_floor_note": {
        "zh": "有些调用还没有单价记录，所以这个数字是下限，实际略高。",
        "en": "Some calls have no price on file, so this total is a floor — "
              "the true figure is slightly higher.",
    },
    "cap_change_summary": {
        "zh": "修改上限 / Change the cap",
        "en": "Change the cap",
    },
    "btn_set_cap": {
        "zh": "设定每月上限（美元）/ Set monthly cap (US$)",
        "en": "Set monthly cap (US$)",
    },
    "cap_invalid": {
        "zh": "这不是一个有效的金额，上限没有改动。",
        "en": "That is not a valid amount — the cap was not changed.",
    },
    "eng_cost_detail": {
        "zh": "按模型细分（`avs cost` 的输出）/ Per-model spend",
        "en": "Per-model spend (what `avs cost` prints)",
    },
    "ent_cap_note": {
        "zh": "上限存放在 .mas/cost-model.yaml —— 它是一份预算决定，价格条目带来源与"
              "日期，导入永远不会覆盖你自己改过的单价。",
        "en": "The cap lives in .mas/cost-model.yaml — a budget decision on "
              "file. Price entries carry a source and a date, and an import "
              "never overwrites a price you corrected yourself.",
    },
    "link_verification": {
        "zh": "🔎 自动验收结果 / What was checked automatically",
        "en": "🔎 What was checked automatically",
    },
    "title_verification": {
        "zh": "自动验收结果 / Automatic verification",
        "en": "Automatic verification",
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
    # The reassurance is always true, so it is always shown. The CAUSE is a
    # separate string chosen from the actual exception (studio.failure_cause)
    # — one hardcoded guess used to claim "missing or exhausted API key" for
    # every failure, including transient overloads on a perfectly good key.
    "failed_safe": {
        "zh": "你的需求和已有成果都还在，什么都没丢。",
        "en": "Nothing was lost — your requirements and anything already built "
              "are still here.",
    },
    "failed_cause_key": {
        "zh": "看起来是模型 API key 的问题：没设置、被拒绝或额度用完了。"
              "修好后重试即可。",
        "en": "This looks like a problem with your model API key — missing, "
              "rejected, or out of credit. Fix that and try again.",
    },
    "failed_cause_busy": {
        "zh": "模型服务当时繁忙或连不上，自动重试也用完了。你的设置没有问题，"
              "过一会儿再点一次就行。",
        "en": "The model service was busy or unreachable, and the automatic "
              "retries ran out. Nothing is wrong with your setup — wait a "
              "moment and press the button again.",
    },
    "failed_cause_unknown": {
        "zh": "这次的原因不能确定，下面的技术细节写明了实际发生了什么。",
        "en": "The cause is not certain this time. The technical detail below "
              "says exactly what happened.",
    },
    "failed_detail": {
        "zh": "技术细节 / Technical detail",
        "en": "Technical detail",
    },
    # ── Lost-update guard on the FDR form ────────────────────────────────
    "title_conflict": {
        "zh": "需求文档在你编辑期间变过 / The requirements changed while you were editing",
        "en": "The requirements changed while you were editing",
    },
    "conflict_lead": {
        "zh": "这个页面打开之后，FDR.md 被改过了。",
        "en": "FDR.md changed after this page was opened.",
    },
    "conflict_hint": {
        "zh": "直接提交会盖掉那些改动，所以先停下来问你一句。两份都在下面，"
              "你选一份 —— 什么都不会自动丢。",
        "en": "Submitting would overwrite those changes, so nothing was saved "
              "yet. Both versions are below — pick one. Nothing is discarded "
              "automatically.",
    },
    "conflict_on_disk": {
        "zh": "磁盘上现在的版本（较新）",
        "en": "What is on disk now (newer)",
    },
    "conflict_yours": {
        "zh": "你这个页面里的版本",
        "en": "What this page had",
    },
    "btn_use_on_disk": {
        "zh": "用磁盘上的这份",
        "en": "Use the version on disk",
    },
    "btn_use_mine": {
        "zh": "用我页面里的这份（会覆盖）",
        "en": "Use mine (overwrites)",
    },
    # ── The conversational intake (studio_chat) ──────────────────────────
    "title_chat": {
        "zh": "一句一句说 / One question at a time",
        "en": "One question at a time",
    },
    "chat_intro": {
        "zh": "我问一句，你答一句，需求文档我来写。随时可以停下来直接生成计划。",
        "en": "I ask one question, you answer it, and I write the requirements "
              "document. You can stop and go straight to the plan at any point.",
    },
    "chat_have_fdr": {
        "zh": "你已经写过需求文档了。",
        "en": "You already have a requirements document.",
    },
    "chat_have_fdr_hint": {
        "zh": "直接用它生成计划，或者改一改；也可以丢开它、用对话重新写一份。",
        "en": "Use it as it stands, edit it, or set it aside and build a new "
              "one through the conversation.",
    },
    "chat_start_over": {
        "zh": "不用这份，用对话重新写",
        "en": "Ignore it and answer questions instead",
    },
    "chat_switch_to_form": {
        "zh": "或者用表格一次填完",
        "en": "Or fill in the whole form instead",
    },
    "chat_switch_to_chat": {
        "zh": "不想填表格？一句一句说",
        "en": "Rather not fill in a form? Answer one question at a time",
    },
    "chat_answer_label": {
        "zh": "你的回答",
        "en": "Your answer",
    },
    "btn_chat_send": {
        "zh": "回答",
        "en": "Answer",
    },
    "btn_chat_skip": {
        "zh": "跳过这一题",
        "en": "Skip this one",
    },
    "btn_chat_enough": {
        "zh": "够了，直接生成计划",
        "en": "That's enough — go to the plan",
    },
    "btn_chat_restart": {
        "zh": "重新开始对话",
        "en": "Start the conversation over",
    },
    "chat_checking": {
        "zh": "正在看你写的需求，可能要一两分钟…",
        "en": "Reading your requirements — this can take a minute or two…",
    },
    "chat_clarify_lead": {
        "zh": "还有几个地方我不确定，问清楚了再动手，免得建错。",
        "en": "A few things I am not sure about. Better to ask than to guess "
              "and build the wrong thing.",
    },
    "chat_rounds_done": {
        "zh": "问得差不多了。剩下不清楚的地方我用合理的默认值处理，"
              "你也可以以后再单独加功能。",
        "en": "That is enough questions. I will use sensible defaults for "
              "whatever is still open — you can always add a feature later.",
    },
    "chat_skipped": {
        "zh": "（跳过）",
        "en": "(skipped)",
    },
    "chat_prior_fdr_saved": {
        "zh": "你原来写的需求已另存为 {name}，没有被覆盖。",
        "en": "Your previous requirements were saved as {name} — nothing was "
              "overwritten.",
    },
    # The six intake questions, conversational rather than form-shaped.
    "chat_q_who": {
        "zh": "这个产品是给谁用的？他们现在是怎么解决这个问题的？",
        "en": "Who is this for, and how do they solve the problem today?",
    },
    "chat_q_actions": {
        "zh": "用户打开它之后会做什么？按顺序说，越具体越好。",
        "en": "What does someone do after they open it? In order, as "
              "specifically as you can.",
    },
    "chat_q_must": {
        "zh": "哪些功能是没有就不能用的？",
        "en": "Which features would make it unusable if they were missing?",
    },
    "chat_q_not_needed": {
        "zh": "有什么是你想到了、但第一版不做的？写下来能防止系统做多。",
        "en": "What have you thought of but do NOT want in the first version? "
              "Naming it stops it being built by mistake.",
    },
    "chat_q_constraints": {
        "zh": "有什么限制或偏好吗？比如只在微信里用、要能发到群里。没有就说没有。",
        "en": "Any constraints or preferences? Say none if there are none.",
    },
    "chat_q_success": {
        "zh": "怎么算成功？一句能验证的话就行。",
        "en": "What does success look like? One sentence you could check.",
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
