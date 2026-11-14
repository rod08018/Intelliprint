"""El brazo de seis ejes y 2 kg (F12.4 (muñeca) y F12.5 (arctos), ADR-022).

La tabla de motores y rodamientos la propuso el asistente y la aprobó el
usuario el 2026-11-14 («Sí, apruebo»), con las reductoras del hombro y del
codo compradas («Ambas compradas»). Aquí está el plan escrito a mano —el que
tendría que salir del desglosador— y sus cuentas de par, a mano y en gramos
por milímetro (1 N·m son 101 972 g·mm), con lo impreso a 0,2 g/mm como en
`dimensionar`.

El brazo es UN proyecto, con la muñeca dentro: el usuario lo dijo ese mismo
día al ver la muñeca medida aparte («no veo por qué son proyectitos
separados»).

Tramos: del hombro al codo 190 mm, del codo al cabeceo 285 y del cabeceo a
la punta de la brida 125. No son los 260, 240 y 100 de la tabla aprobada:
hecha a mano, de la muñeca a la brida no cabe un NEMA 17 con su reductora en
menos de 125, y un tramo de 260 entre ejes da una pieza de más de 300, que
no entra en una impresora de 250 de alto. Desde la punta: el hombro a 600,
el codo a 410, el giro del antebrazo (J4) a 225 —185 mm más allá del codo—,
y el cabeceo (J5) a 125. El
giro de la herramienta (J6) no dice dónde está: lo que lleva la mano se
cuenta en la punta, que es lo peor. Cada giro va sobre un solo componente:
los rodamientos de apoyo de la tabla no entran todavía en el plan. Lo
comprado que lleva cada pieza va en el eje del giro siguiente:

- brazo: el motorreductor del codo, 1600 g.
- antebrazo: lo del J4, 275 + 60 = 335 g.
- giro: lo del J5, 335 g.
- mano: lo del J6, 335 g.

Hombro (a 600): la carga, 2000 × 600 = 1 200 000; su tramo, 38 g a 95,
3 610; lo del brazo a 190, 304 000; el tramo del codo, 37 g a 282,5,
10 452,5; lo del antebrazo a 375, 125 625; el tramo del J4, 20 g a 425,
8 500; lo del giro a 475, 159 125; el tramo del J5, 25 g a 537,5, 13 437,5;
lo de la mano a 600, 201 000. Suma 2 025 750.

Codo (a 410): 820 000 + 37 g a 92,5 (3 422,5) + 335 a 185 (61 975) + 20 g a
235 (4 700) + 335 a 285 (95 475) + 25 g a 347,5 (8 687,5) + 335 a 410
(137 350) = 1 131 610.

J5 (a 125): 250 000 + 25 g a 62,5 (1 562,5) + 335 a 125 (41 875) =
293 437,5.

El J4 y el J6 giran sobre un eje que va a lo largo del brazo: con el brazo
estirado la carga está en su eje y la gravedad no les pide nada. Al J4 le
pide lo mismo que al J5 cuando la muñeca se dobla 90°: lo que cuelga queda
igual de lejos de su eje. Al J6 solo lo que se descentre la carga, que el
plan no dice.
"""

import copy

import pytest

from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra
from tests.test_plan_mecanico import AGUJEROS

