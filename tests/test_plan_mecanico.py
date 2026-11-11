"""Las uniones del plan mecánico (F9.2 (uniones)).

Hasta el 2026-11-10 el desglose decía qué piezas había y nada de cómo se
unían: «espacio para inclinar la plataforma 180°» era una línea de texto, y
el soporte del pan-tilt del banco dejó 12.7 mm para una plataforma de 37.7.
Ahora el plan dice qué gira sobre qué y con cuánto sitio, y qué va
atornillado y con qué; y el código lo comprueba contra las fichas y el
perfil antes de que nadie dibuje nada.

El plan de aquí está escrito a mano, y cada plan roto se rompe a propósito
en una sola cosa. Lo que se compara con él sale de las fichas: el SG90 gira
«approximately 180 degrees (90 in each direction)», según su hoja.
"""

import copy
import os
from pathlib import Path

import pytest

from orchestrator.config import load_env
from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra

PLAN = {
    "titulo": "Pan-tilt con dos SG90",
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "aloja el SG90 de giro", "compra": ["sg90"]},
        {"id": "giro", "nombre": "Soporte de giro", "que_hace": "va en el cuerno del servo de "
         "giro y aloja el SG90 de inclinación", "compra": ["sg90"], "depende_de": ["base"]},
        {"id": "plataforma", "nombre": "Plataforma", "que_hace": "sostiene la cámara",
         "depende_de": ["giro"]},
        {"id": "pan-tilt", "nombre": "El pan-tilt", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "giro", "plataforma"]},
    ],
    "uniones": [
        {"tipo": "fija", "id": "u1", "cabeza": "base", "agarra": "exterior", "metrica": "M4",
         "cantidad": 2},
        {"tipo": "gira", "id": "u2", "gira": "giro", "sobre": "base", "componente": "sg90",
         "recorrido_grados": 180, "radio_libre_mm": 25},
        {"tipo": "gira", "id": "u3", "gira": "plataforma", "sobre": "giro", "componente": "sg90",
         "recorrido_grados": 180, "radio_libre_mm": 25},
    ],
}

# Lo que tabula el perfil de la M5 (`config/printers/`): M3 entero, M4 solo pasante.
AGUJEROS = {"M3_through_mm": 3.3, "M3_selftap_mm": 2.8, "M3_insert_mm": 4.1,
            "M3_nut_af_mm": 5.9, "M4_through_mm": 4.5, "M5_through_mm": 5.5}


def _plan(**cambios) -> dict:
    return {**copy.deepcopy(PLAN), **cambios}


def _con(*uniones, quitar=()) -> dict:
    plan = _plan()
    plan["uniones"] = [u for u in plan["uniones"] if u["id"] not in quitar] + list(uniones)
    return plan


def test_el_plan_del_pan_tilt_escrito_a_mano_vale():
    errores, avisos = validar_plan(Obra(**PLAN), AGUJEROS)
    assert errores == []
    assert avisos == []


def test_un_backlog_de_antes_sin_uniones_sigue_cargando():
    """Los `obra.json` que ya hay en `workspace/` no tienen `uniones`."""
    plan = _plan()
    del plan["uniones"]
    assert Obra(**plan).uniones == []


# --- lo que el esquema rechaza sin mirar ninguna ficha ---------------------------------------

