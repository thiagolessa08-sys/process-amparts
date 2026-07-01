"""Gera o PDF de relatório do assistente.

Dois modos:
- build_report_pdf(report, ...): template RICO a partir de dados estruturados
  (KPIs, composição, barras por dimensão, riscos, resumo) — replica o layout
  do design. É o preferido; a IA emite o `report` via a ferramenta emit_report.
- build_pdf(answer, steps): fallback simples (título + markdown + tabelas)
  quando não há dados estruturados.

fpdf2 com fontes core (latin-1); o texto é sanitizado (cobre pt-BR)."""
import re
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

# paleta
VIOLET = (90, 47, 224)
VIOLET_2 = (123, 84, 238)
VIOLET_BG = (243, 240, 253)
INK = (25, 31, 54)
MUTED = (112, 118, 140)
FAINT = (150, 156, 176)
LINE = (228, 230, 240)
CARD_BG = (250, 250, 253)
GREEN = (22, 163, 74)
AMBER = (224, 130, 14)
RED = (229, 72, 77)
WHITE = (255, 255, 255)

_TONE = {"red": RED, "amber": AMBER, "green": GREEN, "violet": VIOLET_2}
_SEG = {"green": GREEN, "violet": VIOLET_2, "red": RED, "amber": AMBER, "gray": (200, 204, 216)}

_REPL = {
    "•": "-", "→": "->", "–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
    "…": "...", "✓": "OK", "⚠": "!", "❌": "x", "✅": "OK", "≈": "~", " ": " ",
}


def _lat1(s) -> str:
    if s is None:
        return ""
    s = str(s)
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _strip_inline(s: str) -> str:
    return re.sub(r"\*\*|__|`|\*", "", s)


class _Doc(FPDF):
    footer_title = ""

    def footer(self):
        self.set_y(-11)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-9)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*FAINT)
        self.cell((self.w - self.l_margin - self.r_margin) / 3, 5, _lat1("Fluxo mining"))
        self.cell((self.w - self.l_margin - self.r_margin) / 3, 5, _lat1(self.footer_title), align="C")
        self.cell((self.w - self.l_margin - self.r_margin) / 3, 5, _lat1("Confidencial"), align="R")


def _rrect(pdf, x, y, w, h, r=2.5, fill=None, border=None, bw=0.3):
    if fill:
        pdf.set_fill_color(*fill)
    if border:
        pdf.set_draw_color(*border)
        pdf.set_line_width(bw)
    style = ("DF" if (fill and border) else "F" if fill else "D")
    pdf.rect(x, y, w, h, round_corners=True, corner_radius=r, style=style)


def _text(pdf, x, y, txt, size, color, style="", w=0, h=4.5, align="L"):
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(*color)
    pdf.cell(w, h, _lat1(txt), align=align)


def _mtext(pdf, x, y, w, txt, size, color, style="", h=4.6):
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(*color)
    pdf.multi_cell(w, h, _lat1(_strip_inline(txt)), new_x="LMARGIN", new_y="NEXT")
    return pdf.get_y()


def _mh(pdf, w, txt, size, style="", h=4.6):
    pdf.set_font("Helvetica", style, size)
    return pdf.multi_cell(w, h, _lat1(_strip_inline(txt)), dry_run=True, output="HEIGHT")


def _ensure(pdf, y, need, top, bot=15.0):
    """Quebra de página se o bloco (altura `need`) não couber; retorna o novo y."""
    if y + need > pdf.h - bot:
        pdf.add_page()
        return top
    return y


def _ellipsize(pdf, txt, maxw, size, style=""):
    pdf.set_font("Helvetica", style, size)
    t = _lat1(txt)
    if pdf.get_string_width(t) <= maxw:
        return t
    while t and pdf.get_string_width(t + "...") > maxw:
        t = t[:-1]
    return (t + "...") if t else ""


