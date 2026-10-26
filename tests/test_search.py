"""The checks that run after the model answers a search question."""
from casebook.llm import Completion, parse_json
from casebook.search import (COLD_REFERENT_NOTE, NO_MATCH_NOTE, ask, build_messages,
                             is_cold_referent)

from conftest import FRAUD, LENDING, NEOBANK, FakeLLM


def case(title, **overrides):
    return {"case_study": title, "client": "x", "link": "", "nda": "", "summary": "s",
            "results": "r", "why_it_fits": "w", **overrides}


def test_invented_case_is_dropped_and_no_match_said_honestly(corpus):
    llm = FakeLLM({"intro": "Here it is.", "cases": [case("AI Drone Inspection for AgriCorp")],
                   "note": ""})
    a = ask("drone inspection projects?", corpus, llm)
    assert a.cases == []
    assert a.intro == ""
    assert a.note == NO_MATCH_NOTE
    assert a.dropped == ["AI Drone Inspection for AgriCorp"]


def test_real_cases_kept_when_mixed_with_invented_one(corpus):
    llm = FakeLLM({"cases": [case(FRAUD), case("Quantum Logistics Optimizer")], "note": ""})
    a = ask("fintech?", corpus, llm)
    assert [c["case_study"] for c in a.cases] == [FRAUD]
    assert "library" in a.note


def test_title_matching_ignores_case_and_spacing(corpus):
    llm = FakeLLM({"cases": [case("  real-time FRAUD scoring for a  payments processor ")]})
    a = ask("fraud?", corpus, llm)
    assert len(a.cases) == 1
    assert a.cases[0]["case_study"] == FRAUD  # restored to the exact title


def test_link_and_nda_come_from_the_library_not_the_model(corpus):
    llm = FakeLLM({"cases": [case(NEOBANK, client="Chime", link="https://made.up/link", nda="No")]})
    a = ask("support automation in banking?", corpus, llm)
    c = a.cases[0]
    assert c["client"] == "US Neobank (NDA)"
    assert c["link"] == ""
    assert c["nda"] == "Yes"
    assert {f"{NEOBANK}.client", f"{NEOBANK}.link", f"{NEOBANK}.nda"} <= set(a.corrected)


def test_copied_link_placeholder_is_not_logged_as_a_correction(corpus):
    llm = FakeLLM({"cases": [case(NEOBANK, client="US Neobank (NDA)", link="Link coming soon",
                                  nda="Yes", industry="FinTech / Banking")]})
    assert ask("neobank?", corpus, llm).corrected == []


def test_deck_tool_call_becomes_a_deck_request(corpus):
    llm = FakeLLM(Completion(tool_call={"name": "build_pitch_deck",
                                        "input": {"prospect": "Acme Bank"}}))
    a = ask("make a pitch deck for Acme Bank", corpus, llm)
    assert a.deck_request == {"prospect": "Acme Bank"}
    assert llm.calls[0]["tools"][0]["name"] == "build_pitch_deck"


def test_unreadable_model_output_fails_gracefully(corpus):
    a = ask("fintech?", corpus, FakeLLM("I think the best case is..."))
    assert a.cases == [] and "couldn't read" in a.note


def test_cold_pointer_is_answered_without_calling_the_model(corpus):
    llm = FakeLLM()  # no replies scripted: any call would fail
    a = ask("tell me more about that one", corpus, llm)
    assert a.note == COLD_REFERENT_NOTE
    assert llm.calls == []


def test_pointer_with_real_content_is_not_treated_as_cold():
    assert not is_cold_referent("is that fraud project in fintech?", None)
    assert not is_cold_referent("tell me more about that one", [{"role": "user", "content": "hi"}])
    assert is_cold_referent("what about the last one?", None)


def test_history_is_cleaned_for_the_api():
    history = [{"role": "assistant", "content": "Hi! Ask me anything."},
               {"role": "user", "content": "fintech cases?"},
               {"role": "user", "content": "with ML"},
               {"role": "assistant", "content": ""},
               {"role": "system", "content": "ignored"}]
    msgs = build_messages("which used Python?", history)
    assert msgs[0]["role"] == "user"
    roles = [m["role"] for m in msgs]
    assert all(a != b for a, b in zip(roles, roles[1:]))
    assert msgs[-1]["content"].endswith("which used Python?")
    assert "with ML" in msgs[-1]["content"]


def test_parse_json_tolerates_fences_and_prose():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 1} Hope that helps.') == {"a": 1}
    assert parse_json("no json here") == {}
    assert parse_json("[1, 2]") == {}


def test_corpus_cites_titles_without_client_suffix(corpus):
    assert corpus.cited(f"See {LENDING}.") == [LENDING]