@pytest.mark.parametrize("plan, error", [
    # Dos uniones con el mismo id.
    (_con({**PLAN["uniones"][0], "cabeza": "giro"}), "«u1» repetido"),
    # Un nodo que no existe.
    (_con({"tipo": "fija", "id": "u9", "cabeza": "tapa", "agarra": "base", "metrica": "M3",
           "cantidad": 2, "agarre": "tuerca"}), "«tapa»"),
    # El conjunto no es una pieza: no se atornilla a nada.
    (_con({"tipo": "fija", "id": "u9", "cabeza": "pan-tilt", "agarra": "base", "metrica": "M3",
           "cantidad": 2, "agarre": "tuerca"}), "«pan-tilt» es un conjunto"),
    # La plataforma no depende de la base ni la base de ella: no se tocan.
    (_con({"tipo": "fija", "id": "u9", "cabeza": "plataforma", "agarra": "base",
           "metrica": "M3", "cantidad": 2, "agarre": "tuerca"}), "no depende"),
    # Entre dos piezas hay que decir cómo agarra el tornillo.
    (_con({"tipo": "fija", "id": "u9", "cabeza": "giro", "agarra": "base", "metrica": "M3",
           "cantidad": 2}, quitar=("u2",)), "agarre"),
    (_con({"tipo": "fija", "id": "u9", "cabeza": "base", "agarra": "exterior",
           "metrica": "3 mm", "cantidad": 2}), "métrica"),
    # Lo que gira se diseña después de la pieza que monta el actuador.
    (_con({**PLAN["uniones"][1], "gira": "base", "sobre": "giro"}, quitar=("u2",)),
     "«base» no depende de «giro»"),
    # La plataforma no compra nada: no monta ningún servo.
    (_con({"tipo": "gira", "id": "u9", "gira": "plataforma", "sobre": "giro",
           "componente": "608zz", "recorrido_grados": 360}, quitar=("u3",)),
     "«giro» no lleva «608zz»"),
    # Una pieza gira sobre una sola cosa: el conjunto es un árbol.
    (_plan(nodos=[*PLAN["nodos"][:2],
                  {**PLAN["nodos"][2], "depende_de": ["giro", "base"]}, PLAN["nodos"][3]],
           uniones=[*PLAN["uniones"],
                    {"tipo": "gira", "id": "u9", "gira": "plataforma", "sobre": "base",
                     "componente": "sg90", "recorrido_grados": 180, "radio_libre_mm": 25}]),
     "«plataforma» gira sobre dos"),
    # Lo que gira sobre una pieza no va además atornillado a ella.
    (_con({"tipo": "fija", "id": "u9", "cabeza": "giro", "agarra": "base", "metrica": "M3",
           "cantidad": 2, "agarre": "rosca"}), "gira sobre «base»"),
])
def test_una_union_que_no_puede_ser_no_carga(plan, error):
    with pytest.raises(ValueError, match=error):
        Obra(**plan)


# --- lo que se comprueba contra las fichas ---------------------------------------------------

def _errores(plan) -> str:
    return "\n".join(validar_plan(Obra(**plan), AGUJEROS)[0])


def test_no_se_gira_sobre_una_salida_que_la_ficha_no_tiene():
    texto = _errores(_con({**PLAN["uniones"][1], "salida": "cuerno"}, quitar=("u2",)))
    assert "«cuerno»" in texto and "«eje»" in texto


def test_no_se_pide_a_un_servo_mas_recorrido_del_que_da_su_hoja():
    """El SG90 da 90° a cada lado: 180 en total. 200 no los tiene."""
    texto = _errores(_con({**PLAN["uniones"][1], "recorrido_grados": 200}, quitar=("u2",)))
    assert "200" in texto and "180" in texto


def test_dos_piezas_no_giran_sobre_el_mismo_servo():
    """La base lleva un solo SG90: no caben dos giros en él."""
    plan = _plan()
    plan["nodos"].insert(2, {"id": "antena", "nombre": "Antena", "que_hace": "gira aparte",
                             "depende_de": ["base"]})
    plan["nodos"][-1]["depende_de"].append("antena")
    plan["uniones"].append({"tipo": "gira", "id": "u9", "gira": "antena", "sobre": "base",
                            "componente": "sg90", "recorrido_grados": 90, "radio_libre_mm": 10})
    texto = _errores(plan)
    assert "«base» lleva 1 sg90" in texto and "u2" in texto and "u9" in texto


def test_un_giro_sobre_un_servo_dice_cuanto_sitio_necesita():
    """Es justo lo que nadie decidió en el pan-tilt del banco."""
    sin_radio = {k: v for k, v in PLAN["uniones"][2].items() if k != "radio_libre_mm"}
    assert "radio_libre_mm" in _errores(_con(sin_radio, quitar=("u3",)))


def test_un_giro_sobre_un_rodamiento_no_necesita_radio():
    """Lo que gira en un 608ZZ lo abraza: su salida tiene `largo`, y no hay
    un cilindro libre delante de una cara."""
    plan = {"titulo": "Polea", "nodos": [
        {"id": "soporte", "nombre": "Soporte", "que_hace": "aloja el rodamiento",
         "compra": ["608zz"]},
        {"id": "polea", "nombre": "Polea", "que_hace": "gira", "depende_de": ["soporte"]},
        {"id": "todo", "nombre": "El conjunto", "tipo": "conjunto", "que_hace": "gira",
         "depende_de": ["soporte", "polea"]}],
        "uniones": [{"tipo": "gira", "id": "u1", "gira": "polea", "sobre": "soporte",
                     "componente": "608zz", "recorrido_grados": 360}]}
    assert validar_plan(Obra(**plan), AGUJEROS) == ([], [])


