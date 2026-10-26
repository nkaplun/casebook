"""Turn an Answer into Slack Block Kit cards.

Slack has no table block, and a message that breaks any size limit is rejected
whole. So the model never writes Slack formatting; it returns JSON, and this
module builds cards that fit the limits, splitting into several messages when
an answer is long. Kept separate from the Slack connection so it can be tested
without Slack tokens.
"""
from __future__ import annotations

from .search import Answer

SECTION_LIMIT = 3000  # characters in a section's text
FIELD_LIMIT = 2000    # characters in one field
MAX_BLOCKS = 50       # blocks in one message


def split_text(text: str, limit: int = SECTION_LIMIT) -> list[str]:
    """Split text into pieces of at most `limit` characters, breaking at a
    paragraph, line, sentence, or word when one is reasonably close."""
    text = (text or "").strip()
    chunks = []
    while len(text) > limit:
        window = text[:limit]
        cut = limit
        for sep in ("\n\n", "\n", ". ", " "):
            i = window.rfind(sep)
            if i > limit // 2:
                cut = i + len(sep)
                break
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks + ([text] if text else [])


def _section(text: str) -> list[dict]:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": t}} for t in split_text(text)]


def _link(url: str) -> str:
    return f"<{url}|View case study>" if url.startswith("http") else "Link coming soon"


def answer_blocks(answer: Answer) -> list[dict]:
    blocks: list[dict] = []
    if answer.intro:
        blocks += _section(answer.intro)
    for c in answer.cases:
        nda = "🔒 Yes, do not share externally" if c["nda"].lower() == "yes" else "No"
        blocks += _section(f"*{c['client']}*\n{c['case_study']}")
        blocks.append({"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Link*\n{_link(c['link'])}"[:FIELD_LIMIT]},
            {"type": "mrkdwn", "text": f"*NDA*\n{nda}"[:FIELD_LIMIT]},
        ]})
        body = "\n".join(f"*{label}:* {c.get(key, '')}" for label, key in
                         (("Summary", "summary"), ("Results", "results"),
                          ("Why it fits", "why_it_fits")) if c.get(key))
        blocks += _section(body)
        blocks.append({"type": "divider"})
    if answer.note:
        blocks += _section(answer.note)
    while blocks and blocks[-1]["type"] == "divider":
        blocks.pop()
    return blocks


def paginate(blocks: list[dict], size: int = MAX_BLOCKS) -> list[list[dict]]:
    """Split into messages of at most `size` blocks, trimming dividers at the cuts."""
    pages = []
    for i in range(0, len(blocks), size):
        page = blocks[i:i + size]
        while page and page[0]["type"] == "divider":
            page = page[1:]
        while page and page[-1]["type"] == "divider":
            page = page[:-1]
        if page:
            pages.append(page)
    return pages
