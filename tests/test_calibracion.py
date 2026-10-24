"""Pieza de calibración de holguras (F2.18 (calibración)).

Las holguras de config/printers/ son valores por defecto de una boquilla de
0.4, no medidas: `M3_through_mm: 3.3` es casi un ajuste justo y nadie lo
ha comprobado imprimiendo (deuda F2.18 (calibración)). El usuario calibró el LAMINADO
de su M5 (2026-10-24), no esto. Esta pieza lo mide: un peine de agujeros,
un eje de referencia y una placa de agujeros M3. El usuario la imprime,
prueba y apunta qué encajó; solo entonces cambian los valores.

Las cotas esperadas salen del criterio del plan (holguras de 0.0 a 0.5 mm)
y de cálculos a mano, no del generador.
"""

import math
import shutil
from pathlib import Path

import pytest
import yaml

from mech_toolkit.generators import CATALOGO
from mech_toolkit.profile import PrinterProfile
from orchestrator.calibracion import (
    CalibracionInvalida, aplicar_resultados, cuadro, recetas)
from orchestrator.schemas.recipe import Recipe

YAML = Path("config/printers/ankermake_m5_plamas.yaml")


def _diametros(receta: Recipe) -> list[float]:
    return [p.params["diameter_mm"] for p in receta.steps if p.generator == "generate_hole"]


def test_el_peine_tiene_las_holguras_del_plan_sobre_el_eje_de_5_mm():
    piezas = {r.part: r for r in recetas()}

    assert _diametros(piezas["calibracion_agujeros"]) == pytest.approx(
        [5.0, 5.1, 5.2, 5.3, 5.4, 5.5])
    eje = [p for p in piezas["calibracion_eje"].steps if p.generator == "generate_cylinder"]
    assert [p.params["diameter_mm"] for p in eje] == [5.0]


def test_la_placa_m3_cubre_rosca_directa_pasante_e_inserto():
    """De 2.6 a 3.6 cubre rosca directa (2.8 hoy) y pasante (3.3 hoy, ISO
    normal 3.4); de 3.8 a 4.4, el inserto térmico (4.1 hoy)."""
    m3 = {r.part: r for r in recetas()}["calibracion_m3"]

    assert _diametros(m3) == pytest.approx(
        [2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6,
         3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4])


def test_cada_receta_la_acepta_el_catalogo():
    for receta in recetas():
        receta.validate_against(CATALOGO)


def test_los_agujeros_van_de_menor_a_mayor_desde_la_muesca():
    """Sin generador de texto no hay números grabados: el orden y la muesca
    son lo único que dice qué agujero es cuál."""
    for receta in recetas():
        agujeros = [p.params for p in receta.steps if p.generator == "generate_hole"]
        if not agujeros:
            continue
        muesca = next(p.params for p in receta.steps if p.generator == "generate_cut_box")
        for fila in {round(a["y_mm"], 3) for a in agujeros}:
            de_la_fila = sorted((a for a in agujeros if round(a["y_mm"], 3) == fila),
                                key=lambda a: a["x_mm"])
            assert [a["diameter_mm"] for a in de_la_fila] == sorted(
                a["diameter_mm"] for a in de_la_fila)
        assert muesca["x_mm"] < min(a["x_mm"] for a in agujeros)


def test_el_cuadro_dice_que_diametro_tiene_cada_posicion():
    texto = cuadro()
    assert "5.30" in texto and "3.40" in texto and "4.10" in texto
    assert "intelliprint calibrar resultados" in texto


def _freecadcmd():
    import os
    return os.environ.get("FREECADCMD") or shutil.which("freecadcmd")


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_peine_construido_tiene_el_volumen_calculado_a_mano(tmp_path):
    """Placa menos seis agujeros pasantes menos la muesca. Si un agujero no
    atravesara o se saliera de la placa, el volumen no cuadraría."""
    from orchestrator.build import build_part

    receta = {r.part: r for r in recetas()}["calibracion_agujeros"]
    placa = next(p.params for p in receta.steps if p.generator == "generate_box")
    muesca = next(p.params for p in receta.steps if p.generator == "generate_cut_box")
    esperado = (placa["length_mm"] * placa["width_mm"] * placa["height_mm"]
                - sum(math.pi * (d / 2) ** 2 * placa["height_mm"] for d in _diametros(receta))
                - muesca["length_mm"] * muesca["width_mm"] * placa["height_mm"])

    r = build_part(receta, CATALOGO, tmp_path / receta.part, _freecadcmd())

    assert r.solids == 1
    assert r.volume_mm3 == pytest.approx(esperado, rel=0.002)
    assert (tmp_path / receta.part / f"{receta.part}.stl").is_file()


