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
