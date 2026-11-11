"""Cancelar un diseño desde la web (F9.12 (pantalla)).

Un diseño tarda de 5 a 60 minutos y cuesta dinero, y desde la web no
había por dónde pararlo: solo podía Crafty, con `cancelar_proyecto`. Lo que
se pide: una ruta que pare el trabajo en marcha de ESE proyecto y conteste
la verdad —200 si lo paró, 409 con el motivo si no había nada o si no es
suyo—, y un botón en el bloque «Diseñando la versión N».

El «diseñador» de estos tests hace lo que hace el de verdad mientras
trabaja: deja su latido en la carpeta y sigue vivo. Lo esperado sale de lo
que se pide y de cómo se monta cada carpeta, no de lo que conteste la web.
"""

import re
import sys
import time

import pytest
from fastapi.testclient import TestClient

from orchestrator.jobs import JobStore
from orchestrator.web.app import crear_app
from tests.test_web_piezas_sueltas import _pieza
from tests.test_web_ux import _en_marcha

HOST = r"C:\repo\workspace"

LENTO = [sys.executable, "-c", (
    "import pathlib, sys, time\n"
    "carpeta = pathlib.Path(sys.argv[sys.argv.index('--carpeta') + 1])\n"
    "(carpeta / 'latido').touch()\n"
    "print(sys.argv, flush=True)\n"
    "time.sleep(60)\n")]
"""Como `intelliprint pieza` a medias: late (lo ve cualquier contenedor) y
no termina solo. Con un diseñador que no dejara latido, la página dejaría de
decir «Diseñando» al morir el proceso aunque nadie quitara el latido, que es
justo lo que en la realidad la tenía mintiendo minuto y medio."""

AVISO = "Se para el diseño; lo gastado hasta ahora no se recupera"


@pytest.fixture
def web(tmp_path):
    (tmp_path / "projects").mkdir()
    trabajos = JobStore(tmp_path / "projects", comando=LENTO, comando_pieza=LENTO)
    cliente = TestClient(crear_app(tmp_path, host_workspace=HOST, trabajos=trabajos,
                                   orden_pieza=LENTO, orden_obra=LENTO))
    yield cliente
    # Lo que un test deje vivo no se queda un minuto durmiendo en la suite.
    for proceso in trabajos._procesos.values():
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait(timeout=5)


def _lanzar(web, ws, ruta="/api/disenar", cuerpo=None):
    r = web.post(ruta, json=cuerpo or {"tipo": "pieza", "peticion": "un gancho de pared"})
    assert r.status_code == 200, r.text
    carpeta = ws / "projects" / r.json()["id"]
    limite = time.time() + 20
    while not (carpeta / "latido").exists():
        assert time.time() < limite, "el trabajo no llegó a arrancar"
        time.sleep(0.05)
    return carpeta


def test_cancelar_para_el_diseno_y_la_pagina_deja_de_decir_que_disena(web, tmp_path):
    carpeta = _lanzar(web, tmp_path)
    proceso = web.app.state.trabajos._procesos[carpeta.name]
    assert "Diseñando la versión 1" in web.get(f"/p/{carpeta.name}").text

    r = web.post(f"/api/proyectos/{carpeta.name}/cancelar")

    assert r.status_code == 200, r.text
    assert r.json() == {"id": carpeta.name, "proyecto": carpeta.name, "estado": "cancelado"}
    # Parado de verdad: el proceso ha muerto, no solo cambia lo que se pinta.
    assert proceso.wait(timeout=5) != 0
    html = web.get(f"/p/{carpeta.name}").text
    assert "Diseñando" not in html
    assert 'data-cancelar="' not in html
    # Y deja pedir otro: sin quitar el latido, «hay un diseño en marcha»
    # duraba minuto y medio después de cancelarlo.
    assert web.app.state.trabajos.current() is None


def test_cancelar_sin_nada_en_marcha_es_409_y_dice_por_que(web, tmp_path):
    _pieza(tmp_path, "2026-11-06-soporte")

    r = web.post("/api/proyectos/2026-11-06-soporte/cancelar")

    assert r.status_code == 409
    assert "no tiene ningún diseño en marcha" in r.json()["detail"]
    assert not (tmp_path / "projects" / "2026-11-06-soporte" / "cancelado").exists()


def test_cancelar_otro_proyecto_no_para_el_que_trabaja(web, tmp_path):
    """La ruta es de UN proyecto: pedirla para el que está quieto no puede
    parar el diseño de otro."""
    _pieza(tmp_path, "2026-11-06-soporte")
    carpeta = _lanzar(web, tmp_path)

    r = web.post("/api/proyectos/2026-11-06-soporte/cancelar")

    assert r.status_code == 409
    assert web.app.state.trabajos._procesos[carpeta.name].poll() is None
    assert "Diseñando la versión 1" in web.get(f"/p/{carpeta.name}").text


def test_con_el_id_del_proyecto_se_para_la_version_que_trabaja(web, tmp_path):
    """La página de un proyecto se abre con el id de su primera versión, y la
    que trabaja es otra carpeta: la de la modificación."""
    _pieza(tmp_path, "2026-11-06-soporte")
    nueva = _lanzar(web, tmp_path, "/api/proyectos/2026-11-06-soporte/modificar",
                    {"peticion": "que sea 20 mm más largo"})
    assert "Diseñando la versión 2" in web.get("/p/2026-11-06-soporte").text

    r = web.post("/api/proyectos/2026-11-06-soporte/cancelar")

    assert r.status_code == 200, r.text
    assert r.json()["id"] == nueva.name
    assert web.app.state.trabajos._procesos[nueva.name].wait(timeout=5) != 0
    assert "Diseñando" not in web.get("/p/2026-11-06-soporte").text


