"""Event log AM Parts (O2C de acessórios automotivos, com Ordem de Serviço).

Origem: export SQL_PM_ATIVIDADES (eventos) + SQL_PM_CASES (atributos por caso)
— o event log já vem pronto, uma linha por evento com case key, atividade,
timestamp e ordenação. O processo tem uma etapa
a mais que o O2C clássico: a Ordem de Serviço (abertura, recebimento do veículo,
finalização) entre o pedido e o faturamento da saída.

Duas fontes, na ordem: **MySQL** (`amparts.SQL_PM_*`) quando PM_DB_PASSWORD
estiver no ambiente, e o recorte em **arquivo** como contingência.

Nunca carregamos a base inteira: o banco tem 3,4M eventos entre 2023 e 2029 e o
volume total não cabe na memória do servidor. A carga por banco usa a janela
DESDE..hoje; o arquivo de contingência traz o ano de ANO inteiro.
"""
from pathlib import Path

import pandas as pd

from ..connectors.mysql_connector import MySQLConnector

SCHEMA = "amparts"
ACT_TABLE = f"{SCHEMA}.SQL_PM_ATIVIDADES"
CASE_TABLE = f"{SCHEMA}.SQL_PM_CASES"

# fase 1: só 2026 (o export tem 2023-2026, mas 2023 é quase vazio e o volume
# total — 2,8M eventos — não cabe no plano atual de memória do servidor)
ANO = 2026
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ACT_FILE = DATA_DIR / f"amparts_atividades_{ANO}.csv.gz"
CASE_FILE = DATA_DIR / f"amparts_cases_{ANO}.csv.gz"

# Início da janela da carga por banco. Começava em janeiro, mas os ~1,1M eventos
# do ano inteiro não cabem nos 8 GB por réplica do plano: o pico do `concat` no
# fim do streaming derrubava o processo, que reiniciava e recomeçava a carga sem
# nunca chegar ao fim. Junho corta a janela para ~4 meses.
MES_INICIAL = 6
DESDE = f"{ANO}-{MES_INICIAL:02d}-01"

_READ = dict(sep=";", dtype=str, encoding="utf-8-sig", on_bad_lines="skip")


def _periodo_where() -> str:
    """Janela usada na carga por banco: de DESDE até hoje. O teto existe porque
    o export traz eventos carimbados até 2029, que são datas inválidas."""
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"EVENTTIME >= '{DESDE}' AND EVENTTIME <= '{hoje} 23:59:59'"


# colunas da tela Detalhes (a partir da SQL_PM_CASES)
DETAIL_COLS = [
    {"key": "nrOrc", "label": "Nr. ORC", "fmt": "id"},
    {"key": "itemOrc", "label": "Item ORC", "fmt": "id"},
    {"key": "data", "label": "Emissão", "fmt": "text"},
    {"key": "nrPed", "label": "Nr. PED", "fmt": "id"},
    {"key": "nrOs", "label": "Nr. OS", "fmt": "id"},
    {"key": "nrSaida", "label": "Nr. Saída", "fmt": "id"},
    {"key": "cliente", "label": "Cliente", "fmt": "text"},
    {"key": "concessionaria", "label": "Concessionária", "fmt": "text"},
    {"key": "produto", "label": "Produto", "fmt": "text"},
    {"key": "qtde", "label": "Qtde", "fmt": "int"},
    {"key": "valor", "label": "Valor Pedido", "fmt": "money"},
    {"key": "faturado", "label": "Valor Faturado", "fmt": "money"},
    {"key": "cancelado", "label": "Cancelado", "fmt": "text"},
]

