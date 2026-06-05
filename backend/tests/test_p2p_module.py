from app.modules.p2p_module import P2PModule
from app.demo.generate_p2p import build_p2p_log

module = P2PModule()
log = build_p2p_log(n_cases=500, seed=7)


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
