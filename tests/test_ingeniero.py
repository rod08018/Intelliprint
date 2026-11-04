"""El ingeniero: concepto antes que CAD (F3.18 (ingeniero)).

Lo que salía era inusable porque nadie pensaba la pieza: el Part Designer
recibía la petición y dibujaba cajas. La escuadra «para 5 kg» salía con el
espesor que se le ocurría, el gancho sin agujeros y el adaptador sin
holgura. El ingeniero decide cómo se resuelve —camino de carga,
orientación, fijaciones— y el código comprueba lo que se puede contar.
"""

import json
from pathlib import Path

import pytest

from orchestrator.agents.ingeniero import IngenieroAgent
from orchestrator.impresion import perfil_activo
from orchestrator.schemas.spec import Spec
from orchestrator.tasks import spec_to_task

ACTIVO = perfil_activo(Path("."))

SPEC = Spec(
    title="escuadra de repisa", description="aguanta una repisa de 200 mm",
    product_class="static_part", printer="ankermake_m5_plamas", material="PLA+",
    request="escuadra para una repisa de 200 mm de fondo que aguante 5 kg",
    requisitos=[
        {"id": "R1", "tipo": "cota", "texto": "repisa de 200 mm de fondo", "valor": 200,
         "origen": "usuario"},
        {"id": "R2", "tipo": "carga", "texto": "aguante 5 kg", "valor": 5, "unidad": "kg",
         "origen": "usuario"},
    ])


def _concepto(canto_mm=14.0, casos=True, **extra) -> str:
    return json.dumps({
        "idea": "escuadra en L con cartela a 45°, impresa tumbada de lado",
        "camino_de_carga": "la repisa empuja el brazo hacia abajo; la cartela lo lleva a la pared",
        "orientacion": "de lado sobre la cama: las capas quedan paralelas al plano de la L",
        "fijaciones": ["2 tornillos de madera de 4 mm avellanados en el ala de pared"],
        "uso": "estructural",
        "casos_de_carga": [{
            "que": "brazo, en la unión con el ala de pared", "carga_kg": 2.5,
            "brazo_mm": 150, "ancho_mm": 20, "canto_mm": canto_mm,
            "capas_a_traccion": False}] if casos else [],
        "alternativas": ["sin cartela y con más canto: más plástico para lo mismo"],
        "preguntas": [],
        **extra,
    })


class Guion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt, **_):
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


def test_un_concepto_que_no_aguanta_vuelve_con_el_canto_que_hace_falta():
    """2.5 kg a 150 mm con 20 de ancho y 8 de canto: σ = 17.2 MPa, factor 2.0 < 3.
    El ingeniero no recibe «no aguanta», recibe cuánto canto falta."""
    guion = Guion([_concepto(canto_mm=8), _concepto(canto_mm=14)])

    resultado = IngenieroAgent(guion, ACTIVO).concebir(SPEC)

    assert "canto de al menos" in guion.prompts[1]
    assert all(c.cumple for c in resultado.comprobaciones)
    assert resultado.concepto.casos_de_carga[0].canto_mm == 14


def test_si_se_pide_carga_tiene_que_haber_un_caso_de_carga():
    guion = Guion([_concepto(casos=False), _concepto()])

    IngenieroAgent(guion, ACTIVO).concebir(SPEC)

    assert "R2" in guion.prompts[1]


def test_el_ingeniero_ve_la_tornilleria_y_la_resistencia_del_perfil_activo():
    """Sin el perfil, el ingeniero saca las cotas de memoria: M3_through_mm
    nunca llegaba a nadie que diseñara."""
    guion = Guion([_concepto()])
    IngenieroAgent(guion, ACTIVO).concebir(SPEC)
    prompt = guion.prompts[0]
    assert "M3_through_mm" in prompt and "3.3" in prompt
    assert "z_MPa" in prompt
    assert "R2" in prompt and "aguante 5 kg" in prompt


def test_como_mucho_tres_preguntas():
    """Una o dos preguntas, no un interrogatorio (config/openclaw/INTELLIPRINT.md)."""
    muchas = _concepto(preguntas=["a?", "b?", "c?", "d?"])
    guion = Guion([muchas, _concepto(preguntas=["a?"])])
    resultado = IngenieroAgent(guion, ACTIVO).concebir(SPEC)
    assert resultado.concepto.preguntas == ["a?"]


def test_el_texto_para_la_persona_lleva_la_idea_el_calculo_y_las_preguntas():
    guion = Guion([_concepto(preguntas=["¿la repisa es de 18 mm de grueso?"])])
    texto = IngenieroAgent(guion, ACTIVO).concebir(SPEC).texto()
    assert "cartela" in texto
    assert "factor" in texto
    assert "¿la repisa es de 18 mm de grueso?" in texto


def test_el_disenador_recibe_el_concepto_y_las_secciones_minimas():
    """El diseñador tiene que dibujar ESTA idea, y no puede adelgazar la
    sección que el cálculo dio por buena."""
    resultado = IngenieroAgent(Guion([_concepto()]), ACTIVO).concebir(SPEC)
    brief = spec_to_task(SPEC, resultado).brief
    assert "cartela" in brief
    assert "de lado sobre la cama" in brief
    assert "20 x 14" in brief