# painel de atributos do evento (clicar na atividade no Case Explorer)
EVENT_ATTRS = [
    {"label": "Atividade", "col": "activity"},
    {"label": "Case Key", "col": "case_id"},
    {"label": "Eventtime", "col": "eventtime_raw", "fmt": "date"},
    {"label": "Orçamento", "col": "orcamento"},
    {"label": "Item Orç.", "col": "orc_item"},
    {"label": "Pedido", "col": "pedido"},
    {"label": "Item Ped.", "col": "ped_item"},
    {"label": "OS", "col": "os"},
    {"label": "Saída", "col": "saida"},
    {"label": "Cliente", "col": "cliente"},
    {"label": "Concessionária", "col": "concessionaria"},
    {"label": "Produto", "col": "produto_cod"},
    {"label": "Descrição", "col": "prod_nome"},
    {"label": "Usuário", "col": "resource"},
    {"label": "Vendedor", "col": "vendedor"},
    {"label": "Origem", "col": "source_activity"},
    {"label": "Sorting", "col": "sort"},
]

_CASES_DETAIL: pd.DataFrame | None = None
_ORIGEM: str | None = None


def get_cases_detail() -> pd.DataFrame:
    """DataFrame de detalhe (uma linha por caso) da SQL_PM_CASES, ou vazio."""
    return _CASES_DETAIL if _CASES_DETAIL is not None else pd.DataFrame()


def get_origem() -> str | None:
    """"db" | "csv" — de onde veio o log em memória (None antes da 1ª carga).

    Cair no CSV é silencioso por design (é contingência), e em produção isso
    significa servir o recorte congelado achando que é o banco. Exposto em
    /api/debug/config justamente para esse caso ficar visível depois do deploy.
    """
    return _ORIGEM


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _txt(df, col):
    return df[col].astype(str).where(df[col].notna(), None) if col in df else None


