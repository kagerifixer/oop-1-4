import os, re, json, sys, subprocess, tempfile
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
SRC = str(ROOT / 'src' / 'ООПНООФГОС3.0.pdf')
OUT = str(ROOT / 'oop-noo-md')
ASSETS = os.path.join(OUT, 'assets')


def layout_text():
    """Постраничный текст с сохранением колонок (для разбора оглавления)."""
    tmp = os.path.join(tempfile.gettempdir(), 'oop_layout.txt')
    if not os.path.exists(tmp):
        subprocess.run(['pdftotext', '-layout', SRC, tmp], check=True)
    return open(tmp, encoding='utf-8').read().split('\f')

H1_SET = {
    'ПОЯСНИТЕЛЬНАЯ ЗАПИСКА', 'ПЛАНИРУЕМЫЕ РЕЗУЛЬТАТЫ', 'СОДЕРЖАТЕЛЬНЫЙ РАЗДЕЛ',
    'ОРГАНИЗАЦИОННЫЙ РАЗДЕЛ', 'СИСТЕМА ОЦЕНКИ ДОСТИЖЕНИЯ ПЛАНИРУЕМЫХ РЕЗУЛЬТАТОВ',
    'ЛИЧНОСТНЫЕ РЕЗУЛЬТАТЫ', 'МЕТАПРЕДМЕТНЫЕ РЕЗУЛЬТАТЫ', 'ПРЕДМЕТНЫЕ РЕЗУЛЬТАТЫ',
    'УНИВЕРСАЛЬНЫЕ УЧЕБНЫЕ ДЕЙСТВИЯ',
}
H1_RE = re.compile(r'^(Программа (по|курса|внеурочного|интегрированного|формирования)|'
                  r'Рабочая программа воспитания|Программа коррекционной работы)')
H2_RE = re.compile(
    r'^(Пояснительная записка|Содержание\b|Тематическое планирование|Планируемые результаты|'
    r'Система оценки|Учебный план|Годовой учебный план|Календарный\b|Модуль\b|'
    r'РАЗДЕЛ\b|Раздел\b|Общая характеристика|Целевой раздел|Содержательный раздел|'
    r'Организационный раздел|Общая характеристика|Цели изучения|Место\b|'
    r'Основные виды деятельности|Виды деятельности|Материально-техническое|'
    r'Учебно-методическое|Кадровые условия|Финансовые условия|'
    r'Психолого-педагогические|Информационно-образовательная|Общесистемные требования|'
    r'Требования к условиям|Критерии и нормы|Формы промежуточной|'
    r'Содержание обучения|Содержание учебного|Содержание курса|'
    r'Планируемые предметные|Тематическое планирование курса)')
GRADE_RE = re.compile(r'^[1-4]\s*КЛАСС$')

GLYPH = {
    '\uf0b7': '•', '\uf0d8': '•', '\uf0a7': '•', '\uf02d': '•',
    '\uf0fc': '•', '\uf0a2': '•', '\uf074': '•', '\uf0a8': '•',
    '\uf02a': '•', '\uf0d8': '•', '\uf0b0': '•',
}
FOOTERS = {
    'Федеральная рабочая программа | Труд (технология). 1-4 классы',
}

def norm(s):
    for k, v in GLYPH.items():
        s = s.replace(k, v)
    s = s.replace('\u00ad', '').replace('\u00a0', ' ')
    s = s.replace('\ufeff', '')
    return s

def clean(s):
    s = norm(s)
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()

# ---------------- TOC ----------------
def parse_toc(layout_pages):
    entries = []
    for pg in layout_pages[1:4]:
        for line in pg.split('\n'):
            raw = line.rstrip()
            m = re.match(r'^(?P<indent>\s*)(?P<title>.*?)\s*\.{2,}\s*(?P<page>\d{1,4})\s*$', raw)
            if not m:
                continue
            title = m.group('title').strip()
            if not title:
                continue
            entries.append((int(m.group('page')), len(m.group('indent').replace('\t', '    ')), title))
    by_page = {}
    for page, indent, title in entries:
        if page not in by_page or indent < by_page[page][0]:
            by_page[page] = (indent, title)
    ordered = sorted((p, v[1]) for p, v in by_page.items())
    return ordered

