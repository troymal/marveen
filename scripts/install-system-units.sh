#!/usr/bin/env bash
# Install Marveen's services as SYSTEM-scope systemd units.
#
# WHY this script exists:
#   The installer (install-linux.sh) generates USER-scope units under
#   $HOME/.config/systemd/user and enables them with `systemctl --user`. That is
#   correct for a human user with a login session, but WRONG for a service
#   account that never logs in (no SSH, no XDG_RUNTIME_DIR/DBUS in its shell):
#   `systemctl --user` fails with "Failed to connect to bus: No medium found",
#   the doctor/status surfaces report a false "NOT running", and -- because
#   `Restart=always` only lives inside the unit -- a plugin crash leaves the
#   channel dead with nothing to bring it back.
#
#   System-scope units (/etc/systemd/system with User=/Group=) run under the PID 1
#   manager: no linger, no login session, no DBus bus, no env exports needed. They
#   start at boot and `systemctl status` works from any root shell.
#
# WHAT it does (idempotent, safe to re-run):
#   1. Mirrors every existing USER-scope unit (dashboard, channels, morning,
#      db-backup, daily-backup, telegram-progress-watchdog + their timers and
#      drop-ins) into /etc/systemd/system/, adding User=/Group= and rewriting
#      WantedBy=default.target -> multi-user.target (timers keep timers.target).
#      Mirroring (not re-templating) preserves the exact live configuration,
#      including the db-backup/daily-backup units that have no repo template.
#   2. Generates the units the installer is SUPPOSED to ship but which a HOME
#      migration can drop (host-watchdog, notify@ + the OnFailure= drop-ins).
#   3. Disables the USER-scope copies (rename .disabled + drop the wants/ symlinks)
#      so the lingering user-manager never starts a second instance (EADDRINUSE /
#      telegram 409).
#   4. daemon-reload + enable --now for the two long-running services.
#
# WHAT it does NOT do: run the installer, touch .env / store / agents data, or
#   edit anything under the project dir except reading .env and its own templates.
#
# Usage:
#   sudo MARVEEN_RUN_USER=marveen bash scripts/install-system-units.sh
#   (MARVEEN_RUN_USER defaults to the invoking user; set it when running as root
#    for a service account.)

set -uo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
USERD_DIR="${HOME:-/root}/.config/systemd/user"

BOLD='\033[1m'; DIM='\033[2m'; GREEN='\033[0;32m'; ORANGE='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${ORANGE}!${NC} $*"; }
err()  { echo -e "  ${RED}✗${NC} $*"; }

# --- resolve the run identity -------------------------------------------------
# The account the services execute as. When this script runs as root for a
# service account (the marveen user), the operator sets MARVEEN_RUN_USER.
RUN_USER="${MARVEEN_RUN_USER:-$(id -un)}"
RUN_GROUP="${MARVEEN_RUN_GROUP:-$(id -gn "$RUN_USER" 2>/dev/null || echo "$RUN_USER")}"
RUN_HOME="${MARVEEN_RUN_HOME:-$(getent passwd "$RUN_USER" 2>/dev/null | cut -d: -f6)}"
[ -n "$RUN_HOME" ] || RUN_HOME="$HOME"
[ -n "$RUN_HOME" ] || RUN_HOME="/opt/$RUN_USER"

