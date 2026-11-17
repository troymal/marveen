"""pptxzip -- PPTX szerkesztes python-pptx NELKUL, nyers zip/XML uton.

EZ A FALLBACK, NEM AZ ELSO VALASZTAS (javitva 2026-09-29 15:4x).

AZ ELSO VALASZTAS a python-pptx, es AZ ELERHETO. A receptet a
`.claude/skills/pptx-gazda-sablonbol` skill irja le:
    /opt/marveen/.local/bin/python3.11 -m venv <scratchpad>/pptxenv
    <scratchpad>/pptxenv/bin/pip install python-pptx      # 1.0.2
A rendszer-python3.12-ben nincs `pptx` es nincs `pip`, es en ebbol arra kovetkeztettem,
hogy egyaltalan nincs ut. Tevedtem, es ez a modul ELOBB keszult el, mint hogy a sajat
skillemet elolvastam volna.

AMIERT MEGIS MARAD: a venv-hez HALO kell (PyPI). Ehhez a modulhoz semmi, csak a standard
konyvtar. Ha a pip nem er ki, vagy egy masik agens kornyezeteben nincs venv, ez az ut all.

AMIT TUD: meglevo dia klonozasa sablonkent, bekezdes-szoveg csereje, kep csereje,
dia-sorrend es darabszam allitasa. AMIT NEM: uj layoutot rajzolni, es MEGNYITNI a
fajlt -- a vizualis ellenorzes (szovegtulfolyas) a gazdara marad.
"""
import zipfile, re, copy, os
import xml.etree.ElementTree as ET

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('a', A); ET.register_namespace('p', P); ET.register_namespace('r', R)