G = 9.80665e-6
CICLOIDAL_28 = {"motor": "nema17", "tipo": "reductora", "relacion": 28}
PLAN = {
    "titulo": "Brazo de seis ejes y 2 kg", "carga_g": 2000,
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "se atornilla al tablero y gira el brazo",
         "compra": ["6810-2rs", "nema23"]},
        {"id": "torreta", "nombre": "Torreta", "que_hace": "gira sobre la base y aloja el hombro",
         "compra": ["nema23-pg47-76"], "depende_de": ["base"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "del hombro al codo, 190 mm",
         "compra": ["nema23-pg47-56"], "depende_de": ["torreta"]},
        {"id": "antebrazo", "nombre": "Antebrazo", "que_hace": "sale del codo y aloja el giro",
         "compra": ["nema17", "cicloidal-nema17-28"], "depende_de": ["brazo"]},
        {"id": "giro", "nombre": "Giro del antebrazo", "que_hace": "gira sobre el eje del brazo",
         "compra": ["nema17", "cicloidal-nema17-28"], "depende_de": ["antebrazo"]},
        {"id": "mano", "nombre": "Mano", "que_hace": "cabecea y aloja el giro de la herramienta",
         "compra": ["nema17", "cicloidal-nema17-10"], "depende_de": ["giro"]},
        {"id": "brida", "nombre": "Brida", "que_hace": "donde se atornilla la herramienta",
         "depende_de": ["mano"]},
        {"id": "todo", "nombre": "El brazo", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "torreta", "brazo", "antebrazo", "giro", "mano", "brida"]},
    ],
    "uniones": [
        {"tipo": "fija", "id": "u1", "cabeza": "base", "agarra": "exterior", "metrica": "M4",
         "cantidad": 4},
        {"tipo": "gira", "id": "u2", "gira": "torreta", "sobre": "base", "componente": "6810-2rs",
         "recorrido_grados": 180, "eje": "vertical",
         "movido_por": {"motor": "nema23", "tipo": "correa", "relacion": 5}},
        {"tipo": "gira", "id": "u3", "gira": "brazo", "sobre": "torreta",
         "componente": "nema23-pg47-76", "recorrido_grados": 180, "radio_libre_mm": 610,
         "eje": "horizontal", "brazo_mm": 600},
        {"tipo": "gira", "id": "u4", "gira": "antebrazo", "sobre": "brazo",
         "componente": "nema23-pg47-56", "recorrido_grados": 180, "radio_libre_mm": 420,
         "eje": "horizontal", "brazo_mm": 410},
        {"tipo": "gira", "id": "u5", "gira": "giro", "sobre": "antebrazo",
         "componente": "cicloidal-nema17-28", "recorrido_grados": 180, "radio_libre_mm": 135,
         "eje": "horizontal", "brazo_mm": 225, "a_lo_largo": True, "movido_por": CICLOIDAL_28},
        {"tipo": "gira", "id": "u6", "gira": "mano", "sobre": "giro",
         "componente": "cicloidal-nema17-28", "recorrido_grados": 180, "radio_libre_mm": 135,
         "eje": "horizontal", "brazo_mm": 125, "movido_por": CICLOIDAL_28},
        {"tipo": "gira", "id": "u7", "gira": "brida", "sobre": "mano",
         "componente": "cicloidal-nema17-10", "recorrido_grados": 180, "radio_libre_mm": 40,
         "eje": "horizontal", "a_lo_largo": True,
         "movido_por": {"motor": "nema17", "tipo": "reductora", "relacion": 10}},
    ],
}


def test_el_plan_del_brazo_de_2_kg_escrito_a_mano_vale():
    errores, _ = validar_plan(Obra(**PLAN), AGUJEROS)
    assert errores == []


def test_cada_motor_que_levanta_puede_con_lo_suyo():
    """Lo que da cada uno, pidiéndole la mitad de su par: el motorreductor
    de 76 mm del hombro, 1,89 × 46,656 × 0,73 / 2 = 32,186 N·m; el de 56 del
    codo, 1,25 × 46,656 × 0,73 / 2 = 21,287; las cicloidales 28:1 del J4 y
    del J5, 0,400 × 28 × 0,65 / 2 = 3,64. La base, de eje vertical, no carga
    peso y no sale; el J6 tampoco, porque el plan no dice cuánto se
    descentra la carga."""
    from orchestrator.dimensionar import pares
    hombro, codo, j4, j5 = pares(Obra(**PLAN))
    assert [p["union"] for p in (hombro, codo, j4, j5)] == ["u3", "u4", "u5", "u6"]
    assert hombro["pide_Nm"] == pytest.approx(2025750 * G) == pytest.approx(19.866, abs=1e-3)
    assert hombro["da_Nm"] == pytest.approx(32.186, abs=1e-3)
    assert codo["pide_Nm"] == pytest.approx(1131610 * G) == pytest.approx(11.097, abs=1e-3)
    assert codo["da_Nm"] == pytest.approx(21.287, abs=1e-3)
    assert j5["pide_Nm"] == pytest.approx(293437.5 * G) == pytest.approx(2.878, abs=1e-3)
    assert j5["da_Nm"] == pytest.approx(3.64)


def test_un_giro_a_lo_largo_del_brazo_pide_lo_que_la_muneca_doblada():
    """El J4 gira el antebrazo sobre su propio eje. Con la muñeca doblada
    90°, la carga queda a los 125 mm del J5 del eje del J4, y todo lo que
    cuelga del J5 igual de lejos que del suyo: pide lo que el J5, 293 437,5
    g·mm. Contado como un giro que levanta, a 225 mm de la punta, serían más
    de 450 000 (4,4 N·m) y la cicloidal de 28:1 (3,64) no alcanzaría."""
    from orchestrator.dimensionar import errores, pares
    j4 = pares(Obra(**PLAN))[2]
    assert j4["union"] == "u5" and j4["pide_Nm"] == pytest.approx(293437.5 * G)
    assert j4["da_Nm"] == pytest.approx(3.64) and j4["brazo_mm"] == 125
    assert errores(Obra(**PLAN)) == []
    sin_decirlo = copy.deepcopy(PLAN)
    del sin_decirlo["uniones"][4]["a_lo_largo"]
    [error] = errores(Obra(**sin_decirlo))
    assert "u5" in error


