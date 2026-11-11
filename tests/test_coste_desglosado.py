"""Desglose del coste de un proyecto (F5.12 (tope)).

Un total no sirve para decidir nada. Lo que dice si el proyecto sale a
cuenta es en QUÉ se fue: qué agente, con qué modelo y en qué etapa.
"""

import json

import httpx
import pytest

from orchestrator.llm.cost import Presupuesto
from orchestrator.llm.providers.deepseek import DeepSeekClient

PRECIOS = {
    "deepseek-chat": {"in_usd_per_mtok": 0.28, "out_usd_per_mtok": 0.42},
    "deepseek-reasoner": {"in_usd_per_mtok": 0.56, "out_usd_per_mtok": 1.68},
}


def _cliente(modelo, entrada, salida):
    def responder(request):
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            "usage": {"prompt_tokens": entrada, "completion_tokens": salida},
        })

    return DeepSeekClient(api_key="k", model=modelo, transport=httpx.MockTransport(responder))


def _proyecto():
    mecanico = _cliente("deepseek-reasoner", 10_000, 30_000)
    piezas = _cliente("deepseek-chat", 5_000, 1_000)
    presupuesto = Presupuesto(2.0, PRECIOS)
    presupuesto.vigila(mecanico, "Mechanism Designer")
    presupuesto.vigila(piezas, "Part Designer")

    presupuesto.etapa("ronda 1")
    mecanico.complete("diseña")
    presupuesto.etapa("ronda 1 · pieza «base»")
    piezas.complete("dibuja")
    piezas.complete("corrige")
    presupuesto.etapa("ronda 2")
    mecanico.complete("corrige")
    return presupuesto


def test_cada_llamada_queda_apuntada_con_su_agente_su_modelo_y_su_etapa():
    detalle = _proyecto().detalle()

    assert len(detalle) == 4
    primera = detalle[0]
    assert primera["agente"] == "Mechanism Designer"
    assert primera["modelo"] == "deepseek-reasoner"
    assert primera["etapa"] == "ronda 1"
    assert primera["tokens_entrada"] == 10_000
    # 10 k de entrada a 0.56 + 30 k de salida a 1.68
    assert primera["usd"] == pytest.approx(0.0056 + 0.0504)
    assert [d["etapa"] for d in detalle[1:3]] == ["ronda 1 · pieza «base»"] * 2


def test_el_desglose_suma_por_agente_y_por_etapa():
    resumen = _proyecto().resumen()

    assert resumen["total_usd"] == pytest.approx(_proyecto().gastado_usd())
    assert resumen["por_agente"]["Mechanism Designer"]["llamadas"] == 2
    assert resumen["por_agente"]["Part Designer"]["llamadas"] == 2
    assert set(resumen["por_etapa"]) == {"ronda 1", "ronda 1 · pieza «base»", "ronda 2"}
    assert (resumen["por_agente"]["Mechanism Designer"]["usd"]
            > resumen["por_agente"]["Part Designer"]["usd"])


def test_se_guarda_en_la_carpeta_del_proyecto_legible_y_en_datos(tmp_path):
    _proyecto().escribir(tmp_path)

    datos = json.loads((tmp_path / "design_cost.json").read_text(encoding="utf-8"))
    assert len(datos["detalle"]) == 4
    assert datos["resumen"]["total_usd"] > 0

    texto = (tmp_path / "design_cost.md").read_text(encoding="utf-8")
    assert "Mechanism Designer" in texto and "deepseek-reasoner" in texto
    assert "ronda 1 · pieza «base»" in texto
    assert "USD" in texto


def test_sin_precio_conocido_se_cuentan_los_tokens_y_se_avisa(tmp_path):
    cliente = _cliente("modelo-nuevo", 1000, 1000)
    presupuesto = Presupuesto(1.0, PRECIOS)
    presupuesto.vigila(cliente, "Part Designer")
    presupuesto.etapa("ronda 1")
    cliente.complete("hola")

    presupuesto.escribir(tmp_path)

    texto = (tmp_path / "design_cost.md").read_text(encoding="utf-8")
    assert "sin precio" in texto
    assert presupuesto.detalle()[0]["tokens_salida"] == 1000


