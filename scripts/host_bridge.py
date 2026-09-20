r"""Puente del host: el contenedor usa el PrusaSlicer del escritorio
(F0.4 (proxy)).

POR QUÉ PRUSASLICER SE QUEDA FUERA. FreeCAD sí va dentro del contenedor:
es una herramienta interna, nadie la mira, construye y calla. PrusaSlicer
no: es donde la persona comprueba QUÉ va a imprimir y CÓMO antes de
mandarlo a la máquina. Eso tiene que pasar en su PrusaSlicer, con su
versión y sus ajustes, no en una copia distinta metida en una imagen.

Así que el contenedor no lo lleva dentro; se lo pide al host por aquí. Es
el puente que `scripts/README.md` decía que existía y no existía.

Este proceso ejecuta un programa sobre el archivo que se le nombre, y quien
lo llama es un contenedor. Por eso todo lo que entra se comprueba AQUÍ,
aunque el otro lado ya lo haya comprobado: el que ejecuta no puede delegar
la comprobación en el que pide.

Se arranca en el host (ver scripts/start-host-mcps.ps1):
    python -m scripts.host_bridge
"""

import os
import subprocess
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from orchestrator.slicing import LaminadoFallido, slice_stl

PUERTO = int(os.environ.get("PRUSASLICER_BRIDGE_PORT", "8102"))


class FueraDelWorkspace(ValueError):
    """Se nombró un archivo que no está en la carpeta compartida."""


class FueraDelCatalogo(ValueError):
    """Se pidió un perfil que no está en config/slicing/."""


def comprobar_dentro(ruta: str, workspace: Path) -> Path:
    """La ruta, resuelta, dentro de `workspace`. Si no, error.

    `resolve()` sin `strict` para que valga también para la SALIDA, que
    todavía no existe cuando se valida.
    """
    destino = Path(ruta).resolve()
    raiz = Path(workspace).resolve()
    if not destino.is_relative_to(raiz):
        raise FueraDelWorkspace(
            f"{ruta!r} no está dentro de {raiz}: el puente solo toca la "
            "carpeta que el contenedor y el host comparten"
        )
    return destino


def resolver_perfil(nombre: str, catalogo: Path) -> Path:
    """El perfil, buscado POR NOMBRE dentro de `config/slicing/`.

    El contenedor manda un nombre, nunca una ruta. Si mandara la ruta,
    estaría eligiendo qué archivo del host se lee, y el catálogo dejaría de
    ser un catálogo.
    """
    if Path(nombre).name != nombre or nombre in ("", ".", ".."):
        raise FueraDelCatalogo(
            f"{nombre!r} no es un nombre de perfil: se pide por nombre, "
            "no por ruta"
        )
    perfil = Path(catalogo) / nombre
    if not perfil.is_file():
        disponibles = sorted(p.name for p in Path(catalogo).glob("*.ini"))
        raise FueraDelCatalogo(
            f"el perfil {nombre!r} no existe en {catalogo}. Hay: {disponibles}"
        )
    return perfil


def ejecutable_con_ventana(consola: str) -> str:
    """El PrusaSlicer que abre ventana, a partir del de consola.

    PRUSASLICER apunta a `prusa-slicer-console.exe` porque es el que sirve
    para laminar sin ventana y devolver la salida. Para ENSEÑAR algo hace
    falta su hermano, que está en la misma carpeta. En Linux es un solo
    programa y se deja como está.
    """
    # Por texto y no con Path: en Linux (donde corre la suite) `\` no separa
    # carpetas, y Path(r"C:\...\x.exe").name devuelve la cadena entera.
    consola_exe = "prusa-slicer-console.exe"
    if consola.lower().endswith(consola_exe):
        return consola[: -len(consola_exe)] + "prusa-slicer.exe"
    return consola


def orden_para_abrir(programa: str, stls: list[str], perfil: str,
                     workspace: Path, catalogo: Path) -> list[str]:
    """La línea de órdenes que abre PrusaSlicer con las piezas y el perfil.

    SIN ninguna acción (`--export-gcode`, `--slice`…): con una acción,
    PrusaSlicer lamina y se cierra sin enseñar nada. Abrir es justo no
    pedirle nada más que cargar.
    """
    if not stls:
        raise ValueError("no hay ninguna pieza que abrir")
    ini = resolver_perfil(perfil, catalogo)
    piezas = [str(comprobar_dentro(s, workspace)) for s in stls]
    return [programa, "--load", str(ini), *piezas]


