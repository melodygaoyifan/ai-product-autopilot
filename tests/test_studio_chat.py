"""The conversational FDR intake.

The form asks for 4000 characters at once, and the clarify loop then asks
you to edit the right lines inside it. This covers the alternative door:
one question, one answer, FDR.md composed deterministically — and, most
importantly, that the conversation can always be left.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio import studio_chat
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.studio_chat import (
    CLARIFY,
    INTAKE_SLOTS,
    MAX_CLARIFY_ROUNDS,
    append_turn,
    clarify_rounds_used,
    compose_fdr,
    intake_complete,
    load_thread,
    next_intake_slot,
    open_question,
    pairs,
)
from ai_venture_studio.upstream import init_workspace


@pytest.fixture
def workspace(tmp_path):
    return init_workspace(tmp_path / "chat", "chat", "web")


@pytest.fixture
def client(workspace):
    return TestClient(create_studio_app(workspace, provider="mock"))


# ── the state machine, without the web layer ─────────────────────────────

def test_the_six_questions_are_asked_in_order(workspace):
    assert next_intake_slot([]) == INTAKE_SLOTS[0]
    for index, slot in enumerate(INTAKE_SLOTS):
        turns = load_thread(workspace)
        assert next_intake_slot(turns) == slot, f"question {index} out of order"
        append_turn(workspace, "assistant", f"q-{slot}", slot=slot)
        append_turn(workspace, "user", f"a-{slot}")
    assert next_intake_slot(load_thread(workspace)) is None
    assert intake_complete(load_thread(workspace))


def test_an_open_question_is_not_asked_twice(workspace):
    append_turn(workspace, "assistant", "who is it for", slot="who")
    turns = load_thread(workspace)
    assert open_question(turns) is not None
    assert pairs(turns) == []  # unanswered, so not a pair yet
    append_turn(workspace, "user", "small studios")
    assert open_question(load_thread(workspace)) is None


def test_the_fdr_is_composed_from_the_answers(workspace):
    for slot in INTAKE_SLOTS:
        append_turn(workspace, "assistant", f"q-{slot}", slot=slot)
        append_turn(workspace, "user", f"answer about {slot}")
    fdr = compose_fdr(load_thread(workspace), "en")
    for slot in INTAKE_SLOTS:
        assert f"answer about {slot}" in fdr
    assert fdr.startswith("# Product Requirements (FDR)")
    assert "## 1. Who is this for?" in fdr
    assert "## 6. What does success look like?" in fdr


def test_an_unanswered_section_is_visibly_blank_not_omitted(workspace):
    """A gap the assessor can see beats a document that looks complete."""
    append_turn(workspace, "assistant", "q", slot="who")
    append_turn(workspace, "user", "founders")
    fdr = compose_fdr(load_thread(workspace), "en")
    assert "## 3. Must-have features" in fdr
    assert "not answered" in fdr


def test_follow_up_answers_land_in_their_own_section(workspace):
    for slot in INTAKE_SLOTS:
        append_turn(workspace, "assistant", f"q-{slot}", slot=slot)
        append_turn(workspace, "user", f"a-{slot}")
    append_turn(workspace, "assistant", "Where do reviews live?", slot=CLARIFY)
    append_turn(workspace, "user", "under each product")
    fdr = compose_fdr(load_thread(workspace), "en")
    assert "Follow-up answers" in fdr
    assert "Where do reviews live?" in fdr
    assert "under each product" in fdr


def test_the_composer_writes_the_founders_words_verbatim(workspace):
    """No model call, no paraphrase: what they typed is what ships."""
    append_turn(workspace, "assistant", "q", slot="who")
    append_turn(workspace, "user", "中国年轻人，模仿韩国的多巴胺购物网站")
    assert "中国年轻人，模仿韩国的多巴胺购物网站" in compose_fdr(
        load_thread(workspace), "zh"
    )


def test_clarify_rounds_are_counted_in_fives(workspace):
    assert clarify_rounds_used([]) == 0
    for index in range(5):
        append_turn(workspace, "assistant", f"q{index}", slot=CLARIFY)
        append_turn(workspace, "user", f"a{index}")
    assert clarify_rounds_used(load_thread(workspace)) == 1
    append_turn(workspace, "assistant", "q6", slot=CLARIFY)
    append_turn(workspace, "user", "a6")
    assert clarify_rounds_used(load_thread(workspace)) == 2


def test_a_corrupt_line_does_not_destroy_the_conversation(workspace):
    append_turn(workspace, "assistant", "q", slot="who")
    with studio_chat.path_for(workspace).open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    append_turn(workspace, "user", "still here")
    turns = load_thread(workspace)
    assert [turn.text for turn in turns] == ["q", "still here"]


def test_an_unknown_role_is_refused(workspace):
    with pytest.raises(ValueError, match="unknown role"):
        append_turn(workspace, "narrator", "hello")


# ── the flow, through the real app ───────────────────────────────────────

def test_the_conversation_asks_one_question_at_a_time(client):
    page = client.get("/chat").text
    assert "1 / 6" in page
    assert page.count("<textarea") == 1


def test_answering_advances_and_records_both_sides(client, workspace):
    client.get("/chat")
    client.post("/chat", data={"answer": "small studios"}, follow_redirects=True)
    turns = load_thread(workspace)
    assert turns[0].role == "assistant" and turns[0].slot == "who"
    assert turns[1].role == "user" and turns[1].text == "small studios"


def test_a_skipped_question_is_recorded_and_does_not_block(client, workspace):
    client.get("/chat")
    client.post("/chat", data={"answer": "", "skip": "1"}, follow_redirects=True)
    turns = load_thread(workspace)
    assert pairs(turns)  # the question counts as answered
    assert next_intake_slot(turns) == INTAKE_SLOTS[1]


def test_walking_the_whole_conversation_writes_a_real_fdr(client, workspace):
    for slot in INTAKE_SLOTS:
        client.get("/chat")
        client.post("/chat", data={"answer": f"about {slot}"},
                    follow_redirects=True)
    fdr = (workspace / "FDR.md").read_text(encoding="utf-8")
    for slot in INTAKE_SLOTS:
        assert f"about {slot}" in fdr


def test_the_founder_can_always_leave_the_loop(client, workspace):
    """The anti-stuck guarantee: 'enough' writes the FDR and hands over,
    from any point, with no further questions."""
    client.get("/chat")
    client.post("/chat", data={"answer": "founders"}, follow_redirects=True)
    page = client.post("/chat/enough", follow_redirects=True).text
    assert "founders" in page
    assert (workspace / "FDR.md").read_text(encoding="utf-8").count("founders") == 1


def test_the_clarify_loop_is_bounded(workspace):
    """Past MAX_CLARIFY_ROUNDS the conversation stops asking. Without this a
    hard-to-satisfy assessor could question a founder indefinitely."""
    for slot in INTAKE_SLOTS:
        append_turn(workspace, "assistant", f"q-{slot}", slot=slot)
        append_turn(workspace, "user", f"a-{slot}")
    for index in range(5 * MAX_CLARIFY_ROUNDS):
        append_turn(workspace, "assistant", f"c{index}", slot=CLARIFY)
        append_turn(workspace, "user", f"ca{index}")
    assert clarify_rounds_used(load_thread(workspace)) >= MAX_CLARIFY_ROUNDS

    client = TestClient(create_studio_app(workspace, provider="mock"))
    page = client.get("/chat", follow_redirects=True).text
    assert "enough questions" in page.lower() or "够了" in page or "差不多" in page


def test_restart_clears_the_thread(client, workspace):
    """Restart drops every answer and begins again at question one — the
    redirect immediately re-asks it, so the thread holds that question and
    nothing the founder previously said."""
    client.get("/chat")
    client.post("/chat", data={"answer": "founders"}, follow_redirects=True)
    assert load_thread(workspace)

    client.post("/chat/restart", follow_redirects=True)

    turns = load_thread(workspace)
    assert [turn.text for turn in turns if turn.role == "user"] == []
    assert next_intake_slot(turns) == INTAKE_SLOTS[0]
    assert "founders" not in studio_chat.transcript(turns)


def test_the_form_still_works_and_links_to_the_conversation(client):
    """The conversation became the default, but the form is not removed —
    that would strand anyone who prefers to write the whole thing at once."""
    page = client.get("/?form=1").text
    assert "<textarea name=fdr" in page  # the whole-document form field
    assert "/chat" in page


def test_an_existing_fdr_is_offered_back_not_interviewed_over(client, workspace):
    """Chat is the front door now, so most people arriving here already have
    an FDR. Interviewing them about a document they wrote would be absurd."""
    handwritten = "# My product\n\nA long FDR I spent an hour on.\n"
    (workspace / "FDR.md").write_text(handwritten, encoding="utf-8")

    page = client.get("/chat").text

    assert "already have a requirements document" in page
    assert "A long FDR I spent an hour on." in page
    assert "/chat?start=1" in page  # …and starting over is still offered
    assert load_thread(workspace) == []  # nothing was asked yet


def test_an_existing_fdr_is_never_destroyed_by_the_conversation(client, workspace):
    """Someone with a hand-written FDR chooses to start over anyway. Their
    words must survive that."""
    handwritten = "# My product\n\nA long FDR I spent an hour on.\n"
    (workspace / "FDR.md").write_text(handwritten, encoding="utf-8")

    client.get("/chat?start=1")
    client.post("/chat", data={"answer": "founders"}, follow_redirects=True)
    page = client.post("/chat/enough", follow_redirects=True).text

    assert (workspace / "FDR-before-chat.md").read_text(
        encoding="utf-8"
    ) == handwritten
    assert "FDR-before-chat.md" in page
    assert "founders" in (workspace / "FDR.md").read_text(encoding="utf-8")


def test_the_backup_is_not_overwritten_by_a_second_pass(client, workspace):
    """The FIRST version is the one worth keeping; a later pass must not
    clobber the backup with conversation output."""
    handwritten = "# original\n\nthe words that matter\n"
    (workspace / "FDR.md").write_text(handwritten, encoding="utf-8")
    client.get("/chat?start=1")
    client.post("/chat", data={"answer": "one"}, follow_redirects=True)
    client.post("/chat/enough", follow_redirects=True)
    client.post("/chat/restart", follow_redirects=True)
    client.post("/chat", data={"answer": "two"}, follow_redirects=True)
    client.post("/chat/enough", follow_redirects=True)

    assert (workspace / "FDR-before-chat.md").read_text(
        encoding="utf-8"
    ) == handwritten


def test_merely_opening_the_page_does_not_commit_you_to_the_conversation(
    client, workspace
):
    """Loading /chat asks question one, which put a turn in the thread. That
    made the thread look 'started', so a later visit interviewed a founder
    who already had an FDR instead of offering it back. Only an ANSWER
    starts a conversation."""
    client.get("/chat")  # a look around; no answer given
    (workspace / "FDR.md").write_text("# real\n\nreal content\n", encoding="utf-8")

    page = client.get("/chat").text

    assert "already have a requirements document" in page
    assert "real content" in page


def test_open_questions_become_the_conversation(client, workspace):
    """The whole point: assessor questions left by the form are asked here
    one at a time instead of handed back as a list to merge by hand."""
    (workspace / "FDR.md").write_text("# real\n\ncontent\n", encoding="utf-8")
    (workspace / "FDR-QUESTIONS.md").write_text(
        "# questions\n\n1. Where do reviews live?\n2. Is delivery animated?\n",
        encoding="utf-8",
    )

    page = client.get("/chat").text

    assert "Where do reviews live?" in page
    assert "Is delivery animated?" not in page  # one at a time


def test_a_clarify_only_conversation_extends_the_fdr(client, workspace):
    """It must APPEND to the founder's document, not replace it with six
    blank intake sections."""
    original = "# real\n\nthe product I described at length\n"
    (workspace / "FDR.md").write_text(original, encoding="utf-8")
    (workspace / "FDR-QUESTIONS.md").write_text(
        "# q\n\n1. Where do reviews live?\n", encoding="utf-8"
    )

    client.get("/chat")
    client.post("/chat", data={"answer": "under each product"},
                follow_redirects=True)
    client.post("/chat/enough", follow_redirects=True)

    fdr = (workspace / "FDR.md").read_text(encoding="utf-8")
    assert "the product I described at length" in fdr
    assert "under each product" in fdr
    assert "not answered" not in fdr


def test_chat_is_the_default_door(workspace):
    from ai_venture_studio.studio import create_studio_app

    page = TestClient(create_studio_app(workspace, provider="mock")).get("/").text
    assert "One question at a time" in page
    assert "/?form=1" in page  # the form is one click away


def test_the_form_can_still_be_the_default(workspace):
    from ai_venture_studio.studio import create_studio_app

    app = create_studio_app(workspace, provider="mock", entry="form")
    assert "<textarea name=fdr" in TestClient(app).get("/").text


def test_an_unknown_entry_is_refused_loudly(workspace):
    from ai_venture_studio.studio import create_studio_app

    with pytest.raises(ValueError, match="unknown entry"):
        create_studio_app(workspace, provider="mock", entry="carrier-pigeon")


def test_the_conversation_is_a_veneer_over_the_same_fdr(client, workspace):
    """State lives in workspace files, not in the process: a fresh app on the
    same directory continues the same conversation."""
    client.get("/chat")
    client.post("/chat", data={"answer": "founders"}, follow_redirects=True)
    reopened = TestClient(create_studio_app(workspace, provider="mock"))
    assert "founders" in reopened.get("/chat").text
