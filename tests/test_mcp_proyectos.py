"""Lo que Crafty ve y puede hacer con los proyectos (F5.6 (telegram)).

Fallo real (2026-10-26): pidió UN sargento y el workspace acabó con dos
proyectos y una «corrección» suelta. Crafty no tenía con qué pedir una
versión nueva de un proyecto —solo `disenar_mecanismo`, que empieza otro—
y `listar_proyectos` le daba carpetas, no proyectos con sus versiones.
"""

import json
import os
import sys

import pytest

import orchestrator.mcp_server as servidor
from orchestrator.jobs import JobStore


def _ejecucion(ws, nombre, peticion, feedback="", mecanismo=True):
    carpeta = ws / "projects" / nombre
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    (carpeta / "rounds.json").write_text(
        json.dumps([{"number": 1, "feedback": feedback}]), encoding="utf-8")
    if mecanismo:
        (carpeta / "mechanism.json").write_text(json.dumps(
            {"title": "Sargento", "parts": [{"name": "cuerpo"}, {"name": "mango"}]}), encoding="utf-8")
    viejo = 1_700_000_000
    for f in [carpeta, *carpeta.rglob("*")]:
        os.utime(f, (viejo, viejo))
    return carpeta


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("INTELLIPRINT_WORKSPACE", str(tmp_path))
    store = JobStore(tmp_path / "projects", comando=[sys.executable, "-c", "import sys; print(sys.argv)"])
    monkeypatch.setattr(servidor, "_store", lambda: store)
    return tmp_path


def test_el_mcp_usa_un_solo_gestor_de_trabajos(monkeypatch, tmp_path):
    monkeypatch.setenv("INTELLIPRINT_WORKSPACE", str(tmp_path))
    servidor._STORE = None
    assert servidor._store() is servidor._store()


def test_modificar_un_proyecto_crea_una_version_del_mismo(ws):
    _ejecucion(ws, "2026-10-27-035747-sargento", "Un sargento de banco")

    r = servidor.modificar_proyecto("2026-10-27-035747-sargento", "el mango de 40 mm")

    nueva = ws / "projects" / r["version"]
    assert r["proyecto"] == "2026-10-27-035747-sargento"
    assert json.loads((nueva / "proyecto.json").read_text(encoding="utf-8"))["proyecto"] == \
        "2026-10-27-035747-sargento"
    peticion = (nueva / "request.md").read_text(encoding="utf-8")
    assert peticion.startswith("Un sargento de banco")
    assert "el mango de 40 mm" in peticion


def test_modificar_una_pieza_lo_dice_en_la_peticion(ws):
    _ejecucion(ws, "2026-10-27-035747-sargento", "Un sargento de banco")

    r = servidor.modificar_proyecto("2026-10-27-035747-sargento", "Ø40 mm", pieza="mango")

    peticion = (ws / "projects" / r["version"] / "request.md").read_text(encoding="utf-8")
    assert "«mango»" in peticion


def test_modificar_algo_que_no_es_un_proyecto_lo_dice(ws):
    for malo in ("../../etc", "no-existe"):
        assert "error" in servidor.modificar_proyecto(malo, "algo")


def test_listar_da_proyectos_con_sus_versiones(ws):
    """La misma petición dos veces es UN proyecto con dos versiones."""
    _ejecucion(ws, "2026-10-27-035747-sargento", "Un sargento de banco", feedback="- choca")
    _ejecucion(ws, "2026-10-27-040328-sargento", "Un sargento de banco")

    (sargento,) = servidor.listar_proyectos()

    assert sargento["proyecto"] == "2026-10-27-035747-sargento"
    assert [v["id"] for v in sargento["versiones"]] == [
        "2026-10-27-035747-sargento", "2026-10-27-040328-sargento"]
    assert sargento["mejor"] == "2026-10-27-040328-sargento"


def test_la_version_nueva_sabe_de_que_version_y_pieza_parte(ws):
    """La CLI lee esto para editar la base en vez de diseñar desde cero."""
    from orchestrator.web.versiones import edicion_de

    base = _ejecucion(ws, "2026-10-27-035747-sargento", "Un sargento de banco")
    r = servidor.modificar_proyecto("2026-10-27-035747-sargento", "Ø40 mm", pieza="mango")

    assert edicion_de(ws / "projects" / r["version"], ws) == (base, "Ø40 mm", "mango")


def test_un_diseno_nuevo_no_es_una_edicion(ws):
    from orchestrator.web.versiones import edicion_de

    r = servidor.disenar_mecanismo("Un sargento de banco")
    assert edicion_de(ws / "projects" / r["proyecto"], ws) is None


def test_cambiar_una_pieza_que_no_existe_lo_dice_sin_lanzar_nada(ws):
    _ejecucion(ws, "2026-10-27-035747-sargento", "Un sargento de banco")
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = servidor.modificar_proyecto("2026-10-27-035747-sargento", "más grande", pieza="manivela")

    assert "manivela" in r["error"] and "mango" in r["error"]
    assert sorted(p.name for p in (ws / "projects").iterdir()) == antes
