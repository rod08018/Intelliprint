"""La interfaz web: ver los proyectos, bajarlos y abrirlos en PrusaSlicer
(F5.5 (web)).

Corre dentro del contenedor y se ve desde el navegador del PC. Todo lo que
toca lo toca en `workspace/`, y el identificador de un proyecto llega por
la URL: es texto que escribe cualquiera, así que se trata como tal.
"""

import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import yaml
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


def _piezas_de_verdad(ws):
    """El .3mf lleva la malla de cada pieza: las STL vacías del fixture no
    sirven para eso."""
    from tests.test_slicing import _cubo_stl

    carpeta = ws / "projects" / "2026-09-20-trinquete"
    _cubo_stl(carpeta / "parts" / "rueda" / "rueda.stl", 30)
    _cubo_stl(carpeta / "parts" / "pawl" / "pawl.stl", 20)
    return carpeta


def test_abrir_en_prusaslicer_manda_un_proyecto_3mf_con_ruta_del_host(ws, puente):
    """El PrusaSlicer del PC no sabe qué es /workspace: le llega su ruta. Y
    le llega UN proyecto con las piezas dentro, cada una con sus ajustes
    (F3.16 (usos)), no las STL sueltas con un solo perfil para todas."""
    _piezas_de_verdad(ws)
    web = TestClient(crear_app(ws, puente=puente, host_workspace=HOST))

    r = web.post("/proyectos/2026-09-20-trinquete/abrir")

    assert r.status_code == 200, r.text
    assert puente.recibido[0]["stls"] == [
        HOST + r"\projects\2026-09-20-trinquete\imprimir\2026-09-20-trinquete.3mf"]
    assert r.json()["abiertas"] == 2


def test_cada_pieza_del_proyecto_lleva_los_ajustes_de_su_uso(ws, puente):
    """El uso lo declaró el diseñador en mechanism.json; los ajustes salen
    de la tabla. Un mechanism.json anterior a los usos no lo trae: general."""
    carpeta = _piezas_de_verdad(ws)
    (carpeta / "mechanism.json").write_text(json.dumps({"parts": [
        {"name": "rueda", "uso": "estructural"}, {"name": "pawl"}]}), encoding="utf-8")
    web = TestClient(crear_app(ws, puente=puente, host_workspace=HOST))

    assert web.post("/proyectos/2026-09-20-trinquete/abrir").status_code == 200

    piezas = zipfile.ZipFile(carpeta / "imprimir" / "2026-09-20-trinquete.3mf").read(
        "Metadata/Slic3r_PE_model.config").decode()
    rueda = next(o for o in piezas.split("<object ")[1:] if 'value="rueda"' in o)
    pawl = next(o for o in piezas.split("<object ")[1:] if 'value="pawl"' in o)
    assert 'key="perimeters" value="5"' in rueda
    assert 'key="perimeters"' not in pawl


def test_la_ficha_dice_el_uso_de_cada_pieza_que_no_es_general(ws, puente):
    carpeta = ws / "projects" / "2026-09-20-trinquete"
    (carpeta / "mechanism.json").write_text(json.dumps({"parts": [
        {"name": "rueda", "uso": "estructural"}, {"name": "pawl"}]}), encoding="utf-8")
    web = TestClient(crear_app(ws, puente=puente, host_workspace=HOST))

    html = web.get("/p/2026-09-20-trinquete").text

    def rotulo(pieza):
        return re.search(rf'piezas/{pieza}\.png.*?<div class="nombre-pieza">(.*?)</div>',
                         html, re.S).group(1)

    assert '<span class="uso">estructural</span>' in rotulo("rueda")
    assert "uso" not in rotulo("pawl")


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


def test_la_lista_lleva_ronda_coste_y_si_hay_animacion(ws_con_rondas):
    (fila,) = [p for p in _grupos(ws_con_rondas) if p["id"] == "2026-09-20-trinquete"]
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


def test_la_portada_ensena_el_gif(ws_con_rondas, puente):
    html = TestClient(crear_app(ws_con_rondas, puente=puente, host_workspace=HOST)).get("/").text
    assert "/proyectos/2026-09-20-trinquete/animation.gif" in html


def test_el_proyecto_dice_que_impide_terminar(ws_con_rondas, puente):
    """Fallo real: «2/2» en la fila con el proyecto en la ronda 9. Los
    requisitos son solo una parte; el proyecto tiene que decir qué falla."""
    p = ws_con_rondas / "projects" / "2026-09-20-trinquete"
    (p / "rounds.json").write_text('[{"number": 1, "title": "t", "feedback": "- choca"}]',
                                   encoding="utf-8")
    web = TestClient(crear_app(ws_con_rondas, puente=puente, host_workspace=HOST))
    html = web.get("/p/2026-09-20-trinquete").text
    assert "No salió" in html and "choca" in html


