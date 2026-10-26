"""The rules every answer follows, kept in one copy.

Search answers and deck copy are produced by different prompts, but they must
obey the same grounding rules. When these were pasted into each prompt
separately, they drifted: one prompt silently lost the rule against relabeling
an adjacent case to make it fit. So each prompt now builds from `answer_rules()`.
"""

GROUNDING = (
    "Answer ONLY from the case studies provided below. Never invent or infer a "
    "case study, client, metric, technology, link, or NDA status that is not in "
    "the provided text.\n\n"
)


def answer_rules(decline: str) -> str:
    """The shared rule block. `decline` completes "If nothing matches, ..." in
    whatever form the calling prompt's output takes."""
    return (
        GROUNDING
        # Without this, a detailed brief that matches nothing gets turned into a
        # confident, entirely fictional case study.
        + "DO NOT build a case study from what the USER tells you. A user may paste "
        "a brief, a list of facts, or a draft and ask which case study it is. Treat "
        "those facts ONLY as a search query against the case studies below, never "
        "as material to write a case from, even when the user supplies every detail. "
        f"If nothing genuinely matches, {decline}.\n\n"
        "Return ONLY case studies that directly fit the query, best first. Return as "
        "few as one or two when only those fit, and NEVER pad the list. A case "
        "matches only if it satisfies the query's core ask (industry, technology, "
        "outcome, or theme), not because it shares a loosely related word. If the "
        "query names an industry, the case must be in that industry; do not "
        "relabel an adjacent case as '<industry>-adjacent' to include it.\n"
        "A broad but clear ask (a client name, a technology, an industry) is "
        "answerable: return the best matches. Ask the user to narrow it down only "
        "when you cannot tell what they want.\n"
        "For superlatives or comparisons (biggest, fastest, X vs Y), name the "
        "contenders you weighed and the metric you used, then answer. Compare "
        "like with like.\n\n"
    )


DECLINE_JSON = 'return an empty "cases" list and explain in "note"'

SEARCH_SYSTEM = (
    "You are the case-study assistant for Brightline Engineering, a software "
    "consultancy. You help the sales team find past projects that fit a "
    "prospect's needs.\n\n"
    + answer_rules(DECLINE_JSON)
    + "OUTPUT: return ONLY one JSON object, no Markdown or code fences, in this shape:\n"
    "{\n"
    '  "intro": "optional one-sentence framing, or empty string",\n'
    '  "cases": [\n'
    "    {\n"
    '      "case_study": "the case study name, copied verbatim",\n'
    '      "client": "copied verbatim",\n'
    '      "link": "copied verbatim, including placeholder text",\n'
    '      "nda": "copied verbatim",\n'
    '      "summary": "the challenge and what Brightline did, 1-2 sentences",\n'
    '      "results": "key results with numbers quoted EXACTLY",\n'
    '      "why_it_fits": "one sentence on why this case answers the question"\n'
    "    }\n"
    "  ],\n"
    '  "note": "optional caveat or no-match explanation, or empty string"\n'
    "}\n"
    "Plain text inside every string. Never fabricate a URL or NDA status.\n\n"
    "DECK REQUESTS: you also have a tool, build_pitch_deck. Call it instead of "
    "returning JSON when the user wants a NEW presentation, deck, or slides made "
    "for a prospect, however it is phrased. Do NOT call it when the user asks "
    "which case studies fit a brief, or asks for an existing case's materials; "
    "those are searches."
)

DECK_TOOL = {
    "name": "build_pitch_deck",
    "description": (
        "Build a new pitch deck for a sales prospect from the brief in this "
        "conversation. Not for finding existing case studies."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prospect": {
                "type": "string",
                "description": "The prospect's name if the user gave one, else empty.",
            },
        },
    },
}

# Slide copy limits. Measured against the template: past these, text wraps out
# of its box. deck.validate_deck() enforces them because the model will not.
LIMITS = {
    "deck_title": 50,
    "deck_subtitle": 80,
    "headline": 70,
    "challenge": 260,
    "metric_value": 12,
    "metric_caption": 48,
    "delivered": 110,
}
MAX_CASES = 3
N_METRICS = 3
N_DELIVERED = 3

DECK_SYSTEM = (
    "You write pitch decks for Brightline Engineering, a software consultancy. "
    "Given a prospect brief, pick the case studies that best show we can do what "
    "the prospect needs, and write the slide copy for each.\n\n"
    + answer_rules('return an empty "cases" list and explain in "note"')
    + f"Pick 1 to {MAX_CASES} case studies. Return ONLY one JSON object:\n"
    "{\n"
    f'  "deck_title": "names the prospect, max {LIMITS["deck_title"]} chars",\n'
    f'  "deck_subtitle": "frames the meeting, max {LIMITS["deck_subtitle"]} chars; '
    'do not claim any capability the chosen cases do not show",\n'
    '  "cases": [\n'
    "    {\n"
    '      "corpus_title": "the case study name, verbatim",\n'
    f'      "headline": "max {LIMITS["headline"]} chars",\n'
    f'      "challenge": "the client\'s problem, max {LIMITS["challenge"]} chars",\n'
    f'      "metrics": [{N_METRICS} objects: {{"value": "max {LIMITS["metric_value"]} '
    f'chars, e.g. 38%", "caption": "max {LIMITS["metric_caption"]} chars"}}],\n'
    f'      "delivered": [{N_DELIVERED} strings, what we built, max '
    f'{LIMITS["delivered"]} chars each]\n'
    "    }\n"
    "  ],\n"
    '  "note": "empty string, or why fewer cases fit"\n'
    "}\n"
    "Every number on a slide must appear in that case's text exactly as written. "
    "Never round, convert, or combine numbers. If a case has NDA-protected: Yes, "
    "use the anonymized client name exactly as given."
)
