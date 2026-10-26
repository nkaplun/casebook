"""Run the search and deck evals against a real model and write a report.

    python evals/run_evals.py                      # both suites
    python evals/run_evals.py --suite search
    python evals/run_evals.py --price-in 1 --price-cached 0.1 --price-out 5

Prices are dollars per million tokens. They are flags, not constants, because
prices change and a stale number in a cost report is worse than none.

Run the suite for whatever you changed before every deploy, and add a case for
the change.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from casebook.corpus import Corpus  # noqa: E402
from casebook.deck import DeckError, draft_deck  # noqa: E402
from casebook.llm import Usage, default_llm  # noqa: E402
from casebook.search import ask  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def search_failures(case: dict, answer) -> list[str]:
    titles = [c["case_study"] for c in answer.cases]
    fails = []
    if answer.dropped:
        fails.append(f"model invented {answer.dropped} (the check removed them)")
    if "expect_deck" in case and (answer.deck_request is not None) != case["expect_deck"]:
        fails.append("should build a deck" if case["expect_deck"] else "wrongly treated as a deck request")
    if case.get("expect_none") and titles:
        fails.append(f"should have found nothing, returned {titles}")
    if case.get("expect_any") and not set(titles) & set(case["expect_any"]):
        fails.append(f"expected one of {case['expect_any']}, got {titles}")
    for bad in case.get("must_not", []):
        if bad in titles:
            fails.append(f"should not include {bad!r}")
    return fails


def run_search(corpus, llm) -> tuple[list[dict], Usage]:
    rows, total = [], Usage()
    for case in json.loads((HERE / "search_cases.json").read_text()):
        start = time.perf_counter()
        answer = ask(case["question"], corpus, llm)
        secs = time.perf_counter() - start
        fails = search_failures(case, answer)
        _add(total, answer.usage)
        rows.append({"id": case["id"], "pass": not fails, "secs": secs,
                     "detail": "; ".join(fails) or "", "corrected": len(answer.corrected)})
        print(f"{'PASS' if not fails else 'FAIL'}  search/{case['id']}  {secs:.1f}s  {'; '.join(fails)}")
    return rows, total


def run_decks(corpus, llm) -> tuple[list[dict], Usage]:
    rows, total = [], Usage()
    for case in json.loads((HERE / "deck_cases.json").read_text()):
        start = time.perf_counter()
        fails, attempts = [], 0
        try:
            draft = draft_deck(case["brief"], corpus, llm)
            attempts = draft.attempts
            _add(total, draft.usage)
            titles = [c["corpus_title"] for c in draft.content["cases"]]
            if not set(titles) & set(case["expect_any"]):
                fails.append(f"expected one of {case['expect_any']}, got {titles}")
        except DeckError as e:
            fails.append(f"{e} {e.problems[:3]}")
        secs = time.perf_counter() - start
        rows.append({"id": case["id"], "pass": not fails, "secs": secs,
                     "detail": "; ".join(fails) or (f"repaired after {attempts - 1} failed draft"
                                                    if attempts > 1 else "")})
        print(f"{'PASS' if not fails else 'FAIL'}  deck/{case['id']}  {secs:.1f}s  {'; '.join(fails)}")
    return rows, total


def _add(total: Usage, u: Usage) -> None:
    total.input += u.input
    total.cached += u.cached
    total.output += u.output


def report(model: str, suites: dict, prices: tuple | None) -> str:
    lines = [f"# Eval report, {dt.date.today()}", "", f"Model: `{model}`", ""]
    for name, (rows, usage) in suites.items():
        passed = sum(r["pass"] for r in rows)
        secs = sorted(r["secs"] for r in rows)
        lines += [f"## {name}: {passed}/{len(rows)} passed", "",
                  f"Median latency {secs[len(secs) // 2]:.1f}s. Tokens: {usage.input:,} input "
                  f"({usage.cached:,} cached), {usage.output:,} output."]
        if prices:
            p_in, p_cached, p_out = prices
            cost = ((usage.input - usage.cached) * p_in + usage.cached * p_cached
                    + usage.output * p_out) / 1e6
            lines.append(f"Cost: ${cost:.3f} total, ${cost / len(rows):.4f} per question.")
        lines += ["", "| Case | Result | Seconds | Notes |", "|---|---|---|---|"]
        lines += [f"| {r['id']} | {'pass' if r['pass'] else '**FAIL**'} | {r['secs']:.1f} | {r['detail']} |"
                  for r in rows]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser()
    p.add_argument("--suite", choices=["search", "deck", "all"], default="all")
    p.add_argument("--price-in", type=float)
    p.add_argument("--price-cached", type=float)
    p.add_argument("--price-out", type=float)
    args = p.parse_args()
    prices = ((args.price_in, args.price_cached, args.price_out)
              if None not in (args.price_in, args.price_cached, args.price_out) else None)

    corpus, llm = Corpus.load(), default_llm()
    suites = {}
    if args.suite in ("search", "all"):
        suites["Search"] = run_search(corpus, llm)
    if args.suite in ("deck", "all"):
        suites["Deck"] = run_decks(corpus, llm)

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{dt.datetime.now():%Y-%m-%d_%H%M}.md"
    path.write_text(report(getattr(llm, "model", "?"), suites, prices))
    print(f"\nReport: {path.relative_to(ROOT)}")
    return 0 if all(r["pass"] for rows, _ in suites.values() for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
