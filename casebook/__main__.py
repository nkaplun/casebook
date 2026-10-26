"""Command line: ask a question, or build a deck.

    python -m casebook ask "Which fintech projects used machine learning?"
    python -m casebook deck "Regional bank, wants to cut fraud losses" -o pitch.pptx
"""
import argparse
import sys

from dotenv import load_dotenv

from .corpus import Corpus
from .deck import DeckError, draft_deck, render_pptx
from .llm import default_llm
from .search import ask


def print_answer(answer) -> None:
    if answer.intro:
        print(answer.intro, "\n")
    for c in answer.cases:
        print(f"{c['client']}: {c['case_study']}")
        print(f"  Link: {c['link'] or 'coming soon'}   NDA: {c['nda']}")
        print(f"  {c.get('summary', '')}")
        print(f"  Results: {c.get('results', '')}")
        print(f"  Why it fits: {c.get('why_it_fits', '')}\n")
    if answer.note:
        print(answer.note)
    u = answer.usage
    print(f"\n[tokens: {u.input} in ({u.cached} cached), {u.output} out]", file=sys.stderr)


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="casebook")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="find case studies that fit a question")
    a.add_argument("question")
    d = sub.add_parser("deck", help="build a pitch deck from a prospect brief")
    d.add_argument("brief")
    d.add_argument("-o", "--out", default="pitch.pptx")
    args = p.parse_args()

    corpus, llm = Corpus.load(), default_llm()
    if args.cmd == "ask":
        answer = ask(args.question, corpus, llm)
        if answer.deck_request is not None:
            print("That sounds like a deck request. Try: python -m casebook deck \"<brief>\"")
            return 0
        print_answer(answer)
        return 0

    try:
        draft = draft_deck(args.brief, corpus, llm)
    except DeckError as e:
        print(f"Couldn't build the deck: {e}")
        for problem in e.problems:
            print(f"  - {problem}")
        return 1
    render_pptx(draft.content, corpus, args.out)
    titles = ", ".join(c["corpus_title"] for c in draft.content["cases"])
    print(f"Saved {args.out} ({len(draft.content['cases'])} cases: {titles})")
    if draft.attempts > 1:
        print("(The first draft failed validation and was repaired.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
