r"""El contenedor y el host no llaman igual al mismo archivo (F0.7 (rutas)).

El orquestador escribe en `/workspace/projects/…` y el PrusaSlicer del
escritorio abre `C:\…\Intelliprint\workspace\projects\…`. Es el MISMO
archivo: una carpeta del host montada dentro del contenedor. Antes de pedirle
al host que lamine hay que traducir el nombre.

El oráculo es la petición literal: dadas las dos raíces, la ruta traducida es
la que se escribe a mano.
"""

import pytest

from orchestrator.hostpaths import RutaFueraDelWorkspace, a_ruta_del_host

WS = "/workspace"
HOST = r"C:\Users\jdr\Desktop\hobbies\Intelliprint\workspace"


def test_una_ruta_del_workspace_se_traduce_a_la_del_host():
    assert a_ruta_del_host(
        "/workspace/projects/2026-09-20-trinquete/parts/rueda/rueda.stl", WS, HOST
    ) == HOST + r"\projects\2026-09-20-trinquete\parts\rueda\rueda.stl"


def test_el_propio_workspace_se_traduce_a_la_raiz_del_host():
    assert a_ruta_del_host("/workspace", WS, HOST) == HOST


def test_un_host_con_barras_de_unix_tambien_vale():
    """En Linux el host sería otra ruta POSIX; traducir no puede exigir
    Windows."""
    assert a_ruta_del_host(
        "/workspace/a/b.stl", WS, "/home/jdr/Intelliprint/workspace"
    ) == "/home/jdr/Intelliprint/workspace/a/b.stl"


def test_una_ruta_fuera_del_workspace_se_rechaza():
    """El puente del host ejecuta un programa sobre el archivo que se le
    nombre. Si el contenedor pudiera nombrar cualquier ruta, `workspace/`
    dejaría de ser el límite que dice § 8.3 y pasaría a serlo la buena fe
    del que escribe la llamada."""
    with pytest.raises(RutaFueraDelWorkspace):
        a_ruta_del_host("/etc/passwd", WS, HOST)


def test_un_rodeo_para_salirse_tampoco_vale():
    """`/workspace/../etc/passwd` empieza por `/workspace` y no está dentro."""
    with pytest.raises(RutaFueraDelWorkspace):
        a_ruta_del_host("/workspace/../etc/passwd", WS, HOST)


def test_un_nombre_que_solo_comparte_prefijo_no_cuela():
    """`/workspace-ajeno` NO está dentro de `/workspace`."""
    with pytest.raises(RutaFueraDelWorkspace):
        a_ruta_del_host("/workspace-ajeno/x.stl", WS, HOST)


def test_sin_raiz_del_host_el_error_dice_que_falta():
    with pytest.raises(RutaFueraDelWorkspace, match="HOST_WORKSPACE"):
        a_ruta_del_host("/workspace/a.stl", WS, "")
