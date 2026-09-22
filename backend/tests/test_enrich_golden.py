"""Rede de segurança para refatorar o `enrich` sem mudar nenhum número.

O `enrich` ordena o log inteiro sete vezes e o copia quatro — a otimização
óbvia é calcular a tabela de casos uma vez e reaproveitar. Mas "dá o mesmo
resultado" é o tipo de afirmação que tem de ser verificada, não presumida:
`rework` e `cancel` ordenam só por timestamp antes do `first()`, `two_match`
por (caso, timestamp); empates e `first()` são onde refatoração muda número
em silêncio.

Este teste congela a saída completa do `enrich` sobre um log sintético que
exercita cada bloco (caminho feliz, cancelamento no orçamento e no pedido,
retrabalho por repetição, ramo de OS, devolução, dois anos) e compara campo a
campo. Um centavo de diferença em qualquer KPI falha.

Na primeira execução o arquivo dourado não existe: o teste o cria e falha de
propósito, para o arquivo ser revisado e commitado antes de valer como
referência. Também cobre o `default_period` da primeira carga do módulo.
"""
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import auth, data_source
from app import main as app_main
from app.modules.amparts_module import AmPartsModule
from app.sources.amparts import build_eventlog

GOLDEN = Path(__file__).parent / "golden" / "amparts_enrich.json"

# SORTING é o rank fixo por atividade no export (ver amparts_module.py)
SORT = {
    "CANCELOU ORCAMENTO": 5, "CRIOU ORCAMENTO": 10, "CONVERTEU ORCAMENTO": 15,
    "CRIOU PEDIDO": 20, "EDITOU ITENS": 21, "CANCELOU PEDIDO": 22,
    "APROVOU PEDIDO N1": 25, "LIBEROU AUTOMATICO N2": 26,
    "ABRIU OS": 30, "RECEBEU VEICULO": 32, "FINALIZOU OS": 35, "CANCELOU OS": 36,
    "BAIXA AUTOMATICA": 40, "FATUROU SAIDA": 45, "PAGAMENTO": 50,
    "SOLICITOU RETORNO": 70, "APROVOU RETORNO": 72, "RETORNOU PECA": 75,
}


def _feliz(d, users=("u1", "u1", "u2", "u2", "sys", "sys", "u3")):
    """Espinha completa do caminho feliz a partir do dia `d` (YYYY-MM-DD)."""
    return [
        ("CRIOU ORCAMENTO",      f"{d} 09:00", users[0]),
        ("CONVERTEU ORCAMENTO",  f"{d} 10:00", users[1]),
        ("CRIOU PEDIDO",         _dia(d, 1) + " 09:00", users[2]),
        ("APROVOU PEDIDO N1",    _dia(d, 1) + " 11:00", users[3]),
        ("LIBEROU AUTOMATICO N2", _dia(d, 1) + " 11:05", users[4]),
        ("BAIXA AUTOMATICA",     _dia(d, 2) + " 09:00", users[5]),
        ("PAGAMENTO",            _dia(d, 3) + " 09:00", users[6]),
    ]


def _dia(d, mais):
    return (pd.Timestamp(d) + pd.Timedelta(days=mais)).strftime("%Y-%m-%d")


