"""Laminar en el PrusaSlicer del host desde el contenedor (F1.13 (slicing)).

PrusaSlicer NO va dentro del contenedor: es el programa con el que la
persona mira qué va a imprimir, y tiene que ser el suyo. Cuando el sistema
corre en un contenedor, el laminado se le pide al host por el puente
(scripts/host_bridge.py).

Cuando no hay puente configurado —el sistema corriendo nativo en el PC—
sigue llamando al binario de siempre. Es la misma función para los dos.
"""

from pathlib import Path

import pytest
from mcp.server import MCPServer

from orchestrator.slicing import LaminadoFallido, elegir_laminador

HOST = r"C:\repo\workspace"


@pytest.fixture
def puente():
    """Un puente de verdad, en este proceso: prueba el protocolo, no un
    simulacro de él."""
    mcp = MCPServer("puente-de-prueba")
    recibido = {}

    @mcp.tool()
    def laminar(stl: str, salida: str, perfil: str = "ankermake_m5_petg.ini") -> dict:
        recibido.update(stl=stl, salida=salida, perfil=perfil)
        return {"ok": True, "gcode": salida, "plate": 1, "filament_mm": 554.35,
                "grams": 1.69, "time_s": 343, "needs_supports": False,
                "parts": ["cubo"]}

    @mcp.tool()
    def laminar_mal(stl: str, salida: str, perfil: str = "x") -> dict:
        return {"ok": False, "error": "no encuentro el STL: C:\repo\no.stl"}

    mcp.recibido = recibido
    return mcp


def test_con_puente_configurado_lamina_en_el_host(puente):
    laminar = elegir_laminador(
        Path("."),
        {"PRUSASLICER_BRIDGE": puente, "INTELLIPRINT_WORKSPACE": "/workspace",
         "HOST_WORKSPACE": HOST},
    )
    informe = laminar(Path("/workspace/p/cubo.stl"), Path("/workspace/p/cubo.gcode"))

    assert informe.grams == 1.69
    assert informe.time_s == 343


def test_las_rutas_que_recibe_el_host_son_las_suyas(puente):
    """El host no sabe qué es `/workspace`: si se le manda la ruta del
    contenedor, PrusaSlicer no encuentra el archivo y el fallo no dice por
    qué."""
    laminar = elegir_laminador(
        Path("."),
        {"PRUSASLICER_BRIDGE": puente, "INTELLIPRINT_WORKSPACE": "/workspace",
         "HOST_WORKSPACE": HOST},
    )
    laminar(Path("/workspace/p/cubo.stl"), Path("/workspace/p/cubo.gcode"))

    assert puente.recibido["stl"] == HOST + r"\p\cubo.stl"
    assert puente.recibido["salida"] == HOST + r"\p\cubo.gcode"


def test_se_manda_el_NOMBRE_del_perfil_no_su_ruta(puente):
    """El perfil lo resuelve el host en su config/slicing/. Mandar la ruta
    del contenedor (/app/config/…) nombraría un archivo que allí no
    existe."""
    laminar = elegir_laminador(
        Path("."),
        {"PRUSASLICER_BRIDGE": puente, "INTELLIPRINT_WORKSPACE": "/workspace",
         "HOST_WORKSPACE": HOST},
    )
    laminar(Path("/workspace/p/cubo.stl"), Path("/workspace/p/cubo.gcode"))

    assert puente.recibido["perfil"] == "ankermake_m5_petg.ini"


def test_un_fallo_del_host_llega_como_fallo_de_laminado(puente):
    """Y con el motivo. Un `{"ok": False}` sin traducir reventaría más
    tarde como un KeyError sin relación con lo que pasó."""
    laminar = elegir_laminador(
        Path("."),
        {"PRUSASLICER_BRIDGE": puente, "INTELLIPRINT_WORKSPACE": "/workspace",
         "HOST_WORKSPACE": HOST, "PRUSASLICER_BRIDGE_TOOL": "laminar_mal"},
    )
    with pytest.raises(LaminadoFallido, match="no encuentro el STL"):
        laminar(Path("/workspace/p/cubo.stl"), Path("/workspace/p/cubo.gcode"))


def test_sin_puente_se_usa_el_binario_de_siempre(monkeypatch, tmp_path):
    """El sistema nativo en el PC no cambia de comportamiento."""
    llamadas = []
    monkeypatch.setattr(
        "orchestrator.slicing.slice_stl",
        lambda stl, perfil, salida: llamadas.append((stl, perfil, salida)),
    )
    laminar = elegir_laminador(tmp_path, {})
    laminar(Path("a.stl"), Path("a.gcode"))

    assert llamadas == [(Path("a.stl"), tmp_path / "config/slicing/ankermake_m5_petg.ini",
                         Path("a.gcode"))]
