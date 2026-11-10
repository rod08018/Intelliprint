"""La tornillería de un invento (F7.8 (inventario)): cada tornillo, de qué
largo y con qué termina.

«El ensamble debe mostrar todo lo que el BOM requiere, y en el BOM deben ir
todas las cosas que no imprimo» (el usuario, 2026-11-10). Hasta entonces la
lista decía «M3, M4» y nada más: ni cuántos, ni de qué largo, ni las tuercas.
Cada largo esperado está sumado a mano a partir de las cotas del test.
"""

import json

import pytest

from orchestrator.tornilleria import tornillos
from tests.test_conjunto import _obra, _sg90, _sobre


def _agujero(nombre, en, eje=(0, 0, -1), d=3.3, metrica=None, profundidad=None,
             avellanado=None):
    r = {"nombre": nombre, "tipo": "agujero", "diametro_mm": d, "entrada": list(en),
         "eje": list(eje), "profundidad_mm": profundidad, "lagrima": False,
         "avellanado_mm": avellanado}
    return {**r, "tornillo": metrica} if metrica else r


def _tuerca(nombre, en, eje=(0, 0, 1), profundidad=2.4):
    return {"nombre": nombre, "tipo": "tuerca", "entrecaras_mm": 5.9, "entrada": list(en),
            "eje": list(eje), "profundidad_mm": profundidad}


def _uno(lista, **donde):
    [t] = [t for t in lista if all(getattr(t, k) == v for k, v in donde.items())]
    return t


def test_el_tornillo_de_la_oreja_del_sg90_viene_con_el_servo(tmp_path):
    """Como la base del pan-tilt: el SG90 en (23.6, 6, 0) y un agujero guía
    de Ø1.7 y 8 de fondo bajo la muesca de la oreja. La muesca está en
    (-2.95, 6.2, 18.5) de la ficha: (20.65, 12.2, 18.5) en la pieza, en lo
    alto de la oreja (de 15.6 a 18.5). El tornillo va de 18.5 al fondo del
    agujero guía, 15.6 − 8 = 7.6: 10.9 mm, y rosca en el plástico."""
    carpeta = _obra(tmp_path, {"base": ([], [
        _sg90((23.6, 6, 0)),
        _agujero("guia_oreja_izquierda", (20.65, 12.2, 15.6), d=1.7, profundidad=8),
    ], ([0, 0, 0], [70, 34, 18.5]))})
    t = _uno(tornillos(carpeta), pieza="base")
    assert t.metrica == "M2"
    assert t.largo_mm == pytest.approx(10.9)
    assert t.termina == "rosca"
    assert "SG90" in t.viene_con
    assert t.cabeza == pytest.approx([20.65, 12.2, 18.5])
    assert t.eje == pytest.approx([0, 0, -1])


def test_un_tornillo_que_une_dos_piezas_cuenta_una_vez_y_llega_a_su_tuerca(tmp_path):
    """La tapa (5 de grueso) va sobre la base (10), con un M3 que pasa por
    las dos y una tuerca cautiva abajo, en la base. De la cabeza (z = 15 en
    la base) a la cara de abajo (z = 0) hay 15 mm; con tuerca el tornillo
    tiene que llegar, así que va el de catálogo de encima: M3 × 16."""
    carpeta = _obra(tmp_path, {
        "base": ([], [_agujero("pasa", (10, 10, 10), metrica="M3"),
                      _tuerca("tuerca", (10, 10, 0))], ([0, 0, 0], [40, 20, 10])),
        "tapa": (["base"], [_sobre("base", (0, 0, -10)),
                            _agujero("pasa", (10, 10, 5), metrica="M3")],
                 ([0, 0, 0], [40, 20, 5])),
    })
    [t] = tornillos(carpeta)
    assert (t.metrica, t.largo_mm, t.largo, t.termina) == ("M3", pytest.approx(15), 16, "tuerca")
    assert t.pieza == "tapa"                     # la cabeza apoya en la tapa
    assert t.cabeza == pytest.approx([10, 10, 5])
    assert [(n["pieza"], n["en"]) for n in t.tuercas] == [("base", pytest.approx([10, 10, 0]))]


