"""La interfaz web: ver los proyectos, bajarlos y abrirlos en PrusaSlicer
(F5.5 (web)).

Corre dentro del contenedor y se ve desde el navegador del PC. Todo lo que
toca lo toca en `workspace/`, y el identificador de un proyecto llega por
la URL: es texto que escribe cualquiera, así que se trata como tal.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server import MCPServer

from orchestrator.web.app import (
    ProyectoDesconocido, crear_app, empaquetar, piezas_de, resolver_proyecto)

HOST = r"C:\repo\workspace"


@pytest.fixture
def ws(tmp_path):
    """Un workspace con un proyecto aprobado y uno archivado."""
    bueno = tmp_path / "projects" / "2026-09-20-trinquete"
    (bueno / "parts" / "rueda").mkdir(parents=True)
    (bueno / "parts" / "pawl").mkdir(parents=True)
    (bueno / "parts" / "rueda" / "rueda.stl").write_text("solid r\nendsolid r\n", encoding="utf-8")
    (bueno / "parts" / "pawl" / "pawl.stl").write_text("solid p\nendsolid p\n", encoding="utf-8")
    (bueno / "request.md").write_text("un trinquete\n", encoding="utf-8")
    (bueno / "rounds.json").write_text('[{"number": 1, "title": "t", "feedback": ""}]', encoding="utf-8")
    # El versionado por proyecto, F1.15 (versionado), deja un .git dentro.
    (bueno / ".git").mkdir()
    (bueno / ".git" / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")

    viejo = tmp_path / "archivo" / "2026-09-01-leva"
    viejo.mkdir(parents=True)
    (viejo / "request.md").write_text("una leva\n", encoding="utf-8")
    (viejo / "rounds.json").write_text('[{"number": 1, "title": "t", "feedback": "choca"}]', encoding="utf-8")
    return tmp_path


# --- Qué proyecto se pide ------------------------------------------------


def test_un_proyecto_se_encuentra_por_su_id(ws):
    assert resolver_proyecto("2026-09-20-trinquete", ws) == ws / "projects" / "2026-09-20-trinquete"


def test_tambien_se_encuentran_los_archivados(ws):
    """Archivar no es borrar: un intento fallido es la única prueba de por
    qué algo no funcionó, y tiene que poder bajarse."""
    assert resolver_proyecto("2026-09-01-leva", ws) == ws / "archivo" / "2026-09-01-leva"


@pytest.mark.parametrize("malo", [
    "..", "../..", "../../etc", "2026-09-20-trinquete/../../..",
    "a/b", r"a\b", "/etc/passwd", r"C:\Windows", "",
])
def test_un_id_que_no_es_un_nombre_se_rechaza(ws, malo):
    """El id viene de la URL. Sin esto, bajar "el proyecto ../../" sería
    bajar lo que hay dos carpetas por encima del workspace."""
    with pytest.raises(ProyectoDesconocido):
        resolver_proyecto(malo, ws)


def test_un_id_que_no_existe_se_rechaza(ws):
    with pytest.raises(ProyectoDesconocido):
        resolver_proyecto("2099-01-01-nada", ws)


# --- El zip ----------------------------------------------------------------


def test_el_zip_lleva_el_proyecto_dentro_de_una_carpeta_con_su_nombre(ws):
    """Al descomprimir, que no se desparramen los archivos por Descargas."""
    datos = empaquetar(ws / "projects" / "2026-09-20-trinquete")
    nombres = set(zipfile.ZipFile(io.BytesIO(datos)).namelist())

    assert "2026-09-20-trinquete/parts/rueda/rueda.stl" in nombres
    assert "2026-09-20-trinquete/request.md" in nombres


def test_el_zip_no_lleva_el_git_interno_del_proyecto(ws):
    """Es el historial del sistema, no el diseño: engorda la descarga y no
    es lo que se quiere al bajar un proyecto."""
    nombres = zipfile.ZipFile(io.BytesIO(
        empaquetar(ws / "projects" / "2026-09-20-trinquete"))).namelist()
    assert not [n for n in nombres if "/.git/" in n or n.endswith("/.git")]


def test_el_contenido_del_zip_es_el_de_los_archivos(ws):
    """Byte a byte lo que hay en disco. El oráculo es el archivo, no un
    literal: en Windows `write_text` escribe CRLF, y un zip que lo
    "arreglara" a LF ya no sería una copia del proyecto."""
    carpeta = ws / "projects" / "2026-09-20-trinquete"
    z = zipfile.ZipFile(io.BytesIO(empaquetar(carpeta)))
    for relativa in ("request.md", "parts/rueda/rueda.stl"):
        assert z.read(f"2026-09-20-trinquete/{relativa}") == (carpeta / relativa).read_bytes()


def test_las_piezas_son_las_stl_de_parts(ws):
    assert sorted(p.name for p in piezas_de(ws / "projects" / "2026-09-20-trinquete")) == [
        "pawl.stl", "rueda.stl"]


# --- Por HTTP ---------------------------------------------------------------


@pytest.fixture
def puente():
    mcp = MCPServer("puente-de-prueba")
    mcp.recibido = []

    @mcp.tool()
    def abrir_en_prusaslicer(stls: list[str], perfil: str = "ankermake_m5_petg.ini") -> dict:
        mcp.recibido.append({"stls": stls, "perfil": perfil})
        return {"ok": True, "abiertas": len(stls), "perfil": perfil}

    return mcp


@pytest.fixture
def web(ws, puente):
    return TestClient(crear_app(ws, puente=puente, host_workspace=HOST))


def test_la_portada_lista_los_proyectos(web):
    html = web.get("/").text
    assert "2026-09-20-trinquete" in html
    assert "2026-09-01-leva" in html


def test_la_lista_tambien_se_puede_pedir_en_json(web):
    ids = {p["id"] for p in web.get("/api/proyectos").json()}
    assert ids == {"2026-09-20-trinquete", "2026-09-01-leva"}


def test_bajar_un_proyecto_devuelve_un_zip_con_su_nombre(web):
    r = web.get("/proyectos/2026-09-20-trinquete.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "2026-09-20-trinquete.zip" in r.headers["content-disposition"]
    assert "2026-09-20-trinquete/parts/rueda/rueda.stl" in zipfile.ZipFile(
        io.BytesIO(r.content)).namelist()


def test_bajar_un_id_malo_es_404_y_no_un_zip(web):
    for malo in ("..", "..%2F..", "no-existe"):
        assert web.get(f"/proyectos/{malo}.zip").status_code == 404


def test_abrir_en_prusaslicer_manda_las_piezas_con_rutas_del_host(web, puente):
    """El PrusaSlicer del PC no sabe qué es /workspace: le llegan sus rutas."""
    r = web.post("/proyectos/2026-09-20-trinquete/abrir")
    assert r.status_code == 200, r.text
    assert sorted(puente.recibido[0]["stls"]) == [
        HOST + r"\projects\2026-09-20-trinquete\parts\pawl\pawl.stl",
        HOST + r"\projects\2026-09-20-trinquete\parts\rueda\rueda.stl",
    ]


def test_abrir_un_proyecto_sin_piezas_lo_dice(web, puente):
    r = web.post("/proyectos/2026-09-01-leva/abrir")
    assert r.status_code == 409
    assert "pieza" in r.json()["detail"]
    assert puente.recibido == []


def test_sin_puente_configurado_abrir_explica_que_falta(ws):
    """Si nadie arrancó el puente en el PC, el botón tiene que decir qué
    hacer, no fallar con un error de red."""
    r = TestClient(crear_app(ws, puente=None, host_workspace=HOST)).post(
        "/proyectos/2026-09-20-trinquete/abrir")
    assert r.status_code == 503
    assert "start-host-mcps" in r.json()["detail"]


# --- Estadísticas, historia de rondas y animación ----------------------------

GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


@pytest.fixture
def ws_con_rondas(ws):
    p = ws / "projects" / "2026-09-20-trinquete"
    (p / "rondas" / "1").mkdir(parents=True)
    (p / "rondas" / "1" / "resultado.json").write_text(json.dumps({
        "ronda": 1, "titulo": "Trinquete", "resuelta": False, "feedback": "- choca",
        "plan": None, "barrido": {"choques": 1},
        "requisitos": [{"descripcion": "avanza un diente", "esperado": 30, "tolerancia": 2,
                        "medido": 29.1, "desviacion": -0.9, "cumple": True}]}), encoding="utf-8")
    (p / "animation.gif").write_bytes(GIF)
    return ws


def test_la_lista_lleva_ronda_coste_y_si_hay_animacion(ws_con_rondas, puente):
    web = TestClient(crear_app(ws_con_rondas, puente=puente, host_workspace=HOST))
    (fila,) = [p for p in web.get("/api/proyectos").json() if p["id"] == "2026-09-20-trinquete"]
    assert fila["ronda"] == 1
    assert fila["animacion"] is True
    assert fila["requisitos"]["cumplen"] == 1
    # La lista no lleva la historia entera: eso es del detalle. (`rondas`
    # existe, pero es el número que ya daba el registro, no la historia.)
    assert not isinstance(fila.get("rondas"), list)
    assert "filas" not in fila["requisitos"]


def test_el_detalle_lleva_la_historia_de_rondas(ws_con_rondas, puente):
    web = TestClient(crear_app(ws_con_rondas, puente=puente, host_workspace=HOST))
    detalle = web.get("/api/proyectos/2026-09-20-trinquete").json()
    assert detalle["rondas"][0]["feedback"] == "- choca"
    assert detalle["requisitos"]["filas"][0]["medido"] == 29.1


def test_la_animacion_se_sirve_como_gif(ws_con_rondas, puente):
    web = TestClient(crear_app(ws_con_rondas, puente=puente, host_workspace=HOST))
    r = web.get("/proyectos/2026-09-20-trinquete/animation.gif")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/gif"
    assert r.content == GIF


def test_sin_animacion_es_404(web):
    assert web.get("/proyectos/2026-09-01-leva/animation.gif").status_code == 404


def test_el_detalle_y_el_gif_no_aceptan_rutas_por_id(web):
    for malo in ("..", "..%2F..", "no-existe"):
        assert web.get(f"/api/proyectos/{malo}").status_code == 404
        assert web.get(f"/proyectos/{malo}/animation.gif").status_code == 404


def test_la_portada_ensena_la_ronda_y_el_gif(ws_con_rondas, puente):
    html = TestClient(crear_app(ws_con_rondas, puente=puente, host_workspace=HOST)).get("/").text
    assert "/proyectos/2026-09-20-trinquete/animation.gif" in html
    assert "ronda 1" in html.lower()
