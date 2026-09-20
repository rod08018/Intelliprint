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


# --- Abrir en PrusaSlicer ------------------------------------------------
#
# El botón "Slice in PrusaSlicer" no lamina a ciegas: ABRE el PrusaSlicer
# de la persona con las piezas y el perfil ya cargados, que es para lo que
# PrusaSlicer se quedó fuera del contenedor —mirar qué va a salir de la
# impresora antes de mandarlo—.


def test_abrir_carga_el_perfil_y_las_piezas(ws, tmp_path):
    from scripts.host_bridge import orden_para_abrir

    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    (catalogo / "ankermake_m5_petg.ini").write_text("; p\n", encoding="utf-8")
    a = ws / "projects" / "p" / "parts" / "a.stl"
    b = ws / "projects" / "p" / "parts" / "b.stl"
    for f in (a, b):
        f.write_text("solid x\nendsolid x\n", encoding="utf-8")

    orden = orden_para_abrir(
        "C:/PS/prusa-slicer.exe", [str(a), str(b)], "ankermake_m5_petg.ini", ws, catalogo)

    assert orden[0] == "C:/PS/prusa-slicer.exe"
    assert orden[1:3] == ["--load", str(catalogo / "ankermake_m5_petg.ini")]
    assert orden[3:] == [str(a.resolve()), str(b.resolve())]


def test_abrir_no_lleva_ninguna_accion_de_exportar(ws, tmp_path):
    """Con `--export-gcode` PrusaSlicer lamina y se cierra sin enseñar
    nada. Abrir es precisamente NO pasarle ninguna acción."""
    from scripts.host_bridge import orden_para_abrir

    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    (catalogo / "m5.ini").write_text("; p\n", encoding="utf-8")
    stl = ws / "projects" / "p" / "parts" / "a.stl"
    stl.write_text("solid x\nendsolid x\n", encoding="utf-8")

    orden = orden_para_abrir("ps.exe", [str(stl)], "m5.ini", ws, catalogo)
    assert not [o for o in orden if o.startswith("--export")]


def test_abrir_algo_de_fuera_del_workspace_se_rechaza(ws, tmp_path):
    from scripts.host_bridge import orden_para_abrir

    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    (catalogo / "m5.ini").write_text("; p\n", encoding="utf-8")
    with pytest.raises(FueraDelWorkspace):
        orden_para_abrir("ps.exe", [str(tmp_path.parent / "x.stl")], "m5.ini", ws, catalogo)


def test_abrir_sin_piezas_es_un_error_y_no_una_ventana_vacia(ws, tmp_path):
    from scripts.host_bridge import orden_para_abrir

    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    (catalogo / "m5.ini").write_text("; p\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ninguna pieza"):
        orden_para_abrir("ps.exe", [], "m5.ini", ws, catalogo)


def test_el_programa_con_ventana_es_el_hermano_del_de_consola():
    """PRUSASLICER apunta a prusa-slicer-console.exe, que no abre ventana.
    El que la abre está al lado."""
    from scripts.host_bridge import ejecutable_con_ventana

    assert ejecutable_con_ventana(
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
    ) == r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe"
    assert ejecutable_con_ventana("/usr/bin/prusa-slicer") == "/usr/bin/prusa-slicer"
