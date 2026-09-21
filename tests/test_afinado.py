"""Puntuar rondas y afinar números sin el modelo (F3.15 (mecanismos)).

Fallo real, el cuarto trinquete del 2026-09-21: en las rondas 11-16 la
rueda ya avanzaba 37-39° empujada de verdad por la uña (se pedían 45). En
la 17 el diseñador lo tiró todo, empeoró y agotó el dinero. Faltaban dos
cosas: saber cuál era la MEJOR ronda para volver a ella, y que los números
—la amplitud de la palanca— los afinara el código midiendo, en vez del
modelo probando a ciegas a 0.08 USD por intento.
"""

import pytest

from orchestrator.mechanisms.verificacion import Verificacion, afinar, puntuacion
from orchestrator.schemas.mechanism import MechanismSpec
from tests.test_mechanism_flow import _spec


def _v(etapa, fallos=(), desvio=0.0):
    return Verificacion(etapa=etapa, fallos=list(fallos), desvio=desvio)


# --- Qué ronda es mejor -------------------------------------------------------


def test_llegar_mas_lejos_pesa_mas_que_tener_menos_fallos():
    """Una ronda que se cae al buscar apoyos da UN fallo; una que llega al
    barrido y encuentra dos choques da dos. La segunda está más cerca."""
    se_cae_pronto = _v(Verificacion.APOYOS, ["- la uña no llega"])
    llega_al_barrido = _v(Verificacion.BARRIDO, ["- choque a", "- choque b"])
    assert puntuacion(llega_al_barrido) < puntuacion(se_cae_pronto)


def test_en_la_misma_etapa_gana_la_de_menos_fallos():
    assert puntuacion(_v(Verificacion.BARRIDO, ["- x"])) < puntuacion(
        _v(Verificacion.BARRIDO, ["- x", "- y"]))


def test_con_los_mismos_fallos_gana_la_que_se_desvia_menos_de_lo_pedido():
    assert puntuacion(_v(Verificacion.BARRIDO, ["- x"], 0.2)) < puntuacion(
        _v(Verificacion.BARRIDO, ["- x"], 1.1))


def test_una_ronda_sin_fallos_es_la_mejor_posible():
    assert puntuacion(_v(Verificacion.BARRIDO)) < puntuacion(_v(Verificacion.BARRIDO, ["- x"]))


# --- Afinar los números ---------------------------------------------------------


def _con_param(amp):
    s = _spec(0.5)
    s["params"] = {"amp": amp}
    return MechanismSpec(**s)


def test_el_afinado_encuentra_el_numero_que_arregla_la_ronda():
    """Evaluador escrito a mano: la rueda avanza lo que diga `amp`, y se
    piden 45 ± 3. Con amp = 37 falla; el afinado tiene que subirlo."""
    def evaluar(spec):
        amp = spec.params["amp"]
        falta = abs(amp - 45) > 3
        return _v(Verificacion.BARRIDO, ["- la rueda no avanza lo pedido"] if falta else [],
                  desvio=max(0, abs(amp - 45) - 3) / 3)

    base = evaluar(_con_param(37.0))
    resultado = afinar(_con_param(37.0), base, evaluar)

    assert resultado is not None
    spec, ver, notas = resultado
    assert not ver.fallos
    assert 42 <= spec.params["amp"] <= 48
    assert notas and "amp" in notas[0] and "37" in notas[0]


def test_si_nada_mejora_no_se_toca_nada():
    def evaluar(spec):
        return _v(Verificacion.BARRIDO, ["- choque que no depende de amp"])

    assert afinar(_con_param(37.0), evaluar(_con_param(37.0)), evaluar) is None


def test_sin_parametros_no_hay_nada_que_afinar():
    llamadas = []
    spec = MechanismSpec(**_spec(0.5))
    assert afinar(spec, _v(Verificacion.BARRIDO, ["- x"]), lambda s: llamadas.append(s)) is None
    assert llamadas == []


def test_el_afinado_tiene_un_numero_maximo_de_pruebas():
    """Cada prueba es un barrido en FreeCAD: no puede quedarse probando."""
    llamadas = []

    def evaluar(spec):
        llamadas.append(spec)
        return _v(Verificacion.BARRIDO, ["- x"], desvio=1.0)

    s = _spec(0.5)
    s["params"] = {f"p{i}": 10.0 + i for i in range(20)}
    afinar(MechanismSpec(**s), _v(Verificacion.BARRIDO, ["- x"], 1.0), evaluar, max_pruebas=8)
    assert len(llamadas) <= 8


def test_el_afinado_no_cambia_la_especificacion_original():
    def evaluar(spec):
        return _v(Verificacion.BARRIDO, [] if spec.params["amp"] > 40 else ["- x"])

    original = _con_param(37.0)
    afinar(original, evaluar(original), evaluar)
    assert original.params["amp"] == 37.0


