"""Cálculo de resistencia en código (F3.19 (resistencia)).

`payload_g` se pedía y nadie lo usaba: la escuadra de repisa «para 5 kg»
salía con el espesor que se le ocurría al modelo. La cuenta no la hace el
modelo —se equivoca en las potencias y en las unidades— sino el código, y
el modelo solo decide el caso de carga.

Los valores esperados están hechos a mano:
    F = 5 kg · 9.81 = 49.05 N;   M = F · 100 mm = 4905 N·mm
    W = b·h²/6 = 20·5²/6 = 83.33 mm³;   σ = M / W = 58.86 MPa
    canto para un factor 3 con 35 MPa: h = √(6·M·3 / (b·35)) = √126.13 = 11.23 mm
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from orchestrator.impresion import perfil_activo
from orchestrator.ingenieria import CasoDeCarga, Material, comprobar

PLA = Material(xy_MPa=35, z_MPa=15, factor_seguridad=3)
BRAZO = dict(que="brazo de la escuadra", carga_kg=5, brazo_mm=100, ancho_mm=20, canto_mm=5)


def test_tension_de_un_voladizo_con_la_carga_en_la_punta():
    c = comprobar(CasoDeCarga(**BRAZO, capas_a_traccion=False), PLA)
    assert c.tension_MPa == pytest.approx(58.86, abs=0.01)
    assert c.factor_seguridad == pytest.approx(35 / 58.86, abs=0.001)
    assert not c.cumple


def test_dice_el_canto_que_haria_falta():
    """Es lo que vuelve al ingeniero: no «no aguanta», sino cuánto falta."""
    c = comprobar(CasoDeCarga(**BRAZO, capas_a_traccion=False), PLA)
    assert c.canto_minimo_mm == pytest.approx(11.23, abs=0.01)


def test_con_las_capas_a_traccion_vale_la_resistencia_entre_capas():
    """Una pieza FDM se rompe entre capas a una fracción de lo que aguanta
    a lo largo del filamento: orientar mal es perder dos tercios."""
    tumbada = comprobar(CasoDeCarga(**BRAZO, capas_a_traccion=False), PLA)
    de_pie = comprobar(CasoDeCarga(**BRAZO, capas_a_traccion=True), PLA)
    assert de_pie.resistencia_MPa == 15
    assert de_pie.factor_seguridad == pytest.approx(tumbada.factor_seguridad * 15 / 35)


def test_una_seccion_suficiente_cumple():
    c = comprobar(CasoDeCarga(**{**BRAZO, "canto_mm": 12}, capas_a_traccion=False), PLA)
    assert c.cumple and c.factor_seguridad >= 3


def test_un_caso_sin_carga_no_es_un_caso():
    with pytest.raises(ValidationError):
        CasoDeCarga(**{**BRAZO, "carga_kg": 0}, capas_a_traccion=False)


def test_el_perfil_activo_trae_la_resistencia_de_su_material():
    """Sin esto el cálculo usaría un número escrito en el código, y al
    cambiar de PETG a PLA+ (2026-10-24) nadie se acordaría de él."""
    activo = perfil_activo(Path("."))
    m = Material.del_perfil(activo.datos)
    assert 0 < m.z_MPa < m.xy_MPa
    assert m.factor_seguridad >= 2