# caso -> (cliente, produto, valor, qtde, orcado, faturado, cancelado, eventos)
CASOS = {
    "H1": ("ACME", "Filtro", 1000.0, 2, 1100.0, 1000.0, 0, _feliz("2026-01-05")),
    "H2": ("ACME", "Pastilha", 2500.0, 5, 2600.0, 2500.0, 0, [
        ("CRIOU ORCAMENTO", "2026-02-01 08:00", "u1"),
        ("CONVERTEU ORCAMENTO", "2026-02-01 09:00", "u1"),
        ("CRIOU PEDIDO", "2026-02-02 08:00", "u2"),
        ("APROVOU PEDIDO N1", "2026-02-02 09:00", "u2"),
        ("LIBEROU AUTOMATICO N2", "2026-02-02 09:10", "sys"),
        ("BAIXA AUTOMATICA", "2026-02-03 08:00", "sys"),
        ("FATUROU SAIDA", "2026-02-04 08:00", "u3"),
        ("PAGAMENTO", "2026-02-05 08:00", "u3"),
    ]),
    "H3": ("Beta", "Filtro", 800.0, 1, 800.0, 800.0, 0,
           _feliz("2026-02-10", users=("u4",) * 4 + ("sys", "sys", "u4"))),
    # cancelado no orçamento — SORTING 5 vem antes do CRIOU (10) na ordem lógica
    "C1": ("Beta", "Oleo", 300.0, 1, 300.0, 0.0, 1, [
        ("CRIOU ORCAMENTO", "2026-01-10 09:00", "u1"),
        ("CANCELOU ORCAMENTO", "2026-01-11 09:00", "u1"),
    ]),
    "C2": ("ACME", "Oleo", 450.0, 3, 450.0, 0.0, 1, [
        ("CRIOU ORCAMENTO", "2026-01-15 09:00", "u1"),
        ("CONVERTEU ORCAMENTO", "2026-01-15 10:00", "u1"),
        ("CRIOU PEDIDO", "2026-01-16 09:00", "u2"),
        ("CANCELOU PEDIDO", "2026-01-17 09:00", "u2"),
    ]),
    # retrabalho: EDITOU ITENS repetido (mesmo SORTING, timestamps distintos)
    "R1": ("Gama", "Pastilha", 1200.0, 4, 1300.0, 1200.0, 0, [
        ("CRIOU ORCAMENTO", "2026-03-01 09:00", "u5"),
        ("CONVERTEU ORCAMENTO", "2026-03-01 10:00", "u5"),
        ("CRIOU PEDIDO", "2026-03-02 09:00", "u5"),
        ("EDITOU ITENS", "2026-03-02 10:00", "u5"),
        ("EDITOU ITENS", "2026-03-02 11:00", "u5"),
        ("APROVOU PEDIDO N1", "2026-03-03 09:00", "u2"),
        ("LIBEROU AUTOMATICO N2", "2026-03-03 09:05", "sys"),
        ("BAIXA AUTOMATICA", "2026-03-04 09:00", "sys"),
        ("PAGAMENTO", "2026-03-05 09:00", "u3"),
    ]),
    # com Ordem de Serviço (fora do caminho feliz)
    "O1": ("Gama", "Filtro", 3000.0, 1, 3200.0, 3000.0, 0, [
        ("CRIOU ORCAMENTO", "2026-03-10 09:00", "u1"),
        ("CONVERTEU ORCAMENTO", "2026-03-10 10:00", "u1"),
        ("CRIOU PEDIDO", "2026-03-11 09:00", "u2"),
        ("APROVOU PEDIDO N1", "2026-03-11 10:00", "u2"),
        ("LIBEROU AUTOMATICO N2", "2026-03-11 10:05", "sys"),
        ("ABRIU OS", "2026-03-12 08:00", "u6"),
        ("RECEBEU VEICULO", "2026-03-12 09:00", "u6"),
        ("FINALIZOU OS", "2026-03-12 17:00", "u6"),
        ("BAIXA AUTOMATICA", "2026-03-13 09:00", "sys"),
        ("FATUROU SAIDA", "2026-03-14 09:00", "u3"),
        ("PAGAMENTO", "2026-03-15 09:00", "u3"),
    ]),
    # devolução (REVERSAL_ACTS) depois da fatura
    "D1": ("Beta", "Pastilha", 600.0, 2, 600.0, 600.0, 0, [
        ("CRIOU ORCAMENTO", "2026-03-20 09:00", "u4"),
        ("CONVERTEU ORCAMENTO", "2026-03-20 10:00", "u4"),
        ("CRIOU PEDIDO", "2026-03-21 09:00", "u4"),
        ("APROVOU PEDIDO N1", "2026-03-21 10:00", "u2"),
        ("LIBEROU AUTOMATICO N2", "2026-03-21 10:05", "sys"),
        ("BAIXA AUTOMATICA", "2026-03-22 09:00", "sys"),
        ("FATUROU SAIDA", "2026-03-23 09:00", "u3"),
        ("SOLICITOU RETORNO", "2026-03-25 09:00", "u4"),
        ("APROVOU RETORNO", "2026-03-25 10:00", "u2"),
        ("RETORNOU PECA", "2026-03-26 09:00", "u6"),
    ]),
    # ano anterior: garante que o padrão da primeira carga escolhe 2026, e que
    # "sem período" sem a marca continua devolvendo os dois anos
    "P1": ("ACME", "Filtro", 900.0, 1, 900.0, 900.0, 0, _feliz("2025-12-10")),
}

_ACT_COLS = ["CASE_KEY", "ACTIVITY_EN", "EVENTTIME", "SORTING", "USUARIO", "VENDEDOR",
             "ORCAMENTO", "ORC_ITEM", "PEDIDO", "PED_ITEM", "OS", "SAIDA", "CLIENTE",
             "PRODUTO", "PROD_NOME", "CONCESSIONARIA", "SOURCE_ACTIVITY"]
