"""Conector HTTP para o Java Agent (Sybase IQ).

Lê AGENT_URL / AGENT_API_KEY do ambiente. O agent limita cada query a ~5.000
linhas, então há um helper de paginação por faixa de chave.
"""
import json
import os

import httpx
import pandas as pd

PAGE = 5000


class AgentConnector:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or os.environ.get("AGENT_URL", "")).rstrip("/")
        self.key = key or os.environ.get("AGENT_API_KEY", "")

    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _client(self) -> httpx.Client:
        return httpx.Client(verify=False, timeout=180)  # inspeção SSL corporativa

    def query(self, sql: str, limit: int = PAGE) -> dict:
        with self._client() as c:
            r = c.post(
                f"{self.url}/query",
                headers={"X-API-Key": self.key, "Content-Type": "application/json"},
                json={"sql": sql, "limit": limit},
            )
            r.raise_for_status()
            # strict=False: descrições de item podem conter chars de controle (\n, \t)
            return json.loads(r.text, strict=False)

    def query_df(self, sql: str, limit: int = PAGE) -> pd.DataFrame:
        d = self.query(sql, limit)
        cols = [c.strip() for c in d.get("columns", [])]
        return pd.DataFrame(d.get("rows", []), columns=cols)

    def paginate_df(self, select: str, frm: str, key: str,
                    where: str = "", group: str = "", max_pages: int = 200) -> pd.DataFrame:
        """Pagina por faixa de chave numérica `key` (TOP por página).

        select: lista de colunas (o `key` precisa estar incluído e ser o 1º alias 'k').
        group:  expressão de GROUP BY (ex.: a própria chave) para agregação doc-level.
        """
        frames, last, pages = [], None, 0
        while pages < max_pages:
            # chave NULL não pagina nem agrega de forma confiável → exclui
            cond = [f"{key} IS NOT NULL"]
            if where:
                cond.append(f"({where})")
            if last is not None:
                cond.append(f"{key} > {last}")
            wc = " WHERE " + " AND ".join(cond)
            gc = f" GROUP BY {group}" if group else ""
            sql = f"SELECT TOP {PAGE} {select} FROM {frm}{wc}{gc} ORDER BY {key}"
            df = self.query_df(sql)
            if df.empty:
                break
            frames.append(df)
            last = df["k"].iloc[-1]
            pages += 1
            if len(df) < PAGE:
                break
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def paginate_keyset(self, select: str, frm: str, k1: str, k2: str,
                        where: str = "", max_pages: int = 400) -> pd.DataFrame:
        """Paginação keyset por chave composta (k1, k2) — para tabelas item-level
        em que k1=número interno do doc e k2=linha do item (lossless nas bordas)."""
        sel = f"{k1} AS kk1, {k2} AS kk2, {select}"
        frames, l1, l2, pages = [], None, None, 0
        while pages < max_pages:
            # chave interna NULL não pode keyset (e não casa nas junções) → exclui,
            # senão NULLs (que ordenam primeiro) podem encher uma página e quebrar o avanço
            cond = [f"{k1} IS NOT NULL", f"{k2} IS NOT NULL"]
            if where:
                cond.append(f"({where})")
            if l1 is not None:
                cond.append(f"({k1} > {l1} OR ({k1} = {l1} AND {k2} > {l2}))")
            wc = " WHERE " + " AND ".join(cond)
            sql = f"SELECT TOP {PAGE} {sel} FROM {frm}{wc} ORDER BY {k1}, {k2}"
            df = self.query_df(sql)
            if df.empty:
                break
            frames.append(df)
            last1, last2 = df["kk1"].iloc[-1], df["kk2"].iloc[-1]
            if pd.isna(last1) or pd.isna(last2):  # defensivo (não deve ocorrer com o filtro)
                break
            l1, l2 = int(float(last1)), int(float(last2))
            pages += 1
            if len(df) < PAGE:
                break
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