def test_el_que_atraviesa_y_no_llega_a_nada_depende_de_donde_se_fije(tmp_path):
    """Los dos M4 avellanados de la base del pan-tilt la fijan a la mesa:
    la pieza da 18.5 mm y el resto depende de la mesa. No se inventa."""
    carpeta = _obra(tmp_path, {"base": ([], [
        _agujero("fijacion_1", (8, 28, 18.5), d=4.5, metrica="M4", avellanado=8),
    ], ([0, 0, 0], [70, 34, 18.5]))})
    [t] = tornillos(carpeta)
    assert (t.termina, t.largo, t.largo_mm, t.avellanado) == (
        "superficie", None, pytest.approx(18.5), 8)


def _caja_stl(a, b) -> str:
    (x0, y0, z0), (x1, y1, z1) = a, b
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    caras = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = [t for p, q, r, s in caras for t in ((p, q, r), (p, r, s))]
    return "".join("facet normal 0 0 0\nouter loop\n" + "".join(
        f"vertex {v[i][0]} {v[i][1]} {v[i][2]}\n" for i in t) + "endloop\nendfacet\n"
        for t in tris)


def test_lo_que_atraviesa_se_mide_en_la_malla_y_no_en_la_caja(tmp_path):
    """Una escuadra: ala de 40 × 20 × 3 y pared de 3 de grueso y 30 de alto.
    Un M3 que cruza la pared en horizontal atraviesa 3 mm; la caja de la
    pieza diría 40."""
    parte = tmp_path / "parts" / "escuadra"
    parte.mkdir(parents=True)
    (parte / "escuadra.stl").write_text(
        "solid e\n" + _caja_stl((0, 0, 0), (40, 20, 3)) + _caja_stl((0, 0, 3), (3, 20, 30))
        + "endsolid e\n", encoding="utf-8")
    (parte / "envolvente.json").write_text(json.dumps({"min": [0, 0, 0], "max": [40, 20, 30]}),
                                           encoding="utf-8")
    (parte / "rasgos.json").write_text(json.dumps([
        _agujero("pared", (0, 10, 15), eje=(1, 0, 0), metrica="M3")]), encoding="utf-8")
    [t] = tornillos(tmp_path)
    assert t.largo_mm == pytest.approx(3, abs=0.01)


def test_contra_el_perfil_va_a_su_tuerca_en_t_en_cualquier_punto_de_la_ranura(tmp_path):
    """El soporte del MG996R sobre un perfil 2020 (banco 1109-1949): el
    perfil colocado en z = −10 deja su cara de arriba en z = 0, y la pieza,
    de 6 de grueso, tiene dos M5 en x = ±10. La ficha marca el tornillo en
    x = 0, pero puede ir en cualquier punto de la ranura. Cada uno cruza 6
    de pieza y entra 6 en la ranura, donde está la tuerca en T: M5 × 12."""
    parte = tmp_path / "parts" / "soporte"
    parte.mkdir(parents=True)
    (parte / "envolvente.json").write_text(json.dumps({"min": [-30, -10, 0], "max": [30, 40, 6]}),
                                           encoding="utf-8")
    (parte / "rasgos.json").write_text(json.dumps([
        {"nombre": "perfil-2020", "tipo": "componente", "ficha": "perfil-2020",
         "en": [0.0, 0.0, -10.0], "giros": []},
        _agujero("perfil_1", (-10, 0, 6), d=5.5, metrica="M5"),
        _agujero("perfil_2", (10, 0, 6), d=5.5, metrica="M5"),
    ]), encoding="utf-8")
    ts = tornillos(tmp_path)
    assert [(t.metrica, t.largo, t.termina) for t in ts] == [("M5", 12, "componente")] * 2
    assert all(t.compra_aparte == "Tuerca en T M5 (ranura de 6)" for t in ts)


def test_un_agujero_sin_metrica_ni_ficha_no_es_un_tornillo(tmp_path):
    """El hueco de Ø8 del cuerno del soporte de giro deja pasar el cubo del
    cuerno: no lleva tornillo, y nadie lo dice."""
    carpeta = _obra(tmp_path, {"soporte": ([], [
        _agujero("hueco_central", (0, 0, -1), eje=(0, 0, 1), d=8)], ([-28, -17, 0], [28, 17, 31]))})
    assert tornillos(carpeta) == []
