"""Lo que la interfaz cuenta de cada proyecto, sacado de su carpeta
(F5.5 (web)).

Se prueba contra una carpeta armada a mano con la forma que dejan el flujo
y el presupuesto: es la frontera real, y no hace falta un modelo ni FreeCAD.
"""

import json

import pytest

from orchestrator.web.estadisticas import estadisticas


def _json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def _req(desc, cumple, medido=90.0):
    return {"descripcion": desc, "esperado": 90, "tolerancia": 1, "medido": medido,
            "desviacion": medido - 90, "cumple": cumple}


@pytest.fixture
def proyecto(tmp_path):
    p = tmp_path / "2026-09-21-trinquete"
    _json(p / "rondas" / "1" / "resultado.json", {
        "ronda": 1, "titulo": "Trinquete", "plan": None, "resuelta": False,
        "feedback": "- la uña no toca la rueda", "barrido": None,
        "requisitos": [_req("avanza un diente", False, 0.0), _req("bloquea", True)]})
    _json(p / "rondas" / "2" / "resultado.json", {
        "ronda": 2, "titulo": "Trinquete", "resuelta": False,
        "plan": {"causa": "uña mal orientada", "cambio": "giro la uña", "espera": "que toque"},
        "feedback": "- choca", "barrido": {"choques": 2, "posiciones": 36},
        "requisitos": [_req("avanza un diente", True, 30.4), _req("bloquea", True)]})
    # La ronda 3 está EN CURSO: tiene especificación y aún no resultado.
    _json(p / "rondas" / "3" / "mechanism.json", {"title": "Trinquete"})
    _json(p / "design_cost.json", {
        "resumen": {"total_usd": 0.2976, "limite_usd": 2.0, "llamadas": 23,
                    "tokens_entrada": 54003, "tokens_salida": 234478},
        "detalle": [{"etapa": "ronda 3 · diseño del mecanismo"},
                    {"etapa": "ronda 3 · pieza «wheel»"}]})
    return p


def test_la_ronda_en_curso_es_la_ultima_carpeta_aunque_no_haya_terminado(proyecto):
    assert estadisticas(proyecto)["ronda"] == 3


def test_lo_ultimo_que_hizo_sale_de_la_ultima_llamada(proyecto):
    assert estadisticas(proyecto)["ultima_etapa"] == "ronda 3 · pieza «wheel»"


def test_el_coste_se_da_contra_su_tope(proyecto):
    coste = estadisticas(proyecto)["coste"]
    assert coste == {"usd": 0.2976, "tope_usd": 2.0, "fraccion": pytest.approx(0.1488),
                     "tokens_salida": 234478, "llamadas": 23}


def test_los_requisitos_son_los_de_la_ultima_ronda_que_los_midio(proyecto):
    """La ronda 3 aún no ha medido nada: se enseña la 2, y se dice que es
    de la 2."""
    req = estadisticas(proyecto)["requisitos"]
    assert req["de_la_ronda"] == 2
    assert (req["cumplen"], req["total"]) == (2, 2)


def test_un_requisito_que_no_se_pudo_medir_no_cuenta_como_cumplido(proyecto):
    _json(proyecto / "rondas" / "2" / "resultado.json", {
        "ronda": 2, "titulo": "t", "resuelta": False, "feedback": "x",
        "requisitos": [_req("avanza", True), {**_req("bloquea", None), "medido": None}]})
    req = estadisticas(proyecto)["requisitos"]
    assert (req["cumplen"], req["sin_medir"], req["total"]) == (1, 1, 2)


def test_la_historia_lleva_cada_ronda_con_su_plan_y_lo_que_volvio(proyecto):
    historia = estadisticas(proyecto, en_marcha=True)["rondas"]
    assert [r["ronda"] for r in historia] == [1, 2, 3]
    assert historia[1]["plan"]["cambio"] == "giro la uña"
    assert historia[1]["feedback"] == "- choca"
    assert historia[2]["en_curso"] is True


