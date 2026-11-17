#!/usr/bin/env python3
"""Gépi (ASR) előadás-átirat tisztítása .docx-ből.

Két kimenetet ad:
  1. <ki>.md    -- 5 perces [perc:mp] horgonyokkal, a tudásbázisba (munkaanyag)
  2. <ki>.docx  -- IDŐBÉLYEG NÉLKÜL, olvasásra, visszaküldhető

Egyik sem javítja a felismerési hibákat. Használat:
  python3 scripts/atirat-tisztito.py <bemenet.docx> <kimenet-alap> "<cim>"
"""
import sys, re, zipfile, os

TS   = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?$')
DUR  = re.compile(r'^\d+\s*(másodperc|perc|óra)')
DUR2 = re.compile(r'^\d+\s*(óra|perc),')
SKIP = {'Az űrlap teteje', 'Az űrlap alja'}

def olvas(path):
    z = zipfile.ZipFile(path)
    xml = z.read('word/document.xml').decode('utf8')
    paras = re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)
    out = []
    for p in paras:
        t = ''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p, re.S))
        t = t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').strip()
        if t:
            out.append(t)
    return out

def tisztit(raw):
    """(idobelyeg, szoveg) parok, a zaj nelkul."""
    blokkok, buf, ts = [], [], None
    def flush():
        if buf:
            blokkok.append((ts, ' '.join(buf)))
            buf.clear()
    for t in raw:
        if t in SKIP:            continue
        if TS.match(t):          flush(); ts = t; continue
        if DUR.match(t) or DUR2.match(t): continue
        buf.append(t)
    flush()
    return blokkok

def mp(ts):
    r = [int(x) for x in ts.split(':')]
    return r[0]*60 + r[1] if len(r) == 2 else r[0]*3600 + r[1]*60 + r[2]

def esc(s):
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def docx_ir(path, cim, bekezdesek):
    """Minimalis, ervenyes .docx. python-docx nem kell hozza."""
    body = ''.join(
        '<w:p><w:pPr><w:spacing w:after="160"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
        % esc(b) for b in bekezdesek)
    cim_p = ('<w:p><w:pPr><w:spacing w:after="240"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="32"/></w:rPr>'
             '<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % esc(cim))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body>' + cim_p + body + '<w:sectPr/></w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)

def main():
    be, alap, cim = sys.argv[1], sys.argv[2], sys.argv[3]
    raw = olvas(be)
    blokkok = tisztit(raw)
    szoveg = [t for _, t in blokkok]
    hossz = blokkok[-1][0] if blokkok and blokkok[-1][0] else '?'

    # 1) horgonyzott md a tudasbazisba
    sorok, akt = [], -1
    for ts, t in blokkok:
        b = mp(ts)//300 if ts else 0
        if b != akt:
            akt = b
            sorok.append('\n\n### [%d:%02d]\n' % (b*5//60, b*5 % 60))
        sorok.append(t)
    fej = ('# %s -- nyers átirat (tisztított)\n\n'
           'FORRÁS: %s. Gépi átirat.\n'
           'AMIT EZ CSINÁLT: kivette az időbélyeg- és időtartam-sorokat, 5 perces blokkokra tagolt.\n'
           '**AMIT NEM: a felismerési hibákat NEM javította.**\n'
           'Az előadás hossza: %s. Szó: kb. %d.\n'
           % (cim, os.path.basename(be), hossz, sum(len(x.split()) for x in szoveg)))
    open(alap + '.md', 'w').write(fej + re.sub(r' {2,}', ' ', ' '.join(sorok)))

    # 2) idobelyeg NELKULI docx, olvasasra
    # mondathataron bekezdesekbe tordelve, kb. 900 karakteres blokkokban
    egyben = ' '.join(szoveg)
    mondatok = re.split(r'(?<=[.!?]) +', egyben)
    bek, akt_b = [], ''
    for m in mondatok:
        if len(akt_b) + len(m) > 900:
            bek.append(akt_b.strip()); akt_b = ''
        akt_b += m + ' '
    if akt_b.strip():
        bek.append(akt_b.strip())
    docx_ir(alap + '.docx', cim, bek)

    print('md   :', alap + '.md')
    print('docx :', alap + '.docx', '(%d bekezdes)' % len(bek))
    print('szo  :', sum(len(x.split()) for x in szoveg), '| hossz:', hossz)

if __name__ == '__main__':
    main()
