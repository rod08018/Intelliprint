"""La transmisión en el plan (F10.2 (transmisión), ADR-021).

Hasta aquí un giro iba directo sobre lo comprado: el par se leía de la ficha
del componente que hace de eje y se aplicaba tal cual. Un brazo como los que
quiere el usuario no es así: la pieza gira sobre un rodamiento y la mueve un
motor que está al lado, por una correa o una reductora. El plan lo dice en
la unión (`movido_por`) y el estudio lleva el par del motor al eje.

Los oráculos no salen del sistema:

- El par del motor, de su hoja (make.epfl.ch, la tabla «Product
  Parameters»): el 42HD4027-01, el de 40 mm y 275 g, da «Holding torque
  400 mN.m», 0,400 N·m.
- El rendimiento de una correa (0,9) es un supuesto declarado, no una
  medida: va escrito junto a cada carga.
- Cada cifra esperada está calculada a mano en el docstring de su test.
"""

import copy
import json

import pytest

from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra
from tests.test_plan_mecanico import AGUJEROS
from tests.test_plan_mecanico import PLAN as PAN_TILT
from tests.test_tornilleria import _caja_stl

PLAN = {
    "titulo": "Articulación con correa",
    "nodos": [
        {"id": "soporte", "nombre": "Soporte", "que_hace": "aloja el rodamiento y el motor",
         "compra": ["608zz", "nema17"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "levanta 300 g a 150 mm del eje",
         "depende_de": ["soporte"]},
        {"id": "todo", "nombre": "La articulación", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["soporte", "brazo"]},
    ],
    "uniones": [
        {"tipo": "fija", "id": "u1", "cabeza": "soporte", "agarra": "exterior", "metrica": "M4",
         "cantidad": 4},
        {"tipo": "gira", "id": "u2", "gira": "brazo", "sobre": "soporte", "componente": "608zz",
         "recorrido_grados": 180,
         "movido_por": {"motor": "nema17", "tipo": "correa", "relacion": 4}},
    ],
}


def _plan(compra=None, movido_por=None, **del_giro) -> dict:
    plan = copy.deepcopy(PLAN)
    if compra is not None:
        plan["nodos"][0]["compra"] = compra
    if movido_por is not None:
        plan["uniones"][1]["movido_por"].update(movido_por)
    plan["uniones"][1].update(del_giro)
    return plan


def _con_antena(compra, **union) -> dict:
    """La articulación con una segunda pieza que gira sobre el mismo soporte."""
    plan = _plan(compra=compra)
    plan["nodos"].insert(2, {"id": "antena", "nombre": "Antena", "que_hace": "gira aparte",
                             "depende_de": ["soporte"]})
    plan["nodos"][-1]["depende_de"].append("antena")
    plan["uniones"].append({"tipo": "gira", "id": "u3", "gira": "antena", "sobre": "soporte",
                            "recorrido_grados": 90, **union})
    return plan


def _errores(plan) -> str:
    return "\n".join(validar_plan(Obra(**plan), AGUJEROS)[0])


# --- la ficha del motor ----------------------------------------------------------------------

def test_el_nema17_da_su_par_de_retencion_y_tiene_eje():
    """La hoja: «Holding torque 400 mN.m» para el 42HD4027-01. El eje sale
    del centro de la cara de montaje, hacia +z, 24 mm (23 ± 1), y da vueltas
    enteras."""
    from orchestrator.componentes import cargar
    f = cargar("nema17")
    assert f.par_retencion_mNm == 400
    assert f.par_motor_Nm() == pytest.approx(0.400)
    [eje] = f.salidas
    assert (eje.en, eje.eje, eje.recorrido, eje.largo) == ([0, 0, 0], "+z", (0, 360), 24)


def test_un_servo_da_como_motor_su_par_de_bloqueo():
    """El SG90: 1,8 kgf·cm a 4,8 V, 0,1765 N·m. Sin tensión no se sabe."""
    from orchestrator.componentes import cargar
    f = cargar("sg90")
    assert f.par_motor_Nm(4.8) == pytest.approx(1.8 * 9.80665 / 100)
    assert f.par_motor_Nm() is None
    assert cargar("608zz").par_motor_Nm(4.8) is None


# --- el plan ----------------------------------------------------------------------------------

def test_el_plan_de_una_articulacion_con_correa_vale():
    assert validar_plan(Obra(**PLAN), AGUJEROS) == ([], [])
    t = Obra(**PLAN).uniones[1].movido_por
    assert (t.motor, t.tipo, t.relacion) == ("nema17", "correa", 4)


def test_los_planes_de_antes_sin_movido_por_siguen_valiendo():
    """El pan-tilt de `test_plan_mecanico`: sus giros van directos sobre el
    servo y no dicen nada de transmisión."""
    obra = Obra(**PAN_TILT)
    assert [u.movido_por for u in obra.uniones if u.tipo == "gira"] == [None, None]
    assert validar_plan(obra, AGUJEROS)[0] == []


@pytest.mark.parametrize("plan, error", [
    # El motor va en la pieza que monta el rodamiento: ahí se mide después
    # la distancia entre los dos ejes.
    (_plan(compra=["608zz"]), "«soporte» no lleva «nema17»"),
    # 4:1 se escribe 4: las vueltas del motor por cada vuelta de la pieza.
    (_plan(movido_por={"relacion": 0.25}), "relacion"),
    (_plan(movido_por={"tipo": "cadena"}), "tipo"),
    # El rodamiento sobre el que gira no es quien la mueve.
    (_plan(compra=["608zz", "608zz"], movido_por={"motor": "608zz"}), "sobre el que gira"),
])
def test_una_transmision_que_no_puede_ser_no_carga(plan, error):
    with pytest.raises(ValueError, match=error):
        Obra(**plan)


def test_un_motor_no_mueve_dos_giros():
    """El soporte lleva un solo NEMA 17 y dos rodamientos: el motor mueve una
    de las dos piezas. Con dos motores, vale."""
    transmision = {"motor": "nema17", "tipo": "correa", "relacion": 2}
    uno = _con_antena(["608zz", "608zz", "nema17"], componente="608zz", movido_por=transmision)
    texto = _errores(uno)
    assert "«soporte» lleva 1 nema17" in texto and "u2" in texto and "u3" in texto
    dos = _con_antena(["608zz", "608zz", "nema17", "nema17"], componente="608zz",
                      movido_por=transmision)
    assert _errores(dos) == ""


def test_el_servo_que_hace_de_eje_de_un_giro_no_mueve_otro_por_correa():
    """Un SG90 en el soporte: la antena gira directamente en él. No puede
    además mover el brazo por una correa."""
    plan = _con_antena(["608zz", "sg90"], componente="sg90", radio_libre_mm=20)
    plan["uniones"][1]["movido_por"]["motor"] = "sg90"
    texto = _errores(plan)
    assert "«soporte» lleva 1 sg90" in texto and "u2" in texto and "u3" in texto


def test_lo_que_mueve_tiene_que_dar_par():
    """Un sensor de ultrasonidos no mueve nada: su ficha no da ningún par."""
    texto = _errores(_plan(compra=["608zz", "hc-sr04"], movido_por={"motor": "hc-sr04"}))
    assert "u2" in texto and "«hc-sr04»" in texto and "par" in texto


def test_con_transmision_no_se_gira_sobre_algo_que_ya_es_un_actuador():
    """Girar sobre el eje de un SG90 y que además lo mueva un NEMA 17 por
    correa no es nada: o directo sobre el servo, o sobre un rodamiento."""
    texto = _errores(_plan(compra=["sg90", "nema17"], componente="sg90", radio_libre_mm=20))
    assert "u2" in texto and "«sg90»" in texto and "rodamiento" in texto


def test_un_giro_directo_en_el_eje_de_un_motor_dice_cuanto_sitio_necesita():
    """El eje del NEMA 17 ocupa un tramo, como el aro de un rodamiento, pero
    lo que va en él queda delante de la cara del motor, como en un servo:
    hay que decir cuánto sitio se le deja."""
    plan = _plan(compra=["nema17"], componente="nema17")
    del plan["uniones"][1]["movido_por"]
    assert "radio_libre_mm" in _errores(plan)
    plan["uniones"][1]["radio_libre_mm"] = 160
    assert _errores(plan) == ""


def test_un_servo_puede_mover_por_correa_lo_que_gira_en_un_rodamiento():
    """Su único aviso es el de siempre: los M2 del SG90 roscan en la pieza
    y el perfil no tiene ese agujero."""
    obra = Obra(**_plan(compra=["608zz", "sg90"], movido_por={"motor": "sg90", "relacion": 2}))
    assert obra.uniones[1].movido_por.motor == "sg90"
    errores, avisos = validar_plan(obra, AGUJEROS)
    assert errores == []
    assert len(avisos) == 1 and "M2_selftap_mm" in avisos[0]


def test_el_plan_se_lee_con_su_transmision():
    """Lo que ve la persona antes de aprobar."""
    from orchestrator.obra import union_en_palabras
    obra = Obra(**PLAN)
    texto = union_en_palabras(obra, obra.uniones[1])
    assert "«Brazo» gira 180° sobre el Rodamiento 608ZZ" in texto
    assert "NEMA 17" in texto and "correa" in texto and "4:1" in texto


# --- el barrido ------------------------------------------------------------------------------

def test_sobre_un_rodamiento_el_recorrido_pedido_va_la_mitad_a_cada_lado():
    """Un rodamiento da la vuelta entera, de 0° a 360° en su ficha: no tiene
    un lado al que no llegue. A la pieza se le dice «90° a cada lado de como
    se dibuje», y eso es lo que hay que barrer; de 0° a 180° el brazo, que
    se dibuja estirado, nunca bajaría."""
    from orchestrator.conjunto import _lo_pedido
    assert _lo_pedido((0, 360), 180) == (-90, 90)
    assert _lo_pedido((0, 360), None) == (0, 360)
    assert _lo_pedido((0, 360), 360) == (0, 360)
    # El de un servo no cambia: centrado, y corrido si la ficha no llega.
    assert _lo_pedido((-90, 90), 60) == (-30, 30)
    assert _lo_pedido((0, 180), 60) == (0, 60)


# --- el estudio -------------------------------------------------------------------------------

def _articulacion(tmp_path, motor="nema17", relacion=4):
    """El soporte apoyado en z = 0 con un 608ZZ tumbado: su eje pasa por
    (0, ·, 25) hacia −y. Encima, un brazo de 150 × 5 × 10 que sale en x
    desde el eje: 20 g (de PrusaSlicer), con el centro a 75 mm. El motor va
    en el soporte, a un lado."""
    from tests.test_conjunto import _obra, _sobre
    cajas = {"soporte": ((-28, -60, 0), (28, 17.5, 31.5)), "brazo": ((0, -6, 20), (150, -1, 30))}
    rodamiento = {"nombre": "608zz", "tipo": "componente", "ficha": "608zz", "en": [0, 3.5, 25],
                  "giros": [["x", 90]], "entra_por": "+z"}
    el_motor = {"nombre": motor, "tipo": "componente", "ficha": motor, "en": [0, -35, 40],
                "giros": [], "entra_por": "+z"}
    carpeta = _obra(tmp_path, {
        "soporte": ([], [rodamiento, el_motor], [list(c) for c in cajas["soporte"]]),
        "brazo": (["soporte"], [_sobre("soporte", (0, 0, 0))], [list(c) for c in cajas["brazo"]]),
    })
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    plan["nodos"][0]["compra"] = ["608zz", motor]
    plan["uniones"] = [{"tipo": "gira", "id": "u1", "gira": "brazo", "sobre": "soporte",
                        "componente": "608zz", "recorrido_grados": 180,
                        "movido_por": {"motor": motor, "tipo": "correa", "relacion": relacion}}]
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    for i, (a, b) in cajas.items():
        parte = carpeta / "nodos" / i / "parts" / i
        (parte / f"{i}.stl").write_text("solid p\n" + _caja_stl(a, b) + "endsolid p\n",
                                        encoding="utf-8")
        (carpeta / "nodos" / i / "fabrication").mkdir()
        (carpeta / "nodos" / i / "fabrication" / "slicing_report.json").write_text(
            json.dumps({"grams": {"soporte": 30, "brazo": 20}[i]}), encoding="utf-8")
    return carpeta


def test_el_par_del_motor_llega_al_eje_por_la_relacion_y_el_rendimiento(tmp_path):
    """A mano, con la hoja del motor:

    - En el eje: 0,400 N·m × 4 (la correa) × 0,9 (su rendimiento, supuesto)
      = 1,44 N·m. Se le pide como mucho la mitad, como a un servo: 0,72.
    - El brazo solo (20 g a 75 mm) pide 0,020 × 9,80665 × 0,075 =
      0,01471 N·m, estirado en horizontal, a 0°.
    - La carga en la punta, a 150 mm: (0,72 − 0,01471) / (9,80665 × 0,150)
      = 0,4795 kg, 479,5 g.
    - Un paso a paso no tiene tensión de servo ni «segundos por 60°»: no se
      da ni la una ni el tiempo."""
    from orchestrator.estudio import estudiar
    e = estudiar(_articulacion(tmp_path), "conjunto")
    [s] = e["servos"]
    assert s["pieza"] == "brazo"
    assert s["recorrido"] == [-90, 90]
    assert s["par_max_Nm"] == pytest.approx(0.014710, rel=1e-3) and s["angulo_peor"] == 0
    assert s["transmision"] == {"motor": "nema17", "tipo": "correa", "relacion": 4,
                                "rendimiento": 0.9, "par_motor_Nm": pytest.approx(0.4)}
    assert s["par_bloqueo_Nm"] == pytest.approx(1.44)
    assert s["par_disponible_Nm"] == pytest.approx(0.72)
    assert s["aguanta"] is True
    assert s["carga_max_g"] == pytest.approx(479.5, abs=0.2)
    assert "NEMA 17" in s["servo"] and "correa 4:1" in s["servo"]
    assert s.get("tension_V") is None and s.get("tiempo_s") is None
    assert e["tension_V"] is None
    assert any("rendimiento" in a and "supuesto" in a for a in e["avisos"])


def test_sin_transmision_el_rodamiento_no_mueve_nada(tmp_path):
    """El mismo brazo sin `movido_por`: gira suelto en el rodamiento, y de lo
    que lo mueve no se sabe nada. Es lo que había antes."""
    from orchestrator.estudio import estudiar
    carpeta = _articulacion(tmp_path)
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    del plan["uniones"][0]["movido_por"]
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    [s] = estudiar(carpeta, "conjunto")["servos"]
    assert "par_bloqueo_Nm" not in s and "transmision" not in s


def test_con_un_servo_por_correa_la_velocidad_se_divide_por_la_relacion(tmp_path):
    """Un SG90 con correa 2:1. Par en el eje: 0,17652 × 2 × 0,9 =
    0,31774 N·m. En vacío da 60° en 0,1 s; con la correa, en 0,2: los 180°,
    en 0,6 s. Con el brazo, que pide 0,01471 de 0,31774, va un 4,6 % más
    lento: 0,6 / (1 − 0,01471 / 0,31774) = 0,6291 s."""
    from orchestrator.estudio import estudiar
    e = estudiar(_articulacion(tmp_path, motor="sg90", relacion=2), "conjunto")
    [s] = e["servos"]
    assert s["tension_V"] == 4.8
    assert s["par_bloqueo_Nm"] == pytest.approx(0.317736, rel=1e-4)
    assert s["tiempo_s"] == pytest.approx(0.6291, abs=2e-4)


def test_el_estudio_escrito_dice_la_transmision_y_que_el_rendimiento_es_un_supuesto(tmp_path):
    from orchestrator.estudio import estudiar, texto_del_estudio
    texto = texto_del_estudio(estudiar(_articulacion(tmp_path), "conjunto"))
    assert "correa 4:1" in texto and "NEMA 17" in texto
    assert "supuesto" in texto and "90%" in texto
    assert "479.5 g" in texto


# --- lo que se le dice a quien diseña ----------------------------------------------------------

def test_a_la_pieza_que_monta_el_motor_se_le_dice_que_mueve_el_giro(tmp_path):
    """El soporte lleva el rodamiento y el motor: tiene que saber que el uno
    mueve lo que gira en el otro, y que sus ejes van paralelos (una correa
    no tuerce)."""
    from orchestrator.obra import uniones_del_nodo
    [u] = uniones_del_nodo(_articulacion(tmp_path), "soporte")
    assert u["papel"] == "sobre"
    assert "NEMA 17" in u["texto"] and "correa 4:1" in u["texto"] and "paralelo" in u["texto"]


# --- la web -------------------------------------------------------------------------------------

def test_la_pagina_ensena_un_giro_movido_por_un_paso_a_paso(tmp_path):
    """Un paso a paso no tiene «tensión del servo»: la tarjeta la daba por
    hecha en toda fila con par."""
    from tests.test_visor import ID, _con_ensamble, _estudio_hecho, _web
    carpeta = _con_ensamble(tmp_path)
    _estudio_hecho(carpeta)
    ruta = carpeta / "nodos" / "conjunto" / "estudio.json"
    e = json.loads(ruta.read_text(encoding="utf-8"))
    e["tension_V"] = None
    e["servos"] = [{"pieza": "soporte", "nombre": "Pieza soporte",
                    "servo": "Motor paso a paso NEMA 17 (17HS4401, 40 mm) por correa 4:1",
                    "par_max_Nm": 0.01471, "angulo_peor": 0.0, "recorrido": [-90, 90],
                    "transmision": {"motor": "nema17", "tipo": "correa", "relacion": 4,
                                    "rendimiento": 0.9, "par_motor_Nm": 0.4},
                    "par_bloqueo_Nm": 1.44, "par_disponible_Nm": 0.72, "aguanta": True,
                    "margen": 0.98, "carga_max_g": 479.5}]
    ruta.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    r = _web(tmp_path).get(f"/p/{ID}")
    assert r.status_code == 200
    assert "por correa 4:1" in r.text and "supuesto" in r.text


# --- con el modelo de verdad --------------------------------------------------------------------

PETICION = ("Una articulación para un brazo: el brazo gira 180° sobre un rodamiento 608ZZ y lo "
            "mueve un motor NEMA 17 por una correa 4:1. Levanta 300 g a 150 mm del eje. El "
            "soporte se atornilla a un tablero con cuatro tornillos M3.")


@pytest.mark.llm
def test_deepseek_planifica_una_articulacion_con_su_transmision():
    """Lo esperado se lee de la petición, no de lo que salga: «gira 180°
    sobre un rodamiento 608ZZ» y «lo mueve un motor NEMA 17 por una correa
    4:1». Un giro sobre el 608ZZ, movido por el NEMA 17, que va en la misma
    pieza que el rodamiento, con correa y relación 4."""
    import os
    from pathlib import Path

    from orchestrator.agents.desglosador import DesglosadorAgent
    from orchestrator.cli import _cliente
    from orchestrator.config import load_env
    from orchestrator.impresion import perfil_activo
    from orchestrator.llm.router import Router

    env = {**os.environ, **load_env(Path(".env"))}
    if not env.get("DEEPSEEK_API_KEY"):
        pytest.skip("sin DEEPSEEK_API_KEY")
    router = Router.from_config_file(Path("config/models.yaml"), env=env)
    agujeros = perfil_activo(Path(".")).datos["holes"]
    obra = DesglosadorAgent(_cliente(router, env, "reason"),
                            reserva=_cliente(router, env)).desglosar(PETICION, agujeros=agujeros)
    print(obra.model_dump_json(indent=1))
    [giro] = [u for u in obra.uniones if u.tipo == "gira"]
    assert (giro.componente, giro.recorrido_grados) == ("608zz", 180)
    assert giro.movido_por is not None, "el plan no dice qué mueve el giro"
    t = giro.movido_por
    assert (t.motor, t.tipo, t.relacion) == ("nema17", "correa", 4)
    assert "nema17" in obra.nodo(giro.sobre).compra
    assert validar_plan(obra, agujeros)[0] == []
