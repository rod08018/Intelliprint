"""Crafty con un proyecto por partes (F7.3 (arbol)).

Por Telegram no hay árbol que mirar: Crafty tiene que saber qué espera a
la persona (el desglose, el concepto de una pieza, el visto bueno a una
pieza diseñada) y tener con qué pasar su respuesta. Sin eso, la obra se
para y Crafty contesta «por aprobar» sin saber qué enseñar.
"""

from orchestrator import obra as O
import orchestrator.mcp_server as servidor
from tests.test_interfaz_web import _esperar_registro
from tests.test_mcp_proyectos import ws  # noqa: F401 (la fixture)
from tests.test_obra import _disenar_nodo, _obra

ID = "2026-11-09-pan-tilt"


def _empezar(ws, aprobada=False):
    carpeta = ws / "projects" / ID
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text("un pan-tilt con dos SG90\n", encoding="utf-8")
    O.guardar(carpeta, _obra(), por="prueba")
    if aprobada:
        O.aprobar(carpeta, por="prueba")
    return carpeta


def test_el_estado_trae_el_desglose_que_hay_que_ensenar(ws):
    _empezar(ws)
    r = servidor.estado_proyecto(ID)
    assert r["estado"] == "por aprobar"
    assert "Soporte de inclinación" in r["desglose"]
    assert [n["id"] for n in r["nodos"]] == ["base", "giro", "inclinacion"]


def test_el_estado_trae_el_concepto_del_nodo_que_toca(ws):
    carpeta = _empezar(ws, aprobada=True)
    (carpeta / "nodos" / "base").mkdir(parents=True)
    (carpeta / "nodos" / "base" / "concepto.json").write_text("{}", encoding="utf-8")
    (carpeta / "nodos" / "base" / "concepto.md").write_text("**Idea:** caja", encoding="utf-8")
    r = servidor.estado_proyecto(ID)
    assert r["siguiente"] == "base" and "caja" in r["concepto"]
    assert {n["id"]: n["estado"] for n in r["nodos"]}["giro"] == "bloqueado"


def test_una_obra_se_pide_con_su_orden(ws, monkeypatch):
    import sys
    monkeypatch.setattr(servidor, "_orden_obra",
                        lambda: [sys.executable, "-c", "import sys; print(sys.argv)", "obra"])
    r = servidor.disenar_obra("un pan-tilt con dos SG90")
    assert "error" not in r, r
    assert "'obra'" in _esperar_registro(ws / "projects" / r["proyecto"])


def test_pieza_lista_la_ficha_y_sigue(ws):
    carpeta = _empezar(ws, aprobada=True)
    _disenar_nodo(carpeta, "base")
    r = servidor.pieza_lista(ID, "base")
    assert "error" not in r, r
    assert (carpeta / "fichas" / "obra-base.yaml").exists()
    assert "--continuar" in _esperar_registro(carpeta)


def test_rehacer_pieza_dice_que_se_rehace_con_ella(ws):
    carpeta = _empezar(ws, aprobada=True)
    _disenar_nodo(carpeta, "base")
    O.dar_por_lista(carpeta, "base", por="prueba")
    _disenar_nodo(carpeta, "giro")
    r = servidor.rehacer_pieza(ID, "base", cambio="más alta")
    assert r["rehechos"] == ["base", "giro"], r
