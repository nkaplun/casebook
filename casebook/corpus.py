"""The case-study library: loading it, and looking cases up by title.

There is no vector database and no retrieval step. The whole library is small
enough to send to the model on every question, so it can never "miss" a relevant
case and fill the gap with something it made up. `Corpus.context()` is where
retrieval would go if the library ever outgrew the context window.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass, field

DEFAULT_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "case_studies.json"

# Fields the answer shows that must come from the library, never from the model.
# The model is asked to copy them verbatim, but "asked" is not a guarantee, so
# search.restore_fields() overwrites them from the record after every answer.
AUTHORITATIVE_FIELDS = ("client", "industry", "link", "nda")

# A trailing "(Client)" on a title, which the model often drops when the client
# is already named next to it.
_TITLE_SUFFIX_RE = re.compile(r"\s*\([^()]*\)\s*$")


def norm_title(title: str) -> str:
    """Case- and whitespace-insensitive key for matching a title the model returned
    against the real one. Trivial reformatting should not count as a fake case."""
    return " ".join((title or "").split()).casefold()


@dataclass
class Corpus:
    studies: list[dict]
    by_title: dict[str, dict] = field(init=False)

    def __post_init__(self) -> None:
        self.by_title = {norm_title(s["title"]): s for s in self.studies}

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Corpus":
        path = path or os.environ.get("CASEBOOK_CORPUS") or DEFAULT_PATH
        return cls(json.loads(pathlib.Path(path).read_text()))

    @property
    def titles(self) -> list[str]:
        return [s["title"] for s in self.studies]

    def get(self, title: str) -> dict | None:
        return self.by_title.get(norm_title(title))

    def context(self, question: str = "") -> str:
        """Everything the model sees about the library. Returns all of it today;
        a retrieval step would filter here and nothing else would change."""
        return "\n\n".join(_block(s) for s in self.studies)

    def cited(self, text: str) -> list[str]:
        """Titles that appear in `text`, also matching a title with its trailing
        "(Client)" left off."""
        found = []
        for t in self.titles:
            base = _TITLE_SUFFIX_RE.sub("", t).strip()
            if t in text or (base and base in text):
                found.append(t)
        return found


def _block(s: dict) -> str:
    """One case as the model sees it. Empty link/NDA become explicit placeholders
    so the model copies 'Link coming soon' instead of inventing a URL."""
    link = (s.get("link") or "").strip() or "Link coming soon"
    nda = (s.get("nda") or "").strip() or "NDA status unknown"
    return (
        f"=== {s['title']} ===\n"
        f"Case study name: {s['title']}\n"
        f"Client: {s.get('client') or 'Unknown'}\n"
        f"Link: {link}\n"
        f"NDA-protected: {nda}\n\n"
        f"{s['text']}"
    )
