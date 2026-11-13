"""Las piezas de prueba de las transmisiones (F10.8 (calibrar), ADR-021).

Si los dientes engranan no lo dice el código: lo dice una pieza impresa.
La cicloidal lleva 0,15 mm de holgura porque es un número razonable, no
porque nadie lo haya medido en la impresora del usuario. Él imprime la
carcasa, la excéntrica y cuatro discos con holguras distintas, mira con
cuál gira sin atascarse ni bailar, y lo apunta en «Impresora», como el M3.
Desde entonces la reductora se hace con ese número.

Lo esperado sale de lo que se apunta y del archivo de `config/printers/`,
que no puede cambiar.
"""

import hashlib
from pathlib import Path

import pytest

from orchestrator.impresion import perfil_activo
from orchestrator.medidas_impresora import MedidaInvalida, registrar

RAIZ = Path(".")
PERFIL = "ankermake_m5_plamas"
YAML = RAIZ / "config" / "printers" / f"{PERFIL}.yaml"


def test_la_holgura_apuntada_la_devuelve_el_perfil_y_config_no_se_toca(tmp_path):
    antes = hashlib.sha256(YAML.read_bytes()).hexdigest()
    assert "transmision_mm" not in perfil_activo(RAIZ).datos["fits"]

    registrar(tmp_path, PERFIL, "transmision", {"holgura_mm": "0.2"}, fotos=[],
              fecha="2026-11-13")

    medido = perfil_activo(RAIZ, workspace=tmp_path)
    assert medido.datos["fits"]["transmision_mm"] == 0.2
    assert medido.medido["fits.transmision_mm"]["fecha"] == "2026-11-13"
    assert "transmision_mm" not in perfil_activo(RAIZ).datos["fits"]
    assert hashlib.sha256(YAML.read_bytes()).hexdigest() == antes


@pytest.mark.parametrize("valor", [0, 0.6, "mucho"])
def test_una_holgura_que_no_puede_ser_no_se_apunta(tmp_path, valor):
    """Las piezas de prueba van de 0,10 a 0,25: fuera de 0,05 a 0,5 no es
    algo que haya podido salir de ellas."""
    with pytest.raises(MedidaInvalida):
        registrar(tmp_path, PERFIL, "transmision", {"holgura_mm": valor}, fotos=[])


def test_la_reductora_se_hace_con_la_holgura_medida():
    """Con 0,25 mm, el agujero del disco para la leva de Ø12 mide 12,5; con
    la de fábrica (0,15), 12,3."""
    from orchestrator import modulos
    de_fabrica = modulos.cargar("cicloidal-nema17-10")
    medida = modulos.cargar("cicloidal-nema17-10", holgura=0.25)
    assert '"leva", 12.3,' in de_fabrica.piezas["disco"]
    assert '"leva", 12.5,' in medida.piezas["disco"]
    assert medida.piezas["carcasa"] == de_fabrica.piezas["carcasa"]
    assert modulos.holgura_medida({"fits": {"transmision_mm": 0.25}}) == 0.25
    assert modulos.holgura_medida({"fits": {"slide_mm": 0.2}}) is None


def test_las_piezas_de_prueba_son_la_reductora_con_cuatro_discos():
    """La carcasa y la excéntrica de la 10:1 de verdad, sus cuatro discos de
    0,10 a 0,25 —lo que se apunte vale tal cual para la reductora— y una
    polea de 40 dientes para probar cómo asienta la correa."""
    from orchestrator.calibracion import piezas_de_transmision
    piezas = piezas_de_transmision()
    assert list(piezas) == ["carcasa", "excentrica", "disco_010", "disco_015", "disco_020",
                            "disco_025", "polea_40"]
    for nombre, agujero in (("disco_010", "12.2"), ("disco_015", "12.3"),
                            ("disco_020", "12.4"), ("disco_025", "12.5")):
        assert f'"leva", {agujero},' in piezas[nombre]
    assert 'kit.polea_gt2("polea", 40' in piezas["polea_40"]


def test_un_plan_con_transmision_avisa_si_la_holgura_no_esta_medida():
    """«Hasta entonces, la holgura es la del perfil y el invento lo avisa.»"""
    from orchestrator.plan import validar_plan
    from orchestrator.schemas.obra import Obra
    from tests.test_plan_mecanico import AGUJEROS
    from tests.test_plan_mecanico import PLAN as PAN_TILT
    from tests.test_transmision import PLAN
    _, avisos = validar_plan(Obra(**PLAN), AGUJEROS, ajustes={"slide_mm": 0.2})
    [aviso] = [a for a in avisos if "transmis" in a]
    assert "Impresora" in aviso and "calibrar transmision" in aviso
    # Medida, ya no avisa; y sin transmisión no hay nada que avisar.
    assert not [a for a in validar_plan(Obra(**PLAN), AGUJEROS,
                                        ajustes={"transmision_mm": 0.2})[1] if "transmis" in a]
    assert not [a for a in validar_plan(Obra(**PAN_TILT), AGUJEROS, ajustes={})[1]
                if "transmis" in a]
    # Quien no sabe el perfil no avisa de lo que no sabe.
    assert not [a for a in validar_plan(Obra(**PLAN), AGUJEROS)[1] if "transmis" in a]


def test_desde_la_pagina_se_apunta_la_holgura_de_las_transmisiones(tmp_path):
    from tests.test_impresora_medidas import _web
    web = _web(tmp_path)
    assert 'data-tipo="transmision"' in web.get("/impresora").text
    r = web.post("/api/impresora/medidas", json={
        "tipo": "transmision", "valores": {"holgura_mm": "0.2"}, "fotos": []})
    assert r.status_code == 200, r.text
    assert perfil_activo(RAIZ, workspace=tmp_path).datos["fits"]["transmision_mm"] == 0.2
