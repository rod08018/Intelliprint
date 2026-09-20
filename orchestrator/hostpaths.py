r"""Traducir un archivo del contenedor al nombre que tiene en el host
(F0.7 (rutas)).

`workspace/` es una carpeta del host montada dentro del contenedor, así que
cada archivo tiene dos nombres para el mismo contenido:

    contenedor  /workspace/projects/xxx/parts/rueda/rueda.stl
    host        C:\...\Intelliprint\workspace\projects\xxx\parts\rueda\rueda.stl

Hace falta cuando el contenedor le pide al host que haga algo con un archivo
—laminar con el PrusaSlicer del escritorio— porque el programa que lo abre
corre al otro lado del montaje.
"""

import posixpath
from pathlib import PurePosixPath


class RutaFueraDelWorkspace(ValueError):
    """Se pidió traducir algo que no está en la carpeta compartida."""


def _separador(host_workspace: str) -> str:
    """Windows o POSIX, deducido de la raíz del host en vez de del sistema
    donde corre esto: quien traduce es el CONTENEDOR (Linux) y el destino
    puede ser Windows. Mirar `os.sep` aquí daría siempre la respuesta
    equivocada."""
    return "\\" if "\\" in host_workspace else "/"


def a_ruta_del_host(ruta: str, workspace: str, host_workspace: str) -> str:
    """El nombre que tiene `ruta` (del contenedor) visto desde el host.

    Solo traduce lo que está DENTRO de `workspace`. Lo de fuera es un error,
    no un caso a resolver: al otro lado hay un programa que va a abrir el
    archivo que se le nombre, y § 8.3 dice que el límite de lo que el
    sistema toca del PC es `workspace/` y las carpetas que se monten a
    propósito. Si cualquier ruta valiera, el límite sería la buena fe.
    """
    if not host_workspace:
        raise RutaFueraDelWorkspace(
            "no sé cómo se llama el workspace en el host: define HOST_WORKSPACE"
        )

    # normpath resuelve ".." SIN tocar el disco, que es lo que se quiere:
    # /workspace/../etc/passwd empieza por /workspace y no está dentro.
    limpia = PurePosixPath(posixpath.normpath(ruta))
    raiz = PurePosixPath(posixpath.normpath(workspace))

    if not limpia.is_relative_to(raiz):
        raise RutaFueraDelWorkspace(
            f"{ruta!r} está fuera de {workspace!r}: el contenedor solo puede "
            "pedirle al host cosas de la carpeta compartida"
        )

    resto = limpia.relative_to(raiz).parts
    if not resto:
        return host_workspace

    sep = _separador(host_workspace)
    return host_workspace.rstrip("\\/") + sep + sep.join(resto)
