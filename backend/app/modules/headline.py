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


def case_ref_date(log: pd.DataFrame, order_activity: str | None = None):
    """Data de referência por caso: data do evento de pedido (se `order_activity`
    informado e presente) ou o 1º evento do caso (case start)."""
    df = log[[CASE_ID, TIMESTAMP, "activity"]].copy() if order_activity else log[[CASE_ID, TIMESTAMP]].copy()
    df[TIMESTAMP] = pd.to_datetime(df[TIMESTAMP])
    if order_activity:
        ped = df[df["activity"] == order_activity]
        if not ped.empty:
            return ped.groupby(CASE_ID)[TIMESTAMP].min()
    return df.groupby(CASE_ID)[TIMESTAMP].min()


def period_filters(log: pd.DataFrame, order_activity: str | None = None) -> dict:
    """Anos e meses disponíveis, pela data de referência de cada caso (data do
    pedido se `order_activity` informado; senão, o 1º evento)."""
    ref = case_ref_date(log, order_activity)
    years = sorted({int(d.year) for d in ref})
    months = sorted({int(d.month) for d in ref})
    return {
        "years": years,
        "months": [{"value": m, "label": _MONTHS_PT[m - 1]} for m in months],
    }
