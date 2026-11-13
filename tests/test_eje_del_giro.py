"""Hacia dónde mira el eje de un giro, y lo que salió de medir el encargo 14
(F10.3 (correa), corrida 1113-0216 del 2026-11-12).

La articulación con NEMA 17 y correa 4:1 se quedó en 6 de 10. La petición
decía «con el eje horizontal» y al soporte le llegó escrito; se dibujó
tumbado, como se imprime, con el eje hacia arriba, y pasó su bucle: nadie
se lo midió. De ahí salieron tres de los cuatro fallos del banco.

Lo esperado sale de la geometría que monta cada test, hecha a mano.
"""

import json

import pytest

from orchestrator.schemas.obra import Obra
from tests.test_tornilleria import _caja_stl
from tests.test_transmision import PLAN, _articulacion


def _con_eje(carpeta, eje, radio=None, giros_del_rodamiento=None):
    """La articulación de `test_transmision` (el 608ZZ tumbado: su eje va
    hacia −y, horizontal), con lo que el plan diga del eje."""
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    plan["uniones"][0]["eje"] = eje
    if radio:
        plan["uniones"][0]["radio_libre_mm"] = radio
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    if giros_del_rodamiento is not None:
        rasgos = carpeta / "nodos" / "soporte" / "parts" / "soporte" / "rasgos.json"
        suyos = json.loads(rasgos.read_text(encoding="utf-8"))
        suyos[0]["giros"] = giros_del_rodamiento
        rasgos.write_text(json.dumps(suyos), encoding="utf-8")
    return carpeta


# --- el plan ----------------------------------------------------------------------------------

def test_el_plan_puede_decir_hacia_donde_mira_el_eje():
    plan = json.loads(json.dumps(PLAN))
    assert Obra(**plan).uniones[1].eje is None        # los planes de antes
    plan["uniones"][1]["eje"] = "horizontal"
    assert Obra(**plan).uniones[1].eje == "horizontal"
    plan["uniones"][1]["eje"] = "inclinado"
    with pytest.raises(ValueError, match="eje"):
        Obra(**plan)


def test_el_plan_se_lee_con_su_eje():
    from orchestrator.obra import union_en_palabras
    plan = json.loads(json.dumps(PLAN))
    plan["uniones"][1]["eje"] = "horizontal"
    obra = Obra(**plan)
    assert "eje horizontal" in union_en_palabras(obra, obra.uniones[1])


# --- lo que se le dice y se le mide a la pieza que monta el eje --------------------------------

def test_a_la_pieza_que_monta_el_eje_se_le_dice_como_va_puesta(tmp_path):
    """Sin esto dibuja la pieza como mejor se imprime, que no es como se usa."""
    from orchestrator.obra import uniones_del_nodo
    [u] = uniones_del_nodo(_con_eje(_articulacion(tmp_path), "horizontal"), "soporte")
    assert "horizontal" in u["texto"] and "z hacia arriba" in u["texto"]
    assert "como va a quedar puesta" in u["texto"]


def test_un_eje_que_mira_hacia_donde_dice_el_plan_no_tiene_defecto(tmp_path):
    from orchestrator.medida import defectos_de_orientacion
    carpeta = _con_eje(_articulacion(tmp_path), "horizontal")
    assert defectos_de_orientacion(carpeta, "soporte") == []
    assert defectos_de_orientacion(carpeta, "brazo") == []


def test_el_soporte_tumbado_no_pasa_si_el_eje_tenia_que_ir_horizontal(tmp_path):
    """Como el soporte de la corrida 1113-0216: el rodamiento sin girar, con
    su eje hacia +z. El plan pide horizontal."""
    from orchestrator.medida import defectos_de_orientacion
    carpeta = _con_eje(_articulacion(tmp_path), "horizontal", giros_del_rodamiento=[])
    [d] = defectos_de_orientacion(carpeta, "soporte")
    assert "horizontal" in d and "vertical" in d and "u1" in d
    assert defectos_de_orientacion(carpeta, "brazo") == []   # no es cosa del brazo


