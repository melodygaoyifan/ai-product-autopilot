"""The conversational FDR intake — one question at a time.

The form asks for the whole FDR at once. When the assessor comes back with
five questions, the founder has to find and edit the right lines inside a
4000-character textarea, and that edit is where people stop. This asks one
question, takes one answer, and composes the document itself.

Three properties it deliberately keeps:

- **FDR.md stays the single source of truth.** The conversation is an input
  method that COMPOSES the FDR; it is not a second place requirements live.
  discover / plan / spec / build read exactly the file they always read.
- **Deterministic control flow** (CLAUDE.md): Python decides which question
  comes next. The model only ever *generates* clarify questions through the
  existing `assess_fdr`; it never decides whether to ask another round.
- **It cannot trap you.** Clarify rounds are capped, and every turn offers a
  way to stop answering and go build. A loop that keeps asking until the
  model is satisfied is worse than a slightly under-specified FDR — the
  founder can always add a feature FDR later, but they cannot get the
  afternoon back.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from pydantic import BaseModel, Field

#: The six FDR questions, in order. Slot names are stable identifiers — the
#: prose lives in studio_i18n under `chat_q_<slot>`.
INTAKE_SLOTS: tuple[str, ...] = (
    "who", "actions", "must", "not_needed", "constraints", "success",
)

CLARIFY = "clarify"

#: After this many assessor rounds the conversation stops asking and offers
#: to build. Two rounds is ten questions; past that the assessor is usually
#: polishing, not unblocking.
MAX_CLARIFY_ROUNDS = 2

_FILE = "conversation.jsonl"

#: Document headings, per language. These are artifact content (they end up
#: in FDR.md and downstream prompts read them), not UI chrome, so they live
#: beside the composer rather than in the UI string table.
_HEADINGS: dict[str, dict[str, str]] = {
    "zh": {
        "who": "## 1. 这是给谁用的？/ Who is this for?",
        "actions": "## 2. 用户用它来做什么？/ What do users do with it?",
        "must": "## 3. 必须有的功能 / Must-have features",
        "not_needed": "## 4. 暂时不要的功能 / NOT needed for now",
        "constraints": "## 5. 有什么限制或偏好？/ Constraints or preferences",
        "success": "## 6. 怎么算成功？/ What does success look like?",
        "clarify": "## 7. 补充说明 / Follow-up answers",
        "title": "# 产品需求描述 / Product Requirements (FDR)",
    },
    "en": {
        "who": "## 1. Who is this for?",
        "actions": "## 2. What do users do with it?",
        "must": "## 3. Must-have features",
        "not_needed": "## 4. NOT needed for now",
        "constraints": "## 5. Constraints or preferences",
        "success": "## 6. What does success look like?",
        "clarify": "## 7. Follow-up answers",
        "title": "# Product Requirements (FDR)",
    },
}


class Turn(BaseModel):
    """One line of the conversation. `slot` on an assistant turn says which
    question it is; the user turn that follows is its answer."""

    role: str  # assistant | user
    text: str
    slot: str = ""
    at: str = Field(default="")


def path_for(root: str | Path) -> Path:
    return Path(root) / ".mas" / _FILE


def load_thread(root: str | Path) -> list[Turn]:
    """Every turn so far. An unreadable line is skipped rather than fatal —
    a truncated last write must not make the conversation unrecoverable."""
    path = path_for(root)
    if not path.exists():
        return []
    turns: list[Turn] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            turns.append(Turn(**json.loads(line)))
        except Exception:  # noqa: BLE001 — a bad row is not a conversation
            continue
    return turns


def append_turn(root: str | Path, role: str, text: str, slot: str = "") -> Turn:
    if role not in ("assistant", "user"):
        raise ValueError(f"unknown role {role!r} — expected assistant or user")
    turn = Turn(
        role=role, text=text, slot=slot,
        at=dt.datetime.now(dt.UTC).isoformat(),
    )
    path = path_for(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(turn.model_dump(), ensure_ascii=False) + "\n")
    return turn


def reset_thread(root: str | Path) -> None:
    path_for(root).unlink(missing_ok=True)


def pairs(turns: list[Turn]) -> list[tuple[Turn, Turn]]:
    """(question, answer) for every question that has been answered."""
    answered: list[tuple[Turn, Turn]] = []
    for index, turn in enumerate(turns):
        following = turns[index + 1] if index + 1 < len(turns) else None
        if turn.role == "assistant" and following is not None and following.role == "user":
            answered.append((turn, following))
    return answered


def open_question(turns: list[Turn]) -> Turn | None:
    """The question waiting for an answer, if any."""
    if turns and turns[-1].role == "assistant":
        return turns[-1]
    return None


def next_intake_slot(turns: list[Turn]) -> str | None:
    """The next of the six to ask, or None when all six are answered."""
    done = {question.slot for question, _ in pairs(turns)}
    for slot in INTAKE_SLOTS:
        if slot not in done:
            return slot
    return None


def clarify_rounds_used(turns: list[Turn]) -> int:
    """How many assessor questions have been ANSWERED, in rounds of up to
    five. Used against MAX_CLARIFY_ROUNDS so the loop is bounded."""
    answered = sum(
        1 for question, _ in pairs(turns) if question.slot == CLARIFY
    )
    return -(-answered // 5)  # ceiling division: 1-5 answers = round 1


def intake_complete(turns: list[Turn]) -> bool:
    return next_intake_slot(turns) is None


def compose_fdr(turns: list[Turn], lang: str = "en") -> str:
    """Build FDR.md from the answers.

    Deterministic string assembly, never a model call: the founder's words
    go into the document as they typed them. An unanswered section is
    written as an explicit blank rather than omitted, so the assessor sees a
    gap instead of a document that looks complete.
    """
    headings = _HEADINGS.get(lang if lang in _HEADINGS else "en")
    if headings is None:  # pragma: no cover — dict lookup above is total
        raise ValueError(f"no headings for language {lang!r}")
    answers = {
        question.slot: answer.text.strip()
        for question, answer in pairs(turns)
        if question.slot in INTAKE_SLOTS
    }
    blocks = [headings["title"], ""]
    for slot in INTAKE_SLOTS:
        blocks.append(headings[slot])
        blocks.append("")
        blocks.append(answers.get(slot, "") or "(未回答 / not answered)")
        blocks.append("")

    follow_ups = [
        (question, answer)
        for question, answer in pairs(turns)
        if question.slot == CLARIFY
    ]
    if follow_ups:
        blocks.append(headings["clarify"])
        blocks.append("")
        for index, (question, answer) in enumerate(follow_ups, start=1):
            blocks.append(f"{index}. **{question.text.strip()}**")
            blocks.append(f"   {answer.text.strip()}")
        blocks.append("")
    return "\n".join(blocks)


def transcript(turns: list[Turn]) -> str:
    """Plain-text rendering, for the operator and for tests."""
    return "\n".join(f"{turn.role}: {turn.text}" for turn in turns)
