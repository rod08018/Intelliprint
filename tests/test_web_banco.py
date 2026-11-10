"""El banco en la web, para mirar (F7.6 (animacion)).

La ronda de arreglos del 2026-11-09/10 dejó los dos backlogs del banco al
80 %, y en la web no se veía nada: el banco escribe en `workspace/banco/` y
la web solo miraba `workspace/projects/`. «No veo cambios en la web», dijo
el usuario. Lo esperado sale de la carpeta que monta cada test.
"""

from orchestrator import obra as O
from tests.test_interfaz_web import _ws_con_trabajos
from tests.test_obra import _obra
from tests.test_web_obra import _visible

PID = "2026-11-10-031356-un_pan_tilt"
TABLA = """# Banco de piezas — 2026-11-10

**Nota global:** {g} % (8 de 10 exigencias)

| Encargo | Nota | Cumple | No cumple | Sin medir |
|---|---|---|---|---|
| pan_tilt_sg90 | {p} % | 4 | 1 | 0 |
"""


def _corrida(ws):
    corrida = ws / "banco" / "1110-0313"
    carpeta = corrida / "01" / "projects" / PID
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text("un pan-tilt con dos SG90", encoding="utf-8")
    O.guardar(carpeta, _obra(), por="banco")
    O.aprobar(carpeta, por="banco")
    (corrida / "banco.md").write_text(TABLA.format(g=30, p=0), encoding="utf-8")
    # La reanudada es la última palabra de la corrida: es la que se enseña.
    (corrida / "banco_reanudado.md").write_text(TABLA.format(g=80, p=80), encoding="utf-8")
    return carpeta


def test_cada_corrida_del_banco_se_ve_con_su_nota_y_sus_proyectos(tmp_path):
    _corrida(tmp_path)
    web = _ws_con_trabajos(tmp_path)
    assert 'href="/banco"' in web.get("/").text
    r = web.get("/banco")
    assert r.status_code == 200, r.text
    texto = _visible(r.text)
    for parte in ("1110-0313", "80 %", "pan_tilt_sg90"):
        assert parte in texto, parte
    assert "30 %" not in texto and " 0 %" not in texto
    assert f'href="/p/{PID}"' in r.text


def test_un_proyecto_del_banco_se_abre_para_mirar_y_no_se_mezcla_con_los_tuyos(tmp_path):
    _corrida(tmp_path)
    web = _ws_con_trabajos(tmp_path)
    r = web.get(f"/p/{PID}")
    assert r.status_code == 200, r.text
    assert "Del banco" in _visible(r.text) and 'href="/banco"' in r.text
    assert PID not in web.get("/").text


def test_lo_del_banco_no_se_toca_desde_la_web(tmp_path):
    """El banco es una medida: corregir una pieza suya desde la web
    cambiaría lo que se midió sin que constara."""
    _corrida(tmp_path)
    r = _ws_con_trabajos(tmp_path).post(f"/api/proyectos/{PID}/nodos/base/rehacer",
                                        json={"cambio": "más alta"})
    assert r.status_code == 404
