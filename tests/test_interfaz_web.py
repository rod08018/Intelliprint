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


def test_el_detalle_dice_el_uso_de_cada_pieza(ws, puente):
    carpeta = ws / "projects" / "2026-09-20-trinquete"
    (carpeta / "mechanism.json").write_text(json.dumps({"parts": [
        {"name": "rueda", "uso": "estructural"}, {"name": "pawl"}]}), encoding="utf-8")
    web = TestClient(crear_app(ws, puente=puente, host_workspace=HOST))

    detalle = web.get("/api/proyectos/2026-09-20-trinquete").json()

    assert detalle["piezas"] == [{"nombre": "pawl", "uso": "general"},
                                 {"nombre": "rueda", "uso": "estructural"}]


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

    trabajos = JobStore(ws / "projects", comando=[
        sys.executable, "-c", "import sys; print(sys.argv)"])
    return TestClient(crear_app(ws, host_workspace=HOST, trabajos=trabajos))


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
    peticion = "Una bisagra de 40 mm\ncon pasador de 3 mm que gire 180°"

    r = web.post("/api/disenar", json={"peticion": peticion})

    assert r.status_code == 200, r.text
    carpeta = ws / "projects" / r.json()["id"]
    assert (carpeta / "request.md").read_text(encoding="utf-8") == peticion + "\n"
    registro = _esperar_registro(carpeta)
    assert f"'{(carpeta / 'request.md')}'" in registro


def test_partir_de_un_proyecto_lo_pasa_como_referencia(ws):
    web = _ws_con_trabajos(ws)

    r = web.post("/api/disenar", json={"peticion": "como el trinquete, pero con 12 dientes",
                                       "basado_en": "2026-09-20-trinquete"})

    assert r.status_code == 200, r.text
    registro = _esperar_registro(ws / "projects" / r.json()["id"])
    assert "'--adjunto', '2026-09-20-trinquete'" in registro


@pytest.mark.parametrize("vacia", ["", "   \n\t "])
def test_una_peticion_vacia_no_lanza_nada(ws, vacia):
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/disenar", json={"peticion": vacia})

    assert r.status_code == 422
    assert sorted(p.name for p in (ws / "projects").iterdir()) == antes


@pytest.mark.parametrize("malo", ["..", "../projects", "no-existe", "/etc"])
def test_partir_de_algo_que_no_es_un_proyecto_no_lanza_nada(ws, malo):
    web = _ws_con_trabajos(ws)
    antes = sorted(p.name for p in (ws / "projects").iterdir())

    r = web.post("/api/disenar", json={"peticion": "una leva", "basado_en": malo})

    assert r.status_code == 404
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

    r = web.post("/api/disenar", json={"peticion": "una leva"})

    assert r.status_code == 409
    assert "2026-10-23-de-crafty" in r.json()["detail"]
    assert sorted(p.name for p in (ws / "projects").iterdir()) == [
        "2026-09-20-trinquete", "2026-10-23-de-crafty"]


def test_sin_lanzador_configurado_pedir_explica_que_falta(web):
    r = web.post("/api/disenar", json={"peticion": "una leva"})
    assert r.status_code == 503


def test_la_portada_tiene_donde_escribir_la_peticion(ws):
    html = _ws_con_trabajos(ws).get("/").text
    assert '<textarea id="peticion"' in html
    # Se puede partir de los proyectos que hay, archivados incluidos.
    assert '<option value="2026-09-20-trinquete">' in html
    assert '<option value="2026-09-01-leva">' in html


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
    return TestClient(crear_app(ws, host_workspace=HOST)).get("/api/proyectos").json()


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
    assert html.count('data-id="2026-09-21-01-gato"') == 1
    assert 'data-id="2026-09-21-02-gato"' not in html

    # En su página están todas, abre con la mejor, y los botones bajan esa.
    pagina = web.get("/p/2026-09-21-01-gato").text
    for n in (1, 2, 3):
        assert f'?v=2026-09-21-0{n}-gato"' in pagina
    assert 'href="/proyectos/2026-09-21-02-gato.zip"' in pagina


# --- Pedir una modificación dentro del proyecto -----------------------------


