#!/bin/bash
# Unit tests for ledger-backfill-inbound.py (Stop hook).
#
# WHAT IT GUARDS (2026-08-04 regression): ledger-capture.py is a UserPromptSubmit
# hook, so it only sees messages that arrive as a prompt. A message that lands
# while the agent is mid-turn is injected by the --channels runtime and shows up
# in the transcript as a {"type":"queue-operation","content":"<channel .../>"}
# record -- UserPromptSubmit never fires for it, so it was missing from
# conversation_log while the agent's own replies were logged. Because the
# SessionStart replay is built from that table, after a restart the agent saw its
# own answers but not the owner's messages, including ones carrying decisions.
#
# Run: bash scripts/__tests__/ledger-backfill-inbound.test.sh

set -e

PASS=0
FAIL=0
TMPDIR_BASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }
assert_eq() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi; }

INSTALL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
HOOKS_DIR="$INSTALL_DIR/scripts/hooks"

# Run the hook against an isolated DB and offset statefile. MAIN_AGENT_ID is
# pinned so a payload cwd of INSTALL_DIR resolves deterministically to 'marveen'.
run_backfill() {
    local db="$1" state="$2" transcript="$3"
    printf '{"transcript_path":"%s","cwd":"%s"}' "$transcript" "$INSTALL_DIR" |
        LEDGER_DB_PATH="$db" LEDGER_BACKFILL_STATE="$state" MAIN_AGENT_ID="marveen" \
            python3 "$HOOKS_DIR/ledger-backfill-inbound.py"
}

count_in() { sqlite3 "$1" "SELECT COUNT(*) FROM conversation_log WHERE direction='in';"; }
text_of() { sqlite3 "$1" "SELECT text FROM conversation_log WHERE direction='in' AND message_id='$2';"; }

echo "ledger-backfill-inbound.py"
echo ""

# ---------------------------------------------------------------------------
# A mid-turn message (queue-operation record) is recorded
# ---------------------------------------------------------------------------
DB1="$TMPDIR_BASE/a.db"; ST1="$TMPDIR_BASE/a.json"; TR1="$TMPDIR_BASE/a.jsonl"
cat > "$TR1" <<'EOF'
{"type":"queue-operation","operation":"enqueue","content":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\" message_id=\"900\" ts=\"2026-08-04T12:31:16.000Z\">\nmid-turn uzenet\n</channel>"}
EOF
run_backfill "$DB1" "$ST1" "$TR1"
assert_eq "queue-operation record is recorded" "1" "$(count_in "$DB1")"
assert_eq "queue-operation text is stored trimmed" "mid-turn uzenet" "$(text_of "$DB1" 900)"

# ---------------------------------------------------------------------------
# A normal prompt turn (message record, list content) is also picked up, so the
# hook is a complete safety net even if ledger-capture never ran.
# ---------------------------------------------------------------------------
DB2="$TMPDIR_BASE/b.db"; ST2="$TMPDIR_BASE/b.json"; TR2="$TMPDIR_BASE/b.jsonl"
cat > "$TR2" <<'EOF'
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\" message_id=\"901\" ts=\"2026-08-04T12:00:00.000Z\">\nprompt uzenet\n</channel>"}]}}
{"type":"user","message":{"role":"user","content":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\" message_id=\"902\" ts=\"2026-08-04T12:01:00.000Z\">\nstring content\n</channel>"}}
EOF
run_backfill "$DB2" "$ST2" "$TR2"
assert_eq "message records (list + string content) are recorded" "2" "$(count_in "$DB2")"

# ---------------------------------------------------------------------------
# Idempotency: re-running after the offset is discarded must not duplicate rows.
# The offset is only a speed hint -- correctness comes from INSERT OR IGNORE.
# ---------------------------------------------------------------------------
run_backfill "$DB1" "$ST1" "$TR1"
assert_eq "second run with offset is a no-op" "1" "$(count_in "$DB1")"
rm -f "$ST1"
run_backfill "$DB1" "$ST1" "$TR1"
assert_eq "full re-scan without offset does not duplicate" "1" "$(count_in "$DB1")"

# ---------------------------------------------------------------------------
# Appended lines are picked up on the next run (the offset advances, and the
# already-seen rows are not re-inserted).
# ---------------------------------------------------------------------------
cat >> "$TR1" <<'EOF'
{"type":"queue-operation","operation":"enqueue","content":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\" message_id=\"903\" ts=\"2026-08-04T12:40:00.000Z\">\nkesobbi uzenet\n</channel>"}
EOF
run_backfill "$DB1" "$ST1" "$TR1"
assert_eq "appended line is picked up incrementally" "2" "$(count_in "$DB1")"

# ---------------------------------------------------------------------------
# Robustness: a truncated final line is left for the next run (never recorded
# half-parsed), malformed JSON is skipped, and a blocks-without-message_id is
# ignored rather than written with a NULL key.
# ---------------------------------------------------------------------------
DB3="$TMPDIR_BASE/c.db"; ST3="$TMPDIR_BASE/c.json"; TR3="$TMPDIR_BASE/c.jsonl"
cat > "$TR3" <<'EOF'
nem json
{"type":"queue-operation","content":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\">\nnincs message_id\n</channel>"}
{"type":"queue-operation","content":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\" message_id=\"904\" ts=\"2026-08-04T13:00:00.000Z\">\njo sor\n</channel>"}
EOF
printf '{"type":"queue-operation","content":"<channel source=\\"plugin:telegram:telegram\\" chat_id=\\"111\\" message_id=\\"905\\"' >> "$TR3"
run_backfill "$DB3" "$ST3" "$TR3"
assert_eq "malformed/incomplete records are skipped, valid one is kept" "1" "$(count_in "$DB3")"
assert_eq "block without message_id is not recorded" "" "$(text_of "$DB3" '')"

# Once the truncated line is completed, it is recorded on the next run.
printf ' ts=\\"2026-08-04T13:05:00.000Z\\">\\ncsonka volt\\n</channel>"}\n' >> "$TR3"
run_backfill "$DB3" "$ST3" "$TR3"
assert_eq "completed trailing line is recorded on the next run" "2" "$(count_in "$DB3")"

# ---------------------------------------------------------------------------
# Never blocks the turn: a missing transcript path exits 0 without a DB write.
# ---------------------------------------------------------------------------
DB4="$TMPDIR_BASE/d.db"; ST4="$TMPDIR_BASE/d.json"
set +e
run_backfill "$DB4" "$ST4" "$TMPDIR_BASE/nincs-ilyen.jsonl"
RC=$?
set -e
assert_eq "missing transcript exits 0" "0" "$RC"

# A rotated (shorter) transcript resets the offset instead of reading garbage.
DB5="$TMPDIR_BASE/e.db"; ST5="$TMPDIR_BASE/e.json"; TR5="$TMPDIR_BASE/e.jsonl"
cp "$TR1" "$TR5"
run_backfill "$DB5" "$ST5" "$TR5"
cat > "$TR5" <<'EOF'
{"type":"queue-operation","content":"<channel source=\"plugin:telegram:telegram\" chat_id=\"111\" message_id=\"906\" ts=\"2026-08-04T14:00:00.000Z\">\nrotalt\n</channel>"}
EOF
run_backfill "$DB5" "$ST5" "$TR5"
assert_eq "rotated transcript is re-read from the start" "rotalt" "$(text_of "$DB5" 906)"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================="
TOTAL=$((PASS + FAIL))
echo "Results: $PASS/$TOTAL passed"
if [ "$FAIL" -gt 0 ]; then
    echo "FAILED: $FAIL tests"
    exit 1
fi
echo "All tests passed."