class Pptx:
    def __init__(self, path):
        self.parts = {}
        self.order = []
        with zipfile.ZipFile(path) as z:
            for it in z.infolist():
                self.parts[it.filename] = z.read(it.filename)
                self.order.append(it.filename)

    # ---- dia-lista ----
    def slides(self):
        return sorted([n for n in self.parts if re.match(r'ppt/slides/slide\d+\.xml$', n)],
                      key=lambda n: int(re.findall(r'\d+', n)[0]))

    def texts(self, slide):
        """A dia bekezdesei, mindegyik a benne levo run-szovegek listajaval."""
        out = []
        x = self.parts[slide].decode('utf8')
        for m in re.finditer(r'<a:p>.*?</a:p>', x, re.S):
            runs = re.findall(r'<a:t>(.*?)</a:t>', m.group(0), re.S)
            if runs:
                out.append(runs)
        return out

    def set_para(self, slide, old_joined, new_text):
        """Egy bekezdes teljes szovegenek csereje.

        A bekezdes tobb run-ra lehet vagva (nyelvi futamok), ezert az OSSZEFUZOTT
        szoveg alapjan azonositunk, az uj szoveget az ELSO runba tesszuk, a
        tobbit kiuritjuk -- igy a formazas az elso run-tol orokolt marad.

        AZ EGYEZES strip()-elt, mert a runok vegen gyakran all egy-ket szokoz
        (merve: a 09-23-i cimlapon a 'Funkciotervezes' bekezdes runjai
        ['Funkciotervezes', '  '] voltak, tehat a pontos egyezes 0 talalatot adott).
        Ha a talalat nem PONTOSAN egy, kivetelt dobunk: a csendes nem-csere
        rosszabb, mint a hiba, mert a regi szoveg bennemarad a kesz fajlban.
        """
        x = self.parts[slide].decode('utf8')
        hits = 0
        def repl(m):
            nonlocal hits
            blk = m.group(0)
            runs = re.findall(r'<a:t>(.*?)</a:t>', blk, re.S)
            if ''.join(runs).strip() != old_joined.strip():
                return blk
            hits += 1
            first = [True]
            def one(rm):
                if first[0]:
                    first[0] = False
                    return '<a:t>' + new_text + '</a:t>'
                return '<a:t></a:t>'
            return re.sub(r'<a:t>.*?</a:t>', one, blk, flags=re.S)
        x = re.sub(r'<a:p>.*?</a:p>', repl, x, flags=re.S)
        if hits != 1:
            raise ValueError(f'{slide}: {hits} bekezdes egyezett erre: {old_joined!r}')
        self.parts[slide] = x.encode('utf8')

    # ---- dia klonozas ----
    def clone(self, src_slide):
        """Klonozza a diat a prezentacio VEGERE, az uj dia nevet adja vissza.

        A JEGYZETLAP-HIVATKOZAST KIVESSZUK, es ez nem izles kerdese
        (2026-10-27, eles hiba: a PowerPoint javitast ajanlott a kesz fajlra).
        A forras-dia rels-eben benne van a notesSlide hivatkozas. Tizenharom klon
        utan TIZENNEGY dia mutatott ugyanarra a notesSlide1.xml-re, egy jegyzetlap
        viszont EGY diahoz tartozik -- ettol a csomag ervenytelen lett. A klonnak
        amugy sincs szuksege a forras jegyzeteire.
        """
        nums = [int(re.findall(r'\d+', n)[0]) for n in self.slides()]
        new_n = max(nums) + 1
        new = f'ppt/slides/slide{new_n}.xml'
        self.parts[new] = self.parts[src_slide]
        src_rels = src_slide.replace('slides/', 'slides/_rels/') + '.rels'
        new_rels = new.replace('slides/', 'slides/_rels/') + '.rels'
        rels_x = self.parts[src_rels].decode('utf8')
        rels_x = re.sub(r'<Relationship[^>]*?notesSlide[^>]*?/>', '', rels_x)
        self.parts[new_rels] = rels_x.encode('utf8')
        self._add_content_type(new)
        self._append_to_presentation(new)
        return new

    def _add_content_type(self, slide):
        ct = self.parts['[Content_Types].xml'].decode('utf8')
        if f'PartName="/{slide}"' in ct:
            return
        entry = (f'<Override PartName="/{slide}" ContentType="application/vnd.'
                 'openxmlformats-officedocument.presentationml.slide+xml"/>')
        ct = ct.replace('</Types>', entry + '</Types>')
        self.parts['[Content_Types].xml'] = ct.encode('utf8')

    def _append_to_presentation(self, slide):
        rels = self.parts['ppt/_rels/presentation.xml.rels'].decode('utf8')
        used = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels)]
        rid = f'rId{max(used)+1}'
        target = slide.replace('ppt/', '')
        rels = rels.replace('</Relationships>',
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/slide" Target="{target}"/></Relationships>')
        self.parts['ppt/_rels/presentation.xml.rels'] = rels.encode('utf8')
        pr = self.parts['ppt/presentation.xml'].decode('utf8')
        ids = [int(m) for m in re.findall(r'<p:sldId id="(\d+)"', pr)]
        pr = pr.replace('</p:sldIdLst>',
            f'<p:sldId id="{max(ids)+1}" r:id="{rid}"/></p:sldIdLst>')
        self.parts['ppt/presentation.xml'] = pr.encode('utf8')

    def drop_slides(self, keep):
        """Csak a `keep` listaban szereplo diak maradnak, a megadott SORRENDBEN."""
        pr = self.parts['ppt/presentation.xml'].decode('utf8')
        rels = self.parts['ppt/_rels/presentation.xml.rels'].decode('utf8')
        rid_of = {}
        for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="(slides/slide\d+\.xml)"', rels):
            rid_of['ppt/' + m.group(2)] = m.group(1)
        items = ''.join(f'<p:sldId id="{256+i}" r:id="{rid_of[s]}"/>' for i, s in enumerate(keep))
        pr = re.sub(r'<p:sldIdLst>.*?</p:sldIdLst>', f'<p:sldIdLst>{items}</p:sldIdLst>', pr, flags=re.S)
        self.parts['ppt/presentation.xml'] = pr.encode('utf8')

    # ---- kep ----
    def replace_media(self, media_name, file_path):
        """Egy meglevo ppt/media/<nev> bytejainak csereje. A KITERJESZTES marad,
        tehat png helyere png-t, jpg helyere jpg-t tegyel."""
        key = f'ppt/media/{media_name}'
        if key not in self.parts:
            raise KeyError(key)
        self.parts[key] = open(file_path, 'rb').read()

    def save(self, path):
        """Kiirja a csomagot. EGY NEVET CSAK EGYSZER.

        BUKTATO (2026-10-27, eles hiba, a gazda kepernyokepen kuldte vissza a
        PowerPoint >>javitast ajanlok<< ablakat): az `order` tartalmazhat ismetlodo
        nevet, es a regi valtozat ilyenkor KETSZER irta ki ugyanazt a bejegyzest. A
        zipfile csak egy UserWarning-ot ad ra, a csomag viszont ervenytelen lesz.
        A `seen` ezert MINDKET korre vonatkozik, nem csak a masodikra.
        """
        seen = set()
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            for n in self.order:
                if n in self.parts and n not in seen:
                    z.writestr(n, self.parts[n]); seen.add(n)
            for n, d in self.parts.items():
                if n not in seen:
                    z.writestr(n, d); seen.add(n)
        return path


def validate(path):
    """Amit meg lehet ellenorizni megnyitas nelkul. NEM helyettesiti a ranezest."""
    import xml.dom.minidom as md
    z = zipfile.ZipFile(path)
    assert z.testzip() is None, 'serult zip'
    for n in z.namelist():
        if n.endswith(('.xml', '.rels')):
            md.parseString(z.read(n))
    pr = z.read('ppt/presentation.xml').decode('utf8')
    rels = z.read('ppt/_rels/presentation.xml.rels').decode('utf8')
    ct = z.read('[Content_Types].xml').decode('utf8')
    rids = re.findall(r'<p:sldId id="\d+" r:id="(rId\d+)"/>', pr)
    targets = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    res = []
    for rid in rids:
        t = targets.get(rid)
        assert t, f'{rid} nincs a presentation.xml.rels-ben'
        part = 'ppt/' + t.replace('../', '')
        assert part in z.namelist(), f'{part} hivatkozva, de nincs a zipben'
        assert f'PartName="/{part}"' in ct, f'{part} nincs a [Content_Types].xml-ben'
        res.append(part)
    for part in res:
        r = part.replace('slides/', 'slides/_rels/') + '.rels'
        assert r in z.namelist(), f'{r} hianyzik'
        for img in re.findall(r'Target="\.\./(media/[^"]+)"', z.read(r).decode('utf8')):
            assert 'ppt/' + img in z.namelist(), f'{img} hivatkozva, de nincs a zipben'
    return res
