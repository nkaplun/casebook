"""Building a pitch deck from a prospect brief.

    brief -> model picks cases and writes slide copy -> validate -> (one repair
    round if needed) -> render .pptx

Validation is the important part. A deck goes in front of a client, so a number
that is not in the source case study is a made-up claim with our name on it.
`validate_deck()` checks every number on every slide against the case it came
from, and checks every text field against the size of its box on the slide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import prompts
from .corpus import Corpus
from .llm import LLM, Usage, parse_json

MAX_REPAIRS = 1


class DeckError(Exception):
    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


@dataclass
class DeckDraft:
    content: dict
    attempts: int
    usage: Usage = field(default_factory=Usage)


def draft_deck(brief: str, corpus: Corpus, llm: LLM) -> DeckDraft:
    """Ask the model for slide copy, and send it back once with a list of
    problems if validation fails. Raises DeckError if it still fails."""
    messages = [{"role": "user", "content": f"PROSPECT BRIEF:\n{brief}"}]
    total = Usage()
    for attempt in range(1, MAX_REPAIRS + 2):
        result = llm.complete(prompts.DECK_SYSTEM, corpus.context(brief), messages,
                              max_tokens=3000)
        total.input += result.usage.input
        total.cached += result.usage.cached
        total.output += result.usage.output
        content = parse_json(result.text)
        if not content:
            problems = ["The response was not valid JSON."]
        elif not content.get("cases"):
            raise DeckError(content.get("note") or "No case studies fit this brief.")
        else:
            problems = validate_deck(content, corpus)
            if not problems:
                return DeckDraft(content, attempts=attempt, usage=total)
        messages += [
            {"role": "assistant", "content": result.text or "{}"},
            {"role": "user", "content": "Fix these problems and return the full JSON "
             "again:\n- " + "\n- ".join(problems)},
        ]
    raise DeckError("The deck still failed validation after a repair round.", problems)


_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> list[str]:
    return _NUMBER_RE.findall(text or "")


def validate_deck(deck: dict, corpus: Corpus) -> list[str]:
    """Every problem with a drafted deck, as sentences the model can act on.
    Returns [] when the deck is safe to build."""
    problems: list[str] = []
    L = prompts.LIMITS

    def check_len(label: str, text: str, limit: int) -> None:
        if not (text or "").strip():
            problems.append(f"{label} is empty.")
        elif len(text) > limit:
            problems.append(f"{label} is {len(text)} chars, over the {limit} limit: {text!r}")

    check_len("deck_title", deck.get("deck_title", ""), L["deck_title"])
    check_len("deck_subtitle", deck.get("deck_subtitle", ""), L["deck_subtitle"])

    cases = deck.get("cases") or []
    if len(cases) > prompts.MAX_CASES:
        problems.append(f"{len(cases)} cases chosen; the maximum is {prompts.MAX_CASES}.")

    chosen_text = []
    seen = set()
    for i, c in enumerate(cases, start=1):
        title = c.get("corpus_title", "")
        record = corpus.get(title)
        tag = f"case {i} ({title or 'unnamed'})"
        if not record:
            problems.append(f"{tag} is not a case study in the library. Use a real title, verbatim.")
            continue
        if record["title"] in seen:
            problems.append(f"{tag} is chosen twice.")
        seen.add(record["title"])
        source = set(numbers_in(record["text"]))
        chosen_text.append(source)

        check_len(f"{tag} headline", c.get("headline", ""), L["headline"])
        check_len(f"{tag} challenge", c.get("challenge", ""), L["challenge"])
        metrics = c.get("metrics") or []
        delivered = c.get("delivered") or []
        if len(metrics) != prompts.N_METRICS:
            problems.append(f"{tag} has {len(metrics)} metrics; it needs exactly {prompts.N_METRICS}.")
        if len(delivered) != prompts.N_DELIVERED:
            problems.append(f"{tag} has {len(delivered)} delivered items; it needs exactly {prompts.N_DELIVERED}.")
        for j, m in enumerate(metrics, start=1):
            check_len(f"{tag} metric {j} value", m.get("value", ""), L["metric_value"])
            check_len(f"{tag} metric {j} caption", m.get("caption", ""), L["metric_caption"])
        for j, d in enumerate(delivered, start=1):
            check_len(f"{tag} delivered item {j}", d, L["delivered"])

        # The check that matters most: every number on this case's slide must
        # appear in this case's own text. Not another case's, not the brief's.
        slide_text = " ".join([c.get("headline", ""), c.get("challenge", ""),
                               *[m.get("value", "") + " " + m.get("caption", "") for m in metrics],
                               *delivered])
        for n in numbers_in(slide_text):
            if n not in source:
                problems.append(f"{tag} states {n!r}, which is not in that case study. "
                                "Use only numbers from its text, exactly as written.")

    # The subtitle may cite a number only if some chosen case supports it.
    for n in numbers_in(deck.get("deck_subtitle", "")):
        if not any(n in t for t in chosen_text):
            problems.append(f"deck_subtitle states {n!r}, which no chosen case study supports.")
    return problems


# --- rendering ---------------------------------------------------------------
# A plain, readable layout built from scratch with python-pptx, so the project
# runs without any template file or Google account.

def render_pptx(deck: dict, corpus: Corpus, path: str) -> str:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    INK, MUTED, ACCENT, PAPER = (RGBColor(0x14, 0x1B, 0x2D), RGBColor(0x5B, 0x64, 0x76),
                                 RGBColor(0x1F, 0x6F, 0xEB), RGBColor(0xF4, 0xF6, 0xFA))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]

    def text(slide, x, y, w, h, value, size, color=INK, bold=False):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        lines = value if isinstance(value, list) else [value]
        for k, line in enumerate(lines):
            p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
            p.text = line
            p.font.size, p.font.bold, p.font.color.rgb = Pt(size), bold, color
            p.space_after = Pt(8)
        return box

    def fill(slide, x, y, w, h, color):
        shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        return shape

    # Title slide
    s = prs.slides.add_slide(blank)
    fill(s, 0, 0, 13.333, 7.5, INK)
    fill(s, 0.8, 3.1, 1.2, 0.08, ACCENT)
    text(s, 0.8, 1.6, 11, 1.4, deck["deck_title"], 44, RGBColor(0xFF, 0xFF, 0xFF), bold=True)
    text(s, 0.8, 3.4, 11, 1, deck["deck_subtitle"], 22, RGBColor(0xC9, 0xD1, 0xE0))
    text(s, 0.8, 6.5, 11, 0.5, "Brightline Engineering", 14, RGBColor(0x8A, 0x94, 0xA8))

    # One slide per case
    for c in deck["cases"]:
        record = corpus.get(c["corpus_title"])
        s = prs.slides.add_slide(blank)
        text(s, 0.7, 0.45, 12, 0.4, f"{record['client']}  ·  {record['industry']}", 14, ACCENT, bold=True)
        text(s, 0.7, 0.85, 12, 1.2, c["headline"], 30, bold=True)
        text(s, 0.7, 2.0, 5.6, 0.4, "The challenge", 14, MUTED, bold=True)
        text(s, 0.7, 2.4, 5.6, 2.2, c["challenge"], 16)
        text(s, 0.7, 4.7, 5.6, 0.4, "What we delivered", 14, MUTED, bold=True)
        text(s, 0.7, 5.1, 5.6, 2, [f"•  {d}" for d in c["delivered"]], 14)
        for k, m in enumerate(c["metrics"]):
            y = 2.0 + k * 1.75
            fill(s, 6.9, y, 5.7, 1.5, PAPER)
            text(s, 7.15, y + 0.15, 5.3, 0.8, m["value"], 36, ACCENT, bold=True)
            text(s, 7.15, y + 0.9, 5.3, 0.5, m["caption"], 14, MUTED)
        if (record.get("nda") or "").lower() == "yes":
            text(s, 0.7, 7.0, 12, 0.3, "Client name withheld under NDA.", 10, MUTED)

    # Sources slide: every case links back to its full write-up
    s = prs.slides.add_slide(blank)
    text(s, 0.7, 0.6, 12, 0.8, "Sources", 30, bold=True)
    lines = []
    for c in deck["cases"]:
        record = corpus.get(c["corpus_title"])
        lines.append(f"{record['title']}  ·  {record.get('link') or 'Full write-up available on request'}")
    text(s, 0.7, 1.6, 12, 5, lines, 16)

    prs.save(path)
    return path
