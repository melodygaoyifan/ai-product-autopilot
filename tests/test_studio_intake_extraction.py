"""Open-prompt-first intake, and the charter rule that makes it safe.

The conversation used to ask the six FDR questions in a fixed order — a
form wearing a chat's clothes, delivered in six instalments to a founder
who already knew what they wanted. Now: one open prompt, ONE extraction
pass over what they wrote, the result shown back as SAID / GUESS rows, and
questions only about the slots that are genuinely still empty.

The rule everything here defends: **a GUESS is never written into FDR.md as
though the founder said it.** SAID is their own words, lifted verbatim, and
counts as answered. A GUESS is a proposal, and only confirming it makes it
an answer. This is the same no-fabricated-evidence rule the review side
already lives by, applied to the founder's own document.
"""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio import studio_chat
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.studio_chat import (
    GUESS,
    INTAKE_SLOTS,
    OPEN,
    SAID,
    Extraction,
    Guess,
    append_turn,
    apply_extraction,
    compose_fdr,
    extract_intake,
    is_verbatim,
    load_thread,
    next_intake_slot,
    next_question_slot,
    pairs,
    pending_guess,
)
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

PARAGRAPH = (
    "The two of us keep losing tasks in chat. Anyone should be able to add "
    "a task with a title and an owner. We do not want logins yet."
)

QUESTIONS = {slot: f"q-{slot}" for slot in INTAKE_SLOTS}


@pytest.fixture
def workspace(tmp_path):
    return init_workspace(tmp_path / "intake", "intake", "web")


@pytest.fixture
def client(workspace):
    return TestClient(create_studio_app(workspace, provider="mock"))


# ── the extraction pass, without the web layer ───────────────────────────


def test_the_open_prompt_comes_first_and_is_not_one_of_the_six():
    assert next_question_slot([]) == OPEN
    assert OPEN not in INTAKE_SLOTS


def test_extraction_returns_the_founders_own_words_or_nothing():
    extraction = extract_intake(PARAGRAPH, provider="mock")
    assert extraction.said, "the extraction filled nothing at all"
    for slot, value in extraction.said.items():
        assert slot in INTAKE_SLOTS
        assert is_verbatim(value, PARAGRAPH), (
            f"{slot} is not a span of what the founder wrote: {value!r}"
        )


def test_a_paraphrase_is_demoted_to_a_guess_never_taken_as_said(monkeypatch):
    """The charter rule enforced in Python, not asked of the model: a
    `said` value that is not a span of the paragraph has been rewritten,
    and a rewrite is the model's sentence, not the founder's. It is still
    offered — as a proposal to confirm."""
    import ai_venture_studio.providers.base as base

    class _Paraphraser:
        def complete(self, **kwargs):
            return (
                "said:\n"
                "  who: a two-person team that loses work in chat\n"
                "  actions: Anyone should be able to add a task\n"
                "guesses: []\n"
            )

    monkeypatch.setattr(base, "get_provider", lambda name: _Paraphraser())
    monkeypatch.setattr(
        "ai_venture_studio.providers.get_provider", lambda name: _Paraphraser()
    )
    extraction = extract_intake(PARAGRAPH, provider="mock")

    assert "who" not in extraction.said, "a paraphrase was taken as their words"
    assert "actions" in extraction.said  # this one really is a span
    assert [g.slot for g in extraction.guesses] == ["who"]


def test_at_most_two_guesses_are_ever_proposed(monkeypatch):
    """Two is a conversation; six is the form we just replaced."""
    class _Overeager:
        def complete(self, **kwargs):
            return "said: {}\nguesses:\n" + "".join(
                f"  - slot: {slot}\n    value: something\n    why: because\n"
                for slot in INTAKE_SLOTS
            )

    monkeypatch.setattr(
        "ai_venture_studio.providers.get_provider", lambda name: _Overeager()
    )
    assert len(extract_intake(PARAGRAPH, provider="mock").guesses) == 2


def test_an_unparseable_extraction_falls_back_to_asking_everything(monkeypatch):
    class _Rambler:
        def complete(self, **kwargs):
            return "Sure! Here's what I think about your product idea…"

    monkeypatch.setattr(
        "ai_venture_studio.providers.get_provider", lambda name: _Rambler()
    )
    extraction = extract_intake(PARAGRAPH, provider="mock")
    assert extraction.said == {} and extraction.guesses == []


