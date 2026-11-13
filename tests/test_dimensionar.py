"""Que el motor alcance antes de dibujar (F10.4 (dimensionar), ADR-021).

De la carga y de lo que mide el brazo, el código calcula el par que la
gravedad le pide a cada giro con el brazo estirado en horizontal, y lo
compara con lo que da su motor. Si no alcanza, el plan vuelve al
desglosador con las dos cifras antes de gastar en ninguna pieza.

Las cuentas de cada test están hechas a mano, en gramos por milímetro:
1 kgf·cm son 10 000 g·mm, y el SG90 da 1,8 kgf·cm (su hoja), de los que se
le pide como mucho la mitad: 9 000 g·mm, 0,0883 N·m. Lo impreso se estima
en 0,2 g por milímetro de brazo (`dimensionar.GRAMOS_POR_MM`): los dos
tramos del brazo del banco 1112-0318 pesan 21,8 g en 120 mm, 0,18 g/mm.
"""

import copy

import pytest

from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra
from tests.test_plan_mecanico import AGUJEROS

G = 9.80665

UN_TRAMO = {
    "titulo": "Brazo de un tramo",
    "carga_g": 30,
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "aloja el servo", "compra": ["sg90"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "levanta la carga", "depende_de": ["base"]},
        {"id": "todo", "nombre": "El brazo", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "brazo"]},
    ],
    "uniones": [
        {"tipo": "gira", "id": "u1", "gira": "brazo", "sobre": "base", "componente": "sg90",
         "recorrido_grados": 180, "radio_libre_mm": 305, "eje": "horizontal", "brazo_mm": 300},
    ],
}

DOS_TRAMOS = {
    "titulo": "Brazo de dos tramos",
    "carga_g": 30,
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "aloja el servo del hombro",
         "compra": ["sg90"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "primer tramo; aloja el servo del codo",
         "compra": ["sg90"], "depende_de": ["base"]},
        {"id": "antebrazo", "nombre": "Antebrazo", "que_hace": "segundo tramo",
         "depende_de": ["brazo"]},
        {"id": "todo", "nombre": "El brazo", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "brazo", "antebrazo"]},
    ],
    "uniones": [
        {"tipo": "gira", "id": "u1", "gira": "brazo", "sobre": "base", "componente": "sg90",
         "recorrido_grados": 180, "radio_libre_mm": 245, "eje": "horizontal", "brazo_mm": 240},
        {"tipo": "gira", "id": "u2", "gira": "antebrazo", "sobre": "brazo", "componente": "sg90",
         "recorrido_grados": 180, "radio_libre_mm": 125, "eje": "horizontal", "brazo_mm": 120},
    ],
}


def _errores(plan) -> list[str]:
    # Con el M2 de los SG90 en el perfil, para que solo hable el dimensionado.
    return validar_plan(Obra(**plan), {**AGUJEROS, "M2_selftap_mm": 1.7})[0]


def test_un_sg90_no_puede_con_el_hombro_de_un_brazo_de_300_mm():
    """30 g a 300 mm: 9 000 g·mm. El tramo, 0,2 × 300 = 60 g con el centro a
    150: otros 9 000. Pide 18 000 g·mm, 0,1765 N·m: todo el par de bloqueo
    del SG90, y se le deja la mitad, 0,0883."""
    from orchestrator.dimensionar import pares
    [p] = pares(Obra(**UN_TRAMO))
    assert p["pide_Nm"] == pytest.approx(18000e-6 * G) == pytest.approx(0.17652, abs=1e-5)
    assert p["da_Nm"] == pytest.approx(9000e-6 * G)
    [error] = _errores(UN_TRAMO)
    assert "u1" in error and "0.177" in error and "0.088" in error
    assert "300 mm" in error and "30 g" in error


def test_un_brazo_de_dos_tramos_calculado_a_mano():
    """Codo, a 120 mm de la punta: la carga, 30 × 120 = 3 600; su tramo,
    24 g a 60, 1 440. Pide 5 040 g·mm (0,0494 N·m) de 9 000: alcanza.

    Hombro, a 240: la carga, 30 × 240 = 7 200; su tramo (los 120 mm hasta el
    codo), 24 g a 60, 1 440; el servo del codo, 9 g a 120, 1 080; el tramo
    del codo, 24 g a 120 + 60 = 180, 4 320. Pide 14 040 g·mm (0,1377 N·m)
    de 9 000: no alcanza. El error es solo del hombro."""
    from orchestrator.dimensionar import pares
    hombro, codo = pares(Obra(**DOS_TRAMOS))
    assert codo["pide_Nm"] == pytest.approx(5040e-6 * G)
    assert hombro["pide_Nm"] == pytest.approx(14040e-6 * G)
    [error] = _errores(DOS_TRAMOS)
    assert "u1" in error and "u2" not in error


