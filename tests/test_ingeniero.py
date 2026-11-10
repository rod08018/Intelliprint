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


def test_una_alternativa_de_mas_no_tira_el_concepto():
    """Banco 1110-0128: la plataforma del pan-tilt no llegó a diseñarse
    porque el ingeniero contó tres formas descartadas y el esquema admite
    dos; el concepto murió en sus tres intentos. Las descartadas solo se
    leen: con las dos primeras basta, y no se gasta otra llamada."""
    guion = Guion([_concepto(alternativas=["a", "b", "c"])])
    resultado = IngenieroAgent(guion, ACTIVO).concebir(SPEC)
    assert len(guion.prompts) == 1
    assert resultado.concepto.alternativas == ["a", "b"]


def test_el_texto_para_la_persona_lleva_la_idea_el_calculo_y_las_preguntas():
    guion = Guion([_concepto(preguntas=["¿la repisa es de 18 mm de grueso?"])])
    texto = IngenieroAgent(guion, ACTIVO).concebir(SPEC).texto()
    assert "cartela" in texto
    assert "factor" in texto
    assert "¿la repisa es de 18 mm de grueso?" in texto


# --- partir del concepto anterior ------------------------------------------------------
# Base del pan-tilt (2026-11-09): rehecha para que la brida apretara el servo,
# el concepto nuevo salió sin los tornillos que fijaban la base, y nadie lo
# había pedido. Con el anterior delante, lo que no se pide cambiar se queda,
# y lo que cambia se dice.

def _anterior():
    from orchestrator.schemas.concepto import ConceptoComprobado
    return ConceptoComprobado.model_validate({"concepto": json.loads(_concepto(
        fijaciones=["2 tornillos M4 avellanados para fijar la escuadra a la pared"]))})


def test_con_concepto_anterior_el_ingeniero_lo_ve_con_los_cambios():
    guion = Guion([_concepto(fijaciones=["2 tornillos M4 avellanados a la pared"],
                             cambios=["la cartela, más ancha: lo pide la persona"])])
    IngenieroAgent(guion, ACTIVO).concebir(SPEC, anterior=_anterior(),
                                           cambios="la cartela, más ancha")
    prompt = guion.prompts[0]
    assert "2 tornillos M4 avellanados para fijar la escuadra" in prompt
    assert "la cartela, más ancha" in prompt


def test_con_concepto_anterior_hay_que_decir_que_cambia():
    sin_decir = _concepto(fijaciones=["2 tornillos M4 avellanados a la pared"])
    guion = Guion([sin_decir, _concepto(fijaciones=["2 tornillos M4 avellanados a la pared"],
                                        cambios=["la cartela, más ancha"])])
    r = IngenieroAgent(guion, ACTIVO).concebir(SPEC, anterior=_anterior(), cambios="más ancha")
    assert "`cambios`" in guion.prompts[1]
    assert "**Qué cambia respecto al concepto anterior:**" in r.texto()


def test_quitar_una_fijacion_del_anterior_sin_decirlo_no_vale():
    callada = _concepto(fijaciones=["1 tornillo M3 en la cartela"],
                        cambios=["la cartela, más ancha"])
    guion = Guion([callada, _concepto(fijaciones=["2 tornillos M4 avellanados a la pared"],
                                      cambios=["la cartela, más ancha"])])
    IngenieroAgent(guion, ACTIVO).concebir(SPEC, anterior=_anterior(), cambios="más ancha")
    assert "M4" in guion.prompts[1] and "anterior" in guion.prompts[1]


def test_el_disenador_recibe_el_concepto_y_las_secciones_minimas():
    """El diseñador tiene que dibujar ESTA idea, y no puede adelgazar la
    sección que el cálculo dio por buena."""
    resultado = IngenieroAgent(Guion([_concepto()]), ACTIVO).concebir(SPEC)
    brief = spec_to_task(SPEC, resultado).brief
    assert "cartela" in brief
    assert "de lado sobre la cama" in brief
    assert "20 x 14" in brief


# --- el componente como objeto de verdad (F6.11 (biblioteca)) --------------------------

SENSOR = Spec(
    title="soporte del HC-SR04", description="soporte para el sensor en el frente del robot",
    product_class="static_part", printer="ankermake_m5_plamas", material="PLA+",
    request="Soporte para montar un sensor ultrasónico HC-SR04 en el frente de un robot "
            "hecho con perfil de aluminio 2020.")

COMPONENTES = [
    {"id": "hc-sr04", "como_entra": "por delante, deslizando hacia atrás entre dos guías",
     "como_se_sujeta": "las guías abrazan los cantos del PCB"},
    {"id": "perfil-2020", "como_entra": "la pieza apoya en su cara de delante",
     "como_se_sujeta": "un tornillo M5 con tuerca en T"}]


