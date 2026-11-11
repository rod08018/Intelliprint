"""Lo que el plan prevé de tornillería, contra lo que las piezas llevan de
verdad (F9.6 (previsto)).

El pan-tilt que pasó el banco (corrida 1111-1342, 6 de 6) monta dos SG90.
Cada uno se sujeta con los dos tornillos que trae en su bolsa, uno por
oreja: cuatro en total. Su base no tiene ni un agujero debajo de las orejas
—el servo va suelto en su alojamiento— y los dos del soporte miden Ø2.2,
lo mismo que la muesca de la oreja: un tornillo de 2 mm no rosca en un
agujero de 2.2. Nadie lo vio, porque nadie había dicho cuántos tornillos
tenía que haber: la lista se deducía al final de lo que hubiera.

Cada número esperado está contado a mano en el plan de cada test o en la
ficha del SG90 (`library/components/sg90.yaml`: dos fijaciones, M2,
incluidas).
"""

import json

import pytest

from orchestrator import obra as O
from orchestrator.materiales import materiales
from orchestrator.medida import uniones_sin_hacer
from orchestrator.plan import compras_previstas, sin_hacer
from orchestrator.schemas.obra import Obra
from orchestrator.tornilleria import tornillos
from tests.test_conjunto import _obra, _sg90, _sobre
from tests.test_tornilleria import _agujero, _tuerca

CAJA = ([0, 0, 0], [40, 20, 10])


def _nodos(*piezas) -> list[dict]:
    """`piezas`: (id, depende_de, compra)."""
    nodos = [{"id": i, "nombre": i.capitalize(), "que_hace": "x", "depende_de": dep,
              "compra": compra} for i, dep, compra in piezas]
    return nodos + [{"id": "conjunto", "nombre": "El conjunto", "tipo": "conjunto",
                     "que_hace": "x", "depende_de": [i for i, _, _ in piezas]}]


def _fija(id_, cabeza, agarra, cantidad=1, agarre="tuerca", metrica="M3") -> dict:
    return {"tipo": "fija", "id": id_, "cabeza": cabeza, "agarra": agarra, "metrica": metrica,
            "cantidad": cantidad, "agarre": None if agarra == "exterior" else agarre}


