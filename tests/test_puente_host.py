r"""El puente que deja al contenedor usar el PrusaSlicer del escritorio
(F0.4 (proxy)).

PrusaSlicer se queda FUERA del contenedor a propósito: es el programa con el
que la persona mira qué va a imprimir antes de imprimirlo, y tiene que ser
el suyo, el de su versión y sus ajustes. El contenedor no lo lleva dentro;
se lo pide al host por este puente.

El puente ejecuta un programa sobre el archivo que se le nombre, así que lo
que se prueba aquí es sobre todo lo que NO puede hacer.
"""

from pathlib import Path

import pytest

from scripts.host_bridge import FueraDelWorkspace, comprobar_dentro


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "projects" / "p" / "parts").mkdir(parents=True)
    return tmp_path


def test_un_archivo_del_workspace_pasa(ws):
    stl = ws / "projects" / "p" / "parts" / "rueda.stl"
    stl.write_text("solid x\nendsolid x\n", encoding="utf-8")
    assert comprobar_dentro(str(stl), ws) == stl.resolve()


def test_un_archivo_que_aun_no_existe_pasa(ws):
    """La salida del laminado todavía no está escrita cuando se valida."""
    salida = ws / "projects" / "p" / "rueda.gcode"
    assert comprobar_dentro(str(salida), ws) == salida.resolve()


def test_algo_de_fuera_del_workspace_se_rechaza(ws, tmp_path):
    ajeno = tmp_path.parent / "secreto.stl"
    with pytest.raises(FueraDelWorkspace):
        comprobar_dentro(str(ajeno), ws)


def test_un_rodeo_con_dos_puntos_se_rechaza(ws):
    """El contenedor traduce la ruta, pero el que EJECUTA es el puente: no
    puede fiarse de que el otro lado haya validado."""
    with pytest.raises(FueraDelWorkspace):
        comprobar_dentro(str(ws / "projects" / ".." / ".." / "secreto.stl"), ws)


def test_una_ruta_absoluta_del_sistema_se_rechaza(ws):
    with pytest.raises(FueraDelWorkspace):
        comprobar_dentro(r"C:\Windows\System32\config\SAM", ws)


def test_el_perfil_se_busca_por_nombre_y_no_por_ruta(ws, tmp_path):
    """Si el contenedor pudiera mandar la RUTA del perfil, mandaría una
    ruta del host elegida por él. Manda un nombre y lo resuelve el puente
    dentro de config/slicing/."""
    from scripts.host_bridge import FueraDelCatalogo, resolver_perfil

    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    (catalogo / "ankermake_m5_petg.ini").write_text("; perfil\n", encoding="utf-8")

    assert resolver_perfil("ankermake_m5_petg.ini", catalogo).name == "ankermake_m5_petg.ini"
    for intento in ("../../../etc/passwd", r"..\..\secreto.ini", "/etc/passwd"):
        with pytest.raises(FueraDelCatalogo):
            resolver_perfil(intento, catalogo)


def test_un_perfil_que_no_existe_se_distingue_de_uno_prohibido(ws, tmp_path):
    from scripts.host_bridge import FueraDelCatalogo, resolver_perfil

    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    with pytest.raises(FueraDelCatalogo, match="no existe"):
        resolver_perfil("no_lo_tengo.ini", catalogo)
