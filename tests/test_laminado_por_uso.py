"""Laminado por pieza según su uso (F3.16 (usos)).

Una pieza que aguanta la tensión de un resorte no se lamina igual que una
tapa. El diseñador elige el USO de cada pieza en una lista cerrada; los
números de cada uso los fija `config/slicing/usos.yaml`, que revisa una
persona. El modelo nunca escribe un ajuste de PrusaSlicer.

Lo esperado sale de la tabla aprobada por el usuario el 2026-10-24
(estructural: 5 perímetros, gyroid al 40 %, 6 capas arriba y abajo…).
"""

import inspect
import io
import json
import struct
import subprocess
import typing
import zipfile
from pathlib import Path

import pytest

from orchestrator.perfiles_laminado import claves_conocidas
from orchestrator.slicing import (
    USOS, LaminadoFallido, UsoDesconocido, ajustes_de_uso, prusaslicer, slice_stl)
from tests.test_slicing import _cubo_stl

CATALOGO = Path("config/slicing")


def test_los_usos_son_los_aprobados():
    assert USOS == ("general", "estructural", "estetica", "prototipo")


def test_estructural_lleva_lo_que_se_aprobo():
    assert ajustes_de_uso("estructural", CATALOGO) == {
        "perimeters": "5", "fill_density": "40%", "fill_pattern": "gyroid",
        "top_solid_layers": "6", "bottom_solid_layers": "6"}


def test_general_es_el_perfil_base_sin_cambios():
    assert ajustes_de_uso("general", CATALOGO) == {}


def test_un_uso_desconocido_se_rechaza_diciendo_los_que_hay():
    with pytest.raises(UsoDesconocido, match="estructural"):
        ajustes_de_uso("blindado", CATALOGO)


def test_la_tabla_y_la_lista_cerrada_dicen_los_mismos_usos():
    import yaml

    tabla = yaml.safe_load((CATALOGO / "usos.yaml").read_text(encoding="utf-8"))
    assert set(tabla) == set(USOS)


def test_cada_ajuste_de_la_tabla_lo_entiende_prusaslicer():
    """Una errata en la tabla («perimeter» por «perimeters») PrusaSlicer la
    ignora sin avisar, y la pieza estructural saldría como cualquier otra."""
    import yaml

    tabla = yaml.safe_load((CATALOGO / "usos.yaml").read_text(encoding="utf-8"))
    conocidas = claves_conocidas()
    assert [k for ajustes in tabla.values() for k in (ajustes or {}) if k not in conocidas] == []


# --- El diseñador declara el uso; el esquema lo cierra ---------------------


def test_una_pieza_sin_uso_es_general_y_un_uso_inventado_no_pasa():
    from pydantic import ValidationError

    from orchestrator.schemas.mechanism import PartDef

    base = dict(name="tapa", brief="una tapa", bbox_min=[0, 0, 0], bbox_max=[10, 10, 2])
    assert PartDef(**base).uso == "general"
    assert PartDef(**base, uso="estructural").uso == "estructural"
    with pytest.raises(ValidationError):
        PartDef(**base, uso="blindado")


def test_el_esquema_y_la_tabla_no_se_separan():
    from orchestrator.schemas.mechanism import PartDef

    assert typing.get_args(PartDef.model_fields["uso"].annotation) == USOS


def test_el_prompt_del_disenador_explica_cada_uso():
    prompt = Path("config/agents/mechanism_designer.md").read_text(encoding="utf-8")
    for uso in USOS:
        assert f"`{uso}`" in prompt


# --- Cómo llegan los ajustes a PrusaSlicer ---------------------------------