TRANS = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
         'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
         'у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y',
         'ь':'','э':'e','ю':'yu','я':'ya'}
def slug(t):
    out = []
    for ch in t.lower():
        if ch in TRANS:
            out.append(TRANS[ch])
        elif ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        else:
            out.append('-')
    s = re.sub(r'-+', '-', ''.join(out)).strip('-')
    return s[:60] or 'section'

# ---------------- borders/tables ----------------
def thin_rects(page):
    out = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 're':
                r = it[1]
            elif it[0] == 'l':
                p1, p2 = it[1], it[2]
                r = pymupdf.Rect(min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y))
            else:
                continue
            if (r.height <= 1.8 and r.width > 3) or (r.width <= 1.8 and r.height > 3):
                out.append(r)
    return out

def connected(rects, tol=1.5):
    n = len(rects)
    parent = list(range(n))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i in range(n):
        ri = rects[i]
        for j in range(i + 1, n):
            rj = rects[j]
            if (ri.x0 <= rj.x1 + tol and rj.x0 <= ri.x1 + tol and
                    ri.y0 <= rj.y1 + tol and rj.y0 <= ri.y1 + tol):
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[rb] = ra
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(rects[i])
    return list(groups.values())

def cluster(vals, tol=2.0):
    vals = sorted(vals)
    g = []
    for v in vals:
        if g and v - g[-1][-1] <= tol:
            g[-1].append(v)
        else:
            g.append([v])
    return [sum(x) / len(x) for x in g]

def build_table(rects, words):
    H = [r for r in rects if r.height <= 1.8 and r.width > 3]
    V = [r for r in rects if r.width <= 1.8 and r.height > 3]
    if len(H) < 1 or len(V) < 1:
        return None
    allx = cluster([r.x0 for r in V] + [r.x1 for r in V])
    ally = cluster([r.y0 for r in H] + [r.y1 for r in H])
    if len(allx) < 3 or len(ally) < 3:
        return None
    tw = allx[-1] - allx[0]
    th = ally[-1] - ally[0]
    Hf = [r for r in H if r.width >= 0.55 * tw]
    Vf = [r for r in V if r.height >= 0.55 * th]
    xs = cluster([r.x0 for r in Vf] + [r.x1 for r in Vf]) if len(Vf) >= 2 else allx
    ys = cluster([r.y0 for r in Hf] + [r.y1 for r in Hf]) if len(Hf) >= 2 else ally
    if len(xs) < 3 or len(ys) < 3:
        return None
    ncol = len(xs) - 1
    nrow = len(ys) - 1
    cx0 = min(r.x0 for r in rects)
    cx1 = max(r.x1 for r in rects)
    cy0 = min(r.y0 for r in rects)
    cy1 = max(r.y1 for r in rects)
    grid = [[[] for _ in range(ncol)] for _ in range(nrow)]
    for w in words:
        xc = (w[0] + w[2]) / 2
        yc = (w[1] + w[3]) / 2
        if not (cy0 - 1 <= yc <= cy1 + 1 and cx0 - 1 <= xc <= cx1 + 1):
            continue
        ri = 0 if yc < ys[0] else nrow - 1
        for i in range(nrow):
            if ys[i] - 0.5 <= yc < ys[i + 1] + 0.5:
                ri = i
                break
        cj = 0 if xc < xs[0] else ncol - 1
        for j in range(ncol):
            if xs[j] - 0.5 <= xc < xs[j + 1] + 0.5:
                cj = j
                break
        grid[ri][cj].append(w)
    rows = []
    for i in range(nrow):
        row = []
        for j in range(ncol):
            ws = sorted(grid[i][j], key=lambda w: (round((w[1] + w[3]) / 2, 1), w[0]))
            row.append(clean(' '.join(w[4] for w in ws)))
        if any(row):
            rows.append(row)
    if len(rows) < 2:
        return None
    nonempty = sum(1 for r in rows for c in r if c)
    if nonempty < 4:
        return None
    bbox = (cx0, cy0, cx1, cy1)
    return (bbox, rows)