def test_el_ingeniero_recibe_la_ficha_de_lo_que_nombra_la_peticion():
    """El soporte del HC-SR04 salió sin saber que el sensor lleva integrados
    detrás y pines abajo: el ingeniero solo tenía cifras de una tienda."""
    guion = Guion([_concepto(casos=False, componentes=COMPONENTES)])
    IngenieroAgent(guion, ACTIVO).concebir(SENSOR)
    assert "integrados de atrás" in guion.prompts[0]
    assert "45 × 18 × 30.5 mm" in guion.prompts[0]


def test_lo_que_nombra_la_peticion_tiene_que_ir_en_el_concepto():
    guion = Guion([_concepto(casos=False, componentes=COMPONENTES[1:]),
                   _concepto(casos=False, componentes=COMPONENTES)])
    resultado = IngenieroAgent(guion, ACTIVO).concebir(SENSOR)
    assert "hc-sr04" in guion.prompts[1] and "componentes" in guion.prompts[1]
    assert [c.id for c in resultado.concepto.componentes] == ["hc-sr04", "perfil-2020"]


def test_un_componente_sin_ficha_no_se_puede_poner_en_el_concepto():
    otro = [*COMPONENTES, {"id": "hc-sr05", "como_entra": "x", "como_se_sujeta": "y"}]
    guion = Guion([_concepto(casos=False, componentes=otro),
                   _concepto(casos=False, componentes=COMPONENTES)])
    IngenieroAgent(guion, ACTIVO).concebir(SENSOR)
    assert "hc-sr05" in guion.prompts[1] and "raspberry-pi-4" in guion.prompts[1]


def test_el_disenador_recibe_como_colocar_el_componente_y_su_ficha():
    resultado = IngenieroAgent(Guion([_concepto(casos=False, componentes=COMPONENTES)]),
                               ACTIVO).concebir(SENSOR)
    brief = spec_to_task(SENSOR, resultado).brief
    assert 'kit.componente("hc-sr04"' in brief and "hueco()" in brief
    assert "integrados de atrás" in brief and "deslizando hacia atrás" in brief


def test_la_persona_ve_los_componentes_y_que_no_estan_medidos():
    texto = IngenieroAgent(Guion([_concepto(casos=False, componentes=COMPONENTES)]),
                           ACTIVO).concebir(SENSOR).texto()
    assert "Sensor ultrasónico HC-SR04" in texto and "sin verificar con calibre" in texto


RODAMIENTO = Spec(
    title="soporte del 608ZZ", description="soporte de rodamiento",
    product_class="static_part", printer="ankermake_m5_plamas", material="PLA+",
    request="Soporte para un rodamiento 608ZZ que sujete un eje de 8 mm.")


def test_el_ajuste_de_un_componente_se_nombra_y_no_se_inventa_su_diametro():
    """Proyecto del 608ZZ (2026-11-06): el concepto pedía «interferencia de
    0.1 en un alojamiento Ø21.9», contra el perfil, que pone «press» = +0.10
    sobre el nominal (los agujeros FDM salen pequeños): saldría de 21.7 y el
    rodamiento no entraría. El ajuste se dice por su nombre y el diámetro lo
    pone `hueco()` con el perfil."""
    mal = [{"id": "608zz", "como_entra": "a presión por delante",
            "como_se_sujeta": "a presión en un alojamiento Ø21.9 mm, con reborde detrás"}]
    bien = [{"id": "608zz", "como_entra": "a presión por delante",
             "como_se_sujeta": "reborde detrás de Ø18.5 que toca solo el aro exterior",
             "ajuste": "press"}]
    guion = Guion([_concepto(casos=False, componentes=mal),
                   _concepto(casos=False, componentes=bien)])
    resultado = IngenieroAgent(guion, ACTIVO).concebir(RODAMIENTO)
    assert "21.9" in guion.prompts[1] and "press" in guion.prompts[1]
    brief = spec_to_task(RODAMIENTO, resultado).brief
    assert 'hueco(holgura="press")' in brief
    assert "Ajuste: a presión" in resultado.texto()


def test_el_eje_que_pasa_por_dentro_del_rodamiento_no_es_su_alojamiento():
    """Banco 1109-1949 (2026-11-09): la polea del 608ZZ no llegó a diseñarse.
    Pedía «Ø8.2 para el eje de 8 mm», y la regla lo tomó por el alojamiento
    del rodamiento porque el 608ZZ tiene Ø8 de agujero. La salida que daba
    (`hueco()` con un ajuste) aloja el rodamiento por FUERA: con el agujero
    de dentro no se puede cumplir, y el concepto murió tres veces. Solo el
    Ø exterior es el que se aloja."""
    polea = [{"id": "608zz", "como_entra": "la polea se monta sobre el eje que sale del rodamiento",
              "como_se_sujeta": "taladro central Ø8.2 para el eje de 8 mm, con prisionero M3"}]
    guion = Guion([_concepto(casos=False, componentes=polea)])
    IngenieroAgent(guion, ACTIVO).concebir(RODAMIENTO)
    assert len(guion.prompts) == 1
