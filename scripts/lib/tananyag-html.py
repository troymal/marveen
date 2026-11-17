# -*- coding: utf-8 -*-
"""A napi PM-tananyag olvashato HTML-lapja.

MIERT: 2026-09-29-en az 1. nap 15 szamozott Telegram-uzenetben ment ki, es Angelika szo
szerint ezt irta: >>itt borzalmasan faraszto olvasni<<. Igaza van: 45 000 karakter csevego
buborekokban nem olvashato anyag. Ez a szkript ugyanabbol a markdown fajlbol egy onallo,
kepkonyvtar nelkuli HTML-lapot general, amit csatolmanykent lehet kuldeni.

HASZNALAT:
    python3 scripts/lib/tananyag-html.py <nap-NN-*.md> <kimenet.html>
"""
import re, sys, html, os

CSS = """
:root { --szoveg:#22262b; --halvany:#5b636d; --kek:#1f4e79; --sarga:#ffc000;
        --hatter:#fbfaf7; --lap:#ffffff; --vonal:#e3e0d8; }
@media (prefers-color-scheme: dark) {
  :root { --szoveg:#e6e3dd; --halvany:#a2a8b0; --kek:#7fb2e0; --hatter:#15171a;
          --lap:#1c1f23; --vonal:#2e3339; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--hatter); color:var(--szoveg);
       font-family: Georgia, 'Times New Roman', serif; font-size:19px; line-height:1.62; }
.lap { max-width: 44rem; margin: 0 auto; padding: 2.2rem 1.15rem 5rem; background:var(--lap); }
h1 { font-size:1.72rem; line-height:1.25; color:var(--kek); margin:0 0 .3em; }
h1 + .alcim { color:var(--halvany); font-size:.95rem; margin:0 0 2.2rem;
              font-family: system-ui, sans-serif; }
h2 { font-size:1.2rem; color:var(--kek); margin:2.6rem 0 .2em; line-height:1.3;
     font-family: system-ui, sans-serif; }
h2::after { content:""; display:block; width:3.2rem; height:3px;
            background:var(--sarga); margin:.55rem 0 .9rem; }
h3 { font-size:1.02rem; margin:1.8rem 0 .4rem; font-family: system-ui, sans-serif; }
p { margin:0 0 1.05em; }
strong { color:var(--kek); }
nav { background:transparent; border:1px solid var(--vonal); border-radius:10px;
      padding:1rem 1.2rem; margin:0 0 2.6rem; font-family: system-ui, sans-serif;
      font-size:.88rem; line-height:1.75; }
nav b { display:block; margin-bottom:.4rem; color:var(--halvany);
        text-transform:uppercase; letter-spacing:.06em; font-size:.74rem; }
nav a { display:block; color:var(--szoveg); text-decoration:none; }
nav a:hover { color:var(--kek); text-decoration:underline; }
hr { border:0; border-top:1px solid var(--vonal); margin:3rem 0; }
.kerdes { border-left:3px solid var(--sarga); padding-left:1rem; margin:0 0 1.2em; }
.kerdes .k { display:block; font-weight:bold; color:var(--kek); margin-bottom:.25em; }
footer { color:var(--halvany); font-size:.82rem; font-family: system-ui, sans-serif;
         margin-top:3.5rem; padding-top:1.2rem; border-top:1px solid var(--vonal); }
@media (max-width: 34rem) { body { font-size:17.5px; } .lap { padding:1.6rem 1rem 4rem; } }
"""


def alakit(md):
    sorok = md.split('\n')
    cim, alcim = '', ''
    blokkok, most, szint = [], [], None
    for l in sorok:
        if re.fullmatch(r'\s*-{3,}\s*', l):
            continue
        m = re.match(r'^(#{1,3})\s+(.*)', l)
        if m:
            if most:
                blokkok.append((szint, ' '.join(most))); most = []
            szint = len(m.group(1))
            blokkok.append(('h%d' % szint, m.group(2)))
            szint = None
            continue
        if l.strip():
            most.append(l.strip())
        elif most:
            blokkok.append((None, ' '.join(most))); most = []
    if most:
        blokkok.append((None, ' '.join(most)))

    ki, tartalom, n = [], [], 0
    for tipus, szoveg in blokkok:
        if tipus == 'h1':
            cim = szoveg; continue
        sz = html.escape(szoveg)
        sz = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', sz, flags=re.S)
        if tipus == 'h2':
            n += 1
            horgony = f's{n}'
            tartalom.append((horgony, szoveg))
            ki.append(f'<h2 id="{horgony}">{sz}</h2>')
        elif tipus == 'h3':
            ki.append(f'<h3>{sz}</h3>')
        else:
            # szamozott onellenorzo kerdes: a kerdes es a valasz vizualisan elvalik
            km = re.match(r'^(<strong>)?(\d+\.\s.+?\?)(</strong>)?\s*(.*)$', sz, flags=re.S)
            if km and km.group(2) and len(km.group(2)) < 320:
                valasz = km.group(4).strip()
                ki.append(f'<div class="kerdes"><span class="k">{km.group(2)}</span>{valasz}</div>')
            else:
                ki.append(f'<p>{sz}</p>')
    return cim, tartalom, '\n'.join(ki)


def lap(cim, tartalom, torzs, forras):
    tj = '\n'.join(f'<a href="#{h}">{html.escape(c)}</a>' for h, c in tartalom)
    return f"""<!doctype html>
<html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(cim)}</title>
<style>{CSS}</style></head><body><div class="lap">
<h1>{html.escape(cim)}</h1>
<p class="alcim">15 napos projektmenedzser-tanulóterv &middot; Angelika</p>
<nav><b>Ezen a lapon</b>
{tj}
</nav>
{torzs}
<footer>Forrás: {html.escape(forras)}</footer>
</div></body></html>"""


if __name__ == '__main__':
    be, kiut = sys.argv[1], sys.argv[2]
    md = open(be, encoding='utf8').read()
    cim, tartalom, torzs = alakit(md)
    open(kiut, 'w', encoding='utf8').write(lap(cim, tartalom, torzs, os.path.basename(be)))
    print('mentve:', kiut, os.path.getsize(kiut), 'bajt |', len(tartalom), 'szakasz')
