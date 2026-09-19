"""Encaje físico entre una pieza y su hardware (F2.20).

Encajar NO es "intersección nula": eso cuenta tocarse como encajar, y en
FDM los agujeros salen algo más pequeños, así que un saliente de Ø22 en un
taladro de Ø22 no entra. Encajar es tener una holgura radial mayor o igual
que la que pide el perfil de la impresora.
"""

from pydantic import BaseModel

from mech_toolkit.geometry import Cylinder, Frame, find_boss, find_bore
from mech_toolkit.profile import PrinterProfile


class FitResult(BaseModel):
    ok: bool
    clearance_mm: float | None
    """Holgura radial medida. None si falta el agujero o el saliente."""
    required_mm: float
    min_bore_mm: float | None = None
    """Diámetro mínimo que debería tener el agujero. Es lo que hace el
    motivo accionable: el Part Designer recibe qué valor poner, no solo
    que algo falla (el mismo principio que el reintento con el error)."""
    motivo: str


def check_fit(
    caras_pieza: list[Cylinder],
    frame_pieza: Frame,
    caras_hardware: list[Cylinder],
    frame_hardware: Frame,
    profile: PrinterProfile,
    fit: str = "clearance",
) -> FitResult:
    """Holgura entre el agujero de la pieza y el saliente del hardware.

    Cada uno se busca en su propio sistema de coordenadas y en su propio
    frame: la pieza donde el contrato dice que va el agujero, el hardware
    donde su geometría dice que está su cara de montaje.
    """
    requerida = profile.fit_mm(fit) / 2  # el perfil da holgura en diámetro
    agujero = find_bore(caras_pieza, frame_pieza)
    if agujero is None:
        return FitResult(ok=False, clearance_mm=None, required_mm=requerida,
                         motivo="no hay agujero donde el contrato dice que va")
    saliente = find_boss(caras_hardware, frame_hardware)
    if saliente is None:
        return FitResult(ok=False, clearance_mm=None, required_mm=requerida,
                         motivo="el hardware no tiene saliente en su cara de montaje")

    holgura = agujero.radius - saliente.radius
    ok = holgura >= requerida - 1e-9
    minimo = 2 * (saliente.radius + requerida)
    motivo = (
        f"holgura radial {holgura:.3f} mm "
        f"{'≥' if ok else '<'} {requerida:.3f} mm que pide el ajuste {fit!r}: "
        f"agujero Ø{2 * agujero.radius:.2f}, saliente Ø{2 * saliente.radius:.2f}"
    )
    if not ok:
        motivo += f". El agujero tiene que ser de al menos Ø{minimo:.2f}"
    return FitResult(ok=ok, clearance_mm=holgura, required_mm=requerida,
                     min_bore_mm=minimo, motivo=motivo)