# --- Los resultados: el ÚNICO camino por el que cambian las holguras --------


@pytest.fixture
def perfil(tmp_path):
    copia = tmp_path / "m5.yaml"
    shutil.copy(YAML, copia)
    return copia


def _cargar(ruta):
    return PrinterProfile(**yaml.safe_load(ruta.read_text(encoding="utf-8")))


def test_los_resultados_se_escriben_y_el_perfil_queda_calibrado(perfil):
    aplicar_resultados(perfil, press_mm=0.1, slide_mm=0.3, clearance_mm=0.4,
                       m3_through_mm=3.4, m3_selftap_mm=2.8, m3_insert_mm=4.0,
                       fecha="2026-10-30")

    p = _cargar(perfil)
    assert (p.fit_mm("press"), p.fit_mm("slide"), p.fit_mm("clearance")) == (0.1, 0.3, 0.4)
    assert (p.hole_mm("M3_through"), p.hole_mm("M3_selftap"), p.hole_mm("M3_insert")) == (
        3.4, 2.8, 4.0)
    assert p.calibrated is True
    texto = perfil.read_text(encoding="utf-8")
    assert "2026-10-30" in texto
    # Lo demás del archivo, comentarios incluidos, no se toca.
    assert "M3_nut_af_mm: 5.9" in texto and "overhang_max_deg: 45" in texto


@pytest.mark.parametrize("cambio, motivo", [
    (dict(press_mm=0.25), "peine"),             # no hay agujero de 5.25
    (dict(m3_through_mm=3.7), "placa"),          # no hay agujero de 3.7
    (dict(press_mm=0.3, slide_mm=0.2), "press"),  # a presión no puede ser más holgado
    (dict(m3_selftap_mm=3.4, m3_through_mm=3.3), "rosca"),
])
def test_unos_resultados_imposibles_no_tocan_el_perfil(perfil, cambio, motivo):
    antes = perfil.read_text(encoding="utf-8")
    valores = dict(press_mm=0.1, slide_mm=0.2, clearance_mm=0.4, m3_through_mm=3.4,
                   m3_selftap_mm=2.8, m3_insert_mm=4.1) | cambio

    with pytest.raises(CalibracionInvalida, match=motivo):
        aplicar_resultados(perfil, **valores, fecha="2026-10-30")

    assert perfil.read_text(encoding="utf-8") == antes


# --- La orden -----------------------------------------------------------------


def test_la_orden_de_resultados_pide_los_seis_valores():
    from orchestrator.cli import _parser

    args = _parser().parse_args(
        ["calibrar", "resultados", "--press", "0.1", "--slide", "0.2", "--clearance", "0.3",
         "--m3-through", "3.4", "--m3-selftap", "2.8", "--m3-insert", "4.1"])

    assert (args.press, args.slide, args.clearance) == (0.1, 0.2, 0.3)
    assert (args.m3_through, args.m3_selftap, args.m3_insert) == (3.4, 2.8, 4.1)
    with pytest.raises(SystemExit):
        _parser().parse_args(["calibrar", "resultados", "--press", "0.1"])


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_la_orden_de_la_pieza_deja_un_proyecto_que_la_web_puede_abrir(tmp_path):
    """Con request.md, sus tres STL en parts/ y el cuadro para probarla: la
    web lo lista como cualquier proyecto y el botón lo abre en PrusaSlicer."""
    import argparse

    from orchestrator.cli import _calibrar
    from orchestrator.web.app import piezas_de

    _calibrar(argparse.Namespace(accion="pieza"), Path("."),
              {"INTELLIPRINT_WORKSPACE": str(tmp_path), "FREECADCMD": _freecadcmd()}, "Crafty")

    (carpeta,) = (tmp_path / "projects").iterdir()
    assert carpeta.name.endswith("-calibracion_holguras")
    assert [p.stem for p in piezas_de(carpeta)] == [
        "calibracion_agujeros", "calibracion_eje", "calibracion_m3"]
    assert "Posición" in (carpeta / "calibracion.md").read_text(encoding="utf-8")
    assert (carpeta / "request.md").is_file()