# --- El TAMAÑO del fallo -------------------------------------------------------
#
# Fallo real, el Ginebra del 2026-09-21: «el pasador atraviesa la rueda» con
# 29.9, 1.2, 29.9, 29.9 y 1.1 mm³. Las rondas de 1 mm³ estaban casi
# resueltas; para el sistema eran «el mismo fallo» que las de 30. La memoria
# no supo anclarse en la buena y el detector de atasco paró el proyecto.

from orchestrator.mechanisms.verificacion import magnitud_del_fallo  # noqa: E402

MUCHO = "- «rueda_ginebra» está siendo atravesada por «pasador» con t = 15 y no puede apartarse: recorre 90 y lo mejor que consigue es solaparse 29.9 mm³ (con el valor 118.12)."
POCO = "- «rueda_ginebra» está siendo atravesada por «pasador» con t = 5 y no puede apartarse: recorre 90 y lo mejor que consigue es solaparse 1.2 mm³ (con el valor -375.87)."


@pytest.mark.parametrize("linea, esperado", [
    (MUCHO, 29.9),
    ("- «uña» no llega a apoyarse en «rueda» con t = 13: recorre 40 desde 20.00 y lo más cerca que pasa es 0.15 mm (con el valor -20.00).", 0.15),
    ("- palanca / rueda: con t = -15 (1 posiciones). Peor: con t = -15, palanca y rueda se separan 1.10 mm; tienen que seguir en contacto", 1.10),
    ("- el tope entre «a» y «b» en t = 25 no llega a tocar: quedan 0.40 mm de hueco", 0.40),
    ("- el tope entre «a» y «b» en t = 25 ya se atraviesa (3.5 mm³ en común)", 3.5),
    ("- el punto de partida de «trinquete» ya está dentro de «rueda» con t = -20: con el valor 0.00 se solapan 326.9 mm³.", 326.9),
])
def test_el_tamano_se_lee_del_motivo(linea, esperado):
    """Solo las cifras que miden el fallo: ni «recorre 90», ni «con el valor
    118.12», ni «t = 15», que son del ciclo y no de cuánto falla."""
    assert magnitud_del_fallo([linea]) == pytest.approx(esperado)


def test_un_motivo_sin_cifra_de_fallo_cuenta_como_cero():
    assert magnitud_del_fallo(["- la pieza «rueda» no se pudo dibujar"]) == 0.0


def test_con_el_mismo_fallo_gana_el_mas_pequeno():
    lejos = _v(Verificacion.APOYOS, [MUCHO])
    cerca = _v(Verificacion.APOYOS, [POCO])
    assert puntuacion(cerca) < puntuacion(lejos)


def test_el_tamano_pesa_menos_que_la_etapa_y_el_numero_de_fallos():
    """Un solape enorme en el barrido sigue siendo mejor que caerse antes."""
    barrido_grande = _v(Verificacion.BARRIDO, [MUCHO])
    apoyos_pequeno = _v(Verificacion.APOYOS, [POCO])
    assert puntuacion(barrido_grande) < puntuacion(apoyos_pequeno)


# --- Atasco: el mismo fallo, ¿igual de grande? --------------------------------


def test_el_mismo_fallo_que_se_achica_no_cuenta_como_repeticion():
    from orchestrator.mechanisms.flow import contar_repeticion

    vistos = {}
    assert contar_repeticion(vistos, "pasador||rueda", 29.9) == 1
    assert contar_repeticion(vistos, "pasador||rueda", 1.2) == 1     # mucho más pequeño: progreso


def test_el_mismo_fallo_igual_de_grande_si_cuenta():
    from orchestrator.mechanisms.flow import contar_repeticion

    vistos = {}
    for esperado in (1, 2, 3):
        assert contar_repeticion(vistos, "pasador||rueda", 29.9) == esperado


def test_volver_a_un_fallo_mas_grande_que_el_mejor_visto_cuenta():
    """La secuencia real del Ginebra: 29.9, 1.2, 29.9, 29.9. Tras bajar a
    1.2, volver a 29.9 no es progreso: es oscilar, y eso sí se repite."""
    from orchestrator.mechanisms.flow import contar_repeticion

    vistos = {}
    cuentas = [contar_repeticion(vistos, "h", m) for m in (29.9, 1.2, 29.9, 29.9)]
    assert cuentas == [1, 1, 2, 3]


def test_sin_tamano_se_cuenta_como_antes():
    from orchestrator.mechanisms.flow import contar_repeticion

    vistos = {}
    assert [contar_repeticion(vistos, "h", 0.0) for _ in range(3)] == [1, 2, 3]