def test_una_obra_suma_su_gasto_paso_a_paso_en_su_carpeta(tmp_path, monkeypatch):
    """Una obra no dejaba coste: la ronda del pan-tilt del banco (1110-0313)
    no pudo decir cuánto costó. Cada paso es un lanzamiento distinto, así
    que el gasto se suma al que ya había. Aquí, dos desgloses que no salen,
    de 1000 tokens de entrada y 500 de salida cada uno: al precio de
    `config/models.yaml` (0.30 y 1.20 USD por millón), 0.0009 USD cada uno."""
    from pathlib import Path

    from orchestrator import cli
    from orchestrator.agents import desglosador

    monkeypatch.setattr(cli, "DeepSeekClient", lambda api_key, model: DeepSeekClient(
        api_key=api_key, model=model, transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                       "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}))))

    class SinDesglose:
        def __init__(self, cliente, reserva=None):
            self.cliente = cliente

        def desglosar(self, peticion, **_):
            self.cliente.complete("desglosa")
            raise ValueError("no cuadra")

    monkeypatch.setattr(desglosador, "DesglosadorAgent", SinDesglose)
    raiz = Path(__file__).resolve().parents[1]
    for _ in range(2):
        with pytest.raises(SystemExit):
            cli._paso_de_obra(tmp_path, "un pan-tilt", raiz, {"DEEPSEEK_API_KEY": "k"}, "x")

    resumen = json.loads((tmp_path / "design_cost.json").read_text(encoding="utf-8"))["resumen"]
    assert resumen["llamadas"] == 2
    assert resumen["total_usd"] == pytest.approx(2 * (0.0003 + 0.0006))
    assert list(resumen["por_etapa"]) == ["desglose"]
    assert "0.0018 USD" in (tmp_path / "design_cost.md").read_text(encoding="utf-8")


def _ya_gastado(carpeta, usd):
    (carpeta / "design_cost.json").write_text(json.dumps({"resumen": {}, "detalle": [
        {"agente": "razonador", "modelo": "deepseek-reasoner", "etapa": "pieza «Base»",
         "tokens_entrada": 1, "tokens_salida": 1, "usd": usd, "con_precio": True}]}),
        encoding="utf-8")


def test_un_proyecto_que_llego_a_su_tope_no_gasta_mas(tmp_path):
    """El usuario puso el tope en 5 USD por proyecto (2026-09-21). Solo lo
    comprobaba el flujo de mecanismos: una pieza o un backlog, que es lo que
    se usa, podían pasarse sin que nada los parara, aunque la web dijera
    «hasta 5 USD» (visto al quitar ese flujo, 2026-11-11). Cada paso de un
    proyecto —el plan, cada pieza— mira antes de empezar lo que ya lleva."""
    from pathlib import Path

    import yaml

    from orchestrator import cli

    raiz = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((raiz / "config" / "models.yaml").read_text(encoding="utf-8"))
    assert config["escalation"]["max_usd_per_project"] == 5.0, "lo decidió el usuario"
    hecho = []

    _ya_gastado(tmp_path, 5.01)
    with pytest.raises(SystemExit) as parada:
        with cli._apuntar_gasto(raiz, tmp_path, "pieza «Soporte»"):
            hecho.append("gastó")
    assert hecho == []
    assert "5.01 USD" in str(parada.value) and "5.00" in str(parada.value)

    _ya_gastado(tmp_path, 4.99)
    with cli._apuntar_gasto(raiz, tmp_path, "pieza «Soporte»"):
        hecho.append("gastó")
    assert hecho == ["gastó"]


def test_una_pieza_suelta_tambien_deja_su_coste(tmp_path, monkeypatch):
    """Solo los mecanismos dejaban `design_cost.md`; una pieza suelta, que es
    lo que más se pide, no decía cuánto costó. Un concepto que no sale tras
    una llamada de 1000 + 500 tokens: 0.0009 USD."""
    from pathlib import Path

    from orchestrator import cli, pieza

    monkeypatch.setenv("INTELLIPRINT_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setattr(cli, "DeepSeekClient", lambda api_key, model: DeepSeekClient(
        api_key=api_key, model=model, transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                       "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}))))

    def sin_concepto(peticion, carpeta, requisitos, **_):
        requisitos._client.complete("¿qué pide?")
        return None

    monkeypatch.setattr(pieza, "concebir_pieza", sin_concepto)
    carpeta = tmp_path / "gancho"
    raiz = Path(__file__).resolve().parents[1]
    from types import SimpleNamespace
    with pytest.raises(SystemExit):
        cli._pieza(SimpleNamespace(peticion=["un gancho"], archivo=False, carpeta=str(carpeta),
                                   aprobar_concepto=False),
                   raiz, {"DEEPSEEK_API_KEY": "k", "INTELLIPRINT_WORKSPACE": str(tmp_path / "ws")},
                   "x")
    resumen = json.loads((carpeta / "design_cost.json").read_text(encoding="utf-8"))["resumen"]
    assert resumen["llamadas"] == 1
    assert resumen["total_usd"] == pytest.approx(0.0003 + 0.0006)