# --- read .env values (grep, never `source`, so secrets stay out of the env) --
_get_env() { grep -E "^${1}=" "$INSTALL_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2-; }
SERVICE_ID="$(_get_env SERVICE_ID)"
[ -n "$SERVICE_ID" ] || SERVICE_ID="$(_get_env MAIN_AGENT_ID)"
[ -n "$SERVICE_ID" ] || SERVICE_ID="marveen"
BOT_NAME="$(_get_env BOT_NAME)"
[ -n "$BOT_NAME" ] || BOT_NAME="Marveen"

NODE_PATH="${MARVEEN_NODE_PATH:-$(command -v node || echo /usr/bin/node)}"

# --- timezone (mirrors install-linux.sh detection) ---------------------------
SYSTEM_TZ="${MARVEEN_TZ:-$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || true)}"
SYSTEM_TZ="${SYSTEM_TZ%$'\n'}"
[ -n "$SYSTEM_TZ" ] || SYSTEM_TZ="Europe/Budapest"

echo -e "${BOLD}Marveen -- system-scope systemd install (${SERVICE_ID})${NC}"
echo "  run user : $RUN_USER ($RUN_GROUP)"
echo "  home     : $RUN_HOME"
echo "  install  : $INSTALL_DIR"
echo ""

if [ "$(id -u)" -ne 0 ]; then
  err "root kell a /etc/systemd/system irasahoz. Futtasd: sudo bash $0"
  exit 1
fi
mkdir -p "$SYSTEMD_DIR"

# --- helpers -----------------------------------------------------------------
# Inject User=/Group= into a copied unit's [Service] section (idempotent) and
# fix the [Install] target for system scope. $1 = destination file.
patch_system_scope() {
  local dst="$1"
  # Rewrite the user-manager target to the system-manager target. Timers are
  # handled by the caller (they already use timers.target, shared by both).
  sed -i 's#^WantedBy=default\.target#WantedBy=multi-user.target#' "$dst"
  # Point any per-unit USER= env at the real run user (a migrated unit may still
  # carry the OLD user's name).
  sed -i "s#^Environment=USER=.*#Environment=USER=$RUN_USER#" "$dst"
  # Add User=/Group= only if absent (idempotent re-runs).
  grep -q '^User=' "$dst" || sed -i "/^\[Service\]$/a User=$RUN_USER" "$dst"
  grep -q '^Group=' "$dst" || sed -i "/^\[Service\]$/a Group=$RUN_GROUP" "$dst"
}

# Copy one user-scope unit file into system scope and patch it. $1 = rel filename.
mirror_unit() {
  local name="$1" src="$USERD_DIR/$name" dst="$SYSTEMD_DIR/$name"
  [ -f "$src" ] || return 0
  cp -f "$src" "$dst"
  patch_system_scope "$dst"
  echo "  ${DIM}mirrored${NC} $name"
}

# --- 1. mirror existing user units (services, timers, drop-ins) --------------
mirrored=0
if [ -d "$USERD_DIR" ]; then
  echo -e "${BOLD}Existing user-scope units${NC}"
  for f in "$USERD_DIR"/*.service "$USERD_DIR"/*.timer; do
    [ -f "$f" ] || continue
    name="$(basename "$f")"
    case "$name" in
      *.service.marveen-*|*.timer.marveen-*) continue ;;  # original-backup copies
    esac
    mirror_unit "$name"
    mirrored=1
  done
  for d in "$USERD_DIR"/*.service.d; do
    [ -d "$d" ] || continue
    dname="$(basename "$d")"
    case "$dname" in
      *.marveen-*) continue ;;
    esac
    mkdir -p "$SYSTEMD_DIR/$dname"
    cp -f "$d"/*.conf "$SYSTEMD_DIR/$dname/" 2>/dev/null
    echo "  ${DIM}mirrored${NC} $dname/"
    mirrored=1
  done
fi

# --- 2. generate the units a HOME migration can drop -------------------------
# host-watchdog + notify@ live in scripts/systemd as templates; they were
# missing from this install's user dir, so mirroring cannot restore them.
echo -e "${BOLD}Repo-owned units (generated from templates)${NC}"

# host-watchdog.service (btime-based host/VM-restart detector)
HW_SRC="$INSTALL_DIR/scripts/systemd/marveen-host-watchdog.service"
HW_DST="$SYSTEMD_DIR/${SERVICE_ID}-host-watchdog.service"
if [ ! -f "$HW_DST" ]; then
  sed -e "s#/path/to/marveen#$INSTALL_DIR#g" \
      -e "s#/home/USER#$RUN_HOME#g" \
      -e "s#^Description=.*#Description=${BOT_NAME} host/WSL-VM restart watchdog (btime-based)#" \
      "$HW_SRC" > "$HW_DST"
  patch_system_scope "$HW_DST"
  echo "  ${DIM}generated${NC} ${SERVICE_ID}-host-watchdog.service"
else
  ok "${SERVICE_ID}-host-watchdog.service already present"
fi

# notify@.service (templated app-crash notifier)
NOTIFY_SRC="$INSTALL_DIR/scripts/systemd/marveen-notify@.service"
NOTIFY_DST="$SYSTEMD_DIR/${SERVICE_ID}-notify@.service"
if [ ! -f "$NOTIFY_DST" ]; then
  sed -e "s#/path/to/marveen#$INSTALL_DIR#g" \
      -e "s#/home/USER#$RUN_HOME#g" \
      -e "s#^Description=.*#Description=${BOT_NAME} app-crash notifier for %i#" \
      "$NOTIFY_SRC" > "$NOTIFY_DST"
  patch_system_scope "$NOTIFY_DST"
  echo "  ${DIM}generated${NC} ${SERVICE_ID}-notify@.service"
else
  ok "${SERVICE_ID}-notify@.service already present"
fi

# OnFailure= drop-ins wire the app-crash notifier onto the two long-running units.
for u in "${SERVICE_ID}-dashboard" "${SERVICE_ID}-channels"; do
  dropdir="$SYSTEMD_DIR/${u}.service.d"
  mkdir -p "$dropdir"
  if [ ! -f "$dropdir/onfailure.conf" ]; then
    printf '[Unit]\nOnFailure=%s-notify@%%n.service\n' "$SERVICE_ID" > "$dropdir/onfailure.conf"
    echo "  ${DIM}generated${NC} ${u}.service.d/onfailure.conf"
  else
    ok "${u}.service.d/onfailure.conf already present"
  fi
done

# --- 3. disable the user-scope copies ----------------------------------------
# The user-manager may already be running (linger was enabled on this host). A
# disabled unit is still loadable, so rename the files out of the *.service /
# *.timer glob and drop the wants/ symlinks -- file ops only, no reliance on the
# user DBus bus (which a never-login service account cannot reach).
if [ -d "$USERD_DIR" ]; then
  echo -e "${BOLD}Disabling user-scope copies${NC}"
  for f in "$USERD_DIR"/*.service "$USERD_DIR"/*.timer; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in *.marveen-*) continue ;; esac
    mv -f "$f" "$f.disabled"
    echo "  ${DIM}disabled${NC} $(basename "$f")"
  done
  for d in "$USERD_DIR"/*.service.d; do
    [ -d "$d" ] || continue
    mv -f "$d" "$d.disabled"
    echo "  ${DIM}disabled${NC} $(basename "$d")/"
  done
  rm -f "$USERD_DIR/default.target.wants/"* "$USERD_DIR/timers.target.wants/"* 2>/dev/null || true
fi

# --- 4. reload + enable + start ----------------------------------------------
echo ""
echo -e "${BOLD}Reload + enable${NC}"
systemctl daemon-reload || err "daemon-reload sikertelen"
for u in "${SERVICE_ID}-dashboard" "${SERVICE_ID}-channels" "${SERVICE_ID}-morning.timer" "${SERVICE_ID}-host-watchdog.service"; do
  systemctl enable "$u" >/dev/null 2>&1 || warn "enable $u sikertelen (lehet, hogy mar enabled)"
done
systemctl enable --now "${SERVICE_ID}-dashboard" "${SERVICE_ID}-channels" 2>/dev/null \
  || { err "enable --now sikertelen"; exit 1; }

echo ""
echo -e "${BOLD}Kesz. Ellenorzes:${NC}"
echo -e "  ${DIM}systemctl status ${SERVICE_ID}-channels ${SERVICE_ID}-dashboard${NC}"
echo -e "  ${DIM}bash ${INSTALL_DIR}/scripts/verify-channels-health.sh${NC}"
