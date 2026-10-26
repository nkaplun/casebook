"""The Slack bot. Answers @mentions and DMs; builds a deck when asked for one.

Run locally with Socket Mode (no public URL needed):

    SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-... python -m casebook.slack_app

Replies go in a thread, and earlier messages in that thread are passed back as
conversation history, so "which of those used Python?" works as a follow-up.
"""
import logging
import os
import re
import tempfile

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .corpus import Corpus
from .deck import DeckError, draft_deck, render_pptx
from .llm import default_llm
from .search import ask
from .slack_blocks import answer_blocks, paginate

load_dotenv()
logging.basicConfig(level=logging.INFO)
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
corpus, llm = Corpus.load(), default_llm()
_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")


def thread_history(client, channel: str, thread_ts: str, bot_user: str) -> list[dict]:
    replies = client.conversations_replies(channel=channel, ts=thread_ts, limit=30)["messages"]
    return [{"role": "assistant" if m.get("user") == bot_user or m.get("bot_id") else "user",
             "content": _MENTION_RE.sub("", m.get("text") or "")}
            for m in replies[:-1]]  # the last one is the message being answered


def handle(event, client, context) -> None:
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    question = _MENTION_RE.sub("", event.get("text") or "").strip()
    history = (thread_history(client, channel, thread_ts, context.bot_user_id)
               if event.get("thread_ts") else None)

    answer = ask(question, corpus, llm, history)
    if answer.deck_request is None:
        for page in paginate(answer_blocks(answer)):
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, blocks=page,
                                    text="Case studies")
        return

    # Deck request: the brief is everything the user has said in this thread.
    client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                            text="Building a deck from this thread. About a minute.")
    brief = "\n".join(m["content"] for m in (history or []) if m["role"] == "user")
    brief = f"{brief}\n{question}".strip()
    try:
        draft = draft_deck(brief, corpus, llm)
    except DeckError as e:
        detail = "".join(f"\n• {p}" for p in e.problems[:5])
        client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                                text=f"I couldn't build that deck: {e}{detail}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = render_pptx(draft.content, corpus, os.path.join(tmp, "pitch.pptx"))
        client.files_upload_v2(channel=channel, thread_ts=thread_ts, file=path,
                               title=draft.content["deck_title"],
                               initial_comment="Here's the draft. Every number on it "
                                               "is checked against its source case study.")


@app.event("app_mention")
def on_mention(event, client, context):
    handle(event, client, context)


@app.event("message")
def on_dm(event, client, context):
    if event.get("channel_type") == "im" and not event.get("bot_id") and not event.get("subtype"):
        handle(event, client, context)


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
