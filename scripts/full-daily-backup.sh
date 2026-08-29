#!/usr/bin/env bash
# NAPI TELJES MENTÉS -- olyan, amiből egy üres gépre való újratelepítés után
# visszaállítható a teljes Marveen-állapot.
#
# Módszer: rsync --link-dest hardlink-es pillanatkép. Minden nap TELJES fa
# látszik, de a változatlan fájlok hardlinkek, tehát a hely csak a napi
# változással nő. Nem kell hozzá extra eszköz (nincs restic/borg a gépen).
#
# Cél: /opt/marveen/backup/daily/<dátum>/ -- innen Zoltán replikál NAS-ra és felhőbe.
# Terv: store/gallery/mentesi-strategia-0813.md
set -uo pipefail

INSTALL_DIR="/opt/marveen/marveen"
BACKUP_ROOT="/opt/marveen/backup/daily"
TODAY="$(date +%F)"
DEST="$BACKUP_ROOT/$TODAY"
LOG="/opt/marveen/backup/daily-backup.log"
KEEP_DAILY=7
KEEP_WEEKLY=4          # vasárnapi pillanatképek

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

fail() {
  log "HIBA: $*"
  TOKEN_FILE="$INSTALL_DIR/store/.dashboard-token"
  if [ -r "$TOKEN_FILE" ]; then
    curl -s -m 10 -X POST http://localhost:3420/api/messages \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
      -d "{\"from\":\"marveen\",\"to\":\"marveen\",\"content\":\"[MENTÉS-HIBA] A napi teljes mentés elbukott: $* -- log: $LOG\"}" >/dev/null || true
  fi
  exit 1
}

mkdir -p "$DEST" || fail "célkönyvtár nem hozható létre"
PREV="$(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | grep -v "$TODAY" | sort | tail -1)"
LINKDEST=()
[ -n "$PREV" ] && LINKDEST=(--link-dest="${PREV%/}")

# ---------------------------------------------------------------- 1) adatbázis
# Külön, .backup-pal: a WAL miatt a nyers fájlmásolat sérült lehet.
mkdir -p "$DEST/db"
sqlite3 "$INSTALL_DIR/store/claudeclaw.db" ".backup '$DEST/db/claudeclaw.db'" 2>>"$LOG" \
  || fail "sqlite3 .backup sikertelen"
CHECK="$(sqlite3 "$DEST/db/claudeclaw.db" 'PRAGMA integrity_check;' 2>>"$LOG" | head -1)"
[ "$CHECK" = "ok" ] || fail "integrity_check nem ok: '$CHECK'"
ROWS="$(sqlite3 "$DEST/db/claudeclaw.db" 'SELECT count(*) FROM memories;' 2>>"$LOG")"
[ "${ROWS:-0}" -gt 0 ] 2>/dev/null || fail "a memories tábla üres a mentésben"

# ------------------------------------------------------- 2) a PÓTOLHATATLAN adat
# Zoltán döntése (2026-08-13): ami gitből jön és buildelhető, azt NE mentsük --
# újraépíthető. Ezért NEM a teljes fát másoljuk, hanem CSAK azt, ami a gitből
# hiányzik: a .gitignore-olt fájlokat (store/, .env, CLAUDE.md, SOUL.md, agents/,
# DREAM.md, .claude/settings.local.json) -- mínusz a build-melléktermékek.
# A követett fájlok eltéréseit az uncommitted.patch őrzi (6. pont).
#
# A listát a git maga adja, tehát ha új ignorált útvonal keletkezik, magától
# bekerül -- nem kell kézzel karbantartani egy másolatot a .gitignore-ról.
mkdir -p "$DEST/data"
IGNORED="$(git -C "$INSTALL_DIR" ls-files --others --ignored --exclude-standard --directory 2>/dev/null \
  | grep -vE '^(node_modules/|dist/|.*__pycache__/)$')"
[ -n "$IGNORED" ] || fail "a git nem adott ignorált útvonal-listát (üres) -- ez gyanús, inkább leállok"

printf '%s\n' "$IGNORED" > "$DEST/data/.included-paths.txt"
# shellcheck disable=SC2086
# FONTOS: a --files-from KIKAPCSOLJA a rekurziót, ezért a -r EXPLICIT kell.
# Enélkül a store/ könyvtárból csak az üres váz jön át (2026-08-13, elkapva
# ellenőrzéssel: 1,3 MB volt 882 MB helyett).
rsync -a -r --delete --relative "${LINKDEST[@]}" \
  --exclude '*.log' --exclude 'store/tmp/' \
  --exclude 'store/claudeclaw.db' --exclude 'store/claudeclaw.db-wal' --exclude 'store/claudeclaw.db-shm' \
  --files-from=<(printf '%s\n' "$IGNORED") \
  "$INSTALL_DIR/" "$DEST/data/" 2>>"$LOG" || fail "rsync: pótolhatatlan adat"

# ------------------------------------------------- 3) ágens-konfiguráció (~/.claude)
# Csak az, ami NEM állítható elő újratelepítéssel: skillek, ütemezett feladatok,
# beállítások, csatorna-hozzáférés, eszköz-katalógusok. A plugins/ és a cache
# szándékosan kimarad (újratelepíthető), a projects/ külön kezelendő (lásd 4).
mkdir -p "$DEST/claude-config"
for item in skills scheduled-tasks tools settings.json policy-limits.json remote-settings.json keybindings.json; do
  [ -e "$HOME/.claude/$item" ] && rsync -a "${LINKDEST[@]/%/claude-config\/}" "$HOME/.claude/$item" "$DEST/claude-config/" 2>>"$LOG"