def test_un_eje_horizontal_no_pasa_si_tenia_que_ir_vertical(tmp_path):
    from orchestrator.medida import defectos_de_orientacion
    [d] = defectos_de_orientacion(_con_eje(_articulacion(tmp_path), "vertical"), "soporte")
    assert "vertical" in d and "horizontal" in d


def test_sin_eje_en_el_plan_no_se_mide_nada(tmp_path):
    from orchestrator.medida import defectos_de_orientacion
    assert defectos_de_orientacion(_articulacion(tmp_path), "soporte") == []


# --- hasta dónde llega la pieza que gira --------------------------------------------------------

def test_lo_que_llega_una_pieza_se_mide_en_la_pieza_y_no_en_su_caja(tmp_path):
    """El plan de la 1113-0216 reservó 150 mm de radio para un brazo de 150:
    con su ancho, la esquina de su CAJA quedaba a 152,4 mm y no podía cumplir
    a la vez «llega a 150» y «no pasa de 150».

    Aquí el brazo es un cubo de 20 en el eje y una varilla fina hasta
    x = 150: su punto más lejano está a 150,0 mm del eje (la varilla va de
    z = 24,9 a 25,1, y el eje pasa por z = 25), pero la esquina de su caja,
    en (150, ·, 35), a √(150² + 10²) = 150,3."""
    from orchestrator.medida import defectos_de_giro
    carpeta = _con_eje(_articulacion(tmp_path), None, radio=150)
    parte = carpeta / "nodos" / "brazo" / "parts" / "brazo"
    (parte / "brazo.stl").write_text(
        "solid p\n" + _caja_stl((-10, -6, 15), (10, -1, 35))
        + _caja_stl((0, -6, 24.9), (150, -1, 25.1)) + "endsolid p\n", encoding="utf-8")
    (parte / "envolvente.json").write_text(
        json.dumps({"min": [-10, -6, 15], "max": [150, -1, 35]}), encoding="utf-8")
    assert defectos_de_giro(carpeta, "brazo") == []
    # Una varilla de 153 sí pasa del radio, y se dice con su medida.
    (parte / "brazo.stl").write_text(
        "solid p\n" + _caja_stl((0, -6, 24.9), (153, -1, 25.1)) + "endsolid p\n",
        encoding="utf-8")
    (parte / "envolvente.json").write_text(
        json.dumps({"min": [0, -6, 24.9], "max": [153, -1, 25.1]}), encoding="utf-8")
    [d] = defectos_de_giro(carpeta, "brazo")
    assert "153.0 mm" in d and "150" in d


def test_el_sitio_libre_de_un_rodamiento_empieza_donde_acaba_el_rodamiento(tmp_path):
    """El sitio de lo que gira se reserva «desde la cara por donde sale el
    eje hacia fuera». En un servo esa cara es la de la carcasa. Un rodamiento
    va metido en una pared, a lo largo de sus 7 mm: contado desde su cara de
    atrás, la pared que lo sujeta quedaba dentro del sitio «libre» (hecha a
    mano el 2026-11-12: 40 863 mm³ de estorbo en un soporte normal).

    Aquí el 608ZZ empieza en (0, 3.5, 25) y va hacia −y: acaba en y = −3,5."""
    from orchestrator.medida import sondas_de_giro
    [s] = sondas_de_giro(_con_eje(_articulacion(tmp_path), None, radio=150), "soporte")
    assert s.punto == pytest.approx([0, -3.5, 25]) and s.eje == pytest.approx([0, -1, 0])
    assert s.radio_mm == 150


# --- lo que gira en un rodamiento puede tocarlo -------------------------------------------------

