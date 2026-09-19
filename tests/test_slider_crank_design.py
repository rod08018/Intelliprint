"""El Part Designer diseña las piezas del mecanismo a partir de enunciados
que salen de la disposición (F3.14 (mecanismo)).

El oráculo NO es la receta del modelo: es el mecanismo montado. Los ejes
atraviesan los agujeros con la holgura justa, así que un agujero mal
puesto por el modelo choca con su eje en el barrido.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from mech_toolkit.profile import PrinterProfile
from orchestrator.agents.part_designer import PartDesignerAgent
from orchestrator.mechanisms.run import build_mechanism, llm_designer
from orchestrator.mechanisms.slider_crank import SliderCrankLayout
from orchestrator.traceability import untraced
from tests.test_generators import _freecadcmd

PERFIL = PrinterProfile(
    id="ankermake_m5_petg",
    fits={"press_mm": 0.10, "slide_mm": 0.20, "clearance_mm": 0.35},
)
LAY = SliderCrankLayout(stroke_mm=60, profile=PERFIL)


def test_cada_enunciado_lleva_todas_las_cotas_de_su_pieza():
    """Si el enunciado omite una cota, el modelo tiene que inventarla."""
    briefs, recetas = LAY.briefs(), LAY.recipes()
    assert set(briefs) == set(recetas)
    for nombre, receta in recetas.items():
        valores = {abs(float(v)) for p in receta.steps for v in p.params.values()}
        faltan = [v for v in valores if v and f"{v:g} mm" not in briefs[nombre]]
        assert faltan == [], f"{nombre}: el enunciado no dice {faltan}"


def test_cada_enunciado_fija_el_origen_de_la_pieza():
    """Las poses asumen un origen concreto; si el modelo elige otro, el
    ensamble sale descolocado aunque la pieza sea correcta."""
    for nombre, brief in LAY.briefs().items():
        assert "origen" in brief.lower(), nombre


def test_la_trazabilidad_acepta_cotas_negativas():
    """La bancada baja hasta z = -4: el enunciado dice "4 mm por debajo" y
    la receta lleva -4. No es una cota perdida."""
    assert untraced(LAY.briefs()["bancada"], LAY.recipes()["bancada"]) == []


class _Guion:
    """Cliente LLM que responde con recetas fijas, por nombre de pieza."""

    def __init__(self, recetas):
        self._recetas = recetas

    def complete(self, prompt: str) -> str:
        tarea = prompt.split("## Tarea")[-1]
        nombre = next(n for n in self._recetas if f"«{n}»" in tarea)
        return json.dumps(self._recetas[nombre].model_dump())


def _recetas_con(**cambios):
    recetas = LAY.recipes()
    for nombre, params in cambios.items():
        recetas[nombre].steps[0].params.update(params)
    return recetas


needs_freecad = pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")


@needs_freecad
def test_un_disenador_que_sigue_el_enunciado_da_un_mecanismo_sin_choques(tmp_path):
    agente = PartDesignerAgent(_Guion(_recetas_con()), CATALOGO)
    informe = build_mechanism(
        LAY, tmp_path, _freecadcmd(), min_gap_mm=0.1, angulos=[0, 90, 180, 270],
        animar=False, disenar=llm_designer(agente, LAY.briefs(), _freecadcmd()),
    )
    assert informe.ok, [c.motivo for c in informe.collisions]
    assert (tmp_path / "assembly.FCStd").exists()


@needs_freecad
def test_un_agujero_mal_puesto_por_el_modelo_choca_con_su_eje(tmp_path):
    """La biela con 1 mm menos entre centros: la pieza es válida y
    construible, pero su segundo agujero no cae sobre el eje de la corredera."""
    agente = PartDesignerAgent(
        _Guion(_recetas_con(biela={"center_distance_mm": LAY.l - 1})), CATALOGO)
    informe = build_mechanism(
        LAY, tmp_path, _freecadcmd(), min_gap_mm=0.1, angulos=[0, 90],
        animar=False, disenar=llm_designer(agente, LAY.briefs(), _freecadcmd()),
    )
    assert not informe.ok
    assert any("biela" in (c.a, c.b) and "eje_corredera" in (c.a, c.b)
               for c in informe.collisions)
    # El ensamble se guarda igual: es cuando más falta hace abrirlo.
    assert (tmp_path / "assembly.FCStd").exists()


def test_la_disposicion_rechaza_una_bancada_centrada_en_el_origen():
    """Fallo real de DeepSeek: usó generate_plate, que centra la placa en el
    origen con z de 0 a 4, en vez de ponerla bajo z = 0 y en x = 67.5."""
    from orchestrator.schemas.part_result import PartResult

    b = LAY.bounds()["bancada"]
    bien = PartResult(part="bancada", volume_mm3=1, bbox_mm=[1, 1, 1], solids=1,
                      bbox_min=b[0], bbox_max=b[1])
    assert LAY.check_bounds("bancada", bien) is None

    mal = bien.model_copy(update={"bbox_min": [-89, -40, 0], "bbox_max": [89, 40, 5.5]})
    motivo = LAY.check_bounds("bancada", mal)
    assert motivo is not None
    assert "-89" in motivo and f"{b[0][0]:g}" in motivo


@needs_freecad
def test_una_bancada_mal_colocada_vuelve_al_modelo_y_se_corrige(tmp_path):
    # Todas las cotas están (la trazabilidad no la rechaza), pero la placa
    # sube a z = 0 en vez de quedar debajo: invade a las piezas móviles.
    placa = LAY.recipes()["bancada"]
    placa.steps[0].params["z_mm"] = 0

    class Guion(_Guion):
        def __init__(self):
            super().__init__(_recetas_con())
            self.bancadas = 0

        def complete(self, prompt):
            tarea = prompt.split("## Tarea")[-1]
            if "«bancada»" in tarea:
                self.bancadas += 1
                if self.bancadas == 1:
                    return placa.model_dump_json()
            return super().complete(prompt)

    guion = Guion()
    informe = build_mechanism(
        LAY, tmp_path, _freecadcmd(), min_gap_mm=0.1, angulos=[0, 180], animar=False,
        disenar=llm_designer(PartDesignerAgent(guion, CATALOGO), LAY.briefs(), _freecadcmd(),
                             check=LAY.check_bounds),
    )
    assert guion.bancadas >= 2
    assert informe.ok, [c.motivo for c in informe.collisions]
