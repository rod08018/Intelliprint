"""Derivación de aserciones de QA desde el contrato de interfaces.

Ver SISTEMA_MULTIAGENTE.md § 3.3. Una interfaz resuelta contiene todo lo
necesario para escribir sus propias pruebas: esto es lo que convierte al
QA de opinión en verificación (ADR-003).
"""

from typing import Literal

from pydantic import BaseModel

from mech_toolkit.geometry import (
    Cylinder,
    Frame,
    Placement,
    axis_distance,
    find_bore,
    find_holes_on_circle,
)
from mech_toolkit.profile import PrinterProfile


class SinReglaDeDerivacion(NotImplementedError):
    """No hay derivación escrita para este tipo de interfaz.

    Se falla en vez de devolver una lista vacía: cero aserciones haría que
    la capa 1 del QA aprobara cualquier cosa para esa interfaz, y el hueco
    pasaría desapercibido.
    """


class AssertionSpec(BaseModel):
    """Cota exigida, aún sin medir.

    Deliberadamente NO lleva el valor medido: así no se puede construir un
    informe de QA con aserciones sin comprobar.
    """

    name: str
    interface: str
    expected: float
    tol: float
    unit: Literal["mm", "count"] = "mm"
    frame: Frame
    """DÓNDE buscar, en coordenadas del ensamble (ADR-011)."""
    query: dict
    """QUÉ buscar. Se deriva del tipo de interfaz, no lo escribe nadie."""


def _frame(interface) -> Frame:
    return Frame(origin=interface.frame.origin, axis=interface.frame.axis)


def _asiento_de_rodamiento(interface, profile: PrinterProfile) -> list[AssertionSpec]:
    holgura = profile.fit_mm(interface.fit)
    donde = {"frame": _frame(interface), "query": {"kind": "bore"}}
    return [
        AssertionSpec(
            name="hole_diameter",
            interface=interface.id,
            expected=interface.nominal_mm["od"] + holgura,
            tol=profile.assertion_tol_mm,
            **donde,
        ),
        AssertionSpec(
            name="hole_depth",
            interface=interface.id,
            expected=interface.nominal_mm["width"],
            tol=profile.assertion_tol_mm,
            **donde,
        ),
    ]


def _patron_de_tornillos(interface, profile: PrinterProfile) -> list[AssertionSpec]:
    metrica = f"M{int(interface.nominal_mm['d'])}"
    donde = {
        "frame": _frame(interface),
        "query": {"kind": "holes_on_circle", "pcd_mm": interface.nominal_mm["pcd"]},
    }
    return [
        AssertionSpec(
            name="hole_diameter",
            interface=interface.id,
            # Dato tabulado del perfil, afinado con impresiones reales: gana
            # al cálculo nominal+holgura, que para tornillería queda holgado.
            expected=profile.hole_mm(f"{metrica}_through"),
            tol=profile.assertion_tol_mm,
            **donde,
        ),
        AssertionSpec(
            name="hole_count",
            interface=interface.id,
            expected=interface.nominal_mm["count"],
            tol=0,
            unit="count",
            **donde,
        ),
        AssertionSpec(
            name="pcd",
            interface=interface.id,
            expected=interface.nominal_mm["pcd"],
            tol=profile.assertion_tol_mm,
            **donde,
        ),
    ]


_REGLAS = {
    "bearing_seat": _asiento_de_rodamiento,
    "bolt_pattern": _patron_de_tornillos,
}


def derive_assertions(interface, profile: PrinterProfile) -> list[AssertionSpec]:
    regla = _REGLAS.get(interface.type)
    if regla is not None:
        return regla(interface, profile)
    raise SinReglaDeDerivacion(
        f"no hay derivación de aserciones para el tipo {interface.type!r} "
        f"(interfaz {interface.id}). Escríbela en mech_toolkit.assertions "
        "antes de usar este tipo: sin ella el QA no verificaría nada."
    )


def _medir(spec: AssertionSpec, caras: list[Cylinder], frame: Frame) -> float | None:
    tipo = spec.query["kind"]
    if tipo == "bore":
        taladro = find_bore(caras, frame)
        if taladro is None:
            return None
        return {"hole_diameter": 2 * taladro.radius, "hole_depth": taladro.length}[spec.name]

    if tipo == "holes_on_circle":
        agujeros = find_holes_on_circle(caras, frame, spec.query["pcd_mm"])
        if spec.name == "hole_count":
            return float(len(agujeros))  # 0 es una medida, no una ausencia
        if not agujeros:
            return None
        if spec.name == "hole_diameter":
            # El PEOR agujero: si uno solo está mal, la aserción tiene que caer.
            return max((2 * a.radius for a in agujeros), key=lambda d: abs(d - spec.expected))
        if spec.name == "pcd":
            return 2 * sum(axis_distance(a, frame) for a in agujeros) / len(agujeros)

    raise SinReglaDeDerivacion(f"no sé medir {spec.name!r} con la consulta {spec.query}")


def measure(
    specs: list[AssertionSpec], caras: list[Cylinder], placement: Placement
) -> list[tuple[AssertionSpec, float | None]]:
    """Mide cada aserción buscando la geometría donde el contrato dice.

    None = no se encontró nada ahí. El QA lo trata como FAIL (ADR-011).
    """
    return [(s, _medir(s, caras, placement.to_local(s.frame))) for s in specs]
