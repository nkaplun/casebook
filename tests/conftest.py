import json

import pytest

from casebook.corpus import Corpus
from casebook.llm import Completion, Usage


class FakeLLM:
    """Returns scripted completions in order and records what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, instructions, library, messages, tools=None, max_tokens=2000):
        self.calls.append({"instructions": instructions, "messages": messages, "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, Completion):
            return reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return Completion(text=text, usage=Usage(1000, 900, 100))


@pytest.fixture
def corpus():
    return Corpus.load()


FRAUD = "Real-Time Fraud Scoring for a Payments Processor"
LENDING = "Loan Origination Platform Rebuild for a Digital Lender"
NEOBANK = "Customer Support Assistant for a Neobank"