def _raiz() -> Path:
    for carpeta in [Path.cwd(), *Path.cwd().parents]:
        if (carpeta / "config" / "models.yaml").exists():
            return carpeta
    sys.exit("ejecuta el puente dentro del repo de Intelliprint")


def _workspace() -> Path:
    raiz = _raiz()
    return Path(os.environ.get("INTELLIPRINT_WORKSPACE") or raiz / "workspace")


mcp = MCPServer(
    "prusaslicer-host",
    instructions=(
        "Lamina con el PrusaSlicer instalado en este PC. Las rutas son del "
        "host y tienen que estar dentro del workspace compartido."
    ),
)


@mcp.tool()
def laminar(stl: str, salida: str, perfil: str = "ankermake_m5_petg.ini") -> dict:
    """Lamina un STL con el PrusaSlicer del escritorio y devuelve gramos,
    tiempo y si necesita soportes.

    `stl` y `salida` son rutas del HOST dentro del workspace compartido.
    `perfil` es el NOMBRE de un .ini de config/slicing/.
    """
    workspace = _workspace()
    entrada = comprobar_dentro(stl, workspace)
    destino = comprobar_dentro(salida, workspace)
    ini = resolver_perfil(perfil, _raiz() / "config" / "slicing")

    if not entrada.is_file():
        return {"ok": False, "error": f"no encuentro el STL: {entrada}"}
    try:
        informe = slice_stl(entrada, ini, destino)
    except LaminadoFallido as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "gcode": str(destino), **informe.model_dump()}


@mcp.tool()
def abrir_en_prusaslicer(stls: list[str], perfil: str = "ankermake_m5_petg.ini") -> dict:
    """Abre el PrusaSlicer del escritorio con las piezas y el perfil ya
    cargados, para que la persona vea qué va a imprimir y cómo.

    No espera a que se cierre: la ventana es de la persona, no del sistema.
    """
    workspace = _workspace()
    programa = ejecutable_con_ventana(os.environ.get("PRUSASLICER", ""))
    if not programa or not Path(programa).exists():
        return {"ok": False, "error": f"no encuentro PrusaSlicer: {programa or '(sin definir)'}"}
    try:
        orden = orden_para_abrir(
            programa, stls, perfil, workspace, _raiz() / "config" / "slicing")
    except (ValueError, FueraDelWorkspace, FueraDelCatalogo) as e:
        return {"ok": False, "error": str(e)}
    faltan = [s for s in orden[3:] if not Path(s).is_file()]
    if faltan:
        return {"ok": False, "error": f"no encuentro: {faltan}"}

    # Desenganchado: si el puente se reinicia, la ventana de la persona no
    # se cierra con él.
    subprocess.Popen(orden, **_desenganchado())
    return {"ok": True, "abiertas": len(orden) - 3, "perfil": perfil}


def _desenganchado() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP, "close_fds": True}
    return {"start_new_session": True, "close_fds": True}


@mcp.tool()
def perfiles() -> list[str]:
    """Los perfiles de laminado que este PC tiene disponibles."""
    return sorted(p.name for p in (_raiz() / "config" / "slicing").glob("*.ini"))


def main() -> None:
    # 0.0.0.0 porque quien llama es un contenedor: desde dentro, el host no
    # es "localhost" sino `host.docker.internal`, y un servidor atado a
    # 127.0.0.1 no lo ve llegar.
    #
    # Y por eso mismo hay que nombrar ese host aquí: el servidor MCP valida
    # la cabecera Host para que una página web abierta en este PC no pueda
    # llamar al puente a espaldas de nadie (rebinding de DNS). La defensa se
    # queda; solo se le dice cuál es el nombre legítimo.
    seguridad = TransportSecuritySettings(
        allowed_hosts=[f"host.docker.internal:{PUERTO}", f"localhost:{PUERTO}",
                       f"127.0.0.1:{PUERTO}"],
        allowed_origins=["*"],
    )
    # Sin sesión: el puente hace UNA cosa y tarda minutos. Guardar estado
    # entre llamadas solo serviría para que un reinicio del puente dejara al
    # contenedor hablando con una sesión que ya no existe.
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=PUERTO,
        stateless_http=True,
        json_response=True,
        transport_security=seguridad,
    )


if __name__ == "__main__":
    main()
