"""La obra en la web: el árbol y sus botones (F7.3 (arbol)).

Un proyecto por partes para en cada paso a por la persona: el desglose, el
concepto de cada pieza y su «está bien, la siguiente». Si la página no lo
dice, el proyecto se queda parado sin que se sepa por qué (pasó con el
concepto de las piezas sueltas antes de tener sus botones, 2026-11-04).

Lo esperado sale de la carpeta que se monta en cada test, no de lo que
pinte la web.
"""

import json
import re

from orchestrator import obra as O
from tests.test_interfaz_web import _esperar_registro, _ws_con_trabajos
from tests.test_obra import _disenar_nodo, _obra

ID = "2026-11-09-pan-tilt"


def _empezar(ws, aprobada=False):
    carpeta = ws / "projects" / ID
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text("un pan-tilt con dos SG90 para una cámara\n",
                                        encoding="utf-8")
    O.guardar(carpeta, _obra(), por="prueba")
    if aprobada:
        O.aprobar(carpeta, por="prueba")
    return carpeta


def _visible(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_el_desglose_por_aprobar_se_lee_con_sus_piezas_y_sus_botones(tmp_path):
    _empezar(tmp_path)
    html = _ws_con_trabajos(tmp_path).get(f"/p/{ID}").text
    texto = _visible(html)
    for parte in ("Base", "aloja el SG90 de giro", "Soporte de giro", "Soporte de inclinación",
                  "eje de salida del SG90 de giro hacia +z"):
        assert parte in texto, parte
    assert f'data-aprobar="{ID}"' in html
    assert "Aprobar el desglose" in texto


def test_con_el_desglose_aprobado_el_arbol_dice_que_toca_y_que_espera(tmp_path):
    _empezar(tmp_path, aprobada=True)
    texto = _visible(_ws_con_trabajos(tmp_path).get(f"/p/{ID}").text)
    # Su nombre es el del desglose, no la petición cortada.
    assert "<h1>Pan-tilt con dos SG90</h1>" in _ws_con_trabajos(tmp_path).get(f"/p/{ID}").text
    assert "Siguiente: Base" in texto
    assert "Espera a Base" in texto          # el soporte de giro
    assert "Espera a Soporte de giro" in texto


def test_el_concepto_de_un_nodo_se_aprueba_desde_su_tarjeta(tmp_path):
    carpeta = _empezar(tmp_path, aprobada=True)
    nodo = carpeta / "nodos" / "base"
    nodo.mkdir(parents=True)
    (nodo / "concepto.json").write_text("{}", encoding="utf-8")
    (nodo / "concepto.md").write_text("# Base: el concepto\n\n**Idea:** caja con el SG90 "
                                      "tumbado\n", encoding="utf-8")
    web = _ws_con_trabajos(tmp_path)
    html = web.get(f"/p/{ID}").text
    assert "caja con el SG90 tumbado" in html and f'data-aprobar="{ID}"' in html

    r = web.post(f"/api/proyectos/{ID}/aprobar", json={})
    assert r.status_code == 200, r.text
    assert json.loads((nodo / "concepto_aprobado").read_text())["por"] == "web"
    assert "--continuar" in _esperar_registro(carpeta)


def test_esta_bien_la_siguiente_ficha_el_nodo_y_sigue(tmp_path):
    carpeta = _empezar(tmp_path, aprobada=True)
    _disenar_nodo(carpeta, "base")
    web = _ws_con_trabajos(tmp_path)
    html = web.get(f"/p/{ID}").text
    assert 'data-lista="base"' in html and 'data-rehacer="base"' in html
    # Su pieza, a la vista y para abrirla sola: se prueba antes de seguir.
    assert f"/proyectos/{ID}/piezas/base.png" in html
    assert web.get(f"/proyectos/{ID}/piezas/base.png").status_code == 200

    r = web.post(f"/api/proyectos/{ID}/nodos/base/lista", json={})
    assert r.status_code == 200, r.text
    assert (carpeta / "fichas" / "obra-base.yaml").exists()
    assert O.estados(carpeta)["giro"] == "pendiente"
    assert "--continuar" in _esperar_registro(carpeta)


def test_impresa_y_probada_queda_apuntada_con_su_nota_y_no_frena_nada(tmp_path):
    carpeta = _empezar(tmp_path, aprobada=True)
    _disenar_nodo(carpeta, "base")
    O.dar_por_lista(carpeta, "base", por="prueba")
    web = _ws_con_trabajos(tmp_path)

    r = web.post(f"/api/proyectos/{ID}/nodos/base/impresa", json={"nota": "entró justo"})
    assert r.status_code == 200, r.text
    assert O.lista(carpeta, "base")["impresa"] is True
    texto = _visible(web.get(f"/p/{ID}").text)
    assert "Impresa y probada" in texto and "entró justo" in texto


def test_rehacer_avisa_de_lo_que_se_rehace_con_el(tmp_path):
    carpeta = _empezar(tmp_path, aprobada=True)
    _disenar_nodo(carpeta, "base")
    O.dar_por_lista(carpeta, "base", por="prueba")
    _disenar_nodo(carpeta, "giro")
    web = _ws_con_trabajos(tmp_path)
    # El aviso antes de pulsar: rehacer la base deshace el soporte de giro.
    assert "también Soporte de giro" in _visible(web.get(f"/p/{ID}").text)

    r = web.post(f"/api/proyectos/{ID}/nodos/base/rehacer", json={"cambio": "más alta"})
    assert r.status_code == 200, r.text
    assert r.json()["rehechos"] == ["base", "giro"]
    # Construida y con un cambio dicho: se corrige, sin volver al concepto.
    assert O.estados(carpeta)["base"] == "corrigiendo"


def test_cambiar_una_pieza_disenada_la_corrige_sin_rehacer_el_concepto(tmp_path):
    """Desde la web, pedir un cambio a una pieza que ya tiene diseño la
    retoca: no vuelve a pasar por el concepto ni por su visto bueno."""
    carpeta = _empezar(tmp_path, aprobada=True)
    _disenar_nodo(carpeta, "base")
    (carpeta / "nodos" / "base" / "parts" / "base" / "programa.py").write_text(
        "CODIGO", encoding="utf-8")
    web = _ws_con_trabajos(tmp_path)

    r = web.post(f"/api/proyectos/{ID}/nodos/base/rehacer",
                 json={"cambio": "la tuerca más adentro"})
    assert r.status_code == 200, r.text
    assert O.estados(carpeta)["base"] == "corrigiendo"
    _esperar_registro(carpeta)

    # Y quien de verdad quiera empezar de cero lo pide.
    r = web.post(f"/api/proyectos/{ID}/nodos/base/rehacer",
                 json={"cambio": "otra idea", "desde_cero": True})
    assert r.status_code == 200, r.text
    assert O.estados(carpeta)["base"] == "pendiente"


def test_la_tarjeta_dice_que_se_corrige_y_que_se_corrigio(tmp_path):
    """Corrigiendo la base del pan-tilt desde la web (2026-11-09), su tarjeta
    decía «Concepto aprobado» y no qué se había pedido; y el campo del
    cambio era de una línea, con la indicación cortada."""
    carpeta = _empezar(tmp_path, aprobada=True)
    _disenar_nodo(carpeta, "base")
    nodo = carpeta / "nodos" / "base"
    (nodo / "parts" / "base" / "programa.py").write_text("CODIGO", encoding="utf-8")
    web = _ws_con_trabajos(tmp_path)
    assert re.search(r'<textarea[^>]*name="cambio"', web.get(f"/p/{ID}").text)

    O.corregir(carpeta, "base", cambio="la tuerca, 2 mm más adentro")
    texto = _visible(web.get(f"/p/{ID}").text)
    assert "Corrigiéndose" in texto and "la tuerca, 2 mm más adentro" in texto

    _disenar_nodo(carpeta, "base")   # la corrección termina
    texto = _visible(web.get(f"/p/{ID}").text)
    assert "Corregida: la tuerca, 2 mm más adentro" in texto


def test_un_proyecto_de_varias_piezas_se_pide_desde_la_portada(tmp_path):
    import sys

    from fastapi.testclient import TestClient

    from orchestrator.jobs import JobStore
    from orchestrator.web.app import crear_app
    from tests.test_interfaz_web import HOST
    imprime = [sys.executable, "-c", "import sys; print(sys.argv)"]
    web = TestClient(crear_app(tmp_path, host_workspace=HOST,
                               trabajos=JobStore(tmp_path / "projects", comando=imprime),
                               orden_pieza=imprime, orden_obra=[*imprime, "obra"]))
    assert 'value="obra"' in web.get("/").text

    r = web.post("/api/disenar", json={"peticion": "un pan-tilt", "tipo": "obra"})
    assert r.status_code == 200, r.text
    assert "'obra'" in _esperar_registro(tmp_path / "projects" / r.json()["id"])
