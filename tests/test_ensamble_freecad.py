"""Ver el invento montado en el FreeCAD del PC (F13.14 (ensamble)).

Él, el 2026-11-18: «también el ensamble en FreeCAD me gustaría poder verlo, o
sea, darle clic en algún lado de la app y ver el avión ensamblado». La web
enseñaba una foto y un visor; en FreeCAD solo se podía abrir pieza a pieza.

El contenedor escribe un .FCStd con cada pieza en su sitio (las mallas de la
foto montada, `vista.montado`, y lo de dentro), y el puente del host lo abre
con el FreeCAD del escritorio, como abre PrusaSlicer.
"""

import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server import MCPServer

from orchestrator.web.app import crear_app
from tests.test_generators import _freecadcmd
from tests.test_interfaz_web import ws  # noqa: F401  (un proyecto terminado)

HOST = r"C:\repo\workspace"
AVION = Path("/workspace/projects/2026-11-18-ala-volante-29-piezas-a-mano-sin-modelo")


# --- el puente ---------------------------------------------------------------

def test_el_puente_abre_el_ensamble_con_la_macro_del_repo(tmp_path):
    """La macro es la del repo y el archivo va por el entorno: el contenedor
    no puede mandarle al host código que ejecutar."""
    from scripts.host_bridge import MACRO_ENSAMBLE, orden_para_ver_en_freecad
    fcstd = tmp_path / "p" / "vistas" / "ensamble.FCStd"
    fcstd.parent.mkdir(parents=True)
    fcstd.write_bytes(b"PK")
    orden, entorno = orden_para_ver_en_freecad("freecad.exe", str(fcstd), tmp_path)
    assert orden == ["freecad.exe", str(MACRO_ENSAMBLE)]
    assert entorno == {"INTELLIPRINT_FCSTD": str(fcstd.resolve())}
    assert MACRO_ENSAMBLE.is_file()


def test_el_puente_no_abre_nada_de_fuera_del_workspace(tmp_path):
    from scripts.host_bridge import FueraDelWorkspace, orden_para_ver_en_freecad
    fuera = tmp_path / "x.FCStd"
    fuera.write_bytes(b"PK")
    with pytest.raises(FueraDelWorkspace):
        orden_para_ver_en_freecad("freecad.exe", str(fuera), tmp_path / "ws")


def test_el_puente_solo_abre_documentos_de_freecad(tmp_path):
    """Un .py del workspace se ejecutaría al abrirlo."""
    from scripts.host_bridge import orden_para_ver_en_freecad
    malo = tmp_path / "x.py"
    malo.write_text("print(1)", encoding="utf-8")
    with pytest.raises(ValueError):
        orden_para_ver_en_freecad("freecad.exe", str(malo), tmp_path)


# --- la web ------------------------------------------------------------------

@pytest.fixture
def puente():
    mcp = MCPServer("puente-de-prueba")
    mcp.recibido = []

    @mcp.tool()
    def abrir_en_freecad(fcstd: str) -> dict:
        mcp.recibido.append(fcstd)
        return {"ok": True}

    return mcp


def test_la_web_manda_al_puente_la_ruta_del_host(ws, puente, monkeypatch):
    from orchestrator import vista
    hecho = ws / "projects" / "2026-09-20-trinquete" / "vistas" / "ensamble.FCStd"
    monkeypatch.setattr(vista, "ensamble_fcstd", lambda carpeta, freecadcmd=None: hecho)
    web = TestClient(crear_app(ws, puente=puente, host_workspace=HOST))

    r = web.post("/proyectos/2026-09-20-trinquete/abrir-en-freecad")

    assert r.status_code == 200, r.text
    assert puente.recibido == [HOST + r"\projects\2026-09-20-trinquete\vistas\ensamble.FCStd"]


def test_sin_puente_ver_en_freecad_explica_que_falta(ws):
    web = TestClient(crear_app(ws, puente=None, host_workspace=HOST))
    r = web.post("/proyectos/2026-09-20-trinquete/abrir-en-freecad")
    assert r.status_code == 503
    assert "start-host-mcps" in r.json()["detail"]


