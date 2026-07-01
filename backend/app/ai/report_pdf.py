"""Gera um PDF de relatório a partir da resposta do assistente (answer markdown
+ tabelas das consultas). Usa fpdf2 com fontes core (latin-1) — o texto é
sanitizado para latin-1 (cobre pt-BR: ç, ã, á, é…)."""
import re
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

VIOLET = (123, 84, 238)
INK = (29, 42, 63)
MUTED = (110, 116, 140)
SOFT = (243, 240, 253)

_REPL = {
    "•": "-", "→": "->", "–": "-", "—": "-", "“": '"', "”": '"',
    "‘": "'", "’": "'", "…": "...", "✓": "OK", "⚠": "!", "❌": "x", "✅": "OK",
    " ": " ",
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


class _Report(FPDF):
    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, _lat1(f"Fluxo mining  -  pagina {self.page_no()}"), align="C")


def _render_markdown(pdf: FPDF, text: str) -> None:
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(2.5)
            continue
        h = re.match(r"^(#{1,3})\s+(.*)", line)
        b = re.match(r"^\s*[-•*]\s+(.*)", line)
        if h:
            pdf.ln(1.5)
            pdf.set_font("Helvetica", "B", 12.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 6.5, _lat1(_strip_inline(h.group(2))), new_x="LMARGIN", new_y="NEXT")
        elif b:
            pdf.set_font("Helvetica", "", 10.5)
            pdf.set_text_color(*INK)
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(0, 5.6, _lat1("-  " + _strip_inline(b.group(1))), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 10.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 5.6, _lat1(_strip_inline(line)), new_x="LMARGIN", new_y="NEXT")


def _render_table(pdf: FPDF, t: dict) -> None:
    cols = [_lat1(c) for c in t.get("columns", [])]
    rows = t.get("rows", [])[:25]
    if not cols:
        return
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*INK)
    head_style = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=VIOLET)
    with pdf.table(first_row_as_headings=True, headings_style=head_style,
                   cell_fill_color=SOFT, cell_fill_mode="ROWS",
                   line_height=5.5, text_align="LEFT") as table:
        r = table.row()
        for c in cols:
            r.cell(c)
        for row in rows:
            r = table.row()
            for v in row:
                r.cell(_lat1(v))
    extra = len(t.get("rows", [])) - len(rows)
    if extra > 0:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, _lat1(f"... +{extra} linhas"), new_x="LMARGIN", new_y="NEXT")


def build_pdf(module_name: str, question: str, answer: str,
              steps=None, when: datetime | None = None) -> bytes:
    when = when or datetime.now()
    pdf = _Report(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    # cabeçalho
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*VIOLET)
    pdf.multi_cell(0, 9, _lat1(f"Relatorio de Analise - {module_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5.5, _lat1(f"Solicitacao: {question}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5.5, _lat1(when.strftime("Gerado em %d/%m/%Y %H:%M")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_draw_color(*VIOLET)
    pdf.set_line_width(0.5)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(5)

    # análise
    _render_markdown(pdf, answer)

    # tabelas das consultas
    tables = [s.get("table") for s in (steps or []) if s.get("table") and s["table"].get("rows")]
    for i, t in enumerate(tables, 1):
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*INK)
        pdf.cell(0, 7, _lat1(f"Dados - consulta {i}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        _render_table(pdf, t)

    return bytes(pdf.output())