def test_said_slots_count_as_answered_and_gaps_are_what_gets_asked(workspace):
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(said={"who": "The two of us", "actions": "add a task"},
                   guesses=[]),
        QUESTIONS,
    )
    turns = load_thread(workspace)
    assert next_intake_slot(turns) == "must", "an answered slot was asked again"


# ── the charter rule ─────────────────────────────────────────────────────


def test_a_guess_never_lands_in_the_fdr_unconfirmed(workspace):
    """The single most important assertion in this file."""
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(
            said={"who": "The two of us"},
            guesses=[Guess(slot="success", value="we stop losing tasks",
                           why="implied by the first sentence")],
        ),
        QUESTIONS,
    )
    fdr = compose_fdr(load_thread(workspace), "en")

    assert "The two of us" in fdr                 # SAID: their words
    assert "we stop losing tasks" not in fdr      # GUESS: not theirs
    assert "not answered" in fdr                  # the gap stays visible


def test_a_confirmed_guess_becomes_an_answer(workspace, client):
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(said={}, guesses=[
            Guess(slot="success", value="we stop losing tasks", why="implied")
        ]),
        QUESTIONS,
    )
    client.post("/chat/guess", data={"accept": "1"}, follow_redirects=False)

    fdr = compose_fdr(load_thread(workspace), "en")
    assert "we stop losing tasks" in fdr
    assert pending_guess(load_thread(workspace)) is None


def test_a_corrected_guess_lands_as_the_founders_words_not_the_proposal(
    workspace, client
):
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(said={}, guesses=[
            Guess(slot="success", value="we stop losing tasks", why="implied")
        ]),
        QUESTIONS,
    )
    client.post("/chat/guess", data={"answer": "we both use it every day"},
                follow_redirects=False)

    fdr = compose_fdr(load_thread(workspace), "en")
    assert "we both use it every day" in fdr
    assert "we stop losing tasks" not in fdr


def test_a_declined_guess_does_not_pend_forever(workspace, client):
    """Neither confirmed nor corrected. It must not become an answer, and
    it must not trap the conversation on the same proposal."""
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(said={}, guesses=[
            Guess(slot="success", value="we stop losing tasks", why="implied")
        ]),
        QUESTIONS,
    )
    client.post("/chat/guess", data={"answer": ""}, follow_redirects=False)

    assert pending_guess(load_thread(workspace)) is None
    assert "we stop losing tasks" not in compose_fdr(load_thread(workspace), "en")


def test_guesses_are_resolved_one_at_a_time(workspace):
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(said={}, guesses=[
            Guess(slot="constraints", value="phone first", why=""),
            Guess(slot="success", value="we stop losing tasks", why=""),
        ]),
        QUESTIONS,
    )
    first = pending_guess(load_thread(workspace))
    assert first.slot == "constraints"
    studio_chat.resolve_guess(workspace, first, "phone first", "q")
    assert pending_guess(load_thread(workspace)).slot == "success"


def test_a_pending_guess_is_never_answered_by_the_plain_composer(workspace, client):
    """"yes" is not a description of anybody's product. The composer is not
    even rendered while a proposal is open."""
    append_turn(workspace, "assistant", "open?", slot=OPEN)
    append_turn(workspace, "user", PARAGRAPH, slot=OPEN)
    apply_extraction(
        workspace,
        Extraction(said={}, guesses=[
            Guess(slot="success", value="we stop losing tasks", why="implied")
        ]),
        QUESTIONS,
    )
    page = client.get("/chat").text
    assert "action=/chat/guess" in page
    assert "This one is a guess" in page

    client.post("/chat", data={"answer": "yes"}, follow_redirects=False)
    assert "yes" not in compose_fdr(load_thread(workspace), "en").replace(
        "In your own words", ""
    ).split("## 1.")[1]


# ── through the real app ─────────────────────────────────────────────────


def test_one_paragraph_produces_said_and_guess_rows_on_the_page(client):
    client.get("/chat")
    page = client.post("/chat", data={"answer": PARAGRAPH},
                       follow_redirects=True).text

    assert "Taken from what you wrote" in page
    assert "SAID" in page and "GUESS" in page
    assert "The two of us keep losing tasks in chat" in page


