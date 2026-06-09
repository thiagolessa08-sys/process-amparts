"""Diagnóstico da divergência de variantes Cordeiro × Celonis.

Carrega o event log REAL do Cordeiro (mesmo pipeline das telas) e recalcula as
variantes de algumas formas diferentes para descobrir POR QUE a cauda diverge do
Celonis, embora a variante #1 bata.

Hipóteses testadas:
  H1) Ordenação intra-dia: nosso timestamp = data + HORA-DO-DIA (+ offset de
      SORTING em ms). O Celonis normalmente ordena eventos do mesmo dia SÓ pelo
      SORTING, ignorando a hora do relógio. Se for isso, reordenar por
      (data, SORTING) deve aproximar nossos números dos do Celonis.
  H2) Eventos de aprovação inferidos: se 'APROVOU *' entra em casos onde o
      Celonis não coloca, a cauda fragmenta. Removendo as aprovações, a
      distribuição muda de forma reveladora.

Como rodar (no ambiente com o agent configurado, backend\\.env):
    .venv\\Scripts\\python diagnose_cordeiro.py

Não altera nada — só lê e imprime.
"""
import sys
from pathlib import Path

try:  # console do Windows costuma ser cp1252 — evita crash em acentos/setas
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP
from app.sources.cordeiro import load_cordeiro_eventlog

# SORTING oficial por atividade (de app/sources/cordeiro.py)
SORT_MAP = {
    "CRIOU ORCAMENTO": 10, "CANCELOU ORCAMENTO": 11, "APROVOU ORCAMENTO": 15,
    "CRIOU PEDIDO": 20,    "CANCELOU PEDIDO": 21,    "APROVOU PEDIDO": 25,
    "CRIOU FATURA": 30,    "CANCELOU FATURA": 31,    "APROVOU FATURA": 35,
}

# números observados no Celonis (das telas que você mandou), para comparação
CELONIS = [
    ("#1", 101000, 48.0), ("#2", 21600, 10.0), ("#3", 18400, 9.0),
    ("#4", 17300, 8.0),   ("#5", 8060, 4.0),   ("#6", 7500, 4.0),
    ("#7", 6610, 3.0),    ("#8", 4030, 2.0),   ("#9", 3230, 2.0),
]


def variants(seqs: pd.Series, top: int = 12):
    """seqs: Series (índice=case_id, valor=tupla de atividades). Retorna top variantes."""
    vc = seqs.value_counts()
    total = int(len(seqs))
    rows = []
    for i, (seq, cnt) in enumerate(vc.items()):
        if i >= top:
            break
        rows.append((i + 1, int(cnt), 100.0 * cnt / total, seq))
    return rows, total, int(len(vc))


def seq_by(log: pd.DataFrame, order_cols: list[str]) -> pd.Series:
    """Sequência de atividades por caso, na ordem dada por order_cols."""
    s = log.sort_values([CASE_ID] + order_cols, kind="stable")
    return s.groupby(CASE_ID, sort=False)[ACTIVITY].agg(tuple)


def short(seq, n=6):
    """Encurta a sequência de atividades p/ impressão (abrevia nomes)."""
    abbr = {
        "CRIOU ORCAMENTO": "C.ORC", "APROVOU ORCAMENTO": "A.ORC", "CANCELOU ORCAMENTO": "X.ORC",
        "CRIOU PEDIDO": "C.PED", "APROVOU PEDIDO": "A.PED", "CANCELOU PEDIDO": "X.PED",
        "CRIOU FATURA": "C.FAT", "APROVOU FATURA": "A.FAT", "CANCELOU FATURA": "X.FAT",
    }
    parts = [abbr.get(a, a) for a in seq]
    if len(parts) > n:
        parts = parts[:n] + [f"...(+{len(parts) - n})"]
    return " -> ".join(parts)


def print_table(title: str, rows, total, n_variants):
    print(f"\n{'=' * 78}\n{title}")
    print(f"  casos: {total:,}  | variantes distintas: {n_variants:,}".replace(",", "."))
    print(f"  {'#':>3} {'count':>9} {'%':>6}   sequência")
    print(f"  {'-' * 70}")
    for vid, cnt, pct, seq in rows:
        print(f"  {vid:>3} {cnt:>9,} {pct:>5.1f}%   {short(seq)}".replace(",", "."))


def main():
    print("Carregando event log do Cordeiro (pode levar ~1-2 min)...")
    log = load_cordeiro_eventlog()
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    log = log.assign(**{ACTIVITY: log[ACTIVITY].astype(str)})

    total_cases = log[CASE_ID].nunique()
    print(f"OK — {len(log):,} eventos, {total_cases:,} casos.".replace(",", "."))

    print("\nReferência Celonis (das suas telas):")
    for vid, cnt, pct in CELONIS:
        print(f"  {vid:>3} {cnt:>9,} {pct:>5.1f}%".replace(",", "."))

    # ── A) ordenação atual: por timestamp (data + hora-do-dia + offset SORTING) ──
    seqA = seq_by(log, [TIMESTAMP])
    rowsA, totA, nvA = variants(seqA)
    print_table("A) ATUAL — ordena por timestamp (data + hora-do-dia)", rowsA, totA, nvA)

    # ── B) hipótese Celonis: ordena por (data, SORTING), ignorando hora-do-dia ──
    log_b = log.copy()
    log_b["_d"] = log_b[TIMESTAMP].dt.normalize()
    log_b["_s"] = log_b[ACTIVITY].map(SORT_MAP).fillna(99).astype(int)
    seqB = seq_by(log_b, ["_d", "_s"])
    rowsB, totB, nvB = variants(seqB)
    print_table("B) HIPÓTESE H1 — ordena por (data, SORTING), sem hora-do-dia", rowsB, totB, nvB)

    # quantos casos mudam de sequência entre A e B?
    diff = (seqA != seqB.reindex(seqA.index))
    n_diff = int(diff.sum())
    print(f"\n  -> H1: {n_diff:,} de {total_cases:,} casos ({100.0*n_diff/total_cases:.1f}%) "
          f"mudam de sequência ao trocar hora-do-dia por SORTING.".replace(",", "."))

    # exemplos de casos que divergem entre A e B
    ex = seqA.index[diff][:5]
    if len(ex):
        print("  Exemplos (mesmo caso, ordenação A vs B):")
        for cid in ex:
            print(f"    case {cid}")
            print(f"        A: {short(seqA.loc[cid], 8)}")
            print(f"        B: {short(seqB.loc[cid], 8)}")

    # ── C) hipótese H2: remove aprovações e recalcula (ordenação A) ──
    no_apr = log[~log[ACTIVITY].str.startswith("APROVOU")]
    seqC = seq_by(no_apr, [TIMESTAMP])
    rowsC, totC, nvC = variants(seqC)
    print_table("C) HIPÓTESE H2 — SEM eventos 'APROVOU *' (ordenação atual)", rowsC, totC, nvC)

    # quantos casos têm cada aprovação
    print("\n  Cobertura de cada atividade (casos que a contêm):")
    for act in SORT_MAP:
        n = log[log[ACTIVITY] == act][CASE_ID].nunique()
        print(f"    {act:<20} {n:>9,}  ({100.0*n/total_cases:>4.1f}%)".replace(",", "."))

    print("\n" + "=" * 78)
    print("LEITURA: a tabela (A, B ou C) cujos counts da #2 em diante mais se")
    print("aproximarem do Celonis aponta a causa. Se for B -> e' a hora-do-dia.")
    print("Se for C -> sao as aprovacoes. Me mande a saida que eu fecho o ajuste.")


if __name__ == "__main__":
    main()