# --- Pedir un diseño desde la web -------------------------------------------
#
# Antes solo se podía pedir por Telegram o con una orden en la terminal, y
# la orden del README ni siquiera encontraba el archivo dentro del
# contenedor. La web lanza el MISMO trabajo que Crafty (JobStore).


def _ws_con_trabajos(ws):
    """Una web cuyo «diseñador» solo imprime sus argumentos: lo que se
    comprueba es qué se le pide, no el diseño."""
    import sys

    from orchestrator.jobs import JobStore

    imprime = [sys.executable, "-c", "import sys; print(sys.argv)"]
    trabajos = JobStore(ws / "projects", comando=imprime, comando_pieza=imprime)
    return TestClient(crear_app(ws, host_workspace=HOST, trabajos=trabajos,
                                orden_pieza=imprime, orden_obra=imprime))


def _esperar_registro(carpeta, segundos=20):
    import time

    limite = time.time() + segundos
    while time.time() < limite:
        texto = (carpeta / "run.log").read_text(encoding="utf-8")
        if "--archivo" in texto:
            return texto
        time.sleep(0.1)
    raise AssertionError("el trabajo no llegó a arrancar")


def test_pedir_un_diseno_crea_el_proyecto_con_la_peticion_literal(ws):
    web = _ws_con_trabajos(ws)
    peticion = "Un gancho de pared de 40 mm\ncon dos agujeros de 4.5 mm"

    r = web.post("/api/disenar", json={"tipo": "pieza", "peticion": peticion})

    assert r.status_code == 200, r.text
    carpeta = ws / "projects" / r.json()["id"]
    assert (carpeta / "request.md").read_text(encoding="utf-8") == peticion + "\n"
    registro = _esperar_registro(carpeta)
    assert f"'{(carpeta / 'request.md')}'" in registro


@pytest.mark.parametrize("vacia", ["", "   \n\t "])
def test_una_peticion_vacia_no_lanza_nada(ws, vacia):
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/disenar", json={"tipo": "pieza", "peticion": vacia})

    assert r.status_code == 422
    assert sorted(p.name for p in (ws / "projects").iterdir()) == antes


