"""Reconstrói tabelas a partir da posição das palavras na página.

Usado pela seleção (arrastar da primeira à última coluna de uma linha pega a linha toda, com as células de várias
linhas) e pela exportação para Excel. Não depende de linhas desenhadas: funciona em tabelas só com espaçamento.
"""
from dataclasses import dataclass, field


@dataclass
class Seg:
    """Trecho contínuo de uma linha de texto (palavras próximas). Um espaço grande separa colunas."""
    x0: float
    y0: float
    x1: float
    y1: float
    words: list = field(default_factory=list)     # índices das palavras

    @property
    def h(self):
        return max(self.y1 - self.y0, 1)

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


def segments(words, gap=2.5):
    """words: lista de (rect, texto, bloco, linha) como em PdfView.words(). Agrupa por linha visual e corta nos
    espaços grandes. Devolve (segs, seg_de_cada_palavra)."""
    rows = {}
    for k, (r, _t, bl, ln) in enumerate(words):
        rows.setdefault((bl, ln), []).append(k)
    segs, of = [], [None] * len(words)
    for ks in rows.values():
        ks.sort(key=lambda k: words[k][0].x0)
        cur = [ks[0]]
        for k in ks[1:]:
            prev = words[cur[-1]][0]
            h = max(prev.height, words[k][0].height, 4)
            if words[k][0].x0 - prev.x1 > gap * h:
                segs.append(cur)
                cur = [k]
            else:
                cur.append(k)
        segs.append(cur)
    out = []
    for ks in segs:
        rs = [words[k][0] for k in ks]
        s = Seg(min(r.x0 for r in rs), min(r.y0 for r in rs), max(r.x1 for r in rs), max(r.y1 for r in rs), ks)
        for k in ks:
            of[k] = len(out)
        out.append(s)
    return out, of


def _xover(a, b, tol=1.0):
    return a.x0 - tol <= b.x1 and b.x0 - tol <= a.x1


def _cluster(items, key_lo, key_hi):
    """Agrupa intervalos que se sobrepõem (em ordem)."""
    items = sorted(items, key=key_lo)
    groups, hi = [], None
    for it in items:
        if groups and key_lo(it) <= hi:
            groups[-1].append(it)
            hi = max(hi, key_hi(it))
        else:
            groups.append([it])
            hi = key_hi(it)
    return groups


def grid(segs, words):
    """Monta a grade (lista de linhas, cada uma lista de textos por coluna) a partir dos trechos escolhidos."""
    if not segs:
        return []
    # colunas: trechos que se sobrepõem na horizontal
    cols = _cluster(segs, lambda s: s.x0, lambda s: s.x1)
    col_of = {}
    for ci, c in enumerate(cols):
        for s in c:
            col_of[id(s)] = ci
    # células: dentro da coluna, linhas coladas (espaço vertical pequeno) formam uma célula só
    cells = []
    for ci, c in enumerate(cols):
        c = sorted(c, key=lambda s: (s.y0, s.x0))
        cur = [c[0]]
        for s in c[1:]:
            p = cur[-1]
            if s.y0 - p.y1 < 0.7 * min(s.h, p.h) and abs(s.cy - p.cy) > 0.3 * p.h:
                cur.append(s)
            elif abs(s.cy - p.cy) <= 0.3 * p.h:       # mesma linha visual (trechos lado a lado)
                cur.append(s)
            else:
                cells.append((ci, cur))
                cur = [s]
        cells.append((ci, cur))
    # linhas da tabela: células cujo intervalo vertical se sobrepõe
    spans = [(min(s.y0 for s in cs), max(s.y1 for s in cs), ci, cs) for ci, cs in cells]
    rows = _cluster(spans, lambda t: t[0] + 0.15 * (t[1] - t[0]) if t[1] - t[0] > 0 else t[0],
                    lambda t: t[1] - 0.15 * (t[1] - t[0]))
    table = []
    for row in rows:
        line = [""] * len(cols)
        for _y0, _y1, ci, cs in sorted(row, key=lambda t: t[0]):
            txt = " ".join(" ".join(words[k][1] for k in s.words) for s in sorted(cs, key=lambda s: (round(s.cy), s.x0)))
            line[ci] = (line[ci] + " " + txt).strip() if line[ci] else txt
        table.append(line)
    # tira colunas vazias
    keep = [j for j in range(len(cols)) if any(r[j] for r in table)]
    return [[r[j] for j in keep] for r in table]