def test_lo_que_lanzo_otro_contenedor_no_se_da_por_cancelado(web, tmp_path):
    """Lo que lanza Crafty corre en el contenedor del MCP: aquí se ve por su
    latido, pero su pid es de allí y desde este no se le puede mandar nada.
    Contestar 200 sería decir «parado» con el diseño gastando."""
    carpeta = _pieza(tmp_path, "2026-11-09-soporte")
    _en_marcha(carpeta, minutos=3)
    assert "Diseñando la versión 1" in web.get("/p/2026-11-09-soporte").text

    r = web.post("/api/proyectos/2026-11-09-soporte/cancelar")

    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert "otro contenedor" in detalle and "Crafty" in detalle
    # Ni se marca como cancelado ni se le quita el latido: sigue trabajando.
    assert not (carpeta / "cancelado").exists()
    assert (carpeta / "latido").exists()
    assert "Diseñando la versión 1" in web.get("/p/2026-11-09-soporte").text


def test_una_marca_de_cancelado_antigua_no_hace_pasar_por_parado(web, tmp_path):
    """La marca `cancelado` se queda en la carpeta de una vez anterior si el
    trabajo se relanzó a mano: no vale como prueba de que se ha parado."""
    carpeta = _pieza(tmp_path, "2026-11-09-soporte")
    _en_marcha(carpeta, minutos=3)
    (carpeta / "cancelado").write_text("", encoding="utf-8")

    assert web.post("/api/proyectos/2026-11-09-soporte/cancelar").status_code == 409


@pytest.mark.parametrize("malo", ["..", "..%2F..", "no-existe"])
def test_cancelar_algo_que_no_es_un_proyecto_es_404(web, malo):
    assert web.post(f"/api/proyectos/{malo}/cancelar").status_code == 404


def test_sin_lanzador_no_hay_con_que_cancelar(tmp_path):
    _en_marcha(_pieza(tmp_path, "2026-11-09-soporte"), minutos=3)
    web = TestClient(crear_app(tmp_path, host_workspace=HOST))

    assert web.post("/api/proyectos/2026-11-09-soporte/cancelar").status_code == 503
    # Y la página no ofrece un botón que solo puede fallar.
    assert 'data-cancelar="' not in web.get("/p/2026-11-09-soporte").text


# --- El botón -------------------------------------------------------------------


def _bloque_en_marcha(html):
    return re.search(r'<div class="aviso vivo" id="en-marcha".*?</div>', html, re.S).group(0)


def test_el_boton_de_cancelar_sale_solo_mientras_hay_algo_en_marcha(web, tmp_path):
    carpeta = _pieza(tmp_path, "2026-11-09-soporte")

    quieto = web.get("/p/2026-11-09-soporte").text
    _en_marcha(carpeta, minutos=3)
    trabajando = web.get("/p/2026-11-09-soporte").text

    # El guion nombra el atributo sin valor; el botón lo lleva con él.
    assert 'data-cancelar="' not in quieto
    (boton,) = re.findall(r"<button[^>]*data-cancelar=[^>]*>[^<]*</button>",
                          _bloque_en_marcha(trabajando))
    assert 'data-cancelar="2026-11-09-soporte"' in boton
    assert ">Cancelar<" in boton


def test_cancelar_es_una_accion_secundaria_y_se_puede_tocar_con_el_dedo(web, tmp_path):
    """Con el estilo de los demás botones (`.btn`, que mide 44 px con el
    dedo), pero no el principal: parar un diseño no es lo que se viene a hacer."""
    _en_marcha(_pieza(tmp_path, "2026-11-09-soporte"), minutos=3)

    (boton,) = re.findall(r"<button[^>]*data-cancelar=[^>]*>",
                          web.get("/p/2026-11-09-soporte").text)

    assert re.search(r'class="([^"]*)"', boton).group(1).split() == ["btn"]


def test_antes_de_cancelar_se_avisa_de_lo_que_pasa_y_luego_se_recarga(web, tmp_path):
    """Lo gastado no vuelve: se dice antes de parar, con un `confirm()`. El
    botón llama a la ruta con la función común `enviar()` y recarga."""
    _en_marcha(_pieza(tmp_path, "2026-11-09-soporte"), minutos=3)

    html = web.get("/p/2026-11-09-soporte").text

    guion = html.split("<script>")[-1]
    manejador = guion.split('closest("[data-cancelar]")', 1)[1].split("\n  });", 1)[0]
    assert f'confirm("{AVISO}' in manejador
    assert 'enviar("/api/proyectos/" + encodeURIComponent(b.dataset.cancelar) + "/cancelar"' \
        in manejador
    assert "location.reload()" in manejador
    # Si no se pudo (lo lanzó otro contenedor), se dice el motivo que da la ruta.
    assert "avisar(detalle(d)" in manejador
    # El bloque #en-marcha se cambia entero cada 10 s: un manejador puesto en
    # el botón se iría con el primero. Se escucha en la página, que no cambia.
    assert 'querySelectorAll("[data-cancelar]")' not in guion