_CASE_COLS = ["CASE_KEY", "ORCAMENTO", "ORC_ITEM", "PEDIDO", "PED_ITEM", "OS", "SAIDA",
              "CLIENTE", "CONCESSIONARIA", "PROD_NOME", "DATA_ORCAMENTO", "DATA_PEDIDO",
              "ORC_VALOR", "PED_QTDE", "PED_TOTAL", "FAT_TOTAL", "FOI_CANCELADO"]


def _log() -> pd.DataFrame:
    """Monta o log pelo mesmo caminho da produção (tipos do banco)."""
    acts, cases = [], []
    for i, (cid, (cli, prod, valor, qtde, orc, fat, canc, evs)) in enumerate(CASOS.items()):
        num = 900 + i
        primeira = evs[0][1][:10]
        for act, ts, user in evs:
            acts.append({
                "CASE_KEY": cid, "ACTIVITY_EN": act, "EVENTTIME": pd.Timestamp(ts).to_pydatetime(),
                "SORTING": SORT[act], "USUARIO": user, "VENDEDOR": "vend",
                "ORCAMENTO": str(num), "ORC_ITEM": "1", "PEDIDO": str(num + 100), "PED_ITEM": "1",
                "OS": None, "SAIDA": None, "CLIENTE": cli, "PRODUTO": prod[:3].upper(),
                "PROD_NOME": prod, "CONCESSIONARIA": "conc", "SOURCE_ACTIVITY": "PEDIDO",
            })
        cases.append({
            "CASE_KEY": cid, "ORCAMENTO": str(num), "ORC_ITEM": "1", "PEDIDO": str(num + 100),
            "PED_ITEM": "1", "OS": None, "SAIDA": None, "CLIENTE": cli, "CONCESSIONARIA": "conc",
            "PROD_NOME": prod, "DATA_ORCAMENTO": primeira, "DATA_PEDIDO": primeira,
            "ORC_VALOR": orc, "PED_QTDE": qtde, "PED_TOTAL": valor, "FAT_TOTAL": fat,
            "FOI_CANCELADO": canc,
        })
    return build_eventlog(pd.DataFrame(acts, columns=_ACT_COLS),
                          pd.DataFrame(cases, columns=_CASE_COLS))


def _norm(o):
    """Torna o payload comparável: floats arredondados, escalares numpy nativos."""
    if isinstance(o, bool) or o is None:
        return o
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, dict):
        return {str(k): _norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_norm(v) for v in o]
    if hasattr(o, "item"):
        return _norm(o.item())
    return o


def _dump(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1, default=str)


# ── dourado ──────────────────────────────────────────────────────────────────

def test_enrich_bate_com_o_dourado():
    atual = _norm(AmPartsModule().enrich(_log()))

    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(_dump(atual), encoding="utf-8")
        pytest.fail(f"dourado criado em {GOLDEN}. Revise o arquivo, commite e rode de novo.")

    esperado = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if atual != esperado:
        diverg = GOLDEN.with_suffix(".actual.json")
        diverg.write_text(_dump(atual), encoding="utf-8")
        pytest.fail(f"enrich divergiu do dourado; saída atual gravada em {diverg.name}. "
                    "Se a mudança foi intencional, substitua o dourado por ela.")


# ── invariantes que não dependem do dourado ──────────────────────────────────
# Servem para a primeira execução (antes de existir dourado) e como leitura
# humana do que o fixture garante.

@pytest.fixture(scope="module")
def payload():
    return AmPartsModule().enrich(_log())


def test_total_de_casos(payload):
    assert payload["totalCases"] == 9


def test_variantes_cobrem_todos_os_casos(payload):
    assert sum(v["cases"] for v in payload["variants"]) == 9
    assert abs(sum(v["pct"] for v in payload["variants"]) - 100) < 0.11


def test_no_de_criou_orcamento_esta_em_todo_caso(payload):
    nos = {n["id"]: n for n in payload["nodes"]}
    assert nos["CRIOU ORCAMENTO"]["cases"] == 9
    assert nos["EDITOU ITENS"]["freq"] == 2          # a repetição do R1


def test_retrabalho_conta_os_quatro_casos(payload):
    # C1 e C2 (cancelamentos), R1 (EDITOU ITENS repetido), D1 (ciclo de retorno)
    assert payload["rework"]["itensRetrabalho"] == 4


def test_cancelamentos_incluem_a_devolucao(payload):
    # CANCEL ∪ REVERSAL_ACTS: C1, C2 e D1 (RETORNOU PECA)
    assert payload["cancelamentos"]["casosCancelados"] == 3