def to_tsv(table):
    """Texto que o Excel/Planilhas cola já separado em colunas."""
    def cell(t):
        t = t.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        return t
    return "\n".join("\t".join(cell(c) for c in r) for r in table)


CELL_MAX = 0.35      # trecho mais largo que isso (fração da página) é texto corrido, não célula


def row_selection(words, segs, of, a, b, page_width, tables=None):
    """Seleção “por linha de tabela”: começo e fim em colunas diferentes, em trechos curtos (células), na mesma
    linha da tabela — ou os dois dentro de uma mesma tabela detectada (aí pega várias linhas).
    Devolve (índices das palavras, trechos) ou None se não for o caso."""
    sa, sb = segs[of[a]], segs[of[b]]
    if _xover(sa, sb, tol=2):
        return None                       # mesma coluna: seleção normal (filtrada pela coluna)
    if max(sa.x1 - sa.x0, sb.x1 - sb.x0) > CELL_MAX * page_width:
        return None                       # linhas longas = texto corrido (ex.: artigo em duas colunas)
    same_row = sa.y0 < sb.y1 and sb.y0 < sa.y1
    if not same_row:
        def inside(s, box):
            return box[0] <= s.x0 and s.x1 <= box[2] and box[1] <= s.cy <= box[3]
        if not any(inside(sa, box) and inside(sb, box) for box, _g in (tables or [])):
            return None
    lo, hi = min(sa.x0, sb.x0) - 2, max(sa.x1, sb.x1) + 2
    top, bot = min(sa.y0, sb.y0), max(sa.y1, sb.y1)
    cand = [s for s in segs if s.x1 >= lo and s.x0 <= hi]
    chosen = [s for s in cand if top - 0.2 * s.h <= s.cy <= bot + 0.2 * s.h]
    if not chosen:
        return None
    # cresce na vertical para pegar o resto das células de várias linhas
    changed = True
    while changed:
        changed = False
        for s in cand:
            if s in chosen:
                continue
            for c in chosen:
                if _xover(s, c) and (0 <= s.y0 - c.y1 < 0.7 * min(s.h, c.h) or 0 <= c.y0 - s.y1 < 0.7 * min(s.h, c.h)):
                    chosen.append(s)
                    changed = True
                    break
    return sorted(k for s in chosen for k in s.words), chosen


def page_tables(words, page_width, min_cols=2, min_rows=2):
    """Todas as regiões da página com cara de tabela (várias colunas alinhadas), como grades."""
    segs, _ = segments(words)
    if not segs:
        return []
    # linhas visuais com 2+ trechos curtos = linha de tabela
    vis = _cluster(segs, lambda s: s.cy - 0.3 * s.h, lambda s: s.cy + 0.3 * s.h)
    tab_lines = [v for v in vis if len(v) >= min_cols and max(s.x1 - s.x0 for s in v) < CELL_MAX * page_width]
    if not tab_lines:
        return []
    # junta linhas de tabela vizinhas (e as linhas de continuação de células entre elas) em blocos
    tab_lines.sort(key=lambda v: min(s.y0 for s in v))
    blocks, cur = [], [tab_lines[0]]
    for v in tab_lines[1:]:
        prev_bot = max(s.y1 for s in cur[-1])
        h = max(s.h for s in v)
        if min(s.y0 for s in v) - prev_bot < 3.5 * h:
            cur.append(v)
        else:
            blocks.append(cur)
            cur = [v]
    blocks.append(cur)
    out = []
    for blk in blocks:
        if len(blk) < min_rows:
            continue
        y0 = min(s.y0 for v in blk for s in v) - 1
        y1 = max(s.y1 for v in blk for s in v) + 1
        x0 = min(s.x0 for v in blk for s in v) - 1
        x1 = max(s.x1 for v in blk for s in v) + 1
        # células de várias linhas passam do topo/fundo da primeira/última linha alinhada: inclui a continuação
        grew = True
        while grew:
            grew = False
            for s in segs:
                if s.x0 >= x0 and s.x1 <= x1 and not (y0 <= s.cy <= y1):
                    if s.cy < y0 and y0 - s.y1 < 0.7 * s.h:
                        y0, grew = s.y0 - 1, True
                    elif s.cy > y1 and s.y0 - y1 < 0.7 * s.h:
                        y1, grew = s.y1 + 1, True
        inside = [s for s in segs if s.cy >= y0 and s.cy <= y1 and s.x0 >= x0 and s.x1 <= x1]
        g = grid(inside, words)
        if len(g) >= min_rows and max(len(r) for r in g) >= min_cols:
            out.append(((x0, y0, x1, y1), g))
    return out
