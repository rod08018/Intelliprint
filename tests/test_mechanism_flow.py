"""Flujo del Mechanism Designer (F3.15 (mecanismos)), con modelos guionizados.

Lo que se prueba es el bucle: una especificación que choca vuelve al
agente con el motivo concreto, la ronda siguiente se construye, y el
ensamble y la animación se guardan siempre.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.profile import PrinterProfile
from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
from orchestrator.agents.part_designer import PartDesignerAgent
from orchestrator.mechanisms.flow import design_mechanism
from tests.test_generators import _freecadcmd

PERFIL = PrinterProfile(id="m5", fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35})


def _spec(z_brazo: float) -> dict:
    """Un brazo que gira sobre una base con un pasador vertical."""
    return {
        "title": "Brazo giratorio", "summary": "s", "assumptions": ["pasador de Ø3"],
        "driver": {"start": 0, "end": 90, "step": 45, "label": "giro"},
        "parts": [
            {"name": "base", "brief": "Pieza «base»: placa 40x20x4, cara superior en z = 0.",
             "bbox_min": [-20, -10, -4], "bbox_max": [20, 10, 0]},
            {"name": "brazo", "origin": [0, 0, z_brazo],
             "joint": {"type": "revolute", "axis": [0, 0, 1], "value": "t"},
             "brief": "Pieza «brazo»: barra de 30 entre centros.",
             "bbox_min": [-5, -5, 0], "bbox_max": [35, 5, 5]},
        ],
        "pins": [{"name": "eje", "origin": [0, 0, -4], "diameter_mm": 3, "length_mm": 9}],
        "rules": [{"a": "base", "b": "eje", "kind": "fixed"}],
        "checks": [{"body": "brazo", "measure": "rotation", "axis": "z", "expected": 90,
                    "tolerance": 1, "description": "gira 90°"}],
    }


def _correccion(z, cambio="ajusto la altura"):
    """Spec de una ronda de corrección: lleva `fix_plan`, que es obligatorio."""
    s = _spec(z)
    s["fix_plan"] = {"causa": "chocaban", "cambio": cambio, "espera": "que no choquen"}
    return s


RECETAS = {
    "base": {"part": "base", "steps": [
        {"generator": "generate_box", "params": {"length_mm": 40, "width_mm": 20, "height_mm": 4,
                                                 "x_mm": 0, "y_mm": 0, "z_mm": -4}},
        {"generator": "generate_hole", "params": {"diameter_mm": 3, "x_mm": 0, "y_mm": 0}}]},
    "brazo": {"part": "brazo", "steps": [
        {"generator": "generate_link", "params": {"center_distance_mm": 30, "width_mm": 10,
                                                  "thickness_mm": 5, "hole_diameter_mm": 3.35}}]},
}


class Guion:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        r = self.respuestas.pop(0)
        return r(prompt) if callable(r) else r


class DisenadorDePiezas:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        tarea = prompt.split("## Tarea")[-1]
        return json.dumps(next(v for k, v in RECETAS.items() if f"«{k}»" in tarea))


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_choque_vuelve_al_agente_y_la_ronda_siguiente_lo_corrige(tmp_path):
    # Ronda 1: el brazo en z = 0 se hunde en la base. Ronda 2: z = 0.5.
    mecanico = Guion([json.dumps(_spec(0.0)), json.dumps(_correccion(0.5))])
    piezas = DisenadorDePiezas()
    informe = design_mechanism(
        "un brazo que gire 90° sobre una base",
        MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(piezas, CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, animar=False,
    )
    assert len(informe.rounds) == 2
    assert "base" in informe.rounds[0].feedback and "brazo" in informe.rounds[0].feedback
    assert "Tu diseño anterior NO funciona" in mecanico.prompts[1]
    assert informe.ok
    assert (tmp_path / "assembly.FCStd").exists()
    assert (tmp_path / "rondas" / "1" / "mechanism.json").exists()
    # La base no cambió entre rondas: no se vuelve a pedir al modelo.
    assert sum("«base»" in p.split("## Tarea")[-1] for p in piezas.prompts) == 1


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_si_ninguna_ronda_funciona_el_ensamble_se_guarda_igual(tmp_path):
    mecanico = Guion([json.dumps(_spec(0.0)), json.dumps(_correccion(0.0))])
    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, max_rounds=2, animar=False,
    )
    assert not informe.ok
    assert (tmp_path / "assembly.FCStd").exists()
    assert informe.final is not None and informe.final.collisions


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_pieza_que_gira_sin_agujero_en_su_eje_se_explica(tmp_path):
    """Fallo real (bisagra): la pieza giraba alrededor de su origen, pero su
    agujero estaba 30 mm más allá. El motivo tiene que decir dónde está."""
    from orchestrator.build import build_part
    from orchestrator.mechanisms.checks import joint_axis_problems
    from orchestrator.schemas.mechanism import MechanismSpec
    from orchestrator.schemas.recipe import Recipe

    receta = Recipe(part="brazo", steps=[
        {"generator": "generate_box", "params": {"length_mm": 40, "width_mm": 10, "height_mm": 5,
                                                 "x_mm": 0, "y_mm": 0, "z_mm": 0}},
        {"generator": "generate_hole", "params": {"diameter_mm": 3.35, "x_mm": -15, "y_mm": 0}}])
    build_part(receta, CATALOGO, tmp_path / "brazo", _freecadcmd())
    spec = MechanismSpec(**_spec(0.5))
    problemas = joint_axis_problems(spec, {"brazo": tmp_path / "brazo" / "brazo.step"}, _freecadcmd())
    assert len(problemas) == 1
    assert "(-15, 0," in problemas[0] and "ORIGEN LOCAL" in problemas[0]

    bien = Recipe(**RECETAS["brazo"])
    build_part(bien, CATALOGO, tmp_path / "ok", _freecadcmd())
    assert joint_axis_problems(spec, {"brazo": tmp_path / "ok" / "brazo.step"}, _freecadcmd()) == []


def _corredera_con_pared(tope):
    from orchestrator.schemas.mechanism import MechanismSpec
    return MechanismSpec(**{
        "title": "corredera", "summary": "s",
        "driver": {"unit": "mm", "start": 0, "end": 25, "step": 5},
        "parts": [
            {"name": "base", "brief": "b", "bbox_min": [-20, -10, -4], "bbox_max": [35, 10, 10]},
            {"name": "carro", "origin": [0, 0, 0.5],
             "joint": {"type": "prismatic", "axis": [1, 0, 0], "value": "t"},
             "brief": "c", "bbox_min": [-5, -5, 0], "bbox_max": [5, 5, 5]},
        ],
        "stops": [tope],
    })


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
@pytest.mark.parametrize("tope, esperado", [
    ({"a": "base", "b": "carro", "at": 25, "beyond": "above"}, None),
    ({"a": "base", "b": "carro", "at": 20, "beyond": "above"}, "no llega a tocar"),
    ({"a": "base", "b": "carro", "at": 25, "beyond": "below"}, "no bloquea"),
])
def test_un_tope_tiene_que_tocar_en_su_valor_y_bloquear_despues(tmp_path, tope, esperado):
    """Carro de 10 mm que avanza t mm hacia una pared en x = 30: su cara
    llega a la pared en t = 25 (cálculo a mano)."""
    from orchestrator.build import build_part
    from orchestrator.mechanisms.checks import stop_problems
    from orchestrator.mechanisms.spec_layout import SpecLayout
    from orchestrator.schemas.recipe import Recipe

    caja = lambda l, w, h, x, z: {"generator": "generate_box", "params": {  # noqa: E731
        "length_mm": l, "width_mm": w, "height_mm": h, "x_mm": x, "y_mm": 0, "z_mm": z}}
    build_part(Recipe(part="base", steps=[caja(55, 20, 4, 7.5, -4), caja(5, 20, 10, 32.5, 0)]),
               CATALOGO, tmp_path / "base", _freecadcmd())
    build_part(Recipe(part="carro", steps=[caja(10, 10, 5, 0, 0)]),
               CATALOGO, tmp_path / "carro", _freecadcmd())
    spec = _corredera_con_pared(tope)
    steps = {n: tmp_path / n / f"{n}.step" for n in ("base", "carro")}
    problemas = stop_problems(spec, SpecLayout(spec), steps, _freecadcmd())
    if esperado is None:
        assert problemas == []
    else:
        assert any(esperado in p for p in problemas), problemas


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_revisor_recibe_lo_medido_y_su_informe_se_guarda(tmp_path):
    """El revisor solo puede apoyarse en lo que midió el código, y tiene que
    ver qué movimiento está IMPUESTO por fórmula: es lo que nadie verifica."""
    from orchestrator.agents.design_reviewer import DesignReviewerAgent

    visto = {}

    class Revisor:
        def complete(self, prompt):
            visto["prompt"] = prompt
            return json.dumps({"items": [
                {"requirement": "gira 90°", "verdict": "cumple", "comment": "medido"},
                {"requirement": "es robusto", "verdict": "no_verificable", "comment": "nadie lo probó"}],
                "summary": "resumen"})

    informe = design_mechanism(
        "un brazo que gire 90° sobre una base",
        MechanismDesignerAgent(Guion([json.dumps(_spec(0.5))]), CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, animar=False,
        reviewer=DesignReviewerAgent(Revisor()),
    )
    assert "barrido de 3 posiciones" in visto["prompt"]
    assert "requisito medido con la cinemática" in visto["prompt"]
    assert "IMPUESTO por fórmula" in visto["prompt"] and "«brazo»" in visto["prompt"]
    assert informe.review is not None
    assert len(informe.review.por_veredicto("no_verificable")) == 1
    assert "no_verificable" in (tmp_path / "review.md").read_text()


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_se_puede_continuar_un_proyecto_fallido_sin_empezar_de_cero(tmp_path):
    """Sin esto, reintentar tiraba a la basura lo aprendido en 5 rondas: el
    modelo volvía a proponer desde la nada y repetía los mismos fallos."""
    # Primer intento: una sola ronda, que falla por choque.
    mecanico = Guion([json.dumps(_spec(0.0))])
    design_mechanism(
        "un brazo que gire sobre una base",
        MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, max_rounds=1, animar=False,
    )

    # Segundo intento sobre la misma carpeta: arranca con el diseño anterior
    # y con el motivo por el que falló.
    segundo = Guion([json.dumps(_correccion(0.5))])
    informe = design_mechanism(
        "un brazo que gire sobre una base",
        MechanismDesignerAgent(segundo, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, max_rounds=1, animar=False,
        continuar=True,
    )

    assert "Tu diseño anterior NO funciona" in segundo.prompts[0]
    assert "base" in segundo.prompts[0] and "brazo" in segundo.prompts[0]
    assert informe.ok


def _informe_de_revision(items):
    return json.dumps({"items": items, "summary": "s"})


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_lo_que_el_revisor_marca_como_no_cumple_vuelve_al_disenador(tmp_path):
    """Un fallo detectado al final tiene que volver al diseñador. Si no, el
    sistema 'termina' con requisitos incumplidos y nadie los corrige."""
    from orchestrator.agents.design_reviewer import DesignReviewerAgent

    mecanico = Guion([json.dumps(_spec(0.5)), json.dumps(_correccion(0.6))])
    revisor = Guion([
        _informe_de_revision([{"requirement": "el brazo mide 30 mm",
                               "verdict": "no_cumple", "comment": "mide 25"}]),
        _informe_de_revision([{"requirement": "el brazo mide 30 mm",
                               "verdict": "cumple", "comment": "medido"}]),
    ])
    informe = design_mechanism(
        "un brazo que gire sobre una base",
        MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, animar=False,
        reviewer=DesignReviewerAgent(revisor),
    )

    assert len(informe.rounds) == 2
    assert "el brazo mide 30 mm" in mecanico.prompts[1]
    assert informe.ok


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_si_se_atasca_repitiendo_el_mismo_fallo_para_y_lo_dice(tmp_path):
    """Sin esto, un fallo que el modelo no sabe arreglar quema el presupuesto
    entero repitiendo la misma propuesta."""
    mecanico = Guion([json.dumps(_spec(0.0))] + [json.dumps(_correccion(0.0))] * 11)
    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, animar=False,
    )

    assert not informe.ok
    assert informe.stopped_because == "atascado"
    assert 2 < len(informe.rounds) < 8
    assert (tmp_path / "assembly.FCStd").exists()


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_al_agotarse_el_presupuesto_se_para_y_se_pregunta(tmp_path):
    from orchestrator.llm.cost import Presupuesto

    class Caro:
        modelo = "deepseek-chat"

        def __init__(self, guion):
            self._guion = guion
            self.llamadas = []

        def complete(self, prompt):
            self.llamadas.append({"modelo": self.modelo, "entrada": 1_000_000, "salida": 0})
            return self._guion.complete(prompt)

    cliente = Caro(Guion([json.dumps(_spec(0.0))] + [json.dumps(_correccion(0.0))] * 4))
    presupuesto = Presupuesto(0.5, {"deepseek-chat": {"in_usd_per_mtok": 0.28,
                                                      "out_usd_per_mtok": 0.42}})
    presupuesto.vigila(cliente, "Mechanism Designer")

    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(cliente, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO),
        tmp_path, _freecadcmd(), min_gap_mm=0.1, animar=False, presupuesto=presupuesto,
    )

    assert informe.stopped_because == "presupuesto"
    assert len(informe.rounds) == 2


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_coste_desglosado_se_guarda_en_la_carpeta_del_proyecto(tmp_path):
    """Aunque el proyecto no salga: saber en qué se fue el dinero es lo que
    deja decidir si vale la pena seguir."""
    from orchestrator.llm.cost import Presupuesto

    class Medido:
        modelo = "deepseek-chat"

        def __init__(self, guion):
            self._guion = guion
            self.llamadas = []

        def complete(self, prompt):
            self.llamadas.append({"modelo": self.modelo, "entrada": 1000, "salida": 500})
            return self._guion.complete(prompt)

    mecanico = Medido(Guion([json.dumps(_spec(0.0))] * 6))
    presupuesto = Presupuesto(2.0, {"deepseek-chat": {"in_usd_per_mtok": 0.28,
                                                      "out_usd_per_mtok": 0.42}})
    presupuesto.vigila(mecanico, "Mechanism Designer")
    piezas = DisenadorDePiezas()

    design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(piezas, CATALOGO), tmp_path, _freecadcmd(),
        min_gap_mm=0.1, animar=False, presupuesto=presupuesto,
    )

    texto = (tmp_path / "design_cost.md").read_text(encoding="utf-8")
    assert "Mechanism Designer" in texto
    assert "ronda 1 · diseño del mecanismo" in texto
    assert (tmp_path / "design_cost.json").exists()


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_siempre_queda_la_animacion_aunque_el_mecanismo_no_salga(tmp_path):
    """Se perdió al reescribir el bucle: los proyectos terminaban sin GIF y
    era lo único que el usuario quería ver."""
    mecanico = Guion([json.dumps(_spec(0.0))] + [json.dumps(_correccion(0.0))] * 5)
    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO), tmp_path, _freecadcmd(),
        min_gap_mm=0.1,
    )
    assert not informe.ok                       # se atascó...
    assert informe.final.animation is not None  # ...y aun así hay animación
    assert (tmp_path / "animation.gif").exists()


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_coste_se_puede_consultar_mientras_trabaja(tmp_path):
    """Antes solo se escribía al final: en un proyecto de 40 minutos no había
    forma de saber cuánto llevabas gastado."""
    from orchestrator.llm.cost import Presupuesto

    costes = []

    class Medido:
        modelo = "deepseek-chat"

        def __init__(self, guion):
            self._guion = guion
            self.llamadas = []

        def complete(self, prompt):
            self.llamadas.append({"modelo": self.modelo, "entrada": 1000, "salida": 500})
            costes.append((tmp_path / "design_cost.md").exists())
            return self._guion.complete(prompt)

    cliente = Medido(Guion([json.dumps(_spec(0.0))] + [json.dumps(_correccion(0.0))] * 5))
    presupuesto = Presupuesto(2.0, {"deepseek-chat": {"in_usd_per_mtok": 0.28,
                                                      "out_usd_per_mtok": 0.42}})
    presupuesto.vigila(cliente, "Mechanism Designer")

    design_mechanism(
        "un brazo", MechanismDesignerAgent(cliente, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO), tmp_path, _freecadcmd(),
        min_gap_mm=0.1, animar=False, presupuesto=presupuesto,
    )

    # Ya existía antes de la última llamada: se va escribiendo por el camino.
    assert costes[-1] is True


def test_dos_fallos_iguales_salvo_los_numeros_cuentan_como_repeticion():
    """«se quedó a 9.38 mm» y «se quedó a 0.32 mm» son el mismo muro. Sin
    esto, el sistema quema rondas creyendo que avanza."""
    from orchestrator.mechanisms.flow import huella_de_fallo

    a = "- «pawl» no llega a apoyarse en «rueda» con t = 30: se queda a 9.38 mm"
    b = "- «pawl» no llega a apoyarse en «rueda» con t = 90: se queda a 0.32 mm"
    c = "- «pawl» y «base» se solapan (3 mm³ en común)"

    assert huella_de_fallo(a) == huella_de_fallo(b)
    assert huella_de_fallo(a) != huella_de_fallo(c)


def _spec_con_plan(z, causa, cambio):
    s = _spec(z)
    s["fix_plan"] = {"causa": causa, "cambio": cambio, "espera": "que deje de chocar"}
    return s


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_al_corregir_hay_que_declarar_causa_y_cambio(tmp_path):
    """Sin plan, el agente vuelve a proponer a ciegas y nadie sabe qué
    intentó. El plan es dato: se guarda y se compara."""
    mecanico = Guion([
        json.dumps(_spec(0.0)),                                  # ronda 1: choca
        json.dumps(_spec(0.0)),                                  # corrección SIN plan: se rechaza
        json.dumps(_spec_con_plan(0.5, "el brazo rozaba la base", "subo el brazo 0.5 mm")),
    ])
    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO), tmp_path, _freecadcmd(),
        min_gap_mm=0.1, animar=False,
    )

    assert informe.ok
    assert "plan" in mecanico.prompts[2].lower()        # se le exigió el plan
    assert informe.rounds[-1].plan["cambio"] == "subo el brazo 0.5 mm"


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_repetir_el_mismo_plan_ante_el_mismo_fallo_es_atasco(tmp_path):
    """Proponer tres veces la misma idea contra el mismo muro es atasco,
    aunque cambien los números."""
    mismo = _spec_con_plan(0.0, "el brazo roza", "lo subo un poco")
    mecanico = Guion([json.dumps(_spec(0.0))] + [json.dumps(mismo)] * 6)

    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(mecanico, CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO), tmp_path, _freecadcmd(),
        min_gap_mm=0.1, animar=False,
    )

    assert informe.stopped_because == "atascado"
    texto = (tmp_path / "blocked.md").read_text(encoding="utf-8")
    assert "Qué intentó" in texto and "lo subo un poco" in texto
    assert "Qué puedes hacer" in texto


def test_la_huella_del_plan_mira_que_piezas_toca_no_como_lo_redacta():
    """El plan es prosa: dos redacciones distintas de la misma idea no se
    repiten nunca literalmente, así que el atasco no saltaba y el bucle
    corría hasta agotar el presupuesto."""
    from orchestrator.mechanisms.flow import huella_de_plan

    a = {"causa": "el pawl roza la rueda", "cambio": "subo pawl 0.5 mm y alejo rueda",
         "espera": "que no choquen"}
    b = {"causa": "creo que el pawl toca la rueda antes de tiempo",
         "cambio": "muevo el pawl 0.8 mm hacia arriba, separando la rueda",
         "espera": "dejar de chocar"}
    c = {"causa": "el muelle no empuja", "cambio": "cambio el muelle por uno de lámina",
         "espera": "que empuje"}

    piezas = ["pawl", "rueda", "muelle"]
    assert huella_de_plan(a, piezas) == huella_de_plan(b, piezas)   # misma idea, otra redacción
    assert huella_de_plan(a, piezas) != huella_de_plan(c, piezas)   # idea distinta


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_tres_veces_la_misma_idea_con_otras_palabras_es_atasco(tmp_path):
    planes = [
        {"causa": "el brazo roza la base", "cambio": "subo el brazo 0.4 mm", "espera": "que no roce"},
        {"causa": "parece que el brazo toca la base", "cambio": "elevo el brazo 0.6 mm",
         "espera": "no rozar"},
        {"causa": "el brazo sigue rozando la base", "cambio": "muevo el brazo 0.7 mm arriba",
         "espera": "que deje de rozar"},
    ]
    especs = [json.dumps(_spec(0.0))]
    for p in planes:
        s = _spec(0.0)
        s["fix_plan"] = p
        especs.append(json.dumps(s))
    informe = design_mechanism(
        "un brazo", MechanismDesignerAgent(Guion(especs * 3), CATALOGO, PERFIL, (235, 235, 250), 0.1),
        PartDesignerAgent(DisenadorDePiezas(), CATALOGO), tmp_path, _freecadcmd(),
        min_gap_mm=0.1, animar=False,
    )

    assert informe.stopped_because == "atascado"
    assert len(informe.rounds) <= 4