def test_el_rodamiento_en_el_que_gira_una_pieza_no_cuenta_para_los_choques(tmp_path):
    """El eje del brazo va encajado en el aro del 608ZZ: tocarlo es lo que
    tiene que hacer. En la 1113-0216 «chocaban», a 0,00 mm. El rodamiento
    sale de lo que se barre; el motor, que va al lado, se queda: sus cuatro
    cuerpos son los de su ficha (cuerpo, resalte, eje y conector)."""
    from orchestrator.conjunto import _solidos, articulaciones_de, leer_piezas
    carpeta = _articulacion(tmp_path)
    piezas = leer_piezas(carpeta, "conjunto")
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    _, solidos, _ = _solidos(piezas, arts)
    assert len(solidos["soporte: montado"]) == 4
    _, todos, _ = _solidos(piezas)
    assert len(todos["soporte: montado"]) == 5


def test_el_servo_sobre_el_que_gira_una_pieza_si_cuenta(tmp_path):
    """Un servo no se abraza: la pieza va en su cuerno, por delante de la
    carcasa, y si la toca es un choque de verdad. Nada cambia para él."""
    from orchestrator.conjunto import _solidos, articulaciones_de, leer_piezas
    from tests.test_estudio import _brazo_en_voladizo
    carpeta = _brazo_en_voladizo(tmp_path)
    piezas = leer_piezas(carpeta, "conjunto")
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    assert _solidos(piezas, arts)[1] == _solidos(piezas)[1]


# --- al reanudar, se corrige la pieza de abajo si es la que no vale -----------------------------

def test_si_la_de_abajo_no_vale_el_banco_la_corrige_a_ella(tmp_path):
    """En la 1113-0216 el brazo gastó cinco intentos en un defecto que era
    del soporte: su eje vertical y el del motor sin asomar. Reanudar habría
    corregido otra vez el brazo."""
    from orchestrator.banco import la_de_abajo_que_no_vale
    carpeta = _con_eje(_articulacion(tmp_path), "horizontal", giros_del_rodamiento=[])
    abajo, falta = la_de_abajo_que_no_vale(carpeta, "brazo")
    assert abajo == "soporte" and "horizontal" in falta


def test_si_la_de_abajo_vale_no_se_toca(tmp_path):
    from orchestrator.banco import la_de_abajo_que_no_vale
    from tests.test_correa import _con_correa
    carpeta = _con_eje(_con_correa(tmp_path), "horizontal")
    assert la_de_abajo_que_no_vale(carpeta, "brazo") is None
    assert la_de_abajo_que_no_vale(carpeta, "soporte") is None


# --- con el modelo de verdad --------------------------------------------------------------------

@pytest.mark.llm
def test_deepseek_apunta_en_el_plan_que_el_eje_va_horizontal():
    """La petición del encargo 14, tal cual: «con el eje horizontal». Lo
    esperado se lee de ella."""
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
    assert "con el eje horizontal" in encargo["peticion"]
    router = Router.from_config_file(Path("config/models.yaml"), env=env)
    obra = DesglosadorAgent(_cliente(router, env, "reason"), reserva=_cliente(router, env)).desglosar(
        encargo["peticion"], agujeros=perfil_activo(Path(".")).datos["holes"])
    print(obra.model_dump_json(indent=1))
    [giro] = [u for u in obra.uniones if u.tipo == "gira"]
    assert giro.eje == "horizontal"
    assert giro.movido_por is not None and giro.movido_por.relacion == 4


def test_si_la_de_abajo_no_cabe_en_la_impresora_se_rehace_ella(tmp_path):
    """En la 1113-1330 el brazo superior gastó sus cinco intentos contra una
    torreta de 430 mm de alto, que no cabe en una impresora de 250 y estaba
    dada por buena. Reanudar habría corregido otra vez el brazo superior.

    El mismo soporte que vale en el test de arriba, en una impresora en la
    que no cabe (20 mm de lado) y en la de verdad."""
    from orchestrator.banco import la_de_abajo_que_no_vale
    from tests.test_correa import _con_correa
    carpeta = _con_eje(_con_correa(tmp_path), "horizontal")
    abajo, falta = la_de_abajo_que_no_vale(carpeta, "brazo", cama_mm=(20, 20, 20))
    assert abajo == "soporte" and "no cabe en la impresora" in falta
    assert la_de_abajo_que_no_vale(carpeta, "brazo", cama_mm=(235, 235, 250)) is None