def test_pedir_una_modificacion_crea_una_version_del_mismo_proyecto(ws):
    base = ws / "projects" / "2026-09-20-trinquete"
    (base / "mechanism.json").write_text('{"title": "Trinquete"}', encoding="utf-8")
    web = _ws_con_trabajos(ws)

    r = web.post("/api/proyectos/2026-09-20-trinquete/modificar",
                 json={"peticion": "que la rueda tenga 12 dientes"})

    assert r.status_code == 200, r.text
    nueva = ws / "projects" / r.json()["id"]
    # El diseñador recibe lo que se pidió al principio y el cambio, literal.
    peticion = (nueva / "request.md").read_text(encoding="utf-8")
    assert peticion.startswith("un trinquete\n")
    assert peticion.rstrip().endswith("que la rueda tenga 12 dientes")
    assert "2026-09-20-trinquete" in peticion
    # Y el diseño del que parte, como referencia.
    assert "'--adjunto', '2026-09-20-trinquete'" in _esperar_registro(nueva)
    (trinquete,) = [g for g in web.get("/api/proyectos").json()
                    if g["id"] == "2026-09-20-trinquete"]
    assert [v["id"] for v in trinquete["versiones"]] == ["2026-09-20-trinquete", nueva.name]
    assert trinquete["versiones"][1]["modificacion"] == "que la rueda tenga 12 dientes"


def test_modificar_una_modificacion_sigue_en_el_proyecto_original(ws):
    web = _ws_con_trabajos(ws)
    primera = web.post("/api/proyectos/2026-09-20-trinquete/modificar",
                       json={"peticion": "12 dientes"}).json()["id"]
    _esperar_registro(ws / "projects" / primera)
    # El «diseñador» de prueba no deja rondas: sin rounds.json, una carpeta
    # recién tocada cuenta como en marcha y no dejaría lanzar la segunda.
    web.app.state.trabajos._procesos[primera].wait(timeout=20)
    (ws / "projects" / primera / "rounds.json").write_text(
        '[{"number": 1, "title": "t", "feedback": ""}]', encoding="utf-8")

    r = web.post(f"/api/proyectos/{primera}/modificar", json={"peticion": "y más grueso"})

    assert r.status_code == 200, r.text
    peticion = (ws / "projects" / r.json()["id"] / "request.md").read_text(encoding="utf-8")
    # Las modificaciones se acumulan: la segunda parte de la primera.
    assert "12 dientes" in peticion and "y más grueso" in peticion
    (trinquete,) = [g for g in web.get("/api/proyectos").json()
                    if g["id"] == "2026-09-20-trinquete"]
    assert len(trinquete["versiones"]) == 3


def test_modificar_una_version_sin_diseno_no_la_pasa_como_referencia(ws):
    """El cargador de referencias rechaza un proyecto sin mechanism.json y el
    trabajo moriría al arrancar: la petición ya lleva lo que se pidió."""
    web = _ws_con_trabajos(ws)

    r = web.post("/api/proyectos/2026-09-01-leva/modificar", json={"peticion": "más alta"})

    assert r.status_code == 200, r.text
    assert "--adjunto" not in _esperar_registro(ws / "projects" / r.json()["id"])


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
    web = _ws_con_trabajos(ws)

    r = web.post("/api/proyectos/2026-09-20-trinquete/modificar", json={"peticion": "algo"})

    assert r.status_code == 409


def test_el_detalle_de_una_version_dice_que_modificacion_se_pidio(ws):
    web = _ws_con_trabajos(ws)
    nueva = web.post("/api/proyectos/2026-09-20-trinquete/modificar",
                     json={"peticion": "12 dientes"}).json()["id"]

    detalle = web.get(f"/api/proyectos/{nueva}").json()

    assert detalle["modificacion"] == "12 dientes"
    assert detalle["peticion"].startswith("un trinquete")


def test_cada_mecanismo_tiene_donde_pedir_una_modificacion(ws):
    (ws / "projects" / "2026-09-20-trinquete" / "mechanism.json").write_text(
        '{"parts": []}', encoding="utf-8")
    html = _ws_con_trabajos(ws).get("/p/2026-09-20-trinquete").text
    assert 'data-modificar="2026-09-20-trinquete"' in html
