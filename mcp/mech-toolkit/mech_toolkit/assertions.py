"""Derivación de aserciones de QA desde el contrato de interfaces.

Ver SISTEMA_MULTIAGENTE.md § 3.3. Una interfaz resuelta contiene todo lo
necesario para escribir sus propias pruebas: esto es lo que convierte al
QA de opinión en verificación (ADR-003).
"""

from typing import Literal

from pydantic import BaseModel

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


def _asiento_de_rodamiento(interface, profile: PrinterProfile) -> list[AssertionSpec]:
    holgura = profile.fit_mm(interface.fit)
    return [
        AssertionSpec(
            name="hole_diameter",
            interface=interface.id,
            expected=interface.nominal_mm["od"] + holgura,
            tol=profile.assertion_tol_mm,
        ),
        AssertionSpec(
            name="hole_depth",
            interface=interface.id,
            expected=interface.nominal_mm["width"],
            tol=profile.assertion_tol_mm,
        ),
    ]


def _patron_de_tornillos(interface, profile: PrinterProfile) -> list[AssertionSpec]:
    metrica = f"M{int(interface.nominal_mm['d'])}"
    return [
        AssertionSpec(
            name="hole_diameter",
            interface=interface.id,
            # Dato tabulado del perfil, afinado con impresiones reales: gana
            # al cálculo nominal+holgura, que para tornillería queda holgado.
            expected=profile.hole_mm(f"{metrica}_through"),
            tol=profile.assertion_tol_mm,
        ),
        AssertionSpec(
            name="hole_count",
            interface=interface.id,
            expected=interface.nominal_mm["count"],
            tol=0,
            unit="count",
        ),
        AssertionSpec(
            name="pcd",
            interface=interface.id,
            expected=interface.nominal_mm["pcd"],
            tol=profile.assertion_tol_mm,
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
