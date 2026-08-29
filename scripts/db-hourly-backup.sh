#!/usr/bin/env bash
# Óránkénti, konzisztens mentés a claudeclaw.db-ről.
#
# MIÉRT NEM `cp`: az adatbázis WAL módban fut (van .db-wal fájl), így egy futó
# szolgáltatás mellett készült nyers másolat SÉRÜLT lehet. A `sqlite3 .backup`
# tranzakció-konzisztens pillanatképet ad leállítás nélkül.
#
# Cél: /opt/marveen/backup/db -- innen Zoltán replikálja tovább (NAS + felhő).
# Megőrzés: 7 gördülő példány (kb. 175 MB).
#
# Hibánál: inter-agent üzenet a marveen sorába, hogy a következő heartbeatnél
# látszódjon. SIKERES mentésről NEM üzen (a néma siker a helyes viselkedés).
#
# 2026-08-13, Zoltán kérésére. Kapcsolódó terv: store/gallery/mentesi-strategia-0813.md
set -uo pipefail

INSTALL_DIR="/opt/marveen/marveen"
DB="$INSTALL_DIR/store/claudeclaw.db"
DEST_DIR="/opt/marveen/backup/db"
KEEP=7
STAMP="$(date +%Y%m%d-%H%M)"
TMP="$DEST_DIR/.tmp-$STAMP.db"
FINAL="$DEST_DIR/claudeclaw-$STAMP.db"
LOG="$DEST_DIR/backup.log"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

fail() {
  log "HIBA: $*"
  rm -f "$TMP"
  # Csak jelzés, nem Telegram: a következő heartbeat felszedi és eldöntöm, eszkalálom-e.
  TOKEN_FILE="$INSTALL_DIR/store/.dashboard-token"
  if [ -r "$TOKEN_FILE" ]; then
    curl -s -m 10 -X POST http://localhost:3420/api/messages \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
      -d "{\"from\":\"marveen\",\"to\":\"marveen\",\"content\":\"[MENTÉS-HIBA] Az óránkénti DB-mentés elbukott: $* -- részletek: $LOG\"}" >/dev/null || true
  fi
  exit 1
}

mkdir -p "$DEST_DIR" || fail "a célkönyvtár nem hozható létre: $DEST_DIR"
[ -r "$DB" ] || fail "az adatbázis nem olvasható: $DB"

# 1) Konzisztens pillanatkép
sqlite3 "$DB" ".backup '$TMP'" 2>>"$LOG" || fail "sqlite3 .backup sikertelen"

# 2) Ellenőrzés MIELŐTT a helyére kerül -- sérült mentés rosszabb, mint a semmi,
#    mert azt hisszük, van mentésünk.
CHECK="$(sqlite3 "$TMP" 'PRAGMA integrity_check;' 2>>"$LOG" | head -1)"
[ "$CHECK" = "ok" ] || fail "integrity_check nem ok: '$CHECK'"

# 3) Épség-próba tartalomra is: a memories tábla olvasható és nem üres
ROWS="$(sqlite3 "$TMP" 'SELECT count(*) FROM memories;' 2>>"$LOG")"
[ -n "$ROWS" ] && [ "$ROWS" -gt 0 ] 2>/dev/null || fail "a memories tábla üres vagy olvashatatlan a mentésben"

mv "$TMP" "$FINAL" || fail "a mentés nem mozgatható a helyére"

# 4) Megőrzés: a legfrissebb $KEEP marad
ls -1t "$DEST_DIR"/claudeclaw-*.db 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old" && log "torolve (retencio): $(basename "$old")"
done

SIZE="$(du -h "$FINAL" | cut -f1)"
log "OK: $(basename "$FINAL") ($SIZE, memories=$ROWS, integrity=ok)"
exit 0