def test_los_ajustes_van_en_un_segundo_perfil_que_se_carga_despues(monkeypatch, tmp_path):
    """Un segundo `--load` pisa al primero: así los ajustes del uso mandan
    sobre la base sin traducir cada clave a opciones de la línea de órdenes
    (los interruptores, como `ironing`, no se escriben igual ahí)."""
    visto = {}

    def falso(orden, **kw):
        visto["orden"] = orden
        segundo = orden[orden.index("--load", 2) + 1]
        visto["ajustes"] = Path(segundo).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(orden, 1, "", "falso")

    monkeypatch.setattr("orchestrator.slicing.prusaslicer", lambda: "ps")
    monkeypatch.setattr("orchestrator.slicing.subprocess.run", falso)
    base = tmp_path / "base.ini"
    base.write_text("perimeters = 3\n", encoding="utf-8")

    with pytest.raises(LaminadoFallido):
        slice_stl(tmp_path / "a.stl", base, tmp_path / "a.gcode",
                  ajustes={"perimeters": "5", "fill_density": "40%"})

    assert visto["orden"][1:3] == ["--load", str(base)]
    assert visto["orden"].count("--load") == 2
    assert "perimeters = 5" in visto["ajustes"] and "fill_density = 40%" in visto["ajustes"]


def test_el_laminador_local_aplica_el_uso(monkeypatch):
    from orchestrator.slicing import elegir_laminador

    llamadas = []
    monkeypatch.setattr("orchestrator.slicing.slice_stl",
                        lambda stl, perfil, salida, ajustes=None: llamadas.append(ajustes))

    elegir_laminador(Path("."), {})(Path("a.stl"), Path("a.gcode"), uso="estructural")

    assert llamadas == [ajustes_de_uso("estructural", CATALOGO)]


def test_el_puente_recibe_el_uso_y_no_ajustes_libres():
    """Si el puente aceptara ajustes, el contenedor podría meter cualquier
    opción en la orden de PrusaSlicer del host (un `post_process` que
    ejecute un programa, por ejemplo). Recibe el NOMBRE del uso, y el host
    lo resuelve en su propia tabla, igual que el perfil."""
    from scripts.host_bridge import laminar

    parametros = inspect.signature(laminar).parameters
    assert "uso" in parametros
    assert not {"ajustes", "opciones", "config"} & set(parametros)


def test_el_puente_rechaza_un_uso_desconocido(monkeypatch, tmp_path):
    from scripts import host_bridge

    monkeypatch.setattr(host_bridge, "_workspace", lambda: tmp_path)
    stl = tmp_path / "a.stl"
    _cubo_stl(stl)

    r = host_bridge.laminar(str(stl), str(tmp_path / "a.gcode"), uso="blindado")

    assert r["ok"] is False and "blindado" in r["error"]


# --- El proyecto .3mf: una pieza por STL con sus ajustes ---------------------


def _dos_cubos(tmp_path):
    # 30 y 20 mm, no 10: el STL binario de un cubo de 10 mm empieza con
    # bytes que parecen texto, y PrusaSlicer lo lee como STL ASCII y falla.
    a, b = tmp_path / "tapa.stl", tmp_path / "gatillo.stl"
    _cubo_stl(a, 30)
    _cubo_stl(b, 20)
    return a, b


def test_el_3mf_lleva_cada_pieza_con_sus_ajustes(tmp_path):
    from orchestrator.proyecto_3mf import Pieza, escribir_3mf

    a, b = _dos_cubos(tmp_path)
    perfil = CATALOGO / "m5_esun_plamas_precision.ini"
    destino = escribir_3mf(
        [Pieza("tapa", a, {}), Pieza("gatillo", b, ajustes_de_uso("estructural", CATALOGO))],
        perfil, tmp_path / "proyecto.3mf")

    z = zipfile.ZipFile(destino)
    modelo = z.read("3D/3dmodel.model").decode()
    piezas = z.read("Metadata/Slic3r_PE_model.config").decode()
    config = z.read("Metadata/Slic3r_PE.config").decode()

    # Un cubo son 8 vértices y 12 triángulos, cada uno.
    assert modelo.count("<object ") == 2
    assert modelo.count("<vertex ") == 16 and modelo.count("<triangle ") == 24
    # Los ajustes del gatillo, solo en el gatillo.
    objetos = piezas.split("<object ")[1:]
    assert 'value="tapa"' in objetos[0] and 'key="perimeters"' not in objetos[0]
    assert 'value="gatillo"' in objetos[1] and 'key="perimeters" value="5"' in objetos[1]
    # La configuración base viaja dentro: el proyecto se abre sin más.
    assert "; temperature = 210" in config.splitlines()