def test_lo_que_gira_tiene_un_conjunto_que_lo_mueva():
    """Un giro solo se verifica moviéndolo, y eso lo hace el nodo conjunto
    con las dos piezas dentro."""
    plan = _plan()
    plan["nodos"][-1]["depende_de"] = ["base", "giro"]
    texto = _errores(plan)
    assert "u3" in texto and "conjunto" in texto and "u2" not in texto


def test_una_pieza_que_no_se_une_a_nada_no_vale():
    """Con uniones en el plan, una pieza sin ninguna está flotando."""
    texto = _errores(_con(quitar=("u3",)))
    assert "«plataforma»" in texto and "no se une a nada" in texto


def test_una_metrica_que_el_perfil_no_tabula_es_un_aviso_y_no_un_error():
    """El perfil no tiene M6. No se puede taladrar hasta que el usuario lo
    mida en «Impresora», pero eso no es motivo para tirar el plan entero: se
    le enseña."""
    plan = _con({"tipo": "fija", "id": "u9", "cabeza": "base", "agarra": "exterior",
                 "metrica": "M6", "cantidad": 2}, quitar=("u1",))
    errores, avisos = validar_plan(Obra(**plan), AGUJEROS)
    assert errores == []
    assert len(avisos) == 1 and "M6_through_mm" in avisos[0] and "Impresora" in avisos[0]


def test_el_agarre_que_el_perfil_no_tabula_tambien_se_avisa():
    """Una tapa atornillada a la base con M4 y tuerca: el perfil tiene el
    pasante de M4, no su tuerca."""
    plan = _plan()
    plan["nodos"].insert(1, {"id": "tapa", "nombre": "Tapa", "que_hace": "cierra la base",
                             "depende_de": ["base"]})
    plan["uniones"].append({"tipo": "fija", "id": "u9", "cabeza": "tapa", "agarra": "base",
                            "metrica": "M4", "cantidad": 2, "agarre": "tuerca"})
    errores, avisos = validar_plan(Obra(**plan), AGUJEROS)
    assert errores == []
    assert len(avisos) == 1 and "M4_nut_af_mm" in avisos[0]
    plan["uniones"][-1].update(metrica="M3", agarre="inserto")
    assert validar_plan(Obra(**plan), AGUJEROS) == ([], [])


# --- con el modelo de verdad (F9.3 (planificador)) -------------------------------------------

_env = {**os.environ, **load_env(Path(".env"))}


@pytest.mark.llm
@pytest.mark.skipif(not _env.get("DEEPSEEK_API_KEY"), reason="sin DEEPSEEK_API_KEY")
def test_deepseek_planifica_el_pan_tilt_del_banco_con_sus_dos_giros():
    """La petición del encargo 11, tal cual. Lo esperado se lee de ella, no
    de lo que salga: «dos servos SG90: el de abajo gira y el de arriba
    inclina una plataforma», «cada uno recorre 180°». Son dos giros de 180°
    sobre un SG90; el servo de arriba va en la pieza que mueve el de abajo; y
    cada giro dice cuánto sitio necesita, que es lo que nadie decidió en la
    corrida 1110-0313."""
    import yaml

    from orchestrator.agents.desglosador import DesglosadorAgent
    from orchestrator.cli import _cliente
    from orchestrator.impresion import perfil_activo
    from orchestrator.llm.router import Router

    encargo = yaml.safe_load(
        Path("tests/banco/encargos/11_pan_tilt_sg90.yaml").read_text(encoding="utf-8"))
    router = Router.from_config_file(Path("config/models.yaml"), env=_env)
    agujeros = perfil_activo(Path(".")).datos["holes"]
    obra = DesglosadorAgent(_cliente(router, _env, "reason"),
                            reserva=_cliente(router, _env)).desglosar(
        encargo["peticion"], agujeros=agujeros)
    print(obra.model_dump_json(indent=1))
    giros = [u for u in obra.uniones if u.tipo == "gira"]
    assert [(u.componente, u.recorrido_grados) for u in giros] == [("sg90", 180), ("sg90", 180)]
    assert {u.gira for u in giros} & {u.sobre for u in giros}, "el servo de arriba va en lo que gira"
    assert all(u.radio_libre_mm for u in giros)
    assert validar_plan(obra, agujeros)[0] == []