def _fit_size(pdf, txt, maxw, base, style="B", minsize=8.0):
    """Maior tamanho <= base que faz `txt` caber em `maxw` (evita estouro lateral)."""
    t = _lat1(txt)
    size = base
    while size > minsize:
        pdf.set_font("Helvetica", style, size)
        if pdf.get_string_width(t) <= maxw:
            return size
        size -= 0.5
    return minsize


# ───────────────────────── template RICO ─────────────────────────
def build_report_pdf(report: dict, module_name: str, when: datetime | None = None) -> bytes:
    when = when or datetime.now()
    pdf = _Doc(format="A4")
    pdf.footer_title = _lat1(report.get("title", "Relatorio"))
    pdf.set_auto_page_break(False)   # relatório de 1 página: sem quebra espúria
    L, R, T = 14.0, 14.0, 12.0
    pdf.set_margins(L, T, R)
    pdf.add_page()
    W = pdf.w - L - R
    NEWTOP = 16.0   # topo do conteúdo nas páginas de continuação (sem cabeçalho)

    # ── cabeçalho ──
    _rrect(pdf, L, T, 8, 8, r=2, fill=VIOLET)
    _text(pdf, L + 2.1, T + 1.5, "F", 11, WHITE, "B")
    _text(pdf, L + 11, T + 1, module_name, 9.5, INK, "B", h=6)
    _text(pdf, L, T + 0.5, "GERADO EM", 7.5, FAINT, "B", w=W, h=3.5, align="R")
    _text(pdf, L, T + 4, when.strftime("%d/%m/%Y - %H:%M"), 8.5, INK, "B", w=W, h=4, align="R")
    y = T + 14

    _text(pdf, L, y, "RELATORIO - ASSISTENTE IA", 8, VIOLET, "B", h=4)
    y += 5.5
    y = _mtext(pdf, L, y, W, report.get("title", "Relatorio"), 21, INK, "B", h=9) + 0.5
    if report.get("subtitle"):
        y = _mtext(pdf, L, y, W, report["subtitle"], 11.5, MUTED, "", h=6)
    y += 2.5

    # ── definição adotada (callout) ──
    if report.get("definition"):
        tw = W - 10
        th = _mh(pdf, tw, report["definition"], 9, "", 4.4)
        bh = th + 7
        y = _ensure(pdf, y, bh + 5, NEWTOP)
        _rrect(pdf, L, y, W, bh, r=2.5, fill=VIOLET_BG)
        _rrect(pdf, L, y, 1.3, bh, r=0.6, fill=VIOLET)
        _mtext(pdf, L + 5, y + 3.5, tw, report["definition"], 9, INK, "", 4.4)
        y += bh + 5

    # ── KPIs ──
    kpis = (report.get("kpis") or [])[:4]
    if kpis:
        n = len(kpis)
        gap = 4
        cw = (W - gap * (n - 1)) / n
        ch = 26
        y = _ensure(pdf, y, ch + 5, NEWTOP)
        for i, k in enumerate(kpis):
            x = L + i * (cw + gap)
            hot = bool(k.get("highlight"))
            _rrect(pdf, x, y, cw, ch, r=3,
                   fill=(VIOLET if hot else CARD_BG), border=(None if hot else LINE))
            lab_c = ((235, 228, 255) if hot else MUTED)
            val_c = (WHITE if hot else INK)
            sub_c = ((220, 210, 250) if hot else FAINT)
            _mtext(pdf, x + 4, y + 3.5, cw - 8, k.get("label", ""), 7.6, lab_c, "B", 3.3)
            vsize = _fit_size(pdf, k.get("value", ""), cw - 8, 14.5, "B", 8.5)
            _text(pdf, x + 4, y + 12.5, k.get("value", ""), vsize, val_c, "B", h=6)
            if k.get("sub"):
                _mtext(pdf, x + 4, y + 20, cw - 8, k["sub"], 6.8, sub_c, "", 3.0)
        y += ch + 5

    # ── composição (barra empilhada) ──
    comp = report.get("composition")
    if comp and comp.get("segments"):
        segs = comp["segments"]
        total = sum(max(0, float(s.get("value", 0))) for s in segs) or 1
        bh = 22
        y = _ensure(pdf, y, bh + 5, NEWTOP)
        _rrect(pdf, L, y, W, bh, r=3, fill=CARD_BG, border=LINE)
        _text(pdf, L + 5, y + 3.2, comp.get("label", "Composicao"), 9.5, INK, "B", h=4)
        if comp.get("total"):
            _text(pdf, L, y + 3.2, comp["total"], 8.5, MUTED, "", w=W - 5, h=4, align="R")
        # barra
        bx, by, bw = L + 5, y + 9.5, W - 10
        cur = bx
        for s in segs:
            sw = bw * (max(0, float(s.get("value", 0))) / total)
            pdf.set_fill_color(*_SEG.get(s.get("color", "violet"), VIOLET_2))
            pdf.rect(cur, by, max(sw, 0.4), 5, style="F")
            cur += sw
        # legenda
        lx = bx
        pdf.set_font("Helvetica", "", 7.8)
        for s in segs:
            pdf.set_fill_color(*_SEG.get(s.get("color", "violet"), VIOLET_2))
            pdf.rect(lx, by + 8.5, 3, 3, round_corners=True, corner_radius=0.6, style="F")
            txt = _lat1(f"{s.get('label','')}")
            _text(pdf, lx + 4.5, by + 8.2, txt, 7.8, MUTED, "", h=4)
            lx += 5 + pdf.get_string_width(txt) + 6
        y += bh + 5

    # ── painéis de barras (top listas) ──
    bars = (report.get("bars") or [])[:2]
    if bars:
        gap = 5
        pw = (W - gap) / 2 if len(bars) == 2 else W
        rows_max = max(len(b.get("items", [])) for b in bars)
        ph = 14 + rows_max * 9.5 + (9 if any(b.get("note") for b in bars) else 0)
        y = _ensure(pdf, y, ph + 5, NEWTOP)
        for i, b in enumerate(bars):
            x = L + i * (pw + gap)
            _rrect(pdf, x, y, pw, ph, r=3, fill=CARD_BG, border=LINE)
            _text(pdf, x + 5, y + 3.4, b.get("title", ""), 10, INK, "B", h=4)
            if b.get("subtitle"):
                _text(pdf, x + 5, y + 7.6, b["subtitle"], 7.3, MUTED, "", h=3.5)
            items = b.get("items", [])
            mx = max([float(it.get("amount", 0)) for it in items] or [1]) or 1
            ry = y + 12.5
            for it in items:
                lab = _ellipsize(pdf, it.get("label", ""), pw - 33, 8, "B")
                _text(pdf, x + 5, ry, lab, 8, INK, "B", h=4)
                _text(pdf, x, ry, it.get("value", ""), 8, INK, "", w=pw - 5, h=4, align="R")
                frac = max(0.0, float(it.get("amount", 0)) / mx)
                pdf.set_fill_color(*VIOLET_2)
                pdf.rect(x + 5, ry + 4.6, max((pw - 10) * frac, 0.6), 1.7,
                         round_corners=True, corner_radius=0.85, style="F")
                ry += 9.5
            if b.get("note"):
                nh = _mh(pdf, pw - 14, b["note"], 7.3, "", 3.2) + 3
                _rrect(pdf, x + 5, ry - 0.5, pw - 10, nh, r=2, fill=VIOLET_BG)
                _mtext(pdf, x + 7, ry + 1, pw - 14, b["note"], 7.3, VIOLET, "", 3.2)
        y += ph + 5

    # ── riscos e recomendações ──
    risks = (report.get("risks") or [])[:3]
    if risks:
        gap = 4
        n = len(risks)
        cw = (W - gap * (n - 1)) / n
        heights = [_mh(pdf, cw - 8, rk.get("text", ""), 7.6, "", 3.3) for rk in risks]
        ch = max(heights) + 14
        y = _ensure(pdf, y, 6 + ch + 5, NEWTOP)
        _text(pdf, L, y, "Riscos e recomendacoes", 11, INK, "B", h=5)
        y += 6
        for i, rk in enumerate(risks):
            x = L + i * (cw + gap)
            tone = _TONE.get(rk.get("tone", "violet"), VIOLET_2)
            _rrect(pdf, x, y, cw, ch, r=3, fill=CARD_BG, border=LINE)
            pdf.set_fill_color(*tone)
            pdf.rect(x, y, cw, 1.6, round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=3, style="F")
            _mtext(pdf, x + 4, y + 4, cw - 8, rk.get("title", ""), 8, tone, "B", 3.5)
            ty = pdf.get_y()
            _mtext(pdf, x + 4, ty + 0.3, cw - 8, rk.get("text", ""), 7.6, INK, "", 3.3)
        y += ch + 5

    # ── resumo (faixa roxa) ──
    if report.get("summary"):
        tw = W - 10
        th = _mh(pdf, tw, report["summary"], 9.5, "B", 4.6)
        bh = th + 10
        y = _ensure(pdf, y, bh, NEWTOP)
        _rrect(pdf, L, y, W, bh, r=3, fill=VIOLET)
        _text(pdf, L + 5, y + 3.5, "RESUMO", 7.5, (215, 205, 250), "B", h=3.5)
        _mtext(pdf, L + 5, y + 7.5, tw, report["summary"], 9.5, WHITE, "B", 4.6)
        y += bh

    return bytes(pdf.output())


