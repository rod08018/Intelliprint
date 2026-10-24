"""Laminado con PrusaSlicer (F1.12 (laminado) + F1.13 (slicing)).

El laminado de una pieza no necesita un LLM: es una llamada determinista
a PrusaSlicer y leer las estadísticas que deja en el G-code. El "Slicing
Agent" solo tendrá trabajo de verdad cuando haya que agrupar varias piezas
en placas (F3.13 (placas)).
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import yaml

from orchestrator.schemas.slicing_report import SlicingReport
from orchestrator.schemas.uso import USOS, Uso  # noqa: F401  (se reexportan)

_MACOS = "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"


class LaminadoFallido(RuntimeError):
    """PrusaSlicer no produjo un G-code utilizable."""


class UsoDesconocido(KeyError):
    """Un uso que no está en la tabla."""


def ajustes_de_uso(uso: str, catalogo: Path) -> dict[str, str]:
    """Los cambios sobre el perfil base que pide `uso`, como texto de .ini.

    `catalogo` es la carpeta config/slicing/ de quien lamina: el puente lo
    resuelve en la SUYA, igual que el perfil."""
    tabla = yaml.safe_load((Path(catalogo) / "usos.yaml").read_text(encoding="utf-8"))
    if uso not in tabla:
        raise UsoDesconocido(f"el uso {uso!r} no existe. Hay: {sorted(tabla)}")
    return {k: str(v) for k, v in (tabla[uso] or {}).items()}


def prusaslicer() -> str | None:
    ruta = (
        os.environ.get("PRUSASLICER")
        or shutil.which("prusa-slicer")
        or (_MACOS if Path(_MACOS).exists() else None)
    )
    return ruta


def parse_tiempo(texto: str) -> int:
    """'1d 2h 3m 4s' → segundos. PrusaSlicer omite las unidades que valen 0."""
    unidades = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * unidades[u] for n, u in re.findall(r"(\d+)([dhms])", texto))


def _dato(gcode: str, patron: str) -> str | None:
    m = re.search(patron, gcode, re.MULTILINE)
    return m.group(1).strip() if m else None


def slice_stl(stl: Path, perfil: Path, salida: Path,
              ajustes: dict[str, str] | None = None) -> SlicingReport:
    ejecutable = prusaslicer()
    if ejecutable is None:
        raise LaminadoFallido("PrusaSlicer no encontrado (define PRUSASLICER)")
    if not Path(perfil).exists():
        raise LaminadoFallido(f"perfil de laminado inexistente: {perfil}")

    # Los ajustes van en un segundo perfil que se carga DESPUÉS y pisa al
    # primero: como opciones sueltas habría que traducir cada clave, y los
    # interruptores (`ironing`) no se escriben igual en la línea de órdenes.
    with tempfile.TemporaryDirectory() as tmp:
        cargar = ["--load", str(perfil)]
        if ajustes:
            extra = Path(tmp) / "ajustes.ini"
            extra.write_text("".join(f"{k} = {v}\n" for k, v in ajustes.items()),
                             encoding="utf-8")
            cargar += ["--load", str(extra)]
        proceso = subprocess.run(
            [ejecutable, *cargar, "--export-gcode", "--output", str(salida), str(stl)],
            capture_output=True, text=True, timeout=600,
        )
    if proceso.returncode != 0 or not Path(salida).exists():
        raise LaminadoFallido(
            f"PrusaSlicer falló (código {proceso.returncode}):\n{proceso.stderr[-800:]}"
        )

    gcode = Path(salida).read_text(encoding="utf-8", errors="ignore")
    filamento = _dato(gcode, r"^; filament used \[mm\] = ([\d.]+)")
    gramos = _dato(gcode, r"^; total filament used \[g\] = ([\d.]+)") or _dato(
        gcode, r"^; filament used \[g\] = ([\d.]+)"
    )
    tiempo = _dato(gcode, r"^; estimated printing time \(normal mode\) = (.+)$")
    soportes = _dato(gcode, r"^; support_material = (\d)")

    if filamento is None or gramos is None or tiempo is None:
        raise LaminadoFallido("el G-code no trae las estadísticas esperadas")

    # SlicingReport rechaza 0 g con filamento gastado: si el perfil no
    # tuviera densidad, el fallo saltaría aquí y no en el resumen del gate.
    return SlicingReport(
        plate=1,
        filament_mm=float(filamento),
        grams=float(gramos),
        time_s=parse_tiempo(tiempo),
        needs_supports=soportes == "1",
        parts=[Path(stl).stem],
    )


def elegir_laminador(raiz: Path, env) -> "Callable[[Path, Path], SlicingReport]":
    """Cómo se lamina aquí: en el host por el puente, o con el binario local.

    PrusaSlicer se queda FUERA del contenedor a propósito (F0.4 (proxy)): es
    el programa con el que la persona comprueba qué va a imprimir antes de
    mandarlo a la máquina, y tiene que ser el suyo, con su versión y sus
    ajustes. FreeCAD sí va dentro, porque nadie lo mira: construye y calla.

    Con `PRUSASLICER_BRIDGE` definido se lamina en el host; sin él, con el
    binario de siempre. Un solo sitio decide, para que el grafo y el CLI no
    tengan que saber dónde está corriendo el sistema.
    """
    from orchestrator.impresion import perfil_activo

    perfil = perfil_activo(raiz).laminado
    destino = env.get("PRUSASLICER_BRIDGE")
    if not destino:
        catalogo = Path(raiz) / "config" / "slicing"
        return lambda stl, salida, uso="general": slice_stl(
            stl, catalogo / perfil, salida, ajustes=ajustes_de_uso(uso, catalogo))

    from orchestrator.hostpaths import a_ruta_del_host
    from orchestrator.mcp.client import ClienteMCP

    workspace = env.get("INTELLIPRINT_WORKSPACE") or "/workspace"
    host_workspace = env.get("HOST_WORKSPACE") or ""
    herramienta = env.get("PRUSASLICER_BRIDGE_TOOL") or "laminar"
    cliente = ClienteMCP(destino)

    def laminar(stl: Path, salida: Path, uso: str = "general") -> SlicingReport:
        # El NOMBRE del uso, nunca sus ajustes: el host lo resuelve en su
        # tabla. Y solo si no es «general», para que un puente sin
        # reiniciar siga laminando lo de siempre.
        extra = {"uso": uso} if uso != "general" else {}
        respuesta = cliente.llamar(
            herramienta,
            **extra,
            # as_posix() y no str(): la ruta del contenedor es POSIX
            # SIEMPRE, y str() de un Path en Windows daría barras
            # invertidas que el traductor no reconoce como suyas.
            stl=a_ruta_del_host(Path(stl).as_posix(), workspace, host_workspace),
            salida=a_ruta_del_host(Path(salida).as_posix(), workspace, host_workspace),
            # El NOMBRE del perfil, no su ruta: el catálogo lo resuelve el
            # host dentro de su config/slicing/. La ruta del contenedor
            # (/app/config/…) allí no existe.
            perfil=perfil,
        )
        if not respuesta.get("ok"):
            # Traducirlo aquí: dejar pasar el diccionario reventaría más
            # tarde con un KeyError que no dice qué falló.
            raise LaminadoFallido(
                respuesta.get("error") or "el host no dijo por qué falló"
            )
        return SlicingReport(**{
            c: respuesta[c] for c in SlicingReport.model_fields if c in respuesta
        })

    return laminar
