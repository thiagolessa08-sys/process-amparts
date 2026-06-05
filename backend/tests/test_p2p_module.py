from app.modules.p2p_module import P2PModule
from app.demo.generate_p2p import build_p2p_log

module = P2PModule()
log    = build_p2p_log(n_cases=500, seed=7)


def test_payload_has_required_keys():
    payload = module.enrich(log)
    for key in ["key", "name", "short", "color", "totalCases", "avgVariants",
                "nodes", "edges", "variants", "kpis", "drill", "filters"]:
        assert key in payload, f"chave ausente: {key}"


def test_nodes_have_visual_and_metric_fields():
    payload = module.enrich(log)
    node = next(n for n in payload["nodes"] if n["id"] == "req")
    assert "x" in node and "y" in node
    assert "cases" in node
    assert "avgDwell" in node


def test_edges_have_bottleneck_and_time():
    payload = module.enrich(log)
    edge = payload["edges"][0]
    assert "bottleneck" in edge
    assert "time" in edge
    assert "cases" in edge


def test_variants_have_conformance_and_tag():
    payload = module.enrich(log)
    v = payload["variants"][0]
    assert "conformant" in v
    assert "tag" in v
    assert "avgDur" in v
    assert "path" in v


def test_happy_path_variant_is_conformant():
    payload = module.enrich(log)
    happy = next((v for v in payload["variants"] if v["conformant"]), None)
    assert happy is not None


def test_kpis_have_trend_and_severity():
    payload = module.enrich(log)
    kpi = payload["kpis"][0]
    assert "trend" in kpi
    assert "sev" in kpi
    assert "value" in kpi


def test_total_cases_matches_log():
    payload = module.enrich(log)
    assert payload["totalCases"] == log["case_id"].nunique()


def test_drill_maverick_has_rows():
    payload = module.enrich(log)
    # ~10% dos casos são maverick — deve haver drill
    assert "maverick" in payload["drill"]
    d = payload["drill"]["maverick"]
    assert d["rows"]
    assert len(d["columns"]) == 5
    # cada linha tem Caso, Comprador, Fornecedor, Valor, Categoria
    row = d["rows"][0]
    assert row[0].startswith("#")


def test_drill_rework_has_rows():
    payload = module.enrich(log)
    assert "rework" in payload["drill"]
    d = payload["drill"]["rework"]
    assert d["rows"]
    row = d["rows"][0]
    assert row[0].startswith("#")


def test_drill_conf_has_rows():
    payload = module.enrich(log)
    assert "conf" in payload["drill"]
    d = payload["drill"]["conf"]
    assert d["rows"]
    # desvio é um dict badge
    assert isinstance(d["rows"][0][3], dict)


def test_kpis_with_drill_have_drill_key():
    payload = module.enrich(log)
    kpis_with_drill = [k for k in payload["kpis"] if "drill" in k]
    assert len(kpis_with_drill) >= 2
    for k in kpis_with_drill:
        assert k["drill"] in payload["drill"]


def test_filters_have_fornecedores():
    payload = module.enrich(log)
    assert len(payload["filters"]["dims"]) > 0