# ───────────────────────── fallback simples ─────────────────────────
def _render_markdown(pdf, text):
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(2.5)
            continue
        h = re.match(r"^(#{1,3})\s+(.*)", line)
        b = re.match(r"^\s*[-•*]\s+(.*)", line)
        if h:
            pdf.ln(1.5)
            _mtext(pdf, pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin,
                   h.group(2), 12.5, INK, "B", 6.5)
        elif b:
            _mtext(pdf, pdf.l_margin + 4, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin - 4,
                   "-  " + b.group(1), 10.5, INK, "", 5.6)
        else:
            _mtext(pdf, pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin,
                   line, 10.5, INK, "", 5.6)


def build_pdf(module_name: str, question: str, answer: str,
              steps=None, when: datetime | None = None) -> bytes:
    when = when or datetime.now()
    pdf = _Doc(format="A4")
    pdf.footer_title = _lat1(module_name)
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()
    _mtext(pdf, 18, 16, pdf.w - 36, f"Relatorio de Analise - {module_name}", 18, VIOLET, "B", 9)
    _mtext(pdf, 18, pdf.get_y(), pdf.w - 36, f"Solicitacao: {question}", 10, MUTED, "", 5.5)
    _text(pdf, 18, pdf.get_y(), when.strftime("Gerado em %d/%m/%Y %H:%M"), 10, MUTED, "", h=5.5)
    pdf.ln(9)
    pdf.set_draw_color(*VIOLET)
    pdf.set_line_width(0.5)
    pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
    pdf.ln(5)
    _render_markdown(pdf, answer)
    tables = [s.get("table") for s in (steps or []) if s.get("table") and s["table"].get("rows")]
    for i, t in enumerate(tables, 1):
        pdf.ln(4)
        _text(pdf, 18, pdf.get_y(), f"Dados - consulta {i}", 11, INK, "B", h=7)
        pdf.ln(8)
        cols = [_lat1(c) for c in t.get("columns", [])]
        rows = t.get("rows", [])[:25]
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*INK)
        hs = FontFace(emphasis="BOLD", color=WHITE, fill_color=VIOLET)
        with pdf.table(first_row_as_headings=True, headings_style=hs,
                       cell_fill_color=VIOLET_BG, cell_fill_mode="ROWS",
                       line_height=5.5, text_align="LEFT") as table:
            r = table.row()
            for c in cols:
                r.cell(c)
            for row in rows:
                r = table.row()
                for v in row:
                    r.cell(_lat1(v))
    return bytes(pdf.output())