def test_el_revisor_se_cuenta_por_veredicto(proyecto):
    _json(proyecto / "review.json", {"summary": "s", "items": [
        {"requirement": "a", "verdict": "cumple", "comment": ""},
        {"requirement": "b", "verdict": "no_verificable", "comment": ""},
        {"requirement": "c", "verdict": "no_verificable", "comment": ""}]})
    assert estadisticas(proyecto)["revisor"] == {"cumple": 1, "no_cumple": 0, "no_verificable": 2}


def test_un_proyecto_antiguo_sin_nada_de_esto_no_rompe(tmp_path):
    """Los proyectos anteriores a esto no tienen rondas/ ni review.json."""
    viejo = tmp_path / "2026-09-01-leva"
    viejo.mkdir()
    e = estadisticas(viejo)
    assert e["ronda"] == 0 and e["rondas"] == [] and e["requisitos"] is None
    assert e["coste"] is None and e["revisor"] is None


def test_solo_la_ultima_ronda_puede_estar_en_curso(tmp_path):
    """Un proyecto lanzado antes de que existiera resultado.json tiene rondas
    sin él. Pintarlas todas «en curso» sería falso: solo la última puede
    estarlo, y solo si el proyecto sigue trabajando."""
    p = tmp_path / "p"
    for n in (1, 2, 3):
        _json(p / "rondas" / str(n) / "mechanism.json", {"title": f"t{n}"})
    vivas = estadisticas(p, en_marcha=True)["rondas"]
    assert [r["en_curso"] for r in vivas] == [False, False, True]
    assert vivas[0]["sin_datos"] is True
    assert [r["en_curso"] for r in estadisticas(p, en_marcha=False)["rondas"]] == [False] * 3


# --- Que «2/2» no parezca «terminado» -----------------------------------------
#
# Fallo real, el quinto trinquete del 2026-09-21: la columna decía 2/2 y el
# proyecto seguía en la ronda 9. Los requisitos son solo una de las cosas
# que tienen que cumplirse (piezas, ejes, apoyos, choques, contactos, topes,
# bloqueos, revisor), y la fila no decía qué faltaba. Peor: en las rondas 2
# y 3 el 2/2 se midió sin haber resuelto los apoyos, en una posición que
# nadie comprobó.


def _ronda(p, n, requisitos, barrido, feedback):
    _json(p / "rondas" / str(n) / "resultado.json", {
        "ronda": n, "titulo": "t", "resuelta": not feedback, "feedback": feedback,
        "barrido": barrido, "requisitos": requisitos})


def test_la_fila_dice_que_fallo_en_la_ultima_ronda(tmp_path):
    p = tmp_path / "p"
    _ronda(p, 1, [_req("a", True)], {"choques": 1},
           "- palanca / rueda: se separan 1.10 mm; tienen que seguir en contacto\n- otra cosa")
    e = estadisticas(p)
    assert e["fallo"].startswith("palanca / rueda: se separan 1.10 mm")
    assert e["fallos"] == 2


def test_una_ronda_resuelta_no_tiene_fallo(tmp_path):
    p = tmp_path / "p"
    _ronda(p, 1, [_req("a", True)], {"choques": 0}, "")
    assert estadisticas(p)["fallo"] is None


def test_los_requisitos_de_una_ronda_que_no_llego_al_barrido_son_provisionales(tmp_path):
    p = tmp_path / "p"
    _ronda(p, 1, [_req("a", True), _req("b", True)], None, "- la uña empieza dentro de la rueda")
    req = estadisticas(p)["requisitos"]
    assert req["provisional"] is True


def test_se_prefieren_los_requisitos_de_la_ultima_ronda_que_llego_al_final(tmp_path):
    p = tmp_path / "p"
    _ronda(p, 1, [_req("a", True), _req("b", False, 0.0)], {"choques": 2}, "- choca")
    _ronda(p, 2, [_req("a", True), _req("b", True)], None, "- la uña no llega")
    req = estadisticas(p)["requisitos"]
    assert req["de_la_ronda"] == 1 and req["provisional"] is False
    assert (req["cumplen"], req["total"]) == (1, 2)