def test_si_la_muneca_no_puede_doblada_lo_dice_el_giro_del_antebrazo():
    """Con una cicloidal de 10:1 en el J4 (0,400 × 10 × 0,65 / 2 = 1,30 N·m)
    no puede con los 2,878 que le pide la muñeca doblada, y el error dice
    con qué giro doblado."""
    from orchestrator.dimensionar import errores
    plan = copy.deepcopy(PLAN)
    plan["nodos"][3]["compra"][1] = "cicloidal-nema17-10"
    plan["uniones"][4].update(componente="cicloidal-nema17-10",
                              movido_por={"motor": "nema17", "tipo": "reductora", "relacion": 10})
    [error] = errores(Obra(**plan))
    assert "u5" in error and "u6" in error and "doblad" in error
    assert "2.878" in error and "1.300" in error and "125 mm" in error


def _desglosar(peticion: str) -> Obra:
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
    obra = DesglosadorAgent(_cliente(router, env, "reason"),
                            reserva=_cliente(router, env)).desglosar(
        peticion, agujeros=perfil_activo(Path(".")).datos["holes"])
    print(obra.model_dump_json(indent=1))
    return obra


@pytest.mark.llm
def test_deepseek_dice_que_el_giro_del_antebrazo_va_a_lo_largo():
    """La muñeca del brazo de 2 kg, sola. La petición dice literalmente que
    el primer eje «va a lo largo del antebrazo» y que el segundo cabecea:
    el primero lleva `a_lo_largo` y 280 mm hasta la punta (180 + 100), y el
    segundo no, y 100. Sin decirlo, el plan no vale: al primero se le
    pedirían 2000 g a 280 mm."""
    obra = _desglosar(
        "Una muñeca de robot con dos giros, con motores NEMA 17. El primero gira el antebrazo "
        "sobre sí mismo: su eje va a lo largo del antebrazo, sobre una reductora cicloidal "
        "28:1. El segundo, 180 mm más allá, cabecea la mano, con el eje horizontal, sobre "
        "otra reductora cicloidal 28:1. Del eje del cabeceo a la punta hay 100 mm, y la punta "
        "levanta 2 kg. Cada eje recorre 180°. La primera pieza se atornilla a un tablero con "
        "cuatro tornillos M3.")
    # Sin que nadie se lo explicara, el modelo dejó el primer giro sin
    # `brazo_mm` (2026-11-14): valía, y nadie comprobaba su motor.
    giros = sorted((u for u in obra.uniones if u.tipo == "gira"),
                   key=lambda u: -(u.brazo_mm or 0))
    assert [(u.a_lo_largo, u.brazo_mm) for u in giros] == [(True, 280), (False, 100)]
    assert obra.carga_g == 2000
    assert all(u.componente == "cicloidal-nema17-28" and u.movido_por.motor == "nema17"
               for u in giros)


@pytest.mark.llm
def test_deepseek_pone_el_motorreductor_en_el_eje_y_sin_movido_por():
    """El hombro del brazo de 2 kg, solo. El motor viene con su reductora
    montada: es un solo componente, y el brazo gira en su eje de salida. La
    petición lo nombra por su número de parte.

    Este test no se vio en rojo: el modelo ya lo hace bien con lo que dicen
    las notas de la ficha, sin ninguna regla en su prompt (comprobado el
    2026-11-14 con el prompt de antes). Se queda de guarda."""
    obra = _desglosar(
        "Un hombro de brazo robot. Un soporte atornillado a un tablero con cuatro tornillos "
        "M4 aloja un motor con su reductora planetaria ya montada, el 23HS30-2804S-PG47, con "
        "el eje horizontal. El brazo gira directamente en el eje de salida de la reductora, "
        "180°; mide 300 mm del eje a la punta y levanta 2 kg.")
    [giro] = [u for u in obra.uniones if u.tipo == "gira"]
    assert giro.componente == "nema23-pg47-76" and giro.movido_por is None
    assert (giro.brazo_mm, giro.eje, obra.carga_g) == (300, "horizontal", 2000)
    assert not giro.a_lo_largo
    assert obra.nodo(giro.sobre).compra == ["nema23-pg47-76"]


