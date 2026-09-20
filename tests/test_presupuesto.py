"""Presupuesto de un proyecto (F5.12 (tope)).

El sistema itera hasta terminar, así que lo que lo detiene no puede ser un
número de rondas inventado: es el dinero. El tope lo pone el usuario y,
al alcanzarlo, el proyecto se para y se le pregunta.
"""

import json

import httpx
import pytest

from orchestrator.llm.cost import Presupuesto, PresupuestoAgotado
from orchestrator.llm.providers.deepseek import DeepSeekClient

PRECIOS = {"deepseek-chat": {"in_usd_per_mtok": 0.28, "out_usd_per_mtok": 0.42}}


def _cliente(tokens_entrada, tokens_salida):
    def responder(request):
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"a": 1}'}}],
            "usage": {"prompt_tokens": tokens_entrada, "completion_tokens": tokens_salida},
        })

    return DeepSeekClient(api_key="k", model="deepseek-chat",
                          transport=httpx.MockTransport(responder))


def test_el_cliente_apunta_lo_que_gasta():
    cliente = _cliente(1000, 500)

    cliente.complete("hola")
    cliente.complete("otra")

    assert cliente.tokens == {"entrada": 2000, "salida": 1000}


def test_el_coste_sale_de_los_tokens_y_del_precio_del_modelo():
    cliente = _cliente(1_000_000, 1_000_000)
    presupuesto = Presupuesto(1.0, PRECIOS)
    presupuesto.vigila(cliente)

    cliente.complete("hola")

    # 1 M de entrada a 0.28 + 1 M de salida a 0.42
    assert presupuesto.gastado_usd() == pytest.approx(0.70)
    assert presupuesto.queda_usd() == pytest.approx(0.30)


def test_al_pasarse_del_tope_se_para_y_se_dice_cuanto_llevaba():
    cliente = _cliente(2_000_000, 0)
    presupuesto = Presupuesto(0.5, PRECIOS)
    presupuesto.vigila(cliente)
    cliente.complete("hola")

    with pytest.raises(PresupuestoAgotado, match="0.56"):
        presupuesto.comprobar()


def test_un_modelo_sin_precio_no_rompe_el_proyecto():
    """Un modelo nuevo o local no tiene precio: no se puede contar, pero
    tampoco puede tumbar el proyecto."""
    cliente = _cliente(1000, 1000)
    presupuesto = Presupuesto(1.0, {})
    presupuesto.vigila(cliente)
    cliente.complete("hola")

    assert presupuesto.gastado_usd() == 0.0
    presupuesto.comprobar()


def test_el_tope_sale_de_la_configuracion():
    config = json.loads(json.dumps({"escalation": {"max_usd_per_project": 3.5},
                                    "pricing": PRECIOS}))
    presupuesto = Presupuesto.from_config(config)
    assert presupuesto.limite_usd == 3.5