done
# Csatorna-hozzáférés: CSAK a config, a média-inbox (138 MB) nem kell a visszaállításhoz.
mkdir -p "$DEST/claude-config/channels"
find "$HOME/.claude/channels" -maxdepth 2 -name '*.json' -exec cp --parents -t "$DEST/claude-config/channels" {} + 2>/dev/null

# --------------------------------------------------------- 4) beszélgetés-napló
# A transzkript az ötödik memória-réteg (lásd nincs-ilyen-allitas-elott skill):
# döntések élnek benne, amik sehol máshol nincsenek. TELJES egészében nagy (547 MB),
# ezért napi szinten az utolsó 30 nap megy, a többit a heti pillanatkép őrzi.
mkdir -p "$DEST/transcripts"
find "$HOME/.claude/projects" -name '*.jsonl' -mtime -30 -exec cp --parents -t "$DEST/transcripts" {} + 2>/dev/null

# ------------------------------------------------------------- 5) systemd unitok
mkdir -p "$DEST/systemd"
cp "$HOME/.config/systemd/user/"marveen-* "$DEST/systemd/" 2>/dev/null

# ------------------------------------------- 6) nem commitolt kódváltozások
# A kód a GitHubon van (origin), de a working tree eltérései nincsenek sehol.
git -C "$INSTALL_DIR" diff HEAD > "$DEST/uncommitted.patch" 2>/dev/null
git -C "$INSTALL_DIR" rev-parse HEAD > "$DEST/git-HEAD.txt" 2>/dev/null

# ------------------------------------------------------------------ 7) manifest
{
  echo "MARVEEN MENTÉS -- $TODAY $(date +%H:%M)"
  echo "gép: $(hostname) | git HEAD: $(cat "$DEST/git-HEAD.txt" 2>/dev/null)"
  echo "adatbázis: memories=$ROWS, integrity=ok"
  echo
  echo "TARTALOM:"
  echo "  db/claudeclaw.db      -- konzisztens pillanatkép (.backup)"
  echo "  data/                 -- CSAK a gitből hiányzó (ignorált) adat: store, .env, CLAUDE.md, SOUL.md, agents"
  echo "  claude-config/        -- skillek, ütemezett feladatok, settings, csatorna-config, tools"
  echo "  transcripts/          -- beszélgetés-naplók, utolsó 30 nap"
  echo "  systemd/              -- user unitok (dashboard, channels, timerek)"
  echo "  uncommitted.patch     -- a working tree eltérése a HEAD-től"
  echo
  echo "MÉRET: $(du -sh "$DEST" | cut -f1) (hardlinkekkel; valós új adat kevesebb)"
} > "$DEST/MANIFEST.txt"

cp "$INSTALL_DIR/scripts/RESTORE.md" "$DEST/RESTORE.md" 2>/dev/null

# ------------------------------------------------------------------ 8) retenció
# 7 legutóbbi napi + minden vasárnapi (max 4). A hardlinkek miatt a törlés alig
# szabadít fel helyet, de a lista áttekinthető marad.
#
# BUKTATÓ, AMIT ITT ELKÖVETTEM (2026-08-13, első futás): a keep-listát bash
# tömbszeletelessel (`"${ALL[@]: -7}"`) építettem. Ha a tömbben KEVESEBB elem van,
# mint az eltolás, a bash ÜRESET ad vissza -- így az első futás törölte a saját,
# épp elkészült mentését, és közben "OK"-t naplózott. Ezért: (a) a keep-lista
# `tail`-lel készül, (b) a végén ELLENŐRZÖM, hogy a mai pillanatkép megvan-e.
KEEP_LIST="$(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | sort | tail -n "$KEEP_DAILY")"
SUNDAY_LIST="$(for d in "$BACKUP_ROOT"/*/; do
  [ -d "$d" ] || continue
  [ "$(date -d "$(basename "${d%/}")" +%u 2>/dev/null)" = "7" ] && echo "$d"
done | sort | tail -n "$KEEP_WEEKLY")"
KEEP_SET="$(printf '%s\n%s\n%s\n' "$KEEP_LIST" "$SUNDAY_LIST" "$DEST/" | grep -v '^$' | sort -u)"

for d in "$BACKUP_ROOT"/*/; do
  [ -d "$d" ] || continue
  if ! printf '%s\n' "$KEEP_SET" | grep -qxF "$d"; then
    rm -rf "$d" && log "torolve (retencio): $(basename "${d%/}")"
  fi
done

# Utolsó ellenőrzés: a mai mentésnek LÉTEZNIE kell, és tartalmaznia az adatbázist.
[ -s "$DEST/db/claudeclaw.db" ] || fail "a mai pillanatkép eltűnt vagy üres a retenció után"

# Tartalmi épség: a store/ nem lehet gyanúsan kicsi. A --files-from/-r csapda
# miatt előfordult, hogy csak az üres könyvtárváz került be, és a szkript OK-t írt.
STORE_MB="$(du -sm "$DEST/data/store" 2>/dev/null | cut -f1)"
[ "${STORE_MB:-0}" -ge 100 ] 2>/dev/null || fail "a mentett store/ csak ${STORE_MB:-0} MB -- hiányos mentés"

SIZE="$(du -sh "$DEST" | cut -f1)"
SNAPS="$(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | wc -l)"
log "OK: $TODAY ($SIZE, memories=$ROWS, megorzott pillanatkepek: $SNAPS)"
exit 0
