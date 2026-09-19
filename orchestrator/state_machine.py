"""Máquina de estados del proyecto. Ver SISTEMA_MULTIAGENTE.md § 4."""

from orchestrator.human.port import HumanPort, Question


class TransicionProhibida(ValueError):
    """La transición no existe en el grafo."""


class AprobacionRequerida(PermissionError):
    """La transición existe, pero es una barrera humana sin aprobar."""


TRANSICIONES: dict[str, set[str]] = {
    "INTAKE": {"SPEC_READY"},
    "SPEC_READY": {"DECOMPOSED"},
    "DECOMPOSED": {"SYSTEM_DESIGNED"},
    "SYSTEM_DESIGNED": {"INTERFACES_RESOLVED"},
    "INTERFACES_RESOLVED": {"PARTS_IN_PROGRESS"},
    "PARTS_IN_PROGRESS": {"ASSEMBLED"},
    "ASSEMBLED": {"TESTED", "PARTS_IN_PROGRESS"},
    "TESTED": {"SLICED", "PARTS_IN_PROGRESS"},
    "SLICED": {"RELEASED"},
    "RELEASED": set(),
}
"""`INTAKE` solo sale hacia `SPEC_READY`. No hay arista hacia ningún estado
de diseño: la barrera de admisión no se puede rodear (ADR-008)."""


BARRERAS_HUMANAS: dict[tuple[str, str], str] = {
    ("INTAKE", "SPEC_READY"): "confirmación de la admisión",
    ("INTERFACES_RESOLVED", "PARTS_IN_PROGRESS"): "gate humano #1",
    ("SLICED", "RELEASED"): "gate humano #2",
}
"""Las tres barreras son la misma operación: preguntar y esperar. Se
implementan una vez, y el `HumanPort` decide por qué canal se pregunta."""


def transition(desde: str, hacia: str, *, approved: bool = False) -> str:
    permitidos = TRANSICIONES.get(desde)
    if permitidos is None:
        raise TransicionProhibida(f"estado desconocido: {desde!r}")
    if hacia not in permitidos:
        raise TransicionProhibida(
            f"{desde} no puede pasar a {hacia}. "
            f"Desde {desde} solo se puede ir a {sorted(permitidos) or 'ningún estado'}."
        )
    barrera = BARRERAS_HUMANAS.get((desde, hacia))
    if barrera and not approved:
        raise AprobacionRequerida(
            f"{desde} → {hacia} requiere {barrera}. El sistema no avanza solo."
        )
    return hacia


def advance(
    desde: str,
    hacia: str,
    *,
    port: HumanPort,
    project: str | None = None,
    resumen: str = "",
) -> str:
    """Avanza pidiendo aprobación por el `HumanPort` si hay barrera.

    Es el único sitio donde se conectan la máquina de estados y el canal
    humano. Cualquier código que llame a `transition(approved=True)` por
    su cuenta se está saltando la pregunta.
    """
    barrera = BARRERAS_HUMANAS.get((desde, hacia))
    if barrera is None:
        return transition(desde, hacia)

    texto = f"{resumen}\n\n¿Confirmas? ({barrera})" if resumen else f"¿Confirmas? ({barrera})"
    aprobado = port.confirm(Question(text=texto.strip(), project=project))
    return transition(desde, hacia, approved=aprobado)
