"""Tarea de diseño de una pieza.

Ver SISTEMA_MULTIAGENTE.md § 4, reglas 1, 2 y 5.
"""

from orchestrator.schemas.part_task import PartTask


def _tarea(iterations: int) -> PartTask:
    return PartTask(
        part="dedo_der",
        state="QA",
        iterations=iterations,
        interfaces=["IF-003"],
    )


def test_una_pieza_agota_sus_reintentos_a_las_tres_iteraciones():
    """Regla 2: máximo 3 iteraciones por pieza.

    Sin tope, una pieza que el modelo no sabe hacer consume GPU en bucle.
    Al agotarse, la regla 5 dice qué sigue: escalar y luego preguntar.
    """
    assert _tarea(2).can_retry is True
    assert _tarea(3).can_retry is False
