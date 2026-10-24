"""El perfil activo: con qué impresora y material se diseña y con qué
perfil de PrusaSlicer se lamina (F1.12 (laminado)).

Lo elige `config/impresion.yaml` y solo él. El nombre del perfil de PETG
estaba escrito en siete sitios; al calibrar la M5 con eSun PLA+
(2026-10-24), cambiar de perfil obligaba a acordarse de todos.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from mech_toolkit.profile import PrinterProfile

ARCHIVO = Path("config") / "impresion.yaml"


class PerfilIncompleto(FileNotFoundError):
    """El perfil activo nombra archivos que no existen."""


@dataclass(frozen=True)
class PerfilActivo:
    impresora: PrinterProfile
    """Holguras y agujeros, para diseñar."""
    datos: dict
    """El YAML de la impresora tal cual: cama, paredes, voladizos."""
    laminado: str
    """NOMBRE del .ini en config/slicing/. Nombre y no ruta: el puente lo
    resuelve en el config/slicing/ del host, donde la ruta del contenedor
    no existe."""

    @property
    def material(self) -> str:
        return self.datos["material"]

    @property
    def densidad_g_cm3(self) -> float:
        return float(self.datos["density_g_cm3"])

    @property
    def cama_mm(self) -> tuple[float, float, float]:
        return tuple(self.datos["bed_mm"][k] for k in "xyz")


def perfil_activo(raiz: Path) -> PerfilActivo:
    raiz = Path(raiz)
    eleccion = yaml.safe_load((raiz / ARCHIVO).read_text(encoding="utf-8"))
    impresora = raiz / "config" / "printers" / f"{eleccion['impresora']}.yaml"
    laminado = raiz / "config" / "slicing" / eleccion["laminado"]
    faltan = [str(p) for p in (impresora, laminado) if not p.is_file()]
    if faltan:
        raise PerfilIncompleto(f"{ARCHIVO} nombra archivos que no existen: {faltan}")
    datos = yaml.safe_load(impresora.read_text(encoding="utf-8"))
    return PerfilActivo(impresora=PrinterProfile(**datos), datos=datos,
                        laminado=eleccion["laminado"])
