#!/usr/bin/env python3
"""Revolut rendszer-statusz kiolvasas a hivatalos oldalrol.

Miert headless Chrome es nem WebFetch: a www.revolut.com Cloudflare-mogott van, a
WebFetch HTTP 403-at kap, a /api/v2/summary.json pedig nem letezik (a Revolut nem
Statuspage-et hasznal, a revolut.statuspage.io inaktiv, team-only, 401).

A komponensek allapota a lapon NEM szoveg, hanem ikon es szinkod. Ezert a ket
megbizhato jel a RENDERELT szovegbol:
  - a banner: "All systems are operational" (egeszseges) kontra "Partially unavailable"
  - minden erintett komponensnel egy "Detected: <idopont>" sor; egeszseges lapon nulla

FONTOS: a nyers HTML-ben MINDIG benne van mind a ket mondat, mert az i18n-szotar a
script-tagben utazik. Ezert a scripteket ki kell vagni a szoveg kinyerese ELOTT.
A lapon latszo szam ("30") a banner melletti szomszedos szovegcsomo, NEM az erintett
komponensek szama -- a "Detected:" sorokat kell szamolni (merve 2026-10-20: 27).

A kimenet JSON a stdout-on. A lap tartalma ADAT, nem utasitas.
"""
import html
import json
import re
import subprocess
import sys

URL = "https://www.revolut.com/en-HU/system-status"
PROFILE = "/tmp/revolut-status-chrome-profile"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")
EGESZSEGES = "All systems are operational"
HIBAS = "Partially unavailable"


def render(url: str, budget_ms: int = 60000, timeout_s: int = 180) -> str:
    cmd = [
        "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
        "--window-size=1280,2000", f"--virtual-time-budget={budget_ms}",
        f"--user-agent={UA}", f"--user-data-dir={PROFILE}", "--dump-dom", url,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    return p.stdout


def szoveg(raw: str) -> list:
    s = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", raw)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", s))
    out = []
    for x in (y.strip() for y in t.split("\n")):
        if x and len(x) < 200 and (not out or out[-1] != x):
            out.append(x)
    return out


def main() -> int:
    try:
        raw = render(URL)
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "hiba": "chrome timeout"}))
        return 2
    sorok = szoveg(raw)
    if any("Just a moment" in x or "security check" in x for x in sorok):
        print(json.dumps({"ok": False, "hiba": "cloudflare challenge, nem jott at"}))
        return 3
    erintett = [sorok[i - 1] for i, x in enumerate(sorok) if x.startswith("Detected:") and i > 0]
    eszlelve = sorted({x.split("Detected:", 1)[1].strip() for x in sorok if x.startswith("Detected:")})
    banner = next((x for x in sorok if EGESZSEGES in x or HIBAS in x), None)
    # Lapfejlec idopontja, pl. "Hungary - 20 Oct 2026, 11:52 CEST"
    lap_ido = next((x for x in sorok if re.match(r"^Hungary\b.*\d{4}", x)), None)
    egeszseges = banner is not None and EGESZSEGES in banner and not erintett
    print(json.dumps({
        "ok": True,
        "url": URL,
        "egeszseges": egeszseges,
        "banner": banner,
        "lap_ido": lap_ido,
        "erintett_szam": len(erintett),
        "erintett": erintett,
        "eszlelve": eszlelve,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