def test_the_paragraph_itself_is_kept_verbatim_in_the_document(client, workspace):
    client.get("/chat")
    client.post("/chat", data={"answer": PARAGRAPH}, follow_redirects=True)
    fdr = compose_fdr(load_thread(workspace), "en")
    assert PARAGRAPH in fdr, "the founder's own framing was thrown away"


def test_the_extraction_is_one_call_and_is_guarded_against_a_double_submit(
    workspace, monkeypatch
):
    """Same in-flight rule as every other model call on this surface: a
    second submit lands on the working page, not on a second extraction."""
    import threading

    started, release = threading.Event(), threading.Event()
    calls = []

    def slow(paragraph, **kwargs):
        calls.append(paragraph)
        started.set()
        release.wait(timeout=10)
        return Extraction()

    monkeypatch.setattr(studio_chat, "extract_intake", slow)
    client = TestClient(
        create_studio_app(workspace, provider="mock"),
        raise_server_exceptions=False,
    )
    client.get("/chat")
    first = threading.Thread(
        target=lambda: client.post("/chat", data={"answer": PARAGRAPH})
    )
    first.start()
    try:
        assert started.wait(timeout=10)
        second = client.post("/chat", data={"answer": PARAGRAPH},
                             follow_redirects=True)
        assert "Working on it" in second.text
    finally:
        release.set()
        first.join(timeout=10)

    assert len(calls) == 1


def test_an_extraction_failure_leaves_the_paragraph_and_falls_back(
    workspace, monkeypatch
):
    def boom(paragraph, **kwargs):
        raise RuntimeError("529 overloaded_error")

    monkeypatch.setattr(studio_chat, "extract_intake", boom)
    client = TestClient(
        create_studio_app(workspace, provider="mock"),
        raise_server_exceptions=False,
    )
    client.get("/chat")
    page = client.post("/chat", data={"answer": PARAGRAPH},
                       follow_redirects=True).text
    assert "did not finish" in page

    turns = load_thread(workspace)
    assert turns[-1].text == PARAGRAPH, "their words were lost"
    # …and the next visit simply asks the six, one at a time.
    assert "1 / 6" in client.get("/chat").text


def test_a_thread_started_before_the_open_prompt_existed_still_works(
    workspace, client
):
    """Existing conversations must not break: a thread that is already
    mid-flight keeps the one-at-a-time path it began with."""
    append_turn(workspace, "assistant", "who is it for?", slot="who")
    append_turn(workspace, "user", "small studios")

    turns = load_thread(workspace)
    assert next_question_slot(turns) == "actions"  # not the open prompt
    page = client.get("/chat").text
    assert "2 / 6" in page
    assert "is plenty" not in page, "an in-flight thread was restarted"


def test_the_form_door_is_untouched(client):
    page = client.get("/?form=1").text
    assert "<textarea name=fdr" in page
    assert "Taken from what you wrote" not in page


def test_said_pairs_do_not_render_as_a_conversation_that_never_happened(client):
    """The synthetic question a SAID pair carries is bookkeeping. Showing
    it as an assistant bubble would show the founder a dialogue they were
    never part of."""
    client.get("/chat")
    page = client.post("/chat", data={"answer": PARAGRAPH},
                       follow_redirects=True).text
    assert page.count("Who is this for?") <= 1  # the sidebar label, not a bubble
    assert "msg-a" in page  # the real open prompt IS a bubble


def test_the_sidebar_shows_what_the_document_would_hold(client):
    client.get("/chat")
    page = client.post("/chat", data={"answer": PARAGRAPH},
                       follow_redirects=True).text
    # The sidebar reads the composed document, so a SAID value is filled…
    assert "The two of us keep losing tasks in chat" in page
    # …and the guessed one is not: it appears only as a proposal, never as
    # a filled section of the document being written.
    assert "<div class=val>people come back" not in page


def test_kinds_are_recorded_in_the_thread(client, workspace):
    client.get("/chat")
    client.post("/chat", data={"answer": PARAGRAPH}, follow_redirects=True)
    kinds = {turn.kind for turn in load_thread(workspace)}
    assert SAID in kinds and GUESS in kinds
    for question, answer in pairs(load_thread(workspace)):
        if question.kind == SAID:
            assert is_verbatim(answer.text, PARAGRAPH)
