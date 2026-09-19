"""Grafo del proyecto (F1.14) y versionado git por etapa (F1.15).

Las dependencias (agentes, construcción, laminado) se inyectan: así el
grafo se prueba en milisegundos sin LLM ni FreeCAD. Los tests de esas
piezas por separado ya existen; aquí se prueba el ORDEN, las barreras y
la persistencia.
"""

import io
import subprocess

import pytest

from orchestrator.graph import Dependencias, crear_grafo
from orchestrator.human.adapters.cli import CliAdapter
from orchestrator.schemas.part_result import PartResult
from orchestrator.schemas.recipe import Recipe, RecipeStep
from orchestrator.schemas.slicing_report import SlicingReport
from orchestrator.schemas.spec import Spec

_SPEC = Spec(
    title="soporte de vaso",
    description="sujeta un vaso a un tubo de 68 mm",
    product_class="static_part",
    printer="ankermake_m5_petg",
    material="PETG",
)


class Registro:
    """Anota qué se llamó y en qué orden."""

    def __init__(self, falla_disenar_veces: int = 0) -> None:
        self.llamadas: list[str] = []
        self._fallos = falla_disenar_veces

    def draft(self, peticion):
        self.llamadas.append("requirements")
        return _SPEC

    def disenar(self, spec, carpeta, part):
        self.llamadas.append("diseno")
        if self._fallos:
            self._fallos -= 1
            raise RuntimeError("se cayó la luz")
        (carpeta / f"{part}.stl").write_text("solid x\nendsolid x\n")
        receta = Recipe(part=part, steps=[RecipeStep(generator="generate_plate")])
        return receta, PartResult(part=part, volume_mm3=1.0, bbox_mm=[1, 1, 1], solids=1)

    def laminar(self, stl, salida):
        self.llamadas.append("laminado")
        salida.write_text("; gcode\n")
        return SlicingReport(plate=1, filament_mm=1000, grams=3, time_s=60,
                             needs_supports=False)


def _deps(reg: Registro, respuesta: str, tmp_path) -> Dependencias:
    return Dependencias(
        requirements=reg,
        disenar=reg.disenar,
        laminar=reg.laminar,
        port=CliAdapter(entrada=io.StringIO(respuesta), salida=io.StringIO()),
        workspace=tmp_path / "projects",
    )


def test_el_grafo_recorre_admision_diseno_y_laminado_en_orden(tmp_path):
    reg = Registro()
    grafo = crear_grafo(_deps(reg, "sí\n", tmp_path), tmp_path / "state.sqlite")

    final = grafo.invoke({"peticion": "soporte de vaso"}, {"configurable": {"thread_id": "p1"}})

    assert reg.llamadas == ["requirements", "diseno", "laminado"]
    assert final["estado"] == "SLICED"
    assert final["slicing"]["grams"] == 3


def test_sin_confirmacion_el_grafo_se_queda_en_intake_y_no_toca_el_disco(tmp_path):
    reg = Registro()
    grafo = crear_grafo(_deps(reg, "no\n", tmp_path), tmp_path / "state.sqlite")

    final = grafo.invoke({"peticion": "soporte"}, {"configurable": {"thread_id": "p2"}})

    assert reg.llamadas == ["requirements"]
    assert final["estado"] == "INTAKE"
    assert not (tmp_path / "projects").exists()


def test_el_estado_sobrevive_a_una_caida_y_no_repite_la_admision(tmp_path):
    """Si el diseño revienta a mitad, reanudar con el mismo proyecto
    continúa desde ahí. No se te vuelve a preguntar lo que ya confirmaste."""
    reg = Registro(falla_disenar_veces=1)
    db = tmp_path / "state.sqlite"
    config = {"configurable": {"thread_id": "p3"}}

    with pytest.raises(RuntimeError, match="se cayó la luz"):
        crear_grafo(_deps(reg, "sí\n", tmp_path), db).invoke({"peticion": "x"}, config)

    # proceso nuevo, grafo nuevo, misma base de datos: se reanuda
    final = crear_grafo(_deps(reg, "", tmp_path), db).invoke(None, config)

    assert final["estado"] == "SLICED"
    assert reg.llamadas.count("requirements") == 1
    assert reg.llamadas.count("diseno") == 2


def test_cada_etapa_deja_un_commit_en_el_proyecto(tmp_path):
    """F1.15: el proyecto es un repo git con un commit por etapa, para poder
    volver atrás y ver qué cambió entre iteraciones."""
    reg = Registro()
    grafo = crear_grafo(_deps(reg, "sí\n", tmp_path), tmp_path / "state.sqlite")

    final = grafo.invoke({"peticion": "soporte"}, {"configurable": {"thread_id": "p4"}})

    log = subprocess.run(
        ["git", "-C", final["proyecto"], "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    assert log == ["laminado: SLICED", "diseño: PARTS_BUILT", "admisión: SPEC_READY"]
