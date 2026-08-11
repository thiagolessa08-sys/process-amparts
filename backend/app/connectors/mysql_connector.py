"""Conector MySQL direto — banco do AM Parts.

Diferente do AgentConnector (HTTP → Java Agent → Sybase IQ), aqui a conexão é
direta com um MySQL, com SSL obrigatório do lado do servidor.

Config por ambiente:
    AMPARTS_DB_HOST      obrigatório
    AMPARTS_DB_PORT      opcional (3306)
    AMPARTS_DB_USER      obrigatório
    AMPARTS_DB_PASSWORD  obrigatório
    AMPARTS_DB_NAME      opcional (amparts)
    AMPARTS_DB_SSL_CA    opcional — caminho do CA. Ver _ssl_context().

O event log tem ~1,1M linhas no recorte de um ano, então a leitura é feita com
cursor server-side (SSCursor) em blocos: sem isso o pymysql materializa o
resultado inteiro em tuplas Python antes de devolver, e o processo estoura a
memória do servidor.
"""
import os
import ssl
import time
from decimal import Decimal

import pandas as pd
import pymysql
from pymysql.cursors import SSCursor

CHUNK = 50_000
# quedas transientes observadas neste servidor ("Lost connection during query"),
# inclusive durante o handshake. SELECT é idempotente → retry é seguro.
_RETRY_EXC = (pymysql.err.OperationalError, pymysql.err.InterfaceError)


class MySQLConnector:
    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        self.host = host or os.environ.get("AMPARTS_DB_HOST", "")
        self.port = int(port or os.environ.get("AMPARTS_DB_PORT") or 3306)
        self.user = user or os.environ.get("AMPARTS_DB_USER", "")
        self.password = password or os.environ.get("AMPARTS_DB_PASSWORD", "")
        self.database = database or os.environ.get("AMPARTS_DB_NAME", "amparts")
        self.ssl_ca = os.environ.get("AMPARTS_DB_SSL_CA", "")

    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.database)

    def _ssl_context(self) -> ssl.SSLContext:
        """Contexto TLS.

        Com AMPARTS_DB_SSL_CA apontando para o CA do servidor, o certificado é
        validado de verdade. Sem ele, o tráfego continua cifrado mas o servidor
        NÃO é autenticado — necessário hoje porque o host é um IP e o certificado
        não tem SAN correspondente, o que faria a verificação falhar. Enquanto
        estiver assim, a conexão é vulnerável a interceptação ativa.
        """
        if self.ssl_ca:
            return ssl.create_default_context(cafile=self.ssl_ca)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def connect(self, cursorclass=None, tries: int = 4):
        last = None
        for attempt in range(tries):
            try:
                return pymysql.connect(
                    host=self.host, port=self.port, user=self.user,
                    password=self.password, database=self.database,
                    ssl=self._ssl_context(), charset="utf8mb4",
                    connect_timeout=20, read_timeout=600, write_timeout=60,
                    cursorclass=cursorclass or pymysql.cursors.Cursor,
                )
            except _RETRY_EXC as exc:  # noqa: PERF203
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise last

    def query_df(self, sql: str, params=None) -> pd.DataFrame:
        """Query pequena (COUNT, amostra). Materializa tudo — não use no log."""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description]
                return _frame(list(cur.fetchall()), cols)
        finally:
            conn.close()

    def stream_df(self, select: str, table: str, where: str = "", order: str = "",
                  params=None, on_rows=None, tries: int = 3) -> pd.DataFrame:
        """Lê a tabela inteira em blocos, via cursor server-side.

        Uma queda no meio do stream perde o progresso parcial (não dá para
        retomar sem uma chave de keyset estável), então o retry refaz a query do
        zero. on_rows(n) recebe o total acumulado, para a barra de progresso.
        """
        wc = f" WHERE {where}" if where else ""
        oc = f" ORDER BY {order}" if order else ""
        sql = f"SELECT {select} FROM {table}{wc}{oc}"

        last = None
        for attempt in range(tries):
            conn = None
            try:
                conn = self.connect(cursorclass=SSCursor)
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    cols = [d[0] for d in cur.description]
                    blocos, total = [], 0
                    while True:
                        linhas = cur.fetchmany(CHUNK)
                        if not linhas:
                            break
                        blocos.append(_frame(linhas, cols))
                        total += len(linhas)
                        if on_rows:
                            on_rows(total)
                    if not blocos:
                        return pd.DataFrame(columns=cols)
                    return pd.concat(blocos, ignore_index=True)
            except _RETRY_EXC as exc:  # noqa: PERF203
                last = exc
                time.sleep(2.0 * (attempt + 1))
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
        raise last


def _frame(linhas: list, cols: list) -> pd.DataFrame:
    """Monta o DataFrame convertendo Decimal → float.

    O caminho do CSV entrega tudo como texto e `build_eventlog` faz a conversão.
    Vindo do banco os numéricos chegam como Decimal, que pandas guarda em coluna
    `object`: qualquer soma vira aritmética de Decimal (lenta) e mistura de
    Decimal com float estoura TypeError. Converter aqui mantém os dois caminhos
    com o mesmo dtype no fim.
    """
    df = pd.DataFrame(linhas, columns=cols)
    for c in df.columns:
        if df[c].dtype == object:
            amostra = df[c].dropna()
            if not amostra.empty and isinstance(amostra.iloc[0], Decimal):
                df[c] = df[c].astype(float)
    return df
