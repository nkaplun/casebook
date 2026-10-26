"""Answering a question: the model picks the cases, Python checks its work.

    question -> model returns JSON -> drop invented cases -> restore facts from
    the library -> Answer

The prompt tells the model not to invent case studies, but a prompt is not a
guarantee. The two checks after the model are deterministic, so they hold even
when the model ignores its instructions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from . import prompts
from .corpus import AUTHORITATIVE_FIELDS, Corpus
from .llm import LLM, Usage, parse_json

log = logging.getLogger(__name__)

NO_MATCH_NOTE = "I don't have a case study that matches that."
FILTERED_NOTE = "(Only case studies found in the library are shown.)"
COLD_REFERENT_NOTE = (
    "I don't have earlier context in this conversation, so I'm not sure which "
    "case study you mean. Tell me the case or topic and I'll pull it up."
)


@dataclass
class Answer:
    intro: str = ""
    cases: list[dict] = field(default_factory=list)
    note: str = ""
    deck_request: dict | None = None  # set when the model asked to build a deck instead
    usage: Usage = field(default_factory=Usage)
    dropped: list[str] = field(default_factory=list)    # invented titles the check removed
    corrected: list[str] = field(default_factory=list)  # "title.field" values overwritten


def ask(question: str, corpus: Corpus, llm: LLM, history: list[dict] | None = None) -> Answer:
    if is_cold_referent(question, history):
        return Answer(note=COLD_REFERENT_NOTE)
    result = llm.complete(prompts.SEARCH_SYSTEM, corpus.context(question),
                          build_messages(question, history), tools=[prompts.DECK_TOOL])
    if result.tool_call and result.tool_call["name"] == prompts.DECK_TOOL["name"]:
        return Answer(deck_request=result.tool_call["input"], usage=result.usage)
    payload = parse_json(result.text)
    if not payload:
        return Answer(note="Sorry, I couldn't read my own answer. Try asking again.",
                      usage=result.usage)
    answer = Answer(intro=payload.get("intro") or "", cases=payload.get("cases") or [],
                    note=payload.get("note") or "", usage=result.usage)
    reject_fabricated(answer, corpus)
    restore_fields(answer, corpus)
    return answer


def reject_fabricated(answer: Answer, corpus: Corpus) -> None:
    """Drop any case whose title is not in the library. If that leaves nothing,
    say so honestly instead of showing an empty list."""
    kept = [c for c in answer.cases if corpus.get(c.get("case_study", ""))]
    answer.dropped = [c.get("case_study") or "(unnamed)" for c in answer.cases if c not in kept]
    if not answer.dropped:
        return
    log.warning("dropped %d invented case(s): %s", len(answer.dropped), answer.dropped)
    answer.cases = kept
    if not kept:
        answer.intro, answer.note = "", NO_MATCH_NOTE
    else:
        answer.note = f"{answer.note}\n\n{FILTERED_NOTE}".strip()


def restore_fields(answer: Answer, corpus: Corpus) -> None:
    """Overwrite client, industry, link, and NDA with the library's values. The
    model was asked to copy them, and usually does, but a wrong NDA flag or a
    made-up link is exactly the mistake a salesperson would forward to a client."""
    for c in answer.cases:
        record = corpus.get(c["case_study"])
        c["case_study"] = record["title"]
        for f in AUTHORITATIVE_FIELDS:
            truth = (record.get(f) or "").strip()
            supplied = (c.get(f) or "").strip()
            if supplied and supplied != truth and not _is_placeholder(f, supplied, truth):
                answer.corrected.append(f"{record['title']}.{f}")
            c[f] = truth


def _is_placeholder(f: str, supplied: str, truth: str) -> bool:
    # The model was shown "Link coming soon" for an empty link and copied it. Not an error.
    return f == "link" and not truth and supplied.lower() == "link coming soon"


def build_messages(question: str, history: list[dict] | None = None) -> list[dict]:
    """Clean chat history into what both APIs accept: only non-empty user and
    assistant turns, starting with a user turn, never two of the same role in a
    row. Chat history from Slack breaks all three rules regularly."""
    raw = list(history or []) + [{"role": "user", "content": question}]
    cleaned = [{"role": m["role"], "content": (m.get("content") or "").strip()}
               for m in raw
               if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    if cleaned and cleaned[0]["role"] == "assistant":
        cleaned.insert(0, {"role": "user", "content": "(Continuing our earlier conversation.)"})
    merged: list[dict] = []
    for m in cleaned:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(m)
    return merged


# "Tell me more about that one" with no earlier conversation has nothing to point
# at. Sent to the model, it picks some real case and answers confidently, which
# the fabrication check cannot catch because the case IS real. So we answer
# before reaching the model.
_POINTER_RE = re.compile(r"\b(that|this|those|these|it|them|the (last|previous|first|other))\b", re.I)
_FILLER = frozenset("""
a about again an and any are can could describe detail details do does elaborate
explain first for give how i is it last me more of on one ones other please
previous say show tell than that the them these this those what which you
""".split())


def is_cold_referent(question: str, history: list[dict] | None) -> bool:
    if history:
        return False
    if not _POINTER_RE.search(question):
        return False
    words = re.findall(r"[a-z']+", question.lower())
    return all(w in _FILLER for w in words)
