"""Homoglifa- es em-dash ellenorzes SCRIPT-BOL kuldott szovegre.

MIERT LETEZIK (2026-10-07, merve): a `scripts/hooks/outgoing-copy-gate.py` a Bash
PARANCS-SZTRINGET vizsgalja. Ha a kuldes egy script FAJLBOL megy (`python3 valami.py`),
a parancssorban nincs szoveg, tehat a kapunak nincs mit megnezni, es a tartalom
ellenorzes nelkul megy ki. Igy csuszott at egy cirill U+0435 egy inter-agent
uzenetbe (agent_messages 1999), holott a kapu sajat homoglifa-detektora a szot
helyesen felismeri -- csak soha nem latta.

HASZNALAT a kuldes ELOTT:
    from kimeno_ellenorzes import ellenorzes
    ellenorzes(TXT)          # AssertionError, ha gond van
"""
import re
import unicodedata

UWORD = re.compile(r"[^\W\d_]+", re.UNICODE)
EM_DASH = "—"


def _script(ch: str) -> str:
    try:
        return unicodedata.name(ch).split(" ")[0]
    except ValueError:
        return "UNKNOWN"


def vegyes_szavak(text: str):
    """[(szo, rossz_karakter, nev), ...] -- latin es nem-latin betu EGY szoban.
    A tisztan nem-latin szo (szandekos idegen idezet) atmegy, ahogy a kapuban is."""
    out = []
    for word in UWORD.findall(text or ""):
        # CSAK BETUKET nezunk. A felso indexes `2` es `3` (U+00B2, U+00B3) szo-karakter
        # a regexnek, de NEM betu -- enelkul az `m2` es `m3` jeloles homoglifanak latszik.
        # Merve 2026-10-08: a memoria-sopres 56 talalatabol tobb tucat ilyen hamis pozitiv volt.
        betuk = [c for c in word if c.isalpha()]
        scripts = {_script(c) for c in betuk}
        if "LATIN" in scripts and len(scripts) > 1:
            bad = next(c for c in betuk if _script(c) != "LATIN")
            try:
                name = unicodedata.name(bad)
            except ValueError:
                name = "UNKNOWN"
            out.append((word, bad, f"{name} (U+{ord(bad):04X})"))
    return out


def problemak(text: str):
    p = []
    m = vegyes_szavak(text)
    if m:
        p.append("VEGYES IRASRENDSZERU SZO (homoglifa): " +
                 "; ".join(f"{w!r} benne {n}" for w, _c, n in m))
    if EM_DASH in (text or ""):
        p.append(f"GONDOLATJEL (em dash) {text.count(EM_DASH)} helyen")
    return p


def ellenorzes(text: str, nev: str = "szoveg") -> str:
    """Dob, ha gond van. Visszaadja a szoveget, hogy be lehessen fuzni a hivasba."""
    p = problemak(text)
    assert not p, f"{nev}: " + " | ".join(p)
    return text


if __name__ == "__main__":
    # onteszt: a 2026-10-07-i eles eset
    assert vegyes_szavak("A legertekesebb reszе az volt")
    assert not vegyes_szavak("A legertekesebb resze az volt")
    assert not vegyes_szavak("Ordensklinikum Linz")
    # 2026-10-08: hamis pozitiv volt, a felso index nem betu
    assert not vegyes_szavak("a zoldterfogat 120 m3, a terulet 253 m2")
    # a valodi homoglifa tovabbra is fennakad, szamjegyes szo belsejeben is
    assert vegyes_szavak("250 m2-es pozici\u043e")
    print("onteszt OK")
