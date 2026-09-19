"""Capa 1 del QA: del contrato a valores medidos (F2.13 (puente), ADR-011).

interfaz resuelta → aserciones (F2.12 (derive_assertions)) → caras reales del STEP → búsqueda
por contrato → `Assertion` con su valor medido, o `None` si no había nada
donde el contrato dice. El veredicto lo calcula `QaReport`, no esto.
"""

from pathlib import Path

from mech_toolkit.assertions import derive_assertions, measure
from mech_toolkit.geometry import Placement
from mech_toolkit.measure import extract_cylinders
from mech_toolkit.profile import PrinterProfile
from orchestrator.schemas.interface import Interface
from orchestrator.schemas.qa_report import Assertion


def measure_interfaces(
    interfaces: list[Interface],
    step: Path,
    placement: Placement,
    profile: PrinterProfile,
    freecadcmd: str,
) -> list[Assertion]:
    caras = extract_cylinders(step, freecadcmd)
    specs = [s for i in interfaces for s in derive_assertions(i, profile)]
    return [
        Assertion(
            name=s.name, interface=s.interface, expected=s.expected,
            tol=s.tol, unit=s.unit, measured=medido,
        )
        for s, medido in measure(specs, caras, placement)
    ]
