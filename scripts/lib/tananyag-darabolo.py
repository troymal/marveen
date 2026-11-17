# -*- coding: utf-8 -*-
"""A napi PM-tananyag Telegram-blokkokra bontasa.

MIERT: a Telegram uzenethatar es a mert legnagyobb kimeno uzenet (4186 karakter, 2026-09-29)
miatt a napi anyag (1. nap: 45 611 karakter) egy uzenetbe nem fer. A vagas TEMAHATARON
tortenik, nem karakterszamra, es minden blokk elejen ott van, hanyadik es hany van osszesen.
Reszletek: ~/.claude/skills/pm-tananyag-esti/SKILL.md
"""
import re, sys

HATAR = 3800


def felkover_le(szoveg):
    """A ** jelolok eltavolitasa a bekezdes OSSZEFUZESE UTAN.

    Merve 2026-09-29: soronkent futtatva a mintat, a tobb sorra tordelt felkover reszek
    (a forrasban `**1. Mi kulonbozteti...` egy soron, a zaro `**` a kovetkezon) NEM
    illeszkedtek, es a csillagok kimentek a csatornara. A 3/15-os uzenetben harom ilyen
    maradt bent. Ezert a csere a teljes bekezdesre megy, nem soronkent.
    """
    return re.sub(r'\*\*(.+?)\*\*', r'\1', szoveg, flags=re.S)


def tiszta(sorok):
    """Markdownbol sima szoveg: a ** jelolok el, a fejlecek sima sorra.

    A FEJLEC A KOVETKEZO BEKEZDESHEZ TAPAD, ES EZ NEM KOZMETIKA. Ha a fejlec onallo
    bekezdes, a darabolo levaghatja a szakasz tartalma ELE, es akkor az uzenet egy
    cim nelkuli cimmel er veget. Merve 2026-09-29-en: az 1. blokk >>5. ELMELETI HATTER<<
    fejleccel zarult, tartalom nelkul. Ezert a fejlec es az utana kovetkezo elso bekezdes
    EGY blokk, egyetlen sortoressel elvalasztva.
    """
    blokkok, most, fejlec_var = [], [], False
    for l in sorok:
        if re.fullmatch(r'\s*-{3,}\s*', l):
            continue          # markdown valasztovonal: a csatornan nem jelent semmit
        m = re.match(r'^(#{1,3})\s+(.*)', l)
        if m:
            if most:
                blokkok.append(' '.join(most)); most = []
            cim = m.group(2).upper() if len(m.group(1)) <= 2 else m.group(2)
            blokkok.append(cim)
            fejlec_var = True
            continue
        if l.strip():
            most.append(l.strip())
        elif most:
            szoveg = felkover_le(' '.join(most)); most = []
            if fejlec_var:
                blokkok[-1] += '\n' + szoveg     # a fejlec es az elso bekezdes egyutt marad
                fejlec_var = False
            else:
                blokkok.append(szoveg)
    if most:
        szoveg = felkover_le(' '.join(most))
        if fejlec_var:
            blokkok[-1] += '\n' + szoveg
        else:
            blokkok.append(szoveg)
    return '\n\n'.join(b for b in blokkok if b.strip())


def darabol(szoveg, hatar=HATAR):
    """Bekezdeshataron vag. Egy bekezdest SOHA nem vag ketté.

    MOHO PAKOLAS, SZANDEKOSAN. 2026-09-29-en megprobaltam >>kiegyensulyozni<< a darabokat
    (eloszor kiszamolni, hany darab kell, aztan egyenletesen pakolni), hogy a vegeken ne
    maradjon rovid csonk. A heurisztikam (>>nyiss uj darabot, ha a cel fole menne ES mar
    tul vagy a cel 60 szazalekan<<) HIBAS volt: ugyanazon a bemeneten 15 darab helyett
    37-et adott, mert a feltetel szinte minden bekezdesnel tuzelt, a ciklus meg csak
    novelni tudta a darabszamot. Visszaallitva a mohora.
    A rovid zaro darab nem hiba: temahataron all, es a blokk vegen amugy is szunet van.
    """
    darabok, most = [], ''
    for bek in szoveg.split('\n\n'):
        if len(bek) > hatar:
            raise ValueError(f'egyetlen bekezdes {len(bek)} karakter: {bek[:80]!r}')
        if most and len(most) + 2 + len(bek) > hatar:
            darabok.append(most); most = bek
        else:
            most = f'{most}\n\n{bek}' if most else bek
    if most:
        darabok.append(most)
    return darabok


if __name__ == '__main__':
    fajl, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    sorok = open(fajl, encoding='utf8').read().split('\n')[a:b]
    for i, d in enumerate(darabol(tiszta(sorok)), 1):
        print(f'@@@DARAB {i} ({len(d)} karakter)')
        print(d)