def page_tables(page, words):
    rs = thin_rects(page)
    if not rs:
        return []
    tabs = []
    for comp in connected(rs):
        t = build_table(comp, words)
        if t:
            tabs.append(t)
    return tabs

def overlap_ratio(bb, rect):
    x0 = max(bb[0], rect[0]); y0 = max(bb[1], rect[1])
    x1 = min(bb[2], rect[2]); y1 = min(bb[3], rect[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area = (bb[2] - bb[0]) * (bb[3] - bb[1])
    return inter / area if area else 0.0

def md_table(rows):
    def esc(c):
        return re.sub(r'\s+', ' ', c.replace('|', '\\|')).strip()
    rows = [[esc(c) for c in r] for r in rows]
    n = max(len(r) for r in rows)
    rows = [r + [''] * (n - len(r)) for r in rows]
    head = rows[0]
    out = ['| ' + ' | '.join(head) + ' |', '| ' + ' | '.join(['---'] * n) + ' |']
    for r in rows[1:]:
        out.append('| ' + ' | '.join(r) + ' |')
    return '\n'.join(out)

def is_heading(t, size, bold):
    if len(t) < 2:
        return None
    if t in H1_SET or GRADE_RE.match(t):
        return 1
    if H1_RE.match(t) and len(t) <= 160 and not t.endswith('.'):
        return 1
    if size >= 13.5 and len(t) <= 160 and not re.search(r'[.;]$', t):
        return 2
    if H2_RE.match(t) and len(t) <= 140 and not t.endswith('.') and t.count(' ') <= 11:
        return 2
    if size >= 12.4 and len(t) <= 120 and not t.endswith('.') and t.count(' ') <= 12:
        return 3
    if bold and t.isupper() and 3 <= len(t) <= 90:
        return 2
    return None

def list_item(t):
    m = re.match(r'^[•\-–—]\s+(.*)$', t)
    if m:
        return '- ' + m.group(1)
    m = re.match(r'^(\d{1,2})[.)]\s+(.*)$', t)
    if m:
        return m.group(1) + '. ' + m.group(2)
    return None

def drop_footer_words(words):
    bands = {}
    for w in words:
        key = round((w[1] + w[3]) / 2)
        bands.setdefault(key, []).append(w)
    drop = set()
    for key, ws in bands.items():
        ws_sorted = sorted(ws, key=lambda w: w[0])
        text = clean(' '.join(w[4] for w in ws_sorted))
        if text in FOOTERS or text.startswith('Федеральная рабочая программа | Труд'):
            for w in ws_sorted:
                drop.add(id(w))
    return [w for w in words if id(w) not in drop]

# ---------------- main ----------------
def main():
    doc = pymupdf.open(SRC)
    layout = layout_text()
    toc = parse_toc(layout)
    print('TOC entries:', len(toc))
    for p, t in toc:
        print('  ', p, t[:70])

    os.makedirs(ASSETS, exist_ok=True)
    pages_elems = {}
    img_meta = []

    N = len(doc)
    for pi in range(N):
        page = doc[pi]
        pageno = pi + 1
        words = drop_footer_words(page.get_text('words'))
        tables = page_tables(page, words)
        trects = [t[0] for t in tables]
        d = page.get_text('dict')
        elems = []
        for tbb, rows in tables:
            elems.append((tbb[1], 'table', rows))
        for block in d['blocks']:
            if block.get('type') != 0:
                continue
            bb = block['bbox']
            if any(overlap_ratio(bb, tr) > 0.5 for tr in trects):
                continue
            buf = []
            state = {'y': block['bbox'][1], 'kind': 'p'}
            pending = {'marker': None}

            def flush():
                if buf:
                    txt = clean(' '.join(buf))
                    txt = re.sub(r'(?<=[а-яёА-ЯЁ])-\s+([а-яё])', r'-\1', txt)
                    if txt:
                        elems.append((state['y'], state['kind'], txt))
                    buf.clear()

            for ln in block['lines']:
                txt = clean(''.join(sp['text'] for sp in ln['spans']))
                if not txt:
                    continue
                y = ln['bbox'][1]
                if txt in FOOTERS:
                    continue
                if re.fullmatch(r'\d{1,4}', txt):
                    continue
                size = max(sp['size'] for sp in ln['spans'])
                bold = any(sp['flags'] & 16 for sp in ln['spans'])
                main = max(ln['spans'], key=lambda sp: len(sp['text'].strip()))
                if len(main['text'].strip()) >= 3:
                    size = main['size']
                    bold = bool(main['flags'] & 16)
                mono = re.fullmatch(r'\d{1,2}[.)]?', txt) or re.fullmatch(r'[•\-–—]', txt)
                if mono:
                    flush()
                    pending['marker'] = txt if txt.endswith(('.', ')')) else '-'
                    continue
                lvl = is_heading(txt, size, bold)
                if lvl:
                    flush()
                    pending['marker'] = None
                    elems.append((y, 'h', (lvl, txt)))
                    continue
                li = list_item(txt)
                if li:
                    flush()
                    pending['marker'] = None
                    buf.append(li)
                    state['y'] = y
                    state['kind'] = 'li'
                    continue
                if pending['marker'] is not None:
                    txt = pending['marker'] + ' ' + txt
                    pending['marker'] = None
                if not buf:
                    state['y'] = y
                    state['kind'] = 'p'
                buf.append(txt)
            flush()
        # images
        for im in page.get_image_info(xrefs=True):
            w = im.get('width') or 0
            h = im.get('height') or 0
            if w >= 200 and h >= 150:
                im = dict(im)
                im['_page'] = pageno
                elems.append((im['bbox'][1], 'img', im))
        elems.sort(key=lambda e: e[0])
        if pageno not in (1, 2, 3, 4, 5):
            pages_elems[pageno] = elems

    # save significant images
    for pageno, elems in pages_elems.items():
        for y, kind, payload in elems:
            if kind != 'img':
                continue
            im = payload
            xref = im.get('xref')
            try:
                ext = doc.extract_image(xref)
            except Exception:
                continue
            fname = f'p{pageno:04d}-x{xref}.{ext["ext"]}'
            with open(os.path.join(ASSETS, fname), 'wb') as f:
                f.write(ext['image'])
            img_meta.append((pageno, xref, fname, im['width'], im['height']))

    # write section files
    ranges = []
    for idx, (start, title) in enumerate(toc):
        end = toc[idx + 1][0] - 1 if idx + 1 < len(toc) else N
        ranges.append((start, end, title))
    manifest = []
    for idx, (start, end, title) in enumerate(ranges):
        name = f'{idx + 1:02d}-{slug(title)}.md'
        lines = [f'# {title}', '',
                 f'> Основная образовательная программа начального общего образования '
                 f'ГБОУ Школа № 1366. ФГОС 3.0. Страницы PDF: {start}–{end}.', '']
        title_key = re.sub(r'\s+', '', title).lower()
        first_h1_seen = False

        flat = []
        for p in range(start, end + 1):
            for y, kind, payload in pages_elems.get(p, []):
                flat.append((p, kind, payload))

        merged = []
        pend = None
        for p, kind, payload in flat:
            if kind == 'table':
                rows = payload
                ncol = max(len(r) for r in rows)
                if pend and p == pend['page'] + 1 and ncol == pend['ncol']:
                    hdr = ' '.join(pend['rows'][0])
                    first = ' '.join(rows[0])
                    if re.sub(r'\s+', '', hdr) == re.sub(r'\s+', '', first):
                        rows = rows[1:]
                    pend['rows'].extend(rows)
                    pend['page'] = p
                else:
                    if pend:
                        merged.append(('table', pend['rows']))
                    pend = {'rows': list(rows), 'ncol': ncol, 'page': p}
            else:
                if pend:
                    merged.append(('table', pend['rows']))
                    pend = None
                merged.append((kind, payload))
        if pend:
            merged.append(('table', pend['rows']))

        def blank():
            if lines and lines[-1] != '':
                lines.append('')

        for kind, payload in merged:
            if kind == 'h':
                lvl, t = payload
                key = re.sub(r'\s+', '', t).lower()
                if lvl == 1 and not first_h1_seen:
                    first_h1_seen = True
                    if title_key.startswith(key) or key.startswith(title_key):
                        continue
                else:
                    first_h1_seen = True
                blank()
                lines.append('#' * lvl + ' ' + t)
                lines.append('')
            elif kind == 'p':
                blank()
                lines.append(payload)
                lines.append('')
            elif kind == 'li':
                lines.append(payload)
            elif kind == 'table':
                blank()
                lines.append(md_table(payload))
                lines.append('')
            elif kind == 'img':
                im = payload
                p = im.get('_page')
                fname = f'p{p:04d}-x{im.get("xref")}.{doc.extract_image(im["xref"])["ext"]}'
                blank()
                lines.append(f'![Изображение (стр. {p}, xref {im.get("xref")})](assets/{fname})')
                lines.append('')
        out = []
        for ln in lines:
            if ln == '' and out and out[-1] == '':
                continue
            out.append(ln)
        lines = out
        text = '\n'.join(lines)
        text = re.sub(r'Федеральная рабочая программа\s*\\?\|\s*', '', text)
        text = re.sub(r'Федеральная рабочая программа\s*\\?\|\s*Труд'
                      r'\s*(?:\(технология\)\.?)?\s*(?:1-4)?\s*(?:классы)?', '', text)
        text = re.sub(r'\(технология\)\.\s*1-4 классы', '', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\|[ \t]+\|', '| |', text)
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            f.write(text)
        manifest.append((idx + 1, name, title, start, end))
        print('wrote', name, start, end)

    # README
    readme = ['# Основная образовательная программа начального общего образования',
              '',
              '**ГБОУ Школа № 1366, Москва, 2025** · ФГОС 3.0 · на основе ФОП НОО',
              '',
              f'- Исходный файл: [`../src/ООПНООФГОС3.0.pdf`](../src/ООПНООФГОС3.0.pdf)',
              f'- Страниц в PDF: {N}',
              f'- Разделов: {len(manifest)}',
              f'- Изображений (значимых): {len({m[2] for m in img_meta})}',
              '',
              '> Документ автоматически сконвертирован из PDF в Markdown: текст, таблицы и '
              'значимые изображения. Таблицы восстановлены по векторным границам ячеек; '
              'в сложных таблицах с объединёнными ячейками возможна неточная разбивка, '
              'но весь исходный текст сохранён. Повторяющиеся колонтитулы и служебные '
              'номера страниц удалены. Дополнительные метаданные — в `manifest.json`.',
              '',
              '## Дополнительные материалы',
              '',
              '- [Промежуточная аттестация по предметам](attestaciya/README.md) — '
              'что ребёнок должен сдать по каждому предмету, сроки и критерии.',
              '',
              '## Оглавление', '']
    for num, name, title, start, end in manifest:
        readme.append(f'{num}. [{title}]({name}) — стр. {start}–{end}')
    readme.append('')
    with open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(readme))
    json.dump({'toc': [(p, t) for p, t in toc], 'manifest': manifest,
               'images': img_meta}, open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('DONE. images:', len(img_meta))

if __name__ == '__main__':
    main()