def test_el_encargo_17_pide_lo_que_dice_su_peticion():
    """La muñeca sola, que es lo que el usuario aprobó medir el 2026-11-14
    («Sí, la muñeca»). De su petición: tres NEMA 17, cicloidales de 28:1 (dos)
    y 10:1, tres ejes horizontales de 180°, 125 mm del cabeceo a la punta y
    2 kg. Tres motores con cuatro M3 cada uno: doce."""
    from pathlib import Path

    from orchestrator.banco import cargar_encargos
    from orchestrator.componentes import mencionados
    [e] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
           if e.nombre == "muneca_tres_ejes_nema17"]
    assert sorted(a.relacion for a in e.oraculo if a.tipo == "reduccion") == [10, 28]
    por_tipo = {a.tipo: a for a in e.oraculo}
    assert por_tipo["componente"].ficha == "nema17" and por_tipo["componente"].cuantos == 3
    assert por_tipo["articulaciones"].ejes == ["horizontal"] * 3
    assert por_tipo["articulaciones"].recorrido_grados == 180
    assert por_tipo["alcance"].minimo_mm == 125 and por_tipo["carga"].minimo_g == 2000
    assert por_tipo["tornillos"].cuantos == 12 == 3 * 4
    assert {"sin_soportes", "encaje", "conjunto_libre"} <= set(por_tipo)
    for texto in ("28:1", "10:1", "125 mm", "2 kg", "180 mm", "a lo largo", "sin soportes"):
        assert texto in e.peticion, texto
    assert {"nema17", "cicloidal-nema17-10", "cicloidal-nema17-28"} <= set(mencionados(e.peticion))


def test_el_encargo_18_es_el_brazo_entero_en_un_solo_proyecto():
    """El brazo completo, con la muñeca dentro: un solo encargo y un solo
    proyecto, como lo pidió el usuario el 2026-11-14. De su petición: 600 mm
    del hombro a la punta (190 + 285 + 125), 2000 g, seis ejes (el primero
    vertical), correa 5:1 en la base, cicloidales de 28:1 y 10:1 en la
    muñeca, y lo comprado por su nombre."""
    from pathlib import Path

    from orchestrator.banco import cargar_encargos
    from orchestrator.componentes import mencionados
    [e] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
           if e.nombre == "brazo_seis_ejes_2kg"]
    assert e.obra
    assert sorted(a.relacion for a in e.oraculo if a.tipo == "reduccion") == [5, 10, 28]
    por_tipo = {a.tipo: a for a in e.oraculo}
    assert por_tipo["articulaciones"].ejes == ["vertical"] + ["horizontal"] * 5
    assert por_tipo["alcance"].minimo_mm == 600 == 190 + 285 + 125
    assert por_tipo["carga"].minimo_g == 2000
    comprado = {a.ficha: a.cuantos for a in e.oraculo if a.tipo == "componente"}
    assert comprado == {"nema17": 3, "nema23": 1, "nema23-pg47-76": 1, "nema23-pg47-56": 1,
                        "6810-2rs": 1}
    tornillos = {a.sujetan: (a.metrica, a.cuantos) for a in e.oraculo if a.tipo == "tornillos"}
    assert tornillos == {"nema17": ("M3", 12), "nema23": ("M4", 4),
                         "nema23-pg47-76": ("M5", 4), "nema23-pg47-56": ("M5", 4)}
    for texto in ("190 mm", "285 mm", "125 mm", "600 mm", "2000 g", "5:1", "a lo largo"):
        assert texto in e.peticion, texto
    assert set(comprado) | {"cicloidal-nema17-10", "cicloidal-nema17-28"} <= set(
        mencionados(e.peticion))
    # Y el plan escrito a mano es el de esa petición.
    plan = Obra(**PLAN)
    assert plan.carga_g == por_tipo["carga"].minimo_g
    assert sorted(c for n in plan.nodos for c in n.compra if not c.startswith("cicloidal")) \
        == sorted(f for f, n in comprado.items() for _ in range(n))


def test_el_sitio_de_un_giro_a_lo_largo_no_es_lo_que_mide_el_brazo():
    """El radio libre de un giro es lo que barre la pieza alrededor de su
    eje. La que cabecea llega a 125 mm de su eje y necesita más de eso; la
    que gira a lo largo tiene la punta a 225 mm, pero sobre su eje: con la
    muñeca doblada barre los 125 del J5 y poco más (135), no 230."""
    errores, _ = validar_plan(Obra(**PLAN), AGUJEROS)
    assert errores == []
    plan = copy.deepcopy(PLAN)
    plan["uniones"][5]["radio_libre_mm"] = 90          # el J5, que sí levanta
    errores, _ = validar_plan(Obra(**plan), AGUJEROS)
    assert any("u6" in e and "radio libre" in e for e in errores)