def build_eventlog(acts: pd.DataFrame, cases: pd.DataFrame) -> pd.DataFrame:
    """Projeta ATIVIDADES + CASES no formato padrão do app.

    Separado da carga para poder ser exercitado sobre uma amostra de CSV sem
    depender do banco (ver testes).
    """
    global _CASES_DETAIL

    if not cases.empty:
        _cancel = _num(cases["FOI_CANCELADO"]).fillna(0)
        # Emissão = data do orçamento; cai para a data do pedido quando o caso
        # nasce direto como pedido (sem orçamento anterior).
        _emissao = pd.to_datetime(cases["DATA_ORCAMENTO"], errors="coerce").fillna(
            pd.to_datetime(cases["DATA_PEDIDO"], errors="coerce"))
        _CASES_DETAIL = pd.DataFrame({
            "_case_id": cases["CASE_KEY"].astype(str),   # oculto: casa com a variante
            "nrOrc": cases["ORCAMENTO"],
            "itemOrc": cases["ORC_ITEM"],
            "data": _emissao.dt.strftime("%Y-%m-%d"),
            "nrPed": cases["PEDIDO"],
            "nrOs": cases["OS"],
            "nrSaida": cases["SAIDA"],
            "cliente": cases["CLIENTE"],
            "concessionaria": cases["CONCESSIONARIA"],
            "produto": cases["PROD_NOME"],
            "qtde": _num(cases["PED_QTDE"]),
            "valor": _num(cases["PED_TOTAL"]),
            "faturado": _num(cases["FAT_TOTAL"]),
            "cancelado": _cancel.map(lambda v: "Sim" if v else "Não"),
        })

    eventtime = pd.to_datetime(acts["EVENTTIME"], errors="coerce")
    sort = _num(acts["SORTING"]).fillna(0)
    produto = acts["PROD_NOME"].where(
        acts["PROD_NOME"].notna() & (acts["PROD_NOME"].astype(str) != ""), acts["PRODUTO"])

    log = pd.DataFrame({
        "case_id": acts["CASE_KEY"].astype(str),
        "activity": acts["ACTIVITY_EN"].astype(str).str.strip(),
        "timestamp": eventtime,
        "sort": sort.astype("int64"),
        "resource": acts["USUARIO"].fillna("—"),
        "vendedor": acts["VENDEDOR"].fillna("—"),
        "cliente": acts["CLIENTE"].fillna("—"),
        "produto": produto.fillna("—"),
        # atributos crus do evento (painel de detalhe no Case Explorer)
        "eventtime_raw": eventtime,
        "produto_cod": _txt(acts, "PRODUTO"),
        "prod_nome": _txt(acts, "PROD_NOME"),
        "orcamento": _txt(acts, "ORCAMENTO"),
        "orc_item": _txt(acts, "ORC_ITEM"),
        "pedido": _txt(acts, "PEDIDO"),
        "ped_item": _txt(acts, "PED_ITEM"),
        "os": _txt(acts, "OS"),
        "saida": _txt(acts, "SAIDA"),
        "concessionaria": _txt(acts, "CONCESSIONARIA"),
        "source_activity": _txt(acts, "SOURCE_ACTIVITY"),
    })
    log = log.dropna(subset=["timestamp"])

    # Colunas de atributo puro (só alimentam o painel do Case Explorer, não
    # entram em groupby/filtro do motor) viram `category`: são textos com
    # repetição altíssima — ex.: source_activity tem 9 valores em 1,1M linhas.
    # Corta ~750 MB do event log, que sem isso estoura a memória do servidor.
    # case_id, activity, cliente e resource ficam de fora de propósito: são
    # usados em groupby/isin pelo mining, e categórico muda o comportamento.
    # NÃO inclua aqui produto/vendedor/resource/activity/cliente/case_id: entram
    # em groupby do motor de mineração. Medido — converter as três primeiras
    # deixou o enrich 41x mais lento (58s -> 2.370s) E alterou o payload.
    for col in ("produto_cod", "prod_nome", "orcamento", "orc_item", "pedido",
                "ped_item", "os", "saida", "concessionaria", "source_activity"):
        if col in log.columns:
            log[col] = log[col].astype("category")

    # valores por caso (somados dos itens do caso) para os 4 KPIs do headline
    if not cases.empty:
        _k = cases["CASE_KEY"].astype(str)
        somas = {
            "qtde_un": _num(cases["PED_QTDE"]).fillna(0.0),
            "orc_total": _num(cases["ORC_VALOR"]).fillna(0.0),
            "valor": _num(cases["PED_TOTAL"]).fillna(0.0),
            "fat_total": _num(cases["FAT_TOTAL"]).fillna(0.0),
        }
        for col, serie in somas.items():
            log[col] = log["case_id"].map(
                cases.assign(_k=_k, _v=serie).groupby("_k")["_v"].sum()).fillna(0.0)
    else:
        for col in ("qtde_un", "orc_total", "valor", "fat_total"):
            log[col] = 0.0

    return _ordena_por_sorting(log)


def _ordena_por_sorting(log: pd.DataFrame) -> pd.DataFrame:
    """Coloca os eventos do caso na ordem lógica (SORTING), preservando os
    instantes reais para o cálculo de duração.

    Regra do projeto (business_rules.md): a ordem lógica de um caso é o SORTING,
    não o EVENTTIME. Na AM Parts isso é decisivo — medido sobre o recorte de
    2026, `LIBEROU PEDIDO N1 → N2` vem invertido em 89,6% dos casos (as duas
    liberações são quase simultâneas) e `CRIOU PEDIDO → PAGAMENTO` em 53,9% (a
    data do pagamento tem semântica diferente da data do pedido). Os demais
    pares da espinha estão 100% consistentes.

    O motor de mineração ordena por (case_id, timestamp), então a correção é
    reatribuir os timestamps do caso na ordem lógica: mantém início, fim,
    duração total e o conjunto de intervalos entre eventos consecutivos —
    muda apenas a qual atividade cada instante pertence, que é justamente o
    que a origem registra de forma não confiável.
    """
    logico = log.sort_values(["case_id", "sort", "timestamp"], kind="stable")
    # mesmo agrupamento por caso nas duas ordenações -> alinhamento posicional
    cronologico = log.sort_values(["case_id", "timestamp"], kind="stable")
    out = logico.reset_index(drop=True)
    out["timestamp"] = cronologico["timestamp"].to_numpy()
    return out


