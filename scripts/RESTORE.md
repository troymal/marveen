# Visszaállítás üres gépre — Marveen

Ez a fájl minden napi mentés mellé bemásolódik. A sorrend számít.

## 0. Mielőtt bármit csinálnál

Nézd meg a `MANIFEST.txt`-et: melyik napról van szó, hány memória-rekord van benne,
és mi volt a git HEAD. Ha a `memories` szám gyanúsan kicsi, NE ezt a mentést használd.

## 1. Alapok

```bash
# Node, git, sqlite3, tmux, Go (a bumblebee-hez)
sudo apt install -y git sqlite3 tmux rsync
# Claude Code CLI telepítése a szokásos módon
```

## 2. A kód

```bash
sudo mkdir -p /opt/marveen && sudo chown "$USER" /opt/marveen
git clone git@github.com:troymal/marveen.git /opt/marveen/marveen
cd /opt/marveen/marveen && git checkout "$(cat <mentés>/git-HEAD.txt)"
# a nem commitolt változások:
git apply <mentés>/uncommitted.patch     # ha üres, kihagyható
npm install && npm run build
```

## 3. Az adatok (ez az, ami sehol máshol nincs meg)

A mentés SZÁNDÉKOSAN nem tartalmazza a gitből jövő, buildelhető részt — azt a 2. lépés
állítja vissza. A `data/` KIZÁRÓLAG azt tartalmazza, ami a gitben nincs benne.

```bash
rsync -a <mentés>/data/ /opt/marveen/marveen/
cp <mentés>/db/claudeclaw.db /opt/marveen/marveen/store/claudeclaw.db
sqlite3 /opt/marveen/marveen/store/claudeclaw.db "PRAGMA integrity_check;"   # 'ok' kell
chmod 600 /opt/marveen/marveen/.env /opt/marveen/marveen/store/.dashboard-token
```

Amit ez visszahoz: `store/` (memória-DB mellett a projektek, a galéria, a tanulós doboz,
az Angelikától kapott anyagok), `.env`, `CLAUDE.md`, `SOUL.md`, `agents/`, `DREAM.md`.
A pontos lista minden mentésben ott van: `data/.included-paths.txt`.

## 4. Az ágens-konfiguráció

```bash
rsync -a <mentés>/claude-config/skills/          ~/.claude/skills/
rsync -a <mentés>/claude-config/scheduled-tasks/ ~/.claude/scheduled-tasks/
rsync -a <mentés>/claude-config/tools/           ~/.claude/tools/
cp <mentés>/claude-config/settings.json          ~/.claude/settings.json
# csatorna-hozzáférés (párosítások!):
rsync -a <mentés>/claude-config/channels/        ~/.claude/channels/
```

A Telegram bot-token a `.env`-ben van. A csatorna `access.json` tartalmazza, ki írhat —
enélkül a bot fut, de senkit nem ismer fel.

## 5. Beszélgetés-naplók (nem kötelező, de érdemes)

```bash
rsync -a <mentés>/transcripts/home/ /home/
```
Ezek a `~/.claude/projects/*.jsonl` fájlok. Nem szükségesek a működéshez, de ez az
ötödik memória-réteg: olyan döntések vannak bennük, amik sehol máshol nem szerepelnek.

## 6. Szolgáltatások

```bash
cp <mentés>/systemd/* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now marveen-dashboard.service marveen-channels.service
systemctl --user enable --now marveen-db-backup.timer marveen-daily-backup.timer marveen-morning.timer
systemctl --user list-timers --no-pager
```

## 7. Ellenőrzés — ne hidd el, hogy kész, amíg ezek nem futnak le

```bash
curl -s -H "Authorization: Bearer $(cat /opt/marveen/marveen/store/.dashboard-token)" \
  "http://localhost:3420/api/memories?agent=marveen&q=pecs" | head -c 200   # jön adat?
sqlite3 /opt/marveen/marveen/store/claudeclaw.db "select count(*) from kanban_cards;"
ls ~/.claude/skills | wc -l          # 60+ kell legyen
systemctl --user is-active marveen-dashboard.service marveen-channels.service
```

És végül a legfontosabb: **írj egy üzenetet Telegramon és nézd meg, megérkezik-e a válasz.**
Egy visszaállítás akkor kész, ha a csatorna él — nem akkor, ha a fájlok a helyükön vannak.

## Amit a mentés SZÁNDÉKOSAN nem tartalmaz

- `node_modules/`, `dist/` — `npm install && npm run build` újraépíti.
- `~/.claude/plugins/` — a Claude Code újratelepíti.
- A Telegram média-inbox (~138 MB fotó) — a projektekhez tartozó képek az
  `install/store/projektek/` alatt vannak, az inbox csak átmeneti tár.
- Logok.
