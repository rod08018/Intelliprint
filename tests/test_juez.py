"""Un juez rápido del concepto: JEV pregunta si algún componente queda suelto.

El usuario propuso (2026-11-09) usar JEV, un modelo de decisión de TypeSafe,
como juez de tareas para atrapar errores de diseño antes de dibujar. Se midió
antes de cablearlo, sobre los conceptos reales del workspace etiquetados a
mano más cuatro mutantes a los que se les quitó la sujeción a mano:

- «¿hay una medida supuesta?», «¿un tornillo inaccesible?» y «¿física
  errónea?» no separaban: daban lo mismo a los buenos que a los malos.
- «¿queda algún componente suelto?», en inglés, sí: los 5 sueltos dieron
  0.77–0.94 y los 15 buenos 0.67 como mucho. En español no separaba.

Por eso es una sola pregunta, en inglés, y solo un AVISO a la persona: nunca
frena ni rehace nada. Si JEV no contesta, el concepto sigue igual.
"""

import json
import os

import httpx
import pytest

from orchestrator.juez import UMBRAL_SUELTO, avisos, juzgar_concepto


def _jev(p=None, estado=200, recibidas=None):
    def responder(request):
        if recibidas is not None:
            recibidas.append(request)
        if estado != 200:
            return httpx.Response(estado, json={"error": "caído"})
        return httpx.Response(200, json={"model": "jev-1.14.0", "answers": {
            "suelto": {"type": "noul", "noul": p}}, "usage": {}})
    return httpx.MockTransport(responder)


def test_el_juez_pregunta_a_jev_si_queda_algo_suelto():
    recibidas = []
    veredicto = juzgar_concepto("El servo baja en una U abierta por arriba.", "clave-de-prueba",
                                transporte=_jev(0.91, recibidas=recibidas))

    assert veredicto == {"suelto": 0.91}
    [r] = recibidas
    assert r.headers["Authorization"] == "Bearer clave-de-prueba"
    cuerpo = json.loads(r.content)
    assert "U abierta por arriba" in cuerpo["state"]
    assert cuerpo["questions"]["suelto"]["type"] == "noul"


def test_sin_clave_no_se_juzga():
    recibidas = []
    assert juzgar_concepto("texto", None, transporte=_jev(0.9, recibidas=recibidas)) is None
    assert juzgar_concepto("texto", "", transporte=_jev(0.9, recibidas=recibidas)) is None
    assert recibidas == []


@pytest.mark.parametrize("estado", [401, 500])
def test_si_jev_falla_el_concepto_sigue_sin_juicio(estado):
    assert juzgar_concepto("texto", "clave", transporte=_jev(estado=estado)) is None


def test_si_jev_no_responde_el_concepto_sigue_sin_juicio():
    def colgado(request):
        raise httpx.ConnectTimeout("sin red", request=request)
    assert juzgar_concepto("texto", "clave", transporte=httpx.MockTransport(colgado)) is None


def test_el_aviso_sale_solo_cuando_jev_esta_seguro():
    """0.77 es el suelto más dudoso de la medida y 0.67 el bueno más alto
    (un 608ZZ a presión, que es como se monta)."""
    assert avisos({"suelto": 0.77}) and "suelto" in avisos({"suelto": 0.77})[0]
    assert avisos({"suelto": 0.67}) == []
    assert avisos(None) == [] and avisos({}) == []
    assert 0.67 < UMBRAL_SUELTO <= 0.77


SUELTO = ("Idea: una placa con una U abierta por arriba donde se baja el servo. "
          "Cómo se sujeta el servo: queda apoyado por su peso en el fondo de la U, sin tornillos "
          "ni tapa.")
SUJETO = ("Idea: una placa con una ranura donde entra el servo. Cómo se sujeta el servo: con "
          "sus dos tornillos en las orejas, a través de la placa, y apoyado en un escalón.")


@pytest.mark.llm
def test_jev_de_verdad_separa_un_servo_suelto_de_uno_atornillado():
    clave = os.environ.get("JEV_API_KEY")
    if not clave:
        pytest.skip("sin JEV_API_KEY")
    suelto, sujeto = juzgar_concepto(SUELTO, clave), juzgar_concepto(SUJETO, clave)
    assert avisos(suelto) and not avisos(sujeto), (suelto, sujeto)