def _backlog(tmp_path, piezas: dict, nodos: list, uniones: list):
    """Las piezas construidas (como `tests.test_conjunto._obra`) con su plan."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _obra(tmp_path, piezas)
    (tmp_path / "obra.json").write_text(
        json.dumps({"titulo": "t", "nodos": nodos, "uniones": uniones}), encoding="utf-8")
    return tmp_path


def _faltas(carpeta) -> list:
    obra = O.cargar_obra(carpeta)
    construidas = {p.name for p in (carpeta / "nodos").iterdir() if (p / "parts").is_dir()}
    return sin_hacer(obra, tornillos(carpeta), construidas)


# --- lo que el plan prevé --------------------------------------------------------------------

PAN_TILT = _nodos(("base", [], ["sg90"]), ("soporte", ["base"], ["sg90"]),
                  ("plataforma", ["soporte"], []))
GIROS = [{"tipo": "gira", "id": "u2", "gira": "soporte", "sobre": "base", "componente": "sg90",
          "recorrido_grados": 180, "radio_libre_mm": 30},
         {"tipo": "gira", "id": "u3", "gira": "plataforma", "sobre": "soporte",
          "componente": "sg90", "recorrido_grados": 180, "radio_libre_mm": 25}]


def test_las_compras_del_pan_tilt_salen_del_plan_y_de_la_ficha_de_cada_servo():
    """Dos M3 a la mesa, que dice el plan, y dos M2 por cada SG90, que dice
    su ficha y no el modelo: 2 SG90 × 2 orejas = 4, y vienen con el servo."""
    obra = Obra(titulo="Pan-tilt", nodos=PAN_TILT,
                uniones=[_fija("u1", "base", "exterior", 2), *GIROS])
    previstas = compras_previstas(obra)
    assert [(p.union, p.piezas, p.metrica, p.cantidad, p.termina, p.componente, p.incluido)
            for p in previstas] == [
        ("u1", ("base",), "M3", 2, "superficie", "", False),
        ("", ("base",), "M2", 2, "", "sg90", True),
        ("", ("soporte",), "M2", 2, "", "sg90", True)]
    assert sum(p.cantidad for p in previstas if p.componente == "sg90") == 4


def test_el_plan_dice_lo_que_hay_que_comprar_antes_de_aprobarlo():
    """La persona aprueba el plan sabiendo qué tornillos lleva: los dos M3
    con su tuerca entre la tapa y la base, y los que trae el servo."""
    obra = Obra(titulo="Caja", nodos=_nodos(("base", [], ["sg90"]), ("tapa", ["base"], [])),
                uniones=[_fija("u1", "tapa", "base", 2, "tuerca")])
    texto = O.presentar(obra)
    assert "## Lo que lleva de tornillería" in texto
    assert "2 tornillos M3 y 2 tuercas M3" in texto
    assert "2 tornillos M2, que vienen con el Micro servo SG90" in texto


# --- lo previsto contra lo construido --------------------------------------------------------

TAPA_Y_BASE = _nodos(("base", [], []), ("tapa", ["base"], []))
BASE_CON_TUERCA = ([], [_agujero("pasa", (10, 10, 10), metrica="M3"),
                        _tuerca("tuerca", (10, 10, 0))], CAJA)


def _tapa(*agujeros):
    return (["base"], [_sobre("base", (0, 0, -10)), *agujeros], ([0, 0, 0], [40, 20, 5]))


def test_la_tapa_y_la_base_con_su_tornillo_y_su_tuerca_no_deben_nada(tmp_path):
    """La tapa y la base de `tests/test_tornilleria.py`: un M3 que pasa por
    las dos y acaba en la tuerca cautiva de la base. El plan pide uno."""
    carpeta = _backlog(tmp_path, {"base": BASE_CON_TUERCA,
                                  "tapa": _tapa(_agujero("pasa", (10, 10, 5), metrica="M3"))},
                       TAPA_Y_BASE, [_fija("u1", "tapa", "base", 1, "tuerca")])
    assert _faltas(carpeta) == []


def test_sin_el_agujero_de_la_tapa_falta_un_tornillo_y_se_le_dice_a_la_tapa(tmp_path):
    """La base tiene su agujero y su tuerca, pero la tapa no está taladrada:
    no hay ningún tornillo que una las dos. Falta 1 de 1, y la que puede
    arreglarlo es la tapa, que se diseña después y contra la base."""
    carpeta = _backlog(tmp_path, {"base": BASE_CON_TUERCA, "tapa": _tapa()},
                       TAPA_Y_BASE, [_fija("u1", "tapa", "base", 1, "tuerca")])
    [falta] = _faltas(carpeta)
    assert (falta.previstos, falta.hechos, falta.piezas) == (1, 0, ("tapa", "base"))
    assert uniones_sin_hacer(carpeta, "base") == []
    [texto] = uniones_sin_hacer(carpeta, "tapa")
    assert "unión u1" in texto and "falta 1" in texto and "«Base»" in texto


def test_dos_previstos_y_uno_hecho_falta_uno(tmp_path):
    carpeta = _backlog(tmp_path, {"base": BASE_CON_TUERCA,
                                  "tapa": _tapa(_agujero("pasa", (10, 10, 5), metrica="M3"))},
                       TAPA_Y_BASE, [_fija("u1", "tapa", "base", 2, "tuerca")])
    [falta] = _faltas(carpeta)
    assert (falta.previstos, falta.hechos) == (2, 1)
    assert "falta 1" in uniones_sin_hacer(carpeta, "tapa")[0]


def test_un_tornillo_que_acaba_de_otra_manera_no_es_el_del_plan(tmp_path):
    """El plan aprobado dice tuerca cautiva. La base lleva un agujero ciego
    de rosca (Ø2.8, 8 de fondo) y ninguna tuerca: hay un tornillo entre las
    dos, pero no el que la persona aprobó."""
    base = ([], [_agujero("rosca", (10, 10, 10), d=2.8, metrica="M3", profundidad=8)], CAJA)
    carpeta = _backlog(tmp_path, {"base": base,
                                  "tapa": _tapa(_agujero("pasa", (10, 10, 5), metrica="M3"))},
                       TAPA_Y_BASE, [_fija("u1", "tapa", "base", 1, "tuerca")])
    [falta] = _faltas(carpeta)
    assert (falta.previstos, falta.hechos, falta.de_otra_manera) == (1, 0, {"rosca": 1})
    assert "acaba en rosca" in uniones_sin_hacer(carpeta, "tapa")[0]


def test_los_que_van_a_la_mesa_se_cuentan_en_la_pieza_que_los_lleva(tmp_path):
    """Dos M3 a la mesa en el plan y un solo pasante en la base: falta 1."""
    base = ([], [_agujero("mesa_1", (5, 5, 10), metrica="M3")], CAJA)
    carpeta = _backlog(tmp_path, {"base": base}, _nodos(("base", [], [])),
                       [_fija("u1", "base", "exterior", 2)])
    [falta] = _faltas(carpeta)
    assert (falta.previstos, falta.hechos, falta.piezas) == (2, 1, ("base",))
    [texto] = uniones_sin_hacer(carpeta, "base")
    assert "unión u1" in texto and "falta 1" in texto


def test_la_que_se_disena_antes_responde_de_su_mitad(tmp_path):
    """La base ya está construida y la tapa aún no. La base lleva los dos
    M3 de la mesa y la mitad del de la tapa: su agujero con su tuerca. Con
    eso no debe nada. Sin la tuerca, le falta su mitad de la unión u2, y es
    ahora cuando se puede arreglar: después la tapa no puede ponérsela."""
    mesa = [_agujero("mesa_1", (5, 5, 10), metrica="M3"),
            _agujero("mesa_2", (35, 5, 10), metrica="M3")]
    uniones = [_fija("u1", "base", "exterior", 2), _fija("u2", "tapa", "base", 1, "tuerca")]
    con = _backlog(tmp_path / "con", {"base": ([], [*mesa, *BASE_CON_TUERCA[1]], CAJA)},
                   TAPA_Y_BASE, uniones)
    assert uniones_sin_hacer(con, "base") == []
    sin = _backlog(tmp_path / "sin",
                   {"base": ([], [*mesa, _agujero("pasa", (10, 10, 10), metrica="M3")], CAJA)},
                   TAPA_Y_BASE, uniones)
    [texto] = uniones_sin_hacer(sin, "base")
    assert "unión u2" in texto and "tuerca" in texto and "falta 1" in texto


# --- los tornillos de lo comprado ------------------------------------------------------------

SERVO = _sg90((23.6, 6, 0))
"""Como en `tests/test_tornilleria.py`: las muescas de las orejas quedan en
(20.65, 12.2) y (49.35, 12.2), y la oreja va de z = 15.6 a 18.5."""


def _guias(d):
    return [_agujero("guia_oreja_eje", (20.65, 12.2, 15.6), d=d, profundidad=8),
            _agujero("guia_oreja_cable", (49.35, 12.2, 15.6), d=d, profundidad=8)]


def _base_con_servo(tmp_path, *agujeros):
    return _backlog(tmp_path, {"base": ([], [SERVO, *agujeros], ([0, 0, 0], [70, 34, 18.5]))},
                    _nodos(("base", [], ["sg90"])), [])


def test_un_servo_sin_agujeros_bajo_las_orejas_no_esta_sujeto(tmp_path):
    """La base de la corrida 1111-1342: coloca su SG90 y no taladra nada
    debajo de las orejas. De los 2 tornillos de la ficha, 0 hechos."""
    carpeta = _base_con_servo(tmp_path)
    [falta] = _faltas(carpeta)
    assert (falta.previstos, falta.hechos, falta.componente) == (2, 0, "sg90")
    [texto] = uniones_sin_hacer(carpeta, "base")
    assert "Micro servo SG90" in texto and "faltan 2" in texto and "agujeros()" in texto


def test_con_un_agujero_guia_bajo_cada_oreja_el_servo_queda_sujeto(tmp_path):
    assert _faltas(_base_con_servo(tmp_path, *_guias(1.7))) == []


def test_un_tornillo_de_2_no_rosca_en_un_agujero_de_2_2(tmp_path):
    """El soporte de la corrida 1111-1342: sus agujeros guía miden Ø2.2, lo
    que la muesca de la oreja. El tornillo es M2: mide 2 y pasa sin tocar."""
    carpeta = _base_con_servo(tmp_path, *_guias(2.2))
    [falta] = _faltas(carpeta)
    assert (falta.previstos, falta.hechos) == (2, 0)
    assert sorted(falta.no_roscan) == ["guia_oreja_cable", "guia_oreja_eje"]
    [texto] = uniones_sin_hacer(carpeta, "base")
    assert "Ø2.2" in texto and "no rosca" in texto


# --- lo que el rasgo guarda ------------------------------------------------------------------

def test_un_agujero_de_inserto_acaba_en_inserto_y_el_inserto_se_compra(tmp_path):
    """Con `tipo="inserto"` el kit taladra Ø4.1 y lo apunta en el rasgo. El
    plan pide inserto: el tornillo vale, y la lista de compras lleva el
    inserto, que hasta ahora no salía en ninguna parte."""
    inserto = {**_agujero("inserto", (10, 10, 10), d=4.1, metrica="M3", profundidad=6),
               "uso": "inserto"}
    carpeta = _backlog(tmp_path, {"base": ([], [inserto], CAJA),
                                  "tapa": _tapa(_agujero("pasa", (10, 10, 5), metrica="M3"))},
                       TAPA_Y_BASE, [_fija("u1", "tapa", "base", 1, "inserto")])
    [t] = tornillos(carpeta)
    assert t.termina == "inserto"
    assert _faltas(carpeta) == []
    assert {"id": "Inserto térmico M3", "nombre": "Inserto térmico M3", "cuantos": 1,
            "tipo": "tornilleria"} in materiales(carpeta)["comprado"]


def test_la_metrica_de_la_tuerca_basta_para_saber_que_tornillo_es(tmp_path):
    """Un agujero hecho con `taladrar` no dice su métrica; la tuerca que
    tiene en línea, sí."""
    base = ([], [_agujero("pasa", (10, 10, 10)), {**_tuerca("tuerca", (10, 10, 0)),
                                                  "metrica": "M3"}], CAJA)
    [t] = tornillos(_backlog(tmp_path, {"base": base}, _nodos(("base", [], [])), []))
    assert (t.metrica, t.termina) == ("M3", "tuerca")


def test_un_backlog_sin_plan_no_debe_nada(tmp_path):
    """Los de antes del 2026-11-10 no tienen uniones: nadie previó nada."""
    carpeta = _obra(tmp_path, {"base": ([], [SERVO], ([0, 0, 0], [70, 34, 18.5]))})
    assert uniones_sin_hacer(carpeta, "base") == []


@pytest.mark.parametrize("nodo, debe", [("base", True), ("otra", False)])
def test_en_el_bucle_de_la_pieza_cada_una_oye_solo_lo_suyo(tmp_path, monkeypatch, nodo, debe):
    """`defectos_de_la_pieza` sabe de qué backlog es la pieza por
    `INTELLIPRINT_UNIONES`, como con el sitio de los giros."""
    from orchestrator.medida import defectos_del_plan
    carpeta = _backlog(tmp_path, {"base": ([], [SERVO], ([0, 0, 0], [70, 34, 18.5])),
                                  "otra": (["base"], [_sobre("base", (0, 0, -20))], CAJA)},
                       _nodos(("base", [], ["sg90"]), ("otra", ["base"], [])), [])
    uniones = carpeta / "nodos" / nodo / "uniones.json"
    uniones.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("INTELLIPRINT_UNIONES", str(uniones))
    assert bool(defectos_del_plan()) is debe


def test_a_la_pieza_que_monta_un_servo_se_le_dice_con_que_se_sujeta_antes_de_dibujarla(tmp_path):
    """Que falten los tornillos se le dice al construir; que los lleva, antes:
    con las uniones del plan, al ingeniero y al diseñador. Lo que dice la
    ficha del SG90: dos M2, incluidos."""
    carpeta = _base_con_servo(tmp_path)
    O.escribir_uniones(carpeta, "base")
    texto = O.uniones_para_el_prompt(carpeta / "nodos" / "base")
    assert "Micro servo SG90" in texto and "2 tornillos M2" in texto
    assert "vienen con él" in texto and "agujeros()" in texto and "más estrecho" in texto


def test_el_plan_avisa_del_tornillo_de_un_servo_que_la_impresora_no_tiene_medido():
    """F9.8 (métricas). Los tornillos del SG90 atraviesan la oreja y roscan
    en la pieza: hace falta el agujero de un M2 de rosca, que el perfil no
    trae. Es un aviso, no un error: se arregla apuntando una medida, y hasta
    entonces el diámetro lo elige el diseñador a ojo."""
    from orchestrator.plan import validar_plan
    obra = Obra(titulo="Pan-tilt", nodos=PAN_TILT, uniones=GIROS)
    errores, avisos = validar_plan(obra, {"M3_through_mm": 3.3})
    assert errores == []
    [aviso] = [a for a in avisos if "M2_selftap_mm" in a]
    assert "«Base»" in aviso and "«Soporte»" in aviso and "«Impresora»" in aviso
    _, avisos = validar_plan(obra, {"M3_through_mm": 3.3, "M2_selftap_mm": 1.7})
    assert not [a for a in avisos if "M2" in a]
