#!/usr/bin/env python3
"""Stop hook: back-fill inbound Telegram messages that never triggered a prompt.

WHY THIS EXISTS (2026-08-04): ledger-capture.py is a UserPromptSubmit hook, so it
only ever sees messages that arrive as a *prompt*. Messages that land while the
agent is mid-turn are injected by the --channels runtime instead, and appear in
the session transcript as

    {"type": "queue-operation", "operation": "enqueue", "content": "<channel .../>"}

records rather than as `message` records. UserPromptSubmit never fires for those,
so they were silently missing from conversation_log -- while the agent's own
replies were logged. The SessionStart replay is built from that same table, so
after a restart the agent saw its own answers but not the owner's messages,
including the ones that carried decisions.

This hook runs at the end of every turn, re-reads the transcript and records any
channel block it finds. log_inbound() is INSERT OR IGNORE on
(agent_id, chat_id, 'in', message_id), so re-processing is free and the pass is
self-healing: whatever an earlier crash missed gets picked up on the next turn.

The byte offset is a pure speed optimisation. If it is wrong or missing we simply
re-scan, and the idempotent insert absorbs it -- a broken offset can never cause
duplicate rows. Never blocks the turn (always exit 0).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_lib  # noqa: E402

CHANNEL_RX = re.compile(
    r'<channel\s+source="plugin:telegram:telegram"([^>]*)>(.*?)</channel>',
    re.DOTALL,
)

def _state_path():
    # Test override: LEDGER_BACKFILL_STATE (mirrors ledger_lib's LEDGER_DB_PATH).
    override = os.environ.get("LEDGER_BACKFILL_STATE")
    if override:
        return override
    return os.path.join(ledger_lib._install_dir(), "store", ".ledger-backfill-offsets.json")


def _attr(attrs, name):
    m = re.search(name + r'="([^"]*)"', attrs)
    return m.group(1) if m else None


def _load_offsets():
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_offsets(offsets):
    try:
        path = _state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(offsets, fh)
        os.replace(tmp, path)
    except Exception:
        pass  # the offset is only a speed hint; losing it costs a re-scan


def _texts(record):
    """Every string in a transcript record that may carry a <channel> block."""
    out = []
    content = record.get("content")
    if isinstance(content, str):
        out.append(content)          # queue-operation (mid-turn injection)
    message = record.get("message")
    if isinstance(message, dict):
        mc = message.get("content")
        if isinstance(mc, str):
            out.append(mc)
        elif isinstance(mc, list):
            for block in mc:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    out.append(block["text"])
    return out


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    path = payload.get("transcript_path")
    if not path or not os.path.isfile(path):
        sys.exit(0)

    agent_id = ledger_lib.agent_id_from_cwd(payload.get("cwd"))
    offsets = _load_offsets()
    key = os.path.basename(path)
    try:
        start = int(offsets.get(key, 0))
    except Exception:
        start = 0
    # Truncated or rotated transcript -> start over rather than read garbage.
    if start > os.path.getsize(path):
        start = 0

    try:
        # Binary + readline(), NOT `for line in fh`: iterating a file object
        # disables tell() ("telling position disabled by next() call"), and we
        # need the offset after every line.
        with open(path, "rb") as fh:
            fh.seek(start)
            while True:
                raw = fh.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    break  # partial trailing line: leave it for the next run
                try:
                    record = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    start = fh.tell()
                    continue
                if not isinstance(record, dict):
                    start = fh.tell()
                    continue
                for text in _texts(record):
                    for attrs, body in CHANNEL_RX.findall(text):
                        chat_id = _attr(attrs, "chat_id")
                        message_id = _attr(attrs, "message_id")
                        if not (chat_id and message_id):
                            continue
                        try:
                            ledger_lib.log_inbound(
                                agent_id, chat_id, message_id,
                                body.strip(), _attr(attrs, "ts"),
                            )
                        except Exception:
                            pass
                start = fh.tell()
    except Exception:
        sys.exit(0)

    offsets[key] = start
    _save_offsets(offsets)
    sys.exit(0)


if __name__ == "__main__":
    main()