def test_la_pagina_del_invento_tiene_el_boton(ws, puente):
    web = TestClient(crear_app(ws, puente=puente, host_workspace=HOST))
    html = web.get("/p/2026-09-20-trinquete").text
    assert 'data-freecad="2026-09-20-trinquete"' in html
    assert "Ver montado en FreeCAD" in html


# --- el ensamble, construido -------------------------------------------------

def _caja_stl(ruta):
    b = Path(ruta).read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    pts = [struct.unpack("<3f", b[84 + k * 50 + 12 + v * 12:84 + k * 50 + 24 + v * 12])
           for k in range(n) for v in range(3)]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


LEER = """
import json, sys, FreeCAD
doc = FreeCAD.openDocument(sys.argv[-2] if sys.argv[-2].endswith('.FCStd') else '{fcstd}')
out = {{}}
for o in doc.Objects:
    if o.TypeId == 'Mesh::Feature':
        b = o.Mesh.BoundBox
        out[o.Label] = {{'caja': [[b.XMin, b.YMin, b.ZMin], [b.XMax, b.YMax, b.ZMax]],
                        'grupo': o.getParentGroup().Label if o.getParentGroup() else None,
                        'color': list(o.Color)[:3] if hasattr(o, 'Color') else None}}
open('{salida}', 'w').write(json.dumps(out))
"""


@pytest.fixture(scope="module")
def ensamble(tmp_path_factory):
    if _freecadcmd() is None or not AVION.is_dir():
        pytest.skip("sin freecadcmd o sin la versión 9 del avión")
    from orchestrator import vista
    copia = tmp_path_factory.mktemp("avion") / AVION.name
    shutil.copytree(AVION, copia, ignore=shutil.ignore_patterns(
        "*.step", "*.FCStd", "vistas", "*.png", "*.gif"))
    fcstd = vista.ensamble_fcstd(copia, _freecadcmd())
    salida = copia / "leido.json"
    guion = copia / "leer.py"
    guion.write_text(LEER.format(fcstd=fcstd.as_posix(), salida=salida.as_posix()),
                     encoding="utf-8")
    subprocess.run([_freecadcmd(), str(guion)], capture_output=True, timeout=600)
    return copia, fcstd, json.loads(salida.read_text(encoding="utf-8"))


def test_el_avion_montado_tiene_sus_29_piezas_lo_comprado_y_lo_de_dentro(ensamble):
    copia, _, leido = ensamble
    piezas = {p.stem for p in copia.glob("nodos/*/parts/*/*.stl")}
    comprado = {p.stem for p in (copia / "comprado").glob("*.stl")}
    dentro = {p.stem for p in (copia / "dentro").glob("*/*.stl")}
    assert len(piezas) == 29
    assert {n for n, o in leido.items() if o["grupo"] == "Impreso"} == piezas
    assert {n for n, o in leido.items() if o["grupo"] == "Comprado"} == comprado
    assert {n for n, o in leido.items() if o["grupo"] == "Dentro"} == dentro


def test_cada_pieza_queda_donde_dice_su_stl(ensamble):
    """Oráculo: la caja de cada STL, leída aquí sin FreeCAD."""
    copia, _, leido = ensamble
    for stl in [*copia.glob("nodos/*/parts/*/*.stl"), *(copia / "comprado").glob("*.stl")]:
        lo, hi = _caja_stl(stl)
        caja = leido[stl.stem]["caja"]
        assert caja[0] == pytest.approx(lo, abs=0.01), stl.stem
        assert caja[1] == pytest.approx(hi, abs=0.01), stl.stem


def test_cada_pieza_lleva_su_color(ensamble):
    """FreeCAD sin ventana no guarda colores de vista: va en una propiedad que
    la macro del puente pinta al abrir."""
    _, _, leido = ensamble
    assert all(o["color"] is not None for o in leido.values())
    assert len({tuple(round(c, 3) for c in o["color"]) for o in leido.values()}) > 2


def test_no_se_rehace_si_no_cambio_nada(ensamble):
    from orchestrator import vista
    copia, fcstd, _ = ensamble
    antes = fcstd.stat().st_mtime_ns
    assert vista.ensamble_fcstd(copia, _freecadcmd()) == fcstd
    assert fcstd.stat().st_mtime_ns == antes
