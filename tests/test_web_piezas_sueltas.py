"""Una pieza suelta en la web es un proyecto como otro cualquiera (F5.17 (pieza)).

La web se hizo para los mecanismos y las piezas sueltas salían de segunda.
Lo vio el análisis de UX del 2026-11-08 en el workspace real:

- el soporte del 608ZZ salía en verde «Listo para imprimir» con la
  ejecución muerta al laminar y `fabrication/` vacía;
- dos proyectos distintos se llamaban igual, «Soporte para un rodamiento
  608ZZ que sujete un eje horizontal de 8…», porque la web solo leía el
  título de `mechanism.json`;
- el progreso decía «arrancando» durante toda la ejecución;
- y no había por dónde pedir un cambio, aunque el servidor sí sabía hacerlo.

Lo que NO se arregla aquí: las piezas siguen entrando en «Otros». Pedirle la
categoría al Requirements Agent cambió cómo describía la pieza y el soporte
NEMA17 de la e2e salió con un pie en L (ver `pieza._redactar`).

Lo esperado sale de cómo se construye cada carpeta, no de lo que pinte la web.
"""

import json
import os

from orchestrator.registry import estado_de
from orchestrator.web.estadisticas import estadisticas
from orchestrator.web.paginas import _progreso
from tests.test_slicing import _cubo_stl
from tests.test_web_galeria import _web

VIEJO = 1_700_000_000