def test_con_otro_proyecto_en_marcha_no_se_lanza_un_segundo(ws):
    """Uno cada vez: dos se pelean por FreeCAD, por el modelo y por el saldo.
    Y el otro puede haberlo lanzado Crafty, desde OTRO contenedor: el
    JobStore de la web no lo conoce, así que se mira el workspace."""
    import os

    otro = ws / "projects" / "2026-10-23-de-crafty"
    otro.mkdir()
    (otro / "request.md").write_text("un gato de tijera\n", encoding="utf-8")
    (otro / "job.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    web = _ws_con_trabajos(ws)

    r = web.post("/api/disenar", json={"tipo": "pieza", "peticion": "un gancho"})

    assert r.status_code == 409
    assert "2026-10-23-de-crafty" in r.json()["detail"]
    assert sorted(p.name for p in (ws / "projects").iterdir()) == [
        "2026-09-20-trinquete", "2026-10-23-de-crafty"]


def test_sin_lanzador_configurado_pedir_explica_que_falta(web):
    r = web.post("/api/disenar", json={"tipo": "pieza", "peticion": "un gancho"})
    assert r.status_code == 503


def test_la_portada_tiene_donde_escribir_la_peticion(ws):
    html = _ws_con_trabajos(ws).get("/").text
    assert '<textarea id="peticion"' in html


def test_lo_que_se_refresca_solo_no_borra_lo_que_estas_escribiendo(ws):
    """La portada se pone al día sola cada 15 s mientras algo trabaja, y
    reemplazaba todo <main>: el texto a medio escribir se perdía. El
    formulario tiene que quedar FUERA de lo que se reemplaza."""
    html = _ws_con_trabajos(ws).get("/").text
    vivo = html.index('<div id="vivo">')
    assert html.index('<textarea id="peticion"') < vivo
    assert 'querySelector("#vivo")' in html
    assert 'querySelector("main")' not in html


# --- Un proyecto es una solicitud; cada ejecución, una versión ---------------
#
# La portada pintaba una fila por carpeta, y una carpeta es una EJECUCIÓN: el
# trinquete del 2026-09-21 salió a la quinta y la lista enseñaba cinco
# «proyectos» con la misma petición, byte a byte. Lo esperado en estos tests
# sale de cómo se construyen los workspaces, no de lo que diga la web.


def _version(ws, nombre, peticion, feedback=None, seccion="projects", requisitos=None):
    """Una ejecución terminada: aprobada si `feedback` es "", fallida si trae
    texto, sin rounds.json (incompleta) si es None."""
    import os

    carpeta = ws / seccion / nombre
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    if feedback is not None:
        (carpeta / "rounds.json").write_text(
            json.dumps([{"number": 1, "title": "t", "feedback": feedback}]), encoding="utf-8")
    if requisitos is not None:
        cumplen, total = requisitos
        (carpeta / "rondas" / "1").mkdir(parents=True)
        (carpeta / "rondas" / "1" / "resultado.json").write_text(json.dumps({
            "ronda": 1, "titulo": "t", "resuelta": not feedback, "feedback": feedback or "",
            "plan": None, "barrido": {"choques": 0},
            "requisitos": [{"descripcion": f"r{i}", "esperado": 1, "tolerancia": 0.1,
                            "medido": 1, "desviacion": 0, "cumple": i < cumplen}
                           for i in range(total)]}), encoding="utf-8")
    # Terminada hace rato: una carpeta recién tocada y sin rounds.json se
    # tomaría por un proyecto en marcha.
    viejo = 1_700_000_000
    for f in [carpeta, *carpeta.rglob("*")]:
        os.utime(f, (viejo, viejo))
    return carpeta


def _grupos(ws):
    """Los proyectos con sus versiones, como los pinta la portada."""
    from orchestrator.web.versiones import proyectos

    return proyectos(ws)


def test_las_ejecuciones_de_la_misma_peticion_son_versiones_de_un_proyecto(ws):
    for hora in ("0252", "0304", "1611"):
        _version(ws, f"2026-09-21-{hora}-gato", "Un gato de tijera\nque suba 10 cm", "- choca")

    (gato,) = [g for g in _grupos(ws) if g["id"].endswith("-gato")]

    # El proyecto se llama como su primera ejecución, y las tres van dentro.
    assert gato["id"] == "2026-09-21-0252-gato"
    assert [v["id"] for v in gato["versiones"]] == [
        "2026-09-21-0252-gato", "2026-09-21-0304-gato", "2026-09-21-1611-gato"]
    assert [v["version"] for v in gato["versiones"]] == [1, 2, 3]


def test_peticiones_distintas_son_proyectos_distintos(ws):
    """Las dos mitades del pastillero se lanzaron en el mismo segundo y son
    dos solicitudes: juntarlas por fecha sería mezclar dos diseños."""
    _version(ws, "2026-09-21-233302-pastillero_3", "Pastillero, mitad de 3 días", "")
    _version(ws, "2026-09-21-233302-pastillero_4", "Pastillero, mitad de 4 días", "")

    ids = {g["id"] for g in _grupos(ws)}

    assert {"2026-09-21-233302-pastillero_3", "2026-09-21-233302-pastillero_4"} <= ids


def test_la_mejor_version_es_la_aprobada_aunque_haya_otras_mas_nuevas(ws):
    _version(ws, "2026-09-21-01-gato", "Un gato", "- choca")
    _version(ws, "2026-09-21-02-gato", "Un gato", "")
    _version(ws, "2026-09-21-03-gato", "Un gato", "- no llega a 10 cm")

    (gato,) = [g for g in _grupos(ws) if g["id"] == "2026-09-21-01-gato"]

    assert gato["mejor"] == "2026-09-21-02-gato"
    # Lo que enseña la fila es lo de la mejor, no lo de la última.
    assert gato["estado"] == "aprobado"


def test_entre_aprobadas_gana_la_mas_reciente(ws):
    """Una modificación aprobada es lo que se pidió después: es la que vale."""
    _version(ws, "2026-09-21-01-gato", "Un gato", "")
    _version(ws, "2026-09-21-02-gato", "Un gato", "")

    (gato,) = [g for g in _grupos(ws) if g["id"] == "2026-09-21-01-gato"]

    assert gato["mejor"] == "2026-09-21-02-gato"


def test_entre_fallidas_gana_la_que_cumple_mas_requisitos(ws):
    _version(ws, "2026-09-21-01-gato", "Un gato", "- choca", requisitos=(2, 3))
    _version(ws, "2026-09-21-02-gato", "Un gato", "- choca", requisitos=(0, 3))

    (gato,) = [g for g in _grupos(ws) if g["id"] == "2026-09-21-01-gato"]

    assert gato["mejor"] == "2026-09-21-01-gato"


def test_un_rediseno_que_cita_otro_proyecto_es_version_de_el(ws):
    """Fallo real: «Rediseño de un mecanismo de Ginebra… Parte del proyecto
    2026-09-21-185919-…» salía como proyecto aparte. La referencia que guardó
    el flujo dice de cuál parte."""
    _version(ws, "2026-09-21-185919-ginebra", "Mecanismo de Ginebra de 4 ranuras", "- atraviesa")
    otro = _version(ws, "2026-09-21-205330-rediseno", "Rediseño del Ginebra", "- choca")
    (otro / "referencias").mkdir()
    (otro / "referencias" / "texto_1.md").write_text(
        "# proyecto 2026-09-21-185919-ginebra (NO llegó a salir entero: úsalo como idea)\n\n"
        "Petición:\n...", encoding="utf-8")

    (ginebra,) = [g for g in _grupos(ws) if "ginebra" in g["id"]]

    assert [v["id"] for v in ginebra["versiones"]] == [
        "2026-09-21-185919-ginebra", "2026-09-21-205330-rediseno"]


def test_las_versiones_pueden_estar_unas_en_archivo_y_otras_no(ws):
    """Archivar no es borrar: un intento fallido archivado sigue siendo una
    versión del proyecto."""
    _version(ws, "2026-09-21-01-gato", "Un gato", "- choca", seccion="archivo")
    _version(ws, "2026-09-21-02-gato", "Un gato", "")

    (gato,) = [g for g in _grupos(ws) if g["id"] == "2026-09-21-01-gato"]

    assert len(gato["versiones"]) == 2
    assert gato["seccion"] == "projects"


def test_la_portada_pinta_un_proyecto_por_solicitud_con_sus_versiones(ws):
    for n in (1, 2, 3):
        _version(ws, f"2026-09-21-0{n}-gato", "Un gato de tijera", "" if n == 2 else "- choca")
    web = TestClient(crear_app(ws, host_workspace=HOST))

    html = web.get("/").text
    assert html.count('href="/p/2026-09-21-01-gato"') == 1
    assert 'href="/p/2026-09-21-02-gato"' not in html

    # En su página están todas, abre con la mejor, y los botones bajan esa.
    pagina = web.get("/p/2026-09-21-01-gato").text
    for n in (1, 2, 3):
        assert f'?v=2026-09-21-0{n}-gato"' in pagina
    assert 'href="/proyectos/2026-09-21-02-gato.zip"' in pagina


# --- Pedir una modificación dentro del proyecto -----------------------------


def _gancho(ws):
    """Una pieza suelta terminada: lo único a lo que se le pide un cambio."""
    base = ws / "projects" / "2026-11-04-gancho"
    base.mkdir()
    (base / "request.md").write_text("un gancho de pared\n", encoding="utf-8")
    (base / "pieza.json").write_text('{"title": "Gancho"}', encoding="utf-8")
    (base / "rounds.json").write_text('[{"number": 1, "title": "t", "feedback": ""}]',
                                      encoding="utf-8")
    return base


def test_pedir_una_modificacion_crea_una_version_del_mismo_proyecto(ws):
    _gancho(ws)
    web = _ws_con_trabajos(ws)

    r = web.post("/api/proyectos/2026-11-04-gancho/modificar",
                 json={"peticion": "que sea 20 mm más largo"})

    assert r.status_code == 200, r.text
    nueva = ws / "projects" / r.json()["id"]
    # El diseñador recibe lo que se pidió al principio y el cambio, literal.
    peticion = (nueva / "request.md").read_text(encoding="utf-8")
    assert peticion.startswith("un gancho de pared\n")
    assert peticion.rstrip().endswith("que sea 20 mm más largo")
    assert "2026-11-04-gancho" in peticion
    _esperar_registro(nueva)
    (gancho,) = [g for g in _grupos(ws) if g["id"] == "2026-11-04-gancho"]
    assert [v["id"] for v in gancho["versiones"]] == ["2026-11-04-gancho", nueva.name]
    assert gancho["versiones"][1]["modificacion"] == "que sea 20 mm más largo"


def test_modificar_una_modificacion_sigue_en_el_proyecto_original(ws):
    _gancho(ws)
    web = _ws_con_trabajos(ws)
    primera = web.post("/api/proyectos/2026-11-04-gancho/modificar",
                       json={"peticion": "20 mm más largo"}).json()["id"]
    _esperar_registro(ws / "projects" / primera)
    # El «diseñador» de prueba no deja lo que deja una pieza: sin rounds.json,
    # una carpeta recién tocada cuenta como en marcha y no dejaría lanzar la
    # segunda; y sin pieza.json no se sabría que es una pieza.
    web.app.state.trabajos._procesos[primera].wait(timeout=20)
    (ws / "projects" / primera / "rounds.json").write_text(
        '[{"number": 1, "title": "t", "feedback": ""}]', encoding="utf-8")
    (ws / "projects" / primera / "pieza.json").write_text('{"title": "Gancho"}', encoding="utf-8")

    r = web.post(f"/api/proyectos/{primera}/modificar", json={"peticion": "y más grueso"})

    assert r.status_code == 200, r.text
    peticion = (ws / "projects" / r.json()["id"] / "request.md").read_text(encoding="utf-8")
    # Las modificaciones se acumulan: la segunda parte de la primera.
    assert "20 mm más largo" in peticion and "y más grueso" in peticion
    (gancho,) = [g for g in _grupos(ws) if g["id"] == "2026-11-04-gancho"]
    assert len(gancho["versiones"]) == 3


@pytest.mark.parametrize("vacia", ["", "  \n "])
def test_una_modificacion_vacia_no_lanza_nada(ws, vacia):
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/proyectos/2026-09-20-trinquete/modificar", json={"peticion": vacia})

    assert r.status_code == 422
    assert sorted(p.name for p in (ws / "projects").iterdir()) == antes


@pytest.mark.parametrize("malo", ["..", "..%2F..", "no-existe"])
def test_modificar_algo_que_no_es_un_proyecto_es_404(ws, malo):
    web = _ws_con_trabajos(ws)
    assert web.post(f"/api/proyectos/{malo}/modificar",
                    json={"peticion": "algo"}).status_code == 404


def test_con_otro_proyecto_en_marcha_no_se_lanza_una_modificacion(ws):
    import os

    otro = ws / "projects" / "2026-10-23-de-crafty"
    otro.mkdir()
    (otro / "request.md").write_text("un gato de tijera\n", encoding="utf-8")
    (otro / "job.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    _gancho(ws)
    web = _ws_con_trabajos(ws)

    r = web.post("/api/proyectos/2026-11-04-gancho/modificar", json={"peticion": "algo"})

    assert r.status_code == 409
    assert "2026-10-23-de-crafty" in r.json()["detail"]


def test_la_version_nueva_dice_que_modificacion_se_pidio(ws):
    _gancho(ws)
    web = _ws_con_trabajos(ws)
    nueva = web.post("/api/proyectos/2026-11-04-gancho/modificar",
                     json={"peticion": "12 mm más ancho"}).json()["id"]

    # En la tira de versiones; la petición entera, en los detalles técnicos.
    assert 'title="12 mm más ancho"' in web.get("/p/2026-11-04-gancho").text
    assert web.get(f"/api/proyectos/{nueva}").json()["peticion"].startswith("un gancho de pared")


def test_pedir_una_pieza_lanza_la_orden_de_piezas_y_no_la_orden_por_omision(ws):
    """F5.17 (pieza): desde la web se elige qué se pide, y una pieza sale
    con la orden de piezas. Cuando no se elegía, un soporte acababa en el
    flujo de mecanismos, que exigía dos piezas."""
    import sys

    from orchestrator.jobs import JobStore

    trabajos = JobStore(ws / "projects", comando=[
        sys.executable, "-c", "import sys; print('OMISION', sys.argv)"])
    web = TestClient(crear_app(ws, host_workspace=HOST, trabajos=trabajos, orden_pieza=[
        sys.executable, "-c", "import sys; print('PIEZA', sys.argv)"]))

    r = web.post("/api/disenar", json={"peticion": "un gancho de pared", "tipo": "pieza"})

    assert r.status_code == 200, r.text
    registro = _esperar_registro(ws / "projects" / r.json()["id"])
    assert "PIEZA" in registro and "OMISION" not in registro


# --- El visto bueno al concepto (F3.20 (concepto)) ---------------------------

def _por_aprobar(ws):
    carpeta = ws / "projects" / "2026-11-04-gancho"
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text("un gancho para la mochila\n", encoding="utf-8")
    (carpeta / "concepto.json").write_text("{}", encoding="utf-8")
    (carpeta / "concepto.md").write_text(
        "# Gancho: el concepto\n\n**Idea:** gancho en J con nervio\n\n"
        "**Necesito que me digas:**\n- ¿cuánto pesa la mochila?\n", encoding="utf-8")
    return carpeta


def test_un_concepto_por_aprobar_se_lee_en_su_pagina_con_sus_botones(ws):
    """Es lo primero que la persona tiene que ver: la idea y las preguntas,
    y con qué aprobarla o contestar. Sin esto, el proyecto se quedaba
    parado sin que nadie supiera por qué."""
    _por_aprobar(ws)
    html = _ws_con_trabajos(ws).get("/p/2026-11-04-gancho").text
    assert "gancho en J con nervio" in html
    assert "¿cuánto pesa la mochila?" in html
    assert 'data-aprobar="2026-11-04-gancho"' in html


URL_LARGA = ("https://thepihut.com/products/ultrasonic-distance-sensor-hcsr04?variant=1"
             "&utm_medium=product_sync&gclid=CjwKCAjwtdeFBhBAEiwAKOIy59#1")


def _concepto_completo(ws, preguntas=()):
    """Como el del HC-SR04 (2026-11-05): idea, carga, impresión, cálculo,
    descartes y catorce medidas con URLs de 250 caracteres, todo en un bloque.
    «Totalmente ilegible: no se sabe qué está aprobando uno»."""
    carpeta = ws / "projects" / "2026-11-05-sensor"
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text(
        "Soporte para un HC-SR04 en un perfil 2020. Se atornilla al perfil con un "
        "tornillo M5 y tuerca en T. Sin soportes de impresión.\n", encoding="utf-8")
    (carpeta / "concepto.json").write_text(json.dumps({
        "concepto": {"idea": "Una cuna que abraza el PCB por los bordes.",
                     "camino_de_carga": "El empuje baja por el respaldo hasta el M5.",
                     "orientacion": "Se apoya en la cama el labio inferior.",
                     "fijaciones": ["1 tornillo M5 con tuerca en T"],
                     "alternativas": ["Atornillar el PCB por sus agujeros de 1 mm."],
                     "preguntas": list(preguntas)},
        "comprobaciones": []}), encoding="utf-8")
    (carpeta / "concepto.md").write_text("# Sensor: el concepto\n\n**Idea:** Una cuna\n",
                                         encoding="utf-8")
    requisito = {"cantidad": None, "seccion_mm": [], "separaciones_mm": [], "unidad": "mm"}
    (carpeta / "spec.yaml").write_text(yaml.safe_dump({"requisitos": [
        {**requisito, "id": "R1", "tipo": "encaje", "origen": "catalogo", "valor": 43.0,
         "texto": "HC-SR04, longitud del PCB: 43 mm (fuente: thepihut.com)"},
        {**requisito, "id": "R5", "tipo": "agujero", "origen": "catalogo", "valor": 8.0,
         "cantidad": 2, "separaciones_mm": [26.0],
         "texto": "HC-SR04, diámetro de los transductores: 8 mm (fuente: thepihut.com)"},
        {**requisito, "id": "R8", "tipo": "fijacion", "origen": "usuario", "valor": 5.0,
         "texto": "Se atornilla al perfil con un tornillo M5 y tuerca en T"},
        {**requisito, "id": "R15", "tipo": "imprimibilidad", "origen": "usuario", "valor": None,
         "texto": "Sin soportes de impresión"},
        {**requisito, "id": "R16", "tipo": "cota", "origen": "estimado", "valor": 3.0,
         "texto": "Pared de la cuna"},
    ]}, allow_unicode=True), encoding="utf-8")
    (carpeta / "investigacion.json").write_text(json.dumps({
        "datos": [{"componente": "HC-SR04", "medida": "longitud del PCB", "valor": 43,
                   "unidad": "mm", "fuente": URL_LARGA, "cita": "Length: 43mm"},
                  {"componente": "HC-SR04", "medida": "diámetro de los transductores",
                   "valor": 8, "unidad": "mm", "fuente": URL_LARGA,
                   "cita": "Transmitter diameter: 8mm"}],
        "sin_encontrar": ["posición de los agujeros respecto a los bordes"]}), encoding="utf-8")
    return carpeta


def _visible(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_el_concepto_dice_que_medidas_se_aprueban_y_de_donde_sale_cada_una(ws):
    _concepto_completo(ws)
    html = _ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text
    texto = _visible(html)

    pediste = texto.index("Lo que pediste")
    internet = texto.index("Buscado en internet")
    sistema = texto.index("Lo decide el sistema")
    assert pediste < texto.index("tornillo M5 y tuerca en T") < internet
    assert internet < texto.index("longitud del PCB") < texto.index("43 mm") < sistema
    assert internet < texto.index("diámetro de los transductores") < sistema
    assert "2 × 8 mm" in texto and "a 26 mm" in texto
    assert sistema < texto.index("Pared de la cuna")
    # La fuente se ve por su dominio; la URL entera, solo en el enlace.
    assert f'href="{URL_LARGA.replace("&", "&amp;")}"' in html
    assert "thepihut.com" in texto and "utm_medium" not in texto
    # La cita, para quien quiera comprobar de dónde salió el número.
    assert "Transmitter diameter: 8mm" in html
    assert "posición de los agujeros respecto a los bordes" in texto


def test_la_idea_a_la_vista_y_el_razonamiento_plegado(ws):
    _concepto_completo(ws)
    html = _ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text
    plegado = html.index('<details class="razonamiento"')
    assert html.index("Una cuna que abraza el PCB") < plegado
    for detalle in ("baja por el respaldo", "labio inferior", "1 tornillo M5",
                    "agujeros de 1 mm"):
        assert html.index(detalle) > plegado, detalle


def test_las_preguntas_van_antes_que_las_medidas(ws):
    _concepto_completo(ws, preguntas=["¿Tu perfil es de ranura 6 u 8?"])
    texto = _visible(_ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text)
    assert texto.index("¿Tu perfil es de ranura 6 u 8?") < texto.index("Lo que pediste")


def test_si_el_juez_cree_que_algo_queda_suelto_lo_avisa_antes_de_aprobar(ws):
    """El primer soporte de giro del pan-tilt (2026-11-09) metía el servo en
    una U abierta por arriba sin nada que lo sujetara; JEV le dio 0.91."""
    carpeta = _concepto_completo(ws)
    (carpeta / "juez.json").write_text('{"suelto": 0.91}', encoding="utf-8")
    texto = _visible(_ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text)
    assert "quede suelto" in texto
    assert texto.index("quede suelto") < texto.index("Aprobar y diseñar")


def test_si_el_juez_no_lo_ve_suelto_no_avisa(ws):
    carpeta = _concepto_completo(ws)
    (carpeta / "juez.json").write_text('{"suelto": 0.4}', encoding="utf-8")
    assert "quede suelto" not in _visible(_ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text)


def test_un_concepto_sin_piezas_no_ofrece_imprimir_ni_descargar(ws):
    _concepto_completo(ws)
    html = _ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text
    assert "data-abrir=" not in html and ".zip\"" not in html
    assert "Todavía no hay imagen" not in html


def test_aprobar_desde_la_web_reanuda_el_diseno(ws):
    carpeta = _por_aprobar(ws)
    web = _ws_con_trabajos(ws)

    r = web.post("/api/proyectos/2026-11-04-gancho/aprobar", json={})

    assert r.status_code == 200, r.text
    assert json.loads((carpeta / "concepto_aprobado").read_text())["por"] == "web"
    assert "--continuar" in _esperar_registro(carpeta)


def test_contestar_desde_la_web_anade_la_respuesta_literal(ws):
    carpeta = _por_aprobar(ws)

    r = _ws_con_trabajos(ws).post("/api/proyectos/2026-11-04-gancho/aprobar",
                                  json={"respuestas": "unos 3 kg"})

    assert r.status_code == 200, r.text
    assert "unos 3 kg" in (carpeta / "respuestas.md").read_text(encoding="utf-8")
    assert not (carpeta / "concepto_aprobado").exists()
    # El concepto contestado queda de punto de partida para el siguiente.
    assert (carpeta / "concepto_anterior.json").exists()


def test_no_se_aprueba_lo_que_no_tiene_concepto(ws):
    r = _ws_con_trabajos(ws).post("/api/proyectos/2026-09-20-trinquete/aprobar", json={})
    assert r.status_code == 409


def test_sin_decir_si_es_pieza_o_mecanismo_no_se_lanza_nada(ws):
    """Fallo real (2026-11-04): el soporte de la Raspberry se pidió desde una
    página abierta antes de que existiera el selector; no mandó `tipo`, la
    API supuso «mecanismo» y salió por el flujo viejo de recetas, sin
    ingeniero ni medidas. Sin tipo no se adivina."""
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/disenar", json={"peticion": "un soporte para una Raspberry"})

    assert r.status_code == 422
    assert sorted(p.name for p in (ws / "projects").iterdir()) == antes


def test_modificar_una_pieza_la_rehace_como_pieza(ws):
    """Fallo real (2026-11-04): cambiar algo del gancho (una pieza) lanzaba
    `intelliprint mecanismo`, la orden por omisión: el flujo viejo."""
    import sys

    from orchestrator.jobs import JobStore

    _gancho(ws)
    trabajos = JobStore(ws / "projects", comando=[
        sys.executable, "-c", "import sys; print('OMISION', sys.argv)"])
    web = TestClient(crear_app(ws, host_workspace=HOST, trabajos=trabajos, orden_pieza=[
        sys.executable, "-c", "import sys; print('PIEZA', sys.argv)"]))

    r = web.post("/api/proyectos/2026-11-04-gancho/modificar", json={"peticion": "más largo"})

    assert r.status_code == 200, r.text
    registro = _esperar_registro(ws / "projects" / r.json()["id"])
    assert "PIEZA" in registro and "OMISION" not in registro


def test_el_concepto_ensena_lo_que_aloja_con_su_ficha(ws):
    """F6.11 (biblioteca): se aprueba también qué componente va dentro, cómo
    entra y de dónde salen sus medidas, que nadie ha medido con calibre."""
    carpeta = _concepto_completo(ws)
    datos = json.loads((carpeta / "concepto.json").read_text(encoding="utf-8"))
    datos["concepto"]["componentes"] = [{
        "id": "hc-sr04", "como_entra": "por delante, deslizando hacia atrás",
        "como_se_sujeta": "dos guías abrazan los cantos del PCB"}]
    (carpeta / "concepto.json").write_text(json.dumps(datos), encoding="utf-8")
    html = _ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text
    texto = _visible(html)
    aloja = texto.index("Lo que aloja")
    assert aloja < texto.index("Sensor ultrasónico HC-SR04") < texto.index("Lo que pediste")
    assert "45 × 18 × 30.5 mm" in texto and "por delante, deslizando hacia atrás" in texto
    assert "sin verificar con calibre" in texto
    assert 'href="https://handsontec.com/dataspecs/sensor/SR-04-Ultrasonic.pdf"' in html


def test_como_entra_y_como_se_sujeta_se_leen_por_separado(ws):
    """Proyecto del 608ZZ (2026-11-06): salía «entra Se introduce a presión…
    .; se sujeta: A presión…», todo pegado en una línea."""
    carpeta = _concepto_completo(ws)
    datos = json.loads((carpeta / "concepto.json").read_text(encoding="utf-8"))
    datos["concepto"]["componentes"] = [{
        "id": "608zz", "como_entra": "Se introduce a presión por la cara de arriba.",
        "como_se_sujeta": "Reborde de Ø18.5 abajo.", "ajuste": "press"}]
    (carpeta / "concepto.json").write_text(json.dumps(datos), encoding="utf-8")
    texto = _visible(_ws_con_trabajos(ws).get("/p/2026-11-05-sensor").text)
    assert "Cómo entra: Se introduce a presión por la cara de arriba." in texto
    assert "Cómo se sujeta: Reborde de Ø18.5 abajo." in texto
    assert "Ajuste: a presión" in texto
    assert ".;" not in texto


# --- Los mecanismos ya no se piden ni se cambian (F9.13 (limpieza)) ------------
#
# El flujo de mecanismos se quitó: lo que se mueve se diseña como conjunto de
# un backlog. Los proyectos que dejó se siguen viendo, pero la web no puede
# lanzar nada sobre ellos, y tiene que decirlo en vez de arrancar otra cosa.


def _nada_nuevo(ws, antes):
    return sorted(p.name for p in (ws / "projects").iterdir()) == antes


def test_pedir_un_mecanismo_se_rechaza_y_dice_que_pedir_en_su_lugar(ws):
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/disenar", json={"tipo": "mecanismo", "peticion": "una bisagra de 40 mm"})

    assert r.status_code == 422
    motivo = json.dumps(r.json(), ensure_ascii=False)
    assert "mecanismo" in motivo and "conjunto" in motivo
    assert _nada_nuevo(ws, antes)


def test_el_dialogo_ofrece_pieza_o_conjunto_y_nada_de_lo_retirado(ws):
    html = _ws_con_trabajos(ws).get("/").text
    assert 'id="tipo"' in html and 'value="pieza"' in html and 'value="obra"' in html
    assert "un backlog: un robot o un conjunto, pieza a pieza" in html
    assert 'value="mecanismo"' not in html
    # «Partir de» solo servía a los mecanismos: con una pieza o un backlog se
    # ignoraba, y partiendo de algo que no fuera un mecanismo el trabajo moría.
    assert "Partir de" not in html and "basado_en" not in html


def test_un_mecanismo_ya_hecho_no_se_puede_modificar(ws):
    base = ws / "projects" / "2026-09-20-trinquete"
    (base / "mechanism.json").write_text(
        '{"title": "Trinquete", "parts": [{"name": "rueda"}, {"name": "pawl"}]}', encoding="utf-8")
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/proyectos/2026-09-20-trinquete/modificar",
                 json={"peticion": "que la rueda tenga 12 dientes"})

    assert r.status_code == 409
    assert "mecanismo" in r.json()["detail"]
    assert _nada_nuevo(ws, antes)


def test_un_backlog_no_se_modifica_entero_y_no_lanza_nada(ws):
    """Sin `pieza.json`, modificar un backlog caía en la orden por omisión, la
    de mecanismos, con la petición del backlog entero. Un backlog se cambia en
    la tarjeta de cada pieza; ampliarlo llegará con F9.10 (ampliar)."""
    from orchestrator import obra as O
    from tests.test_obra import _obra

    carpeta = ws / "projects" / "2026-11-09-pan-tilt"
    carpeta.mkdir()
    (carpeta / "request.md").write_text("un pan-tilt con dos SG90\n", encoding="utf-8")
    O.guardar(carpeta, _obra(), por="prueba")
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/proyectos/2026-11-09-pan-tilt/modificar",
                 json={"peticion": "la base más alta"})

    assert r.status_code == 409
    assert "pieza a pieza" in r.json()["detail"]
    assert _nada_nuevo(ws, antes)


def test_lo_que_no_es_una_pieza_suelta_tampoco_se_modifica(ws):
    """La leva archivada no dejó ni diseño ni `pieza.json`: no hay flujo con
    el que rehacerla."""
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/proyectos/2026-09-01-leva/modificar", json={"peticion": "más alta"})

    assert r.status_code == 409
    assert "pieza suelta" in r.json()["detail"]
    assert _nada_nuevo(ws, antes)
