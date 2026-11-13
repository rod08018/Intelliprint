"""El banco en la web, para mirar (F7.6 (animacion)).

La ronda de arreglos del 2026-11-09/10 dejó los dos backlogs del banco al
80 %, y en la web no se veía nada: el banco escribe en `workspace/banco/` y
la web solo miraba `workspace/projects/`. «No veo cambios en la web», dijo
el usuario. Lo esperado sale de la carpeta que monta cada test.
"""

from pathlib import Path

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


def test_las_corridas_van_de_la_ultima_a_la_primera_aunque_se_llamen_distinto(tmp_path):
    """La de 2026-11-03 se llamaba con el año («2026-11-03-203635») y las de
    después no («1110-0313»): por nombre salía la más vieja la primera."""
    import os

    from orchestrator.web.versiones import corridas_del_banco
    for nombre, cuando in (("2026-11-03-203635", 1_000_000), ("1110-0313", 2_000_000)):
        (tmp_path / "banco" / nombre).mkdir(parents=True)
        informe = tmp_path / "banco" / nombre / "banco.md"
        informe.write_text(TABLA.format(g=50, p=50), encoding="utf-8")
        os.utime(informe, (cuando, cuando))
    assert [c["id"] for c in corridas_del_banco(tmp_path)] == ["1110-0313", "2026-11-03-203635"]


def test_la_ultima_palabra_es_el_informe_mas_reciente_aunque_sea_un_rejuicio(tmp_path):
    """La corrida 1110-0313 se reanudó (80 %) y después se rejuzgó con el
    608ZZ ya medido (90 %): la web seguía enseñando la reanudada."""
    import os

    from orchestrator.web.versiones import corridas_del_banco
    _corrida(tmp_path)
    corrida = tmp_path / "banco" / "1110-0313"
    for nombre, nota, cuando in (("banco_reanudado.md", 80, 1_000_000),
                                 ("banco_rejuzgado.md", 90, 2_000_000)):
        informe = corrida / nombre
        informe.write_text(TABLA.format(g=nota, p=80), encoding="utf-8")
        os.utime(informe, (cuando, cuando))
    [c] = corridas_del_banco(tmp_path)
    assert c["informe"] == "banco_rejuzgado.md" and c["nota"].startswith("90 %")


# --- una corrida en marcha ------------------------------------------------------------------

def _corrida_sin_informe(ws, late=True):
    """Como la 1112-0318 mientras corría: su carpeta, la marca del encargo y
    el proyecto a medias, sin `banco.md`, que se escribe al final."""
    import os
    import time
    corrida = ws / "banco" / "1112-0318"
    carpeta = corrida / "01" / "projects" / PID
    carpeta.mkdir(parents=True)
    (corrida / "01" / "encargo.txt").write_text("brazo_3_ejes_sg90", encoding="utf-8")
    (carpeta / "request.md").write_text("un brazo de tres ejes", encoding="utf-8")
    O.guardar(carpeta, _obra(), por="banco")
    O.aprobar(carpeta, por="banco")
    (carpeta / "latido").write_text("", encoding="utf-8")
    if not late:
        hace_mucho = time.time() - 3600
        os.utime(carpeta / "latido", (hace_mucho, hace_mucho))
    return carpeta


def test_una_corrida_en_marcha_se_ve_antes_de_tener_nota(tmp_path):
    """«Revisa que todo se vea en la app para yo ver cómo va» (el usuario,
    2026-11-11, con el primer brazo corriendo): la corrida no salía en
    «Banco» hasta escribir su informe, al final. Durante la hora que tarda
    no había por dónde entrar a mirarla."""
    from orchestrator.web.versiones import corridas_del_banco
    _corrida_sin_informe(tmp_path)
    [c] = corridas_del_banco(tmp_path)
    assert c["en_marcha"] is True and c["informe"] is None
    assert c["encargos"] == [{"nombre": "brazo_3_ejes_sg90", "nota": "", "proyecto": PID}]
    r = _ws_con_trabajos(tmp_path).get("/banco")
    texto = _visible(r.text)
    for parte in ("1112-0318", "En marcha", "brazo_3_ejes_sg90", "la nota sale al terminar"):
        assert parte in texto, parte
    assert f'href="/p/{PID}"' in r.text
    # Y se pone al día sola: si no, hay que recargar a mano para ver la nota.
    assert 'http-equiv="refresh"' in r.text