def _pieza(ws, nombre, *, titulo="Soporte de rodamiento 608ZZ", categoria=None,
           terminada=True, peticion="Soporte para un rodamiento 608ZZ que sujete un eje"):
    """La carpeta que deja `intelliprint pieza`. `terminada=False` es la
    ejecución que murió después de construir y antes de cerrar: sin
    `rounds.json` ni `pieza_report.json`, como la del 608ZZ del 2026-11-06."""
    carpeta = ws / "projects" / nombre
    (carpeta / "parts" / "soporte").mkdir(parents=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    datos = {"title": titulo, **({"categoria": categoria} if categoria else {})}
    (carpeta / "pieza.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    (carpeta / "concepto.json").write_text("{}", encoding="utf-8")
    (carpeta / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (carpeta / "parts" / "soporte" / "soporte.step").write_text("step", encoding="utf-8")
    _cubo_stl(carpeta / "parts" / "soporte" / "soporte.stl", 20)
    if terminada:
        (carpeta / "rounds.json").write_text(json.dumps(
            [{"number": 1, "title": titulo, "feedback": ""}]), encoding="utf-8")
        (carpeta / "pieza_report.json").write_text(
            json.dumps({"titulo": titulo, "resuelto": True}), encoding="utf-8")
    for f in [carpeta, *carpeta.rglob("*")]:
        os.utime(f, (VIEJO, VIEJO))
    return carpeta


def test_una_pieza_que_murio_a_medias_no_sale_lista_para_imprimir(tmp_path):
    carpeta = _pieza(tmp_path, "2026-11-06-soporte", terminada=False)

    assert estado_de(carpeta)["estado"] == "incompleto"
    html = _web(tmp_path).get("/").text
    assert "Listo para imprimir" not in html
    assert "Se quedó a medias" in html


def test_un_mecanismo_anterior_al_registro_sigue_siendo_obra(tmp_path):
    """La regla de «antiguo» era para lo hecho antes de que hubiera rounds.json;
    eso no cambia. Una pieza suelta siempre nace con el registro."""
    carpeta = tmp_path / "2026-09-01-bisagra"
    carpeta.mkdir()
    (carpeta / "request.md").write_text("una bisagra\n", encoding="utf-8")
    (carpeta / "assembly.FCStd").write_bytes(b"x")
    for f in [carpeta, *carpeta.rglob("*")]:
        os.utime(f, (VIEJO, VIEJO))

    assert estado_de(carpeta)["estado"] == "antiguo"


def test_la_pieza_se_llama_por_su_titulo_y_no_por_la_peticion_cortada(tmp_path):
    # Peticiones distintas: con la misma, la web las junta como versiones.
    _pieza(tmp_path, "2026-11-06-soporte", titulo="Soporte de rodamiento 608ZZ para perfil 2020")
    _pieza(tmp_path, "2026-11-09-soporte", titulo="Soporte de rodamiento 608ZZ con reborde",
           peticion="Soporte para un rodamiento 608ZZ que sujete un eje, con reborde")

    html = _web(tmp_path).get("/").text

    assert "Soporte de rodamiento 608ZZ para perfil 2020" in html
    assert "Soporte de rodamiento 608ZZ con reborde" in html
    assert "que sujete un eje" not in html



def test_lo_que_hace_una_pieza_sale_de_su_registro_de_ejecucion(tmp_path):
    """Una pieza no deja `design_cost.json`, que era de donde salía la etapa:
    el soporte del 608ZZ dijo «arrancando» mientras se dibujaba."""
    carpeta = _pieza(tmp_path, "2026-11-09-soporte", terminada=False)
    (carpeta / "run.log").write_text(
        "[Crafty] Pieza → /workspace/projects/2026-11-09-soporte\n"
        "  «Soporte de rodamiento 608ZZ»: el Part Designer dibuja «soporte»…\n"
        "    intento 1: la sonda mide la pared\n", encoding="utf-8")

    etapa = estadisticas(carpeta, en_marcha=True)["ultima_etapa"]

    # Con el nombre legible, no el de la carpeta (test_web_ux).
    assert _progreso({"ultima_etapa": etapa}) == "dibujando «Soporte»"


def test_la_etapa_de_una_ejecucion_anterior_no_cuenta(tmp_path):
    """Al corregir la base del pan-tilt (2026-11-09) la web dijo «preparando
    la impresión» durante el primer minuto: el `run.log` de una obra se
    alarga en cada lanzamiento, y la última línea de avance era el
    «laminado…» de la vez anterior."""
    carpeta = _pieza(tmp_path, "2026-11-09-soporte", terminada=False)
    (carpeta / "run.log").write_text(
        "[Crafty] Pieza → /workspace/projects/2026-11-09-soporte/nodos/base\n"
        "  laminado…\n"
        "[Crafty] ✋ «Base» diseñada: revísala\n"
        "[Crafty] Backlog → /workspace/projects/2026-11-09-soporte\n"
        "[Crafty] nodo «Base» (base)\n", encoding="utf-8")

    etapa = estadisticas(carpeta, en_marcha=True)["ultima_etapa"]

    assert _progreso({"ultima_etapa": etapa}) == "arrancando"


def test_mientras_lamina_lo_dice(tmp_path):
    carpeta = _pieza(tmp_path, "2026-11-09-soporte", terminada=False)
    (carpeta / "run.log").write_text(
        "  «Soporte»: el Part Designer dibuja «soporte»…\n  laminado…\n", encoding="utf-8")

    etapa = estadisticas(carpeta, en_marcha=True)["ultima_etapa"]

    assert _progreso({"ultima_etapa": etapa}) == "preparando la impresión"


def test_mientras_se_disena_la_pieza_late(tmp_path):
    """Crafty lanza la pieza en el contenedor del MCP y la web la mira desde
    el suyo, donde el pid de job.json no existe: solo el latido dice que
    sigue viva. Sin él, el soporte del 608ZZ en marcha salía terminado."""
    from orchestrator.pieza import disenar_pieza
    from tests.test_pieza import PETICION, Requisitos, _disenar

    visto = []
    construir = _disenar()

    def disenar(spec, carpeta, parte, concepto=None):
        visto.append((tmp_path / "latido").exists())
        return construir(spec, carpeta, parte, concepto)

    disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(), disenar=disenar,
                  log=lambda *_: None)

    assert visto == [True]
    assert not (tmp_path / "latido").exists()


def test_mientras_el_ingeniero_piensa_la_pieza_late(tmp_path):
    from orchestrator.pieza import concebir_pieza
    from tests.test_pieza import PETICION, Requisitos

    visto = []

    class Ingeniero:
        def concebir(self, spec):
            visto.append((tmp_path / "latido").exists())
            raise ValueError("no sale")

    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=Ingeniero(),
                   log=lambda *_: None)

    assert visto == [True]
    assert not (tmp_path / "latido").exists()


def test_a_una_pieza_se_le_puede_pedir_un_cambio(tmp_path):
    _pieza(tmp_path, "2026-11-06-soporte")

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert 'class="cambiar-todo" data-modificar="2026-11-06-soporte"' in html


def test_el_coste_del_paso_anterior_no_dice_lo_que_hace_ahora(tmp_path):
    """Una obra apunta su gasto al acabar cada paso (2026-11-10): mientras
    se dibuja la base, la última etapa del coste es la del desglose, que ya
    pasó. Lo que hace ahora lo dice el registro de este lanzamiento."""
    import json

    carpeta = _pieza(tmp_path, "2026-11-10-pan-tilt", terminada=False)
    (carpeta / "design_cost.json").write_text(json.dumps({
        "resumen": {"total_usd": 0.01, "limite_usd": 5.0, "llamadas": 1},
        "detalle": [{"etapa": "desglose", "usd": 0.01}]}), encoding="utf-8")
    (carpeta / "run.log").write_text(
        "[Crafty] Backlog → /workspace/projects/2026-11-10-pan-tilt\n"
        "[Crafty] nodo «Base» (base)\n", encoding="utf-8")
    assert _progreso({"ultima_etapa": estadisticas(carpeta, en_marcha=True)["ultima_etapa"]}) \
        == "arrancando"

    with (carpeta / "run.log").open("a", encoding="utf-8") as f:
        f.write("  «Soporte»: el Part Designer dibuja «soporte»…\n")
    assert _progreso({"ultima_etapa": estadisticas(carpeta, en_marcha=True)["ultima_etapa"]}) \
        == "dibujando «Soporte»"
