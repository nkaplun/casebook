"""Slack rejects a whole message if any block breaks a size limit."""
from casebook.search import Answer
from casebook.slack_blocks import (FIELD_LIMIT, MAX_BLOCKS, SECTION_LIMIT, answer_blocks,
                                   paginate, split_text)


def card(i, results="r"):
    return {"case_study": f"Case {i}", "client": f"Client {i}", "link": "https://example.com",
            "nda": "No", "summary": "s", "results": results, "why_it_fits": "w"}


def test_long_text_is_split_under_the_limit_at_a_sentence():
    text = ("This is a sentence. " * 400).strip()
    chunks = split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= SECTION_LIMIT for c in chunks)
    assert all(c.endswith(".") for c in chunks)


def test_every_block_respects_slack_limits():
    answer = Answer(intro="i", cases=[card(i, results="x" * 5000) for i in range(30)], note="n")
    for page in paginate(answer_blocks(answer)):
        assert len(page) <= MAX_BLOCKS
        assert page[0]["type"] != "divider" and page[-1]["type"] != "divider"
        for b in page:
            if "text" in b:
                assert len(b["text"]["text"]) <= SECTION_LIMIT
            for f in b.get("fields", []):
                assert len(f["text"]) <= FIELD_LIMIT


def test_nda_case_is_flagged_and_missing_link_says_so():
    c = card(1) | {"nda": "Yes", "link": ""}
    fields = answer_blocks(Answer(cases=[c]))[1]["fields"]
    assert "coming soon" in fields[0]["text"]
    assert "do not share" in fields[1]["text"]