def test_una_corrida_que_murio_sin_informe_no_dice_que_esta_en_marcha(tmp_path):
    """Sin latido reciente no hay proceso: decir «En marcha» sería dejar a
    la persona esperando algo que no va a llegar."""
    from orchestrator.web.versiones import corridas_del_banco
    _corrida_sin_informe(tmp_path, late=False)
    [c] = corridas_del_banco(tmp_path)
    assert c["en_marcha"] is False
    r = _ws_con_trabajos(tmp_path).get("/banco")
    texto = _visible(r.text)
    assert "En marcha" not in texto and "Sin informe" in texto
    assert 'http-equiv="refresh"' not in r.text


def test_una_corrida_que_se_reanuda_dice_que_su_nota_es_la_de_antes(tmp_path):
    """Al reanudar, el informe que hay es el de la vuelta anterior: se ve su
    nota, pero diciendo que se está rehaciendo."""
    carpeta = _corrida(tmp_path)
    (carpeta / "latido").write_text("", encoding="utf-8")
    texto = _visible(_ws_con_trabajos(tmp_path).get("/banco").text)
    assert "En marcha" in texto and "80 %" in texto
    assert "la nota es la de la vuelta anterior" in texto


def test_abrir_un_proyecto_del_banco_no_recorre_las_demas_corridas(tmp_path, monkeypatch):
    """La página de un proyecto del banco tardaba 27 a 33 s (medido el
    2026-11-12 con 20 corridas): para pintar UNO se miraba el estado de los
    112 proyectos de todas las corridas, y cada estado recorre todos los
    archivos de su carpeta. Solo hace falta la corrida del que se abre; y
    lo del banco no lleva botones, así que tampoco hay que mirar si hay
    algo en marcha entre los proyectos de la persona."""
    from orchestrator import registry
    _corrida(tmp_path)
    otra = tmp_path / "banco" / "1109-0101" / "01" / "projects" / "2026-11-09-010101-otro"
    otra.mkdir(parents=True)
    (otra / "request.md").write_text("otra cosa", encoding="utf-8")
    web = _ws_con_trabajos(tmp_path)
    mirados = []
    de_verdad = registry.estado_de

    def espia(carpeta):
        mirados.append(Path(carpeta).relative_to(tmp_path).as_posix())
        return de_verdad(carpeta)

    monkeypatch.setattr(registry, "estado_de", espia)
    r = web.get(f"/p/{PID}")
    assert r.status_code == 200, r.text
    assert mirados == [f"banco/1110-0313/01/projects/{PID}"], mirados


def test_un_backlog_del_banco_ampliado_en_otra_corrida_sigue_siendo_el_mismo(tmp_path,
                                                                             monkeypatch):
    """Una corrida que parte de otra (la del pan-tilt con pinza, 1112-1359,
    partió de la 1111-1342) lleva el mismo backlog con el mismo nombre: los
    dos se siguen mirando al abrirlo. Lo que no se mira es lo ajeno."""
    from orchestrator import registry
    _corrida(tmp_path)
    repetido = tmp_path / "banco" / "1111-0101" / "01" / "projects" / PID
    repetido.mkdir(parents=True)
    (repetido / "request.md").write_text("un pan-tilt con dos SG90 y una pinza", encoding="utf-8")
    ajeno = tmp_path / "banco" / "1111-0101" / "02" / "projects" / "2026-11-11-020202-otro"
    ajeno.mkdir(parents=True)
    (ajeno / "request.md").write_text("otra cosa", encoding="utf-8")
    web = _ws_con_trabajos(tmp_path)
    mirados = []
    de_verdad = registry.estado_de
    monkeypatch.setattr(registry, "estado_de",
                        lambda c: (mirados.append(Path(c).name), de_verdad(c))[1])
    r = web.get(f"/p/{PID}")
    assert r.status_code == 200, r.text
    assert mirados == [PID, PID]