def test_valor_total_pedido_soma_uma_vez_por_caso(payload):
    valped = next(k for k in payload["headlineKpis"] if k["id"] == "valped")
    assert valped["value"] == "10,8K"                # 10.750 somados por caso, não por evento


# ── default_period: primeira carga já filtrada pelo ano ──────────────────────

USUARIO = {"email": "t@t", "name": "T", "modules": ["amparts"], "pass_sha256": ""}


@pytest.fixture
def api(monkeypatch):
    log = _log()
    monkeypatch.setattr(auth, "load_users", lambda: [USUARIO])
    monkeypatch.setitem(data_source._cache, "amparts", log)
    monkeypatch.setitem(data_source._state, "path", None)
    monkeypatch.setattr(app_main, "_ENRICH_CACHE", {})
    cli = TestClient(app_main.app)
    cli.headers["Authorization"] = f"Bearer {auth.make_token(USUARIO['email'])}"
    return cli


def test_ano_padrao_e_o_mais_recente_das_datas_de_referencia():
    assert app_main._ano_padrao(_log(), None) == 2026
    assert app_main._ano_padrao(_log().iloc[0:0], None) is None


def test_primeira_carga_responde_pelo_ano_mais_recente(api):
    r = api.get("/api/modules/amparts?default_period=1")
    assert r.status_code == 200
    assert r.json()["filters"]["years"] == [2026]
    assert r.json()["totalCases"] == 8                 # P1 (2025) fica de fora
    # o ano resolvido entra na chave — é o que faz a 2ª chamada bater no cache
    chaves = list(app_main._ENRICH_CACHE)
    assert len(chaves) == 1 and chaves[0][4] == 2026


def test_segunda_chamada_com_o_ano_bate_no_cache(api):
    primeiro = api.get("/api/modules/amparts?default_period=1").json()
    segundo = api.get("/api/modules/amparts?ano=2026").json()
    assert segundo == primeiro
    assert len(app_main._ENRICH_CACHE) == 1            # não recalculou


def test_sem_a_marca_sem_periodo_continua_sendo_o_log_inteiro(api):
    """Limpar o ano na tela tem de continuar mostrando tudo."""
    r = api.get("/api/modules/amparts")
    assert r.status_code == 200
    assert r.json()["filters"]["years"] == [2025, 2026]
    assert r.json()["totalCases"] == 9


def test_marca_nao_sobrepoe_periodo_explicito(api):
    r = api.get("/api/modules/amparts?default_period=1&ano=2025")
    assert r.status_code == 200
    assert r.json()["totalCases"] == 1


# ── warm: a visão padrão fica pronta antes de a fonte virar `ready` ──────────

def test_warm_deixa_a_visao_padrao_no_cache_e_a_primeira_carga_bate(api):
    app_main._warm_default("amparts", data_source._cache["amparts"], lambda p: None)
    chaves = list(app_main._ENRICH_CACHE)
    assert len(chaves) == 1 and chaves[0][4] == 2026
    r = api.get("/api/modules/amparts?default_period=1")
    assert r.status_code == 200 and r.json()["totalCases"] == 8
    assert len(app_main._ENRICH_CACHE) == 1            # hit: nada recalculado


def test_warm_esta_registrado_para_toda_fonte_real():
    assert set(data_source.WARMERS) == set(data_source.REAL_LOADERS)


def _fonte_isolada(monkeypatch, log, warm):
    monkeypatch.setattr(data_source, "_cache", {})
    monkeypatch.setattr(data_source, "_real",
                        {"amparts": {"loading": True, "error": None, "progress": 0}})
    monkeypatch.setattr(data_source, "_load_real", lambda key, progress=None: log)
    monkeypatch.setattr(data_source, "WARMERS", {"amparts": warm})


def test_bg_load_aquece_antes_de_ficar_ready(monkeypatch):
    visto = []

    def warm(log, progress):
        visto.append(data_source.real_status("amparts"))
        progress(95)

    _fonte_isolada(monkeypatch, _log(), warm)
    data_source._bg_load("amparts")
    assert visto == ["loading"]                        # warm rodou ANTES do ready
    assert data_source.real_status("amparts") == "ready"
    assert data_source.real_progress("amparts") == 100


def test_falha_no_warm_nao_derruba_a_carga(monkeypatch):
    def warm(log, progress):
        raise RuntimeError("boom")

    _fonte_isolada(monkeypatch, _log(), warm)
    data_source._bg_load("amparts")
    assert data_source.real_status("amparts") == "ready"
    assert data_source.real_error("amparts") is None