def test_con_un_nema17_y_correa_el_hombro_alcanza():
    """El mismo hombro sobre un 608ZZ, movido por el NEMA 17 con correa 4:1:
    0,400 × 4 × 0,9 = 1,44 N·m, la mitad 0,72; pide 0,1377 más el servo del
    codo, que ya estaba contado. Sin errores."""
    plan = copy.deepcopy(DOS_TRAMOS)
    plan["nodos"][0]["compra"] = ["608zz", "nema17"]
    plan["uniones"][0].update(componente="608zz", movido_por={
        "motor": "nema17", "tipo": "correa", "relacion": 4})
    del plan["uniones"][0]["radio_libre_mm"]
    assert _errores(plan) == []


def test_un_eje_vertical_no_carga_peso():
    """Un plato que gira sobre un eje vertical no levanta nada: la gravedad
    no le pide par, mida lo que mida lo que lleva encima."""
    plan = copy.deepcopy(UN_TRAMO)
    plan["uniones"][0]["eje"] = "vertical"
    assert _errores(plan) == []


@pytest.mark.parametrize("quitar", ["carga_g", "brazo_mm"])
def test_sin_carga_o_sin_largo_no_hay_nada_que_comprobar(quitar):
    """Los planes de antes no los traen, y siguen valiendo."""
    plan = copy.deepcopy(UN_TRAMO)
    if quitar == "carga_g":
        del plan["carga_g"]
    else:
        del plan["uniones"][0]["brazo_mm"]
    assert _errores(plan) == []


def test_la_carga_y_el_largo_son_positivos():
    for donde, clave in ((lambda p: p, "carga_g"), (lambda p: p["uniones"][0], "brazo_mm")):
        plan = copy.deepcopy(UN_TRAMO)
        donde(plan)[clave] = 0
        with pytest.raises(ValueError, match=clave):
            Obra(**plan)


# --- que el brazo llegue, y que le dejen llegar -------------------------------------------------

def test_el_radio_libre_tiene_que_dejar_sitio_al_brazo_que_se_pide():
    """La articulación del banco 1113-0423 se quedó en 9 de 10 por 0,9 mm:
    el plan reservó 150 mm de radio libre para un brazo que tenía que llegar
    a 150, y al brazo solo le valía medir 150,0 justos. Se pide que el radio
    le saque al menos 5 mm al brazo."""
    plan = copy.deepcopy(UN_TRAMO)
    # Un brazo de 100 mm, con el que el SG90 sí puede (3 000 + 1 000 g·mm).
    plan["uniones"][0].update(brazo_mm=100, radio_libre_mm=100)
    [error] = _errores(plan)
    assert "u1" in error and "100 mm" in error and "105" in error
    plan["uniones"][0]["radio_libre_mm"] = 105
    assert _errores(plan) == []


def test_a_la_pieza_de_la_punta_se_le_mide_que_llega(tmp_path):
    """El brazo de `test_transmision`: llega a √(150² + 5²) = 150,1 mm de su
    eje. Si el plan dice 150, vale; si dice 160, le faltan 9,9."""
    import json

    from orchestrator.medida import defectos_de_alcance
    from tests.test_transmision import _articulacion
    carpeta = _articulacion(tmp_path)
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    for pide, defectos in ((150, 0), (160, 1)):
        plan["uniones"][0]["brazo_mm"] = pide
        (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
        d = defectos_de_alcance(carpeta, "brazo")
        assert len(d) == defectos, d
    assert "150.1 mm" in d[0] and "160" in d[0] and "9.9" in d[0]
    assert defectos_de_alcance(carpeta, "soporte") == []
    # Y se le dice antes de que dibuje, no solo después.
    from orchestrator.obra import uniones_del_nodo
    [u] = uniones_del_nodo(carpeta, "brazo")
    assert "llegar a 160 mm" in u["texto"]


# --- con el modelo de verdad --------------------------------------------------------------------

@pytest.mark.llm
def test_deepseek_apunta_la_carga_y_el_largo_del_brazo():
    """La petición del encargo 14: «La punta del brazo queda a 150 mm del
    eje y levanta 300 g»."""
    import os
    from pathlib import Path

    import yaml

    from orchestrator.agents.desglosador import DesglosadorAgent
    from orchestrator.cli import _cliente
    from orchestrator.config import load_env
    from orchestrator.impresion import perfil_activo
    from orchestrator.llm.router import Router

    env = {**os.environ, **load_env(Path(".env"))}
    if not env.get("DEEPSEEK_API_KEY"):
        pytest.skip("sin DEEPSEEK_API_KEY")
    encargo = yaml.safe_load(Path("tests/banco/encargos/14_articulacion_correa_nema17.yaml")
                             .read_text(encoding="utf-8"))
    router = Router.from_config_file(Path("config/models.yaml"), env=env)
    obra = DesglosadorAgent(_cliente(router, env, "reason"), reserva=_cliente(router, env)).desglosar(
        encargo["peticion"], agujeros=perfil_activo(Path(".")).datos["holes"])
    print(obra.model_dump_json(indent=1))
    [giro] = [u for u in obra.uniones if u.tipo == "gira"]
    assert obra.carga_g == 300 and giro.brazo_mm == 150