ACT_COLS = ("CASE_KEY, ACTIVITY_EN, EVENTTIME, SORTING, USUARIO, VENDEDOR, "
            "ORCAMENTO, ORC_ITEM, PEDIDO, PED_ITEM, OS, SAIDA, CLIENTE, "
            "PRODUTO, PROD_NOME, CONCESSIONARIA, SOURCE_ACTIVITY")
CASE_COLS = ("CASE_KEY, ORCAMENTO, ORC_ITEM, PEDIDO, PED_ITEM, OS, SAIDA, CLIENTE, "
             "CONCESSIONARIA, PROD_NOME, DATA_ORCAMENTO, DATA_PEDIDO, "
             "ORC_VALOR, PED_QTDE, PED_TOTAL, FAT_TOTAL, FOI_CANCELADO")


def load_amparts_eventlog(conn: MySQLConnector | None = None, progress=None) -> pd.DataFrame:
    """Carga padrão do módulo.

    Banco quando PM_DB_PASSWORD estiver configurada; senão, o recorte em arquivo.
    O arquivo continua no repositório de propósito: é o caminho de contingência
    quando o banco está fora, e o que faz os testes e o dev local rodarem sem
    credencial nenhuma.
    """
    db = conn or MySQLConnector()
    if db.configured():
        return load_from_db(db, progress=progress)
    # o fallback não levanta erro (é contingência), então sem esta linha o
    # deploy serve dado congelado sem sinal nenhum nos logs do Railway.
    print("[amparts] PM_DB_PASSWORD ausente — servindo o recorte em CSV, "
          "não o MySQL")
    return load_from_csv(progress=progress)


def load_from_csv(progress=None) -> pd.DataFrame:
    """Carga do recorte de 2026 em arquivo."""
    global _ORIGEM
    _ORIGEM = "csv"
    progress = progress or (lambda p: None)
    if not ACT_FILE.exists() or not CASE_FILE.exists():
        raise RuntimeError(
            f"arquivos do recorte não encontrados em {DATA_DIR} "
            f"({ACT_FILE.name}, {CASE_FILE.name})")

    progress(5)
    acts = pd.read_csv(ACT_FILE, **_READ)
    progress(70)
    cases = pd.read_csv(CASE_FILE, **_READ)
    progress(85)
    return build_eventlog(acts, cases)


def load_from_db(conn: MySQLConnector | None = None, progress=None) -> pd.DataFrame:
    """Carga por banco (MySQL direto)."""
    global _ORIGEM
    _ORIGEM = "db"
    progress = progress or (lambda p: None)
    conn = conn or MySQLConnector()
    if not conn.configured():
        raise RuntimeError("PM_DB_PASSWORD não configurada")

    periodo = _periodo_where()
    total = conn.query_df(f"SELECT COUNT(*) AS n FROM {ACT_TABLE} WHERE {periodo}")
    total = max(int(total["n"].iloc[0]) if not total.empty else 1, 1)
    progress(3)

    # Sem ORDER BY de propósito: `build_eventlog` termina em `_ordena_por_sorting`,
    # que reordena tudo em pandas. Pedir a ordenação ao MySQL 5.6 obrigaria um
    # filesort com tabela temporária em disco sobre ~1,1M linhas, sem ganho algum.
    acts = conn.stream_df(
        ACT_COLS, ACT_TABLE, where=periodo,
        on_rows=lambda n: progress(3 + 78 * min(n, total) / total))
    progress(82)

    cases = conn.stream_df(CASE_COLS, CASE_TABLE)
    progress(90)

    # A tabela de casos cobre 2023–2029 inteiros (363k linhas), enquanto o event
    # log está recortado no período. Sem este filtro a tela Detalhes passaria a
    # listar casos fora da janela — o CSV, por já vir recortado, nunca fez isso.
    if not cases.empty and not acts.empty:
        cases = cases[cases["CASE_KEY"].isin(acts["CASE_KEY"].unique())]

    return build_eventlog(acts, cases)
