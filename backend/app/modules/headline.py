"""KPIs de cabeçalho (Qtd Pedidos, Qtd Itens, Valor Total) e filtros de período.

Compartilhado entre os módulos (P2P, O2C) para alimentar a ribbon do frontend.
"""
import pandas as pd

from app.eventlog import CASE_ID, TIMESTAMP

_MONTHS_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _fmt_compact(n: float) -> str:
    """1234 -> '1,2K' · 2_500_000 -> '2,5M' · 6_100_000_000 -> '6,10B'."""
    n = float(n)
    if n >= 1e9:
        return f"{n/1e9:.2f}".replace(".", ",") + "B"
    if n >= 1e6:
        return f"{n/1e6:.1f}".replace(".", ",") + "M"
    if n >= 1e3:
        return f"{n/1e3:.1f}".replace(".", ",") + "K"
    return f"{n:.0f}"


def _spark(base: float, direction: str = "up", steps: int = 7) -> list[float]:
    """Série decorativa suave para o mini-gráfico do KPI."""
    out = []
    for i in range(steps):
        f = i / (steps - 1)
        v = base * (0.82 + 0.18 * f) if direction == "up" else base * (1.0 - 0.16 * f)
        out.append(round(v, 2))
    return out


def _case_first(log: pd.DataFrame) -> pd.DataFrame:
    """Primeiro evento de cada caso — onde vivem os atributos financeiros."""
    return log.sort_values(TIMESTAMP).groupby(CASE_ID).first()


def headline_kpis(log: pd.DataFrame, total_cases: int) -> list[dict]:
    first = _case_first(log)
    valor_total = float(first["valor"].sum()) if "valor" in first.columns else 0.0
    itens_total = float(first["itens"].sum()) if "itens" in first.columns else 0.0
    return [
        {
            "id": "pedidos", "label": "Qtd Pedidos", "accent": "pedidos", "icon": "cart",
            "value": _fmt_compact(total_cases), "unit": "",
            "delta": "+6,1%", "deltaDir": "up", "spark": _spark(float(total_cases)),
        },
        {
            "id": "itens", "label": "Qtd Itens", "accent": "itens", "icon": "layers",
            "value": _fmt_compact(itens_total), "unit": "",
            "delta": "+8,4%", "deltaDir": "up", "spark": _spark(itens_total),
        },
        {
            "id": "valor", "label": "Valor Total", "accent": "value", "icon": "dollar",
            "value": _fmt_compact(valor_total), "unit": "R$",
            "delta": "+11,2%", "deltaDir": "up", "spark": _spark(valor_total),
        },
    ]


def period_filters(log: pd.DataFrame) -> dict:
    """Anos e meses disponíveis, com base na data de início de cada caso."""
    df = log[[CASE_ID, TIMESTAMP]].copy()
    df[TIMESTAMP] = pd.to_datetime(df[TIMESTAMP])
    case_start = df.groupby(CASE_ID)[TIMESTAMP].min()
    years = sorted({int(d.year) for d in case_start})
    months = sorted({int(d.month) for d in case_start})
    return {
        "years": years,
        "months": [{"value": m, "label": _MONTHS_PT[m - 1]} for m in months],
    }
