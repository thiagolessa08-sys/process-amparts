"""Conector HTTP para o Java Agent (Sybase IQ).

Lê AGENT_URL / AGENT_API_KEY do ambiente. O agent limita cada query a ~5.000
linhas, então há um helper de paginação por faixa de chave.
"""
import json
import os
import time

import httpx
import pandas as pd

PAGE = 5000
_RETRY_EXC = (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout,
              httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class AgentConnector:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or os.environ.get("AGENT_URL", "")).rstrip("/")
        self.key = key or os.environ.get("AGENT_API_KEY", "")

    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _client(self) -> httpx.Client:
        return httpx.Client(verify=False, timeout=180)  # inspeção SSL corporativa

    def query(self, sql: str, limit: int = PAGE, _tries: int = 4) -> dict:
        # SELECT é idempotente → retry em quedas transientes do túnel/agent
        last = None
        for attempt in range(_tries):
            try:
                with self._client() as c:
                    r = c.post(
                        f"{self.url}/query",
                        headers={"X-API-Key": self.key, "Content-Type": "application/json"},
                        json={"sql": sql, "limit": limit},
                    )
                    # 5xx do agent/túnel costuma ser transiente (sobrecarga) →
                    # retry (SELECT é idempotente); 4xx falha de imediato
                    if r.status_code >= 500:
                        last = httpx.HTTPStatusError(
                            f"{r.status_code} do agent", request=r.request, response=r)
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    # Cordeiro/SAP-B1: agent rotula UTF-8 mas entrega bytes cp1252.
                    # Vedara/veddara: agent entrega UTF-8 real (tabelas de PM modernas).
                    # Estratégia: tenta UTF-8 estrito primeiro; se falhar, decodifica
                    # como cp1252 (Cordeiro). strict=False: controles (\n,\t) em textos.
                    try:
                        text = r.content.decode("utf-8")
                    except UnicodeDecodeError:
                        text = r.content.decode("cp1252", errors="replace")
                    return json.loads(text, strict=False)
            except _RETRY_EXC as exc:  # noqa: PERF203
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise last

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

    def paginate_offset(self, select: str, frm: str, order: str,
                        where: str = "", max_pages: int = 400, on_rows=None) -> pd.DataFrame:
        """Paginação por offset (TOP n START AT m) — para tabelas sem chave numérica
        natural (ex.: event log já pronto). ORDER BY estável é obrigatório.
        on_rows(total): callback opcional de progresso com o nº de linhas já carregadas."""
        frames, start, pages = [], 1, 0
        while pages < max_pages:
            wc = f" WHERE {where}" if where else ""
            sql = f"SELECT TOP {PAGE} START AT {start} {select} FROM {frm}{wc} ORDER BY {order}"
            df = self.query_df(sql)
            if df.empty:
                break
            frames.append(df)
            start += len(df)
            pages += 1
            if on_rows:
                on_rows(start - 1)
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