def test_las_piezas_del_3mf_no_se_montan_unas_sobre_otras(tmp_path):
    """Todas las STL salen con su origen en el mismo sitio: sin colocarlas,
    PrusaSlicer las abriría una dentro de otra."""
    import re

    from orchestrator.proyecto_3mf import Pieza, escribir_3mf

    a, b = _dos_cubos(tmp_path)
    destino = escribir_3mf([Pieza("tapa", a, {}), Pieza("gatillo", b, {})],
                           CATALOGO / "m5_esun_plamas_precision.ini", tmp_path / "p.3mf")

    modelo = zipfile.ZipFile(destino).read("3D/3dmodel.model").decode()
    xs = [float(t.split()[9]) for t in re.findall(r'transform="([^"]+)"', modelo)]
    # La tapa mide 30 mm: entre su origen y el del gatillo, al menos 30.
    assert abs(xs[1] - xs[0]) >= 30


def test_abrir_un_3mf_no_carga_otro_perfil_encima(tmp_path):
    """El proyecto ya lleva su configuración y los ajustes de cada pieza: un
    `--load` encima los pisaría."""
    from scripts.host_bridge import orden_para_abrir

    (tmp_path / "projects").mkdir()
    proyecto = tmp_path / "projects" / "p.3mf"
    proyecto.write_bytes(b"PK")
    catalogo = tmp_path / "slicing"
    catalogo.mkdir()
    (catalogo / "m5.ini").write_text("; p\n", encoding="utf-8")

    orden = orden_para_abrir("ps.exe", [str(proyecto)], "m5.ini", tmp_path, catalogo)

    assert orden == ["ps.exe", str(proyecto.resolve())]


# --- Con PrusaSlicer de verdad (en el host) ----------------------------------


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_una_pieza_estructural_lleva_mas_material_que_una_general(tmp_path):
    stl = tmp_path / "cubo.stl"
    _cubo_stl(stl)
    perfil = CATALOGO / "m5_esun_plamas_precision.ini"

    general = slice_stl(stl, perfil, tmp_path / "g.gcode")
    estructural = slice_stl(stl, perfil, tmp_path / "e.gcode",
                            ajustes=ajustes_de_uso("estructural", CATALOGO))

    assert estructural.grams > general.grams * 1.2
    assert "; perimeters = 5" in (tmp_path / "e.gcode").read_text(errors="ignore")


@pytest.mark.skipif(prusaslicer() is None, reason="PrusaSlicer no disponible")
def test_prusaslicer_lee_los_ajustes_de_cada_pieza_del_3mf(tmp_path):
    """El oráculo es laminar cada pieza por separado con sus ajustes: si
    PrusaSlicer leyera el .3mf sin los ajustes por pieza, los gramos
    coincidirían con los de todo en «general»."""
    from orchestrator.proyecto_3mf import Pieza, escribir_3mf

    a, b = _dos_cubos(tmp_path)
    perfil = CATALOGO / "m5_esun_plamas_precision.ini"
    estructural = ajustes_de_uso("estructural", CATALOGO)
    por_separado = (slice_stl(a, perfil, tmp_path / "a.gcode").grams
                    + slice_stl(b, perfil, tmp_path / "b.gcode", ajustes=estructural).grams)
    todo_general = (slice_stl(a, perfil, tmp_path / "a2.gcode").grams
                    + slice_stl(b, perfil, tmp_path / "b2.gcode").grams)

    proyecto = escribir_3mf([Pieza("tapa", a, {}), Pieza("gatillo", b, estructural)],
                            perfil, tmp_path / "p.3mf")
    r = subprocess.run([prusaslicer(), "--export-gcode", "--output", str(tmp_path / "p.gcode"),
                        str(proyecto)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-800:]
    gcode = (tmp_path / "p.gcode").read_text(errors="ignore")
    import re
    gramos = float(re.search(r"^; total filament used \[g\] = ([\d.]+)", gcode, re.M).group(1))

    assert gramos == pytest.approx(por_separado, rel=0.03)
    assert abs(gramos - todo_general) > abs(gramos - por_separado)
    assert "; temperature = 210" in gcode
