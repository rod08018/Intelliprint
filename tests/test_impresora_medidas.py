"""Los datos de la impresora, apuntados por el usuario (F2.21 (impresora)).

El usuario configura y calibra él su impresora (2026-11-09): «yo la voy a
setear». Imprime pruebas, las mide y las fotografía, y quiere que lo
medido entre en el diseño. Decisiones suyas:

- los números los escribe él; la foto queda como evidencia. Una foto no
  enseña si un eje entra justo o con juego;
- las pruebas de Intelliprint (la pieza de F2.18 (calibración) y la barra de
  flexión) cambian el perfil. Las suyas, de Printables u otras, se guardan
  como referencia, sin cambiar números.

`config/` está en solo lectura dentro del contenedor, así que lo medido
vive en `workspace/impresoras/<perfil>/` y manda sobre `config/printers/`,
que no se toca.

Lo esperado sale de la petición literal y de cálculos a mano, no del código.
"""

import base64
import hashlib
import math
import shutil
from pathlib import Path

import pytest
import yaml

from orchestrator.impresion import perfil_activo
from orchestrator.medidas_impresora import MedidaInvalida, registrar, registros

RAIZ = Path(".")
PERFIL = "ankermake_m5_plamas"
YAML = RAIZ / "config" / "printers" / f"{PERFIL}.yaml"

# Una foto de verdad, mínima: la cabecera de un JPEG y de un PNG.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

HOLGURAS = dict(press_mm=0.1, slide_mm=0.2, clearance_mm=0.4,
                m3_through_mm=3.4, m3_selftap_mm=2.8, m3_insert_mm=4.1)


def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


# --- Las holguras -----------------------------------------------------------------


def test_las_holguras_medidas_mandan_sobre_el_perfil_y_config_no_se_toca(tmp_path):
    antes = _huella(YAML)

    registrar(tmp_path, PERFIL, "tolerancias", HOLGURAS, fotos=[("peine.jpg", JPEG)],
              fecha="2026-11-10")

    medido = perfil_activo(RAIZ, workspace=tmp_path)
    assert medido.impresora.hole_mm("M3_through") == 3.4
    assert medido.impresora.fit_mm("clearance") == 0.4
    assert medido.impresora.calibrated is True
    # Sin el workspace, lo de siempre: el valor por defecto sin calibrar.
    assert perfil_activo(RAIZ).impresora.hole_mm("M3_through") == 3.3
    assert _huella(YAML) == antes


@pytest.mark.parametrize("cambio, motivo", [
    (dict(press_mm=0.25), "peine"),              # no hay agujero de 5.25
    (dict(press_mm=0.3, slide_mm=0.2), "press"),  # a presión no puede ser más holgado
    (dict(m3_selftap_mm=3.4, m3_through_mm=3.3), "rosca"),
])
def test_unas_holguras_que_la_pieza_no_puede_dar_no_cambian_nada(tmp_path, cambio, motivo):
    with pytest.raises(MedidaInvalida, match=motivo):
        registrar(tmp_path, PERFIL, "tolerancias", HOLGURAS | cambio,
                  fotos=[("peine.jpg", JPEG)], fecha="2026-11-10")

    # Ni el registro ni la foto: o entra todo, o nada.
    assert not (tmp_path / "impresoras").exists()
    assert perfil_activo(RAIZ, workspace=tmp_path).impresora.hole_mm("M3_through") == 3.3


def test_la_ultima_medida_manda_y_la_anterior_se_guarda(tmp_path):
    """Archivar no es borrar: la medida vieja explica por qué se cambió."""
    registrar(tmp_path, PERFIL, "tolerancias", HOLGURAS, fotos=[], fecha="2026-11-10")
    registrar(tmp_path, PERFIL, "tolerancias", HOLGURAS | dict(m3_through_mm=3.5),
              fotos=[], fecha="2026-11-12")

    assert perfil_activo(RAIZ, workspace=tmp_path).impresora.hole_mm("M3_through") == 3.5
    assert [r["fecha"] for r in registros(tmp_path, PERFIL)] == ["2026-11-10", "2026-11-12"]


# --- La resistencia: la barra de flexión ---------------------------------------------


def test_la_barra_que_rompe_con_2_kg_a_50_mm_da_36_8_mpa(tmp_path):
    """Voladizo de sección 10 × 4 mm: σ = M·c/I = 6·F·L / (b·h²).
    A mano: 6 × (2 × 9.80665) N × 50 mm / (10 × 4² mm³) = 36.775 MPa."""
    registrar(tmp_path, PERFIL, "resistencia", {"orientacion": "xy", "carga_kg": 2.0},
              fotos=[("rota.jpg", JPEG)], fecha="2026-11-10")

    resistencia = perfil_activo(RAIZ, workspace=tmp_path).datos["resistencia"]
    assert resistencia["xy_MPa"] == pytest.approx(36.775, abs=0.01)
    # La de entre capas sigue siendo la estimada: no se ha medido.
    assert resistencia["z_MPa"] == yaml.safe_load(YAML.read_text(encoding="utf-8"))[
        "resistencia"]["z_MPa"]
    # El factor de seguridad no lo cambia una medida.
    assert resistencia["factor_seguridad"] == 3


def test_una_carga_que_no_es_un_peso_no_se_apunta(tmp_path):
    for mala in (0, -1, "dos"):
        with pytest.raises(MedidaInvalida):
            registrar(tmp_path, PERFIL, "resistencia", {"orientacion": "xy", "carga_kg": mala},
                      fotos=[], fecha="2026-11-10")
    with pytest.raises(MedidaInvalida, match="orientación"):
        registrar(tmp_path, PERFIL, "resistencia", {"orientacion": "diagonal", "carga_kg": 1},
                  fotos=[], fecha="2026-11-10")


# --- Las pruebas propias: referencia, sin números ----------------------------------


def test_una_prueba_propia_se_guarda_con_su_foto_sin_cambiar_el_perfil(tmp_path):
    sin_nada = perfil_activo(RAIZ, workspace=tmp_path).datos

    registrar(tmp_path, PERFIL, "referencia",
              {"titulo": "Torre de voladizos de Printables", "nota": "bien hasta 60°"},
              fotos=[("torre.png", PNG)], fecha="2026-11-10")

    assert perfil_activo(RAIZ, workspace=tmp_path).datos == sin_nada
    (r,) = registros(tmp_path, PERFIL)
    assert r["valores"]["titulo"] == "Torre de voladizos de Printables"
    assert (tmp_path / "impresoras" / PERFIL / "fotos" / r["fotos"][0]).read_bytes() == PNG


# --- Las fotos ------------------------------------------------------------------------


def test_lo_que_no_es_una_foto_no_se_guarda(tmp_path):
    with pytest.raises(MedidaInvalida, match="foto"):
        registrar(tmp_path, PERFIL, "referencia", {"titulo": "x"},
                  fotos=[("virus.jpg", b"MZ\x90\x00 esto es un ejecutable")], fecha="2026-11-10")
    with pytest.raises(MedidaInvalida, match="MB"):
        registrar(tmp_path, PERFIL, "referencia", {"titulo": "x"},
                  fotos=[("enorme.jpg", JPEG + b"\x00" * 11_000_000)], fecha="2026-11-10")
    assert not (tmp_path / "impresoras").exists()


def test_el_nombre_de_la_foto_lo_pone_el_servidor(tmp_path):
    """El nombre llega del navegador: es texto ajeno, nunca una ruta."""
    registrar(tmp_path, PERFIL, "referencia", {"titulo": "x"},
              fotos=[("../../../etc/passwd.jpg", JPEG)], fecha="2026-11-10")

    (foto,) = (tmp_path / "impresoras" / PERFIL / "fotos").iterdir()
    assert foto.suffix == ".jpg" and "passwd" not in foto.name and ".." not in foto.name
    assert not (tmp_path.parent / "etc").exists()


# --- La barra de flexión se construye -----------------------------------------------


def _freecadcmd():
    import os
    return os.environ.get("FREECADCMD") or shutil.which("freecadcmd")


def test_las_dos_barras_tienen_la_seccion_y_el_brazo_del_calculo():
    """La cuenta de los MPa supone 10 × 4 mm de sección y 50 mm del borde del
    bloque al agujero; si la pieza cambia, la cuenta tiene que cambiar."""
    from orchestrator.calibracion import BARRA, recetas_barra

    assert (BARRA["ancho_mm"], BARRA["grueso_mm"], BARRA["brazo_mm"]) == (10.0, 4.0, 50.0)
    assert [r.part for r in recetas_barra()] == ["calibracion_barra_xy", "calibracion_barra_z"]


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
@pytest.mark.parametrize("parte", ["calibracion_barra_xy", "calibracion_barra_z"])
def test_la_barra_construida_tiene_el_volumen_calculado_a_mano(tmp_path, parte):
    """Bloque 20 × 10 × 12 (o 12 × 10 × 20 de pie) más la barra de 58 × 10 × 4,
    que se mete 2 mm en el bloque, menos el agujero de Ø5 que atraviesa los 4 mm:
    2400 + 2320 − 80 − π·2.5²·4 = 4561.46 mm³."""
    from mech_toolkit.generators import CATALOGO
    from orchestrator.build import build_part
    from orchestrator.calibracion import recetas_barra

    receta = {r.part: r for r in recetas_barra()}[parte]
    r = build_part(receta, CATALOGO, tmp_path / parte, _freecadcmd())

    assert r.solids == 1
    assert r.volume_mm3 == pytest.approx(2400 + 2320 - 80 - math.pi * 2.5 ** 2 * 4, rel=0.002)


# --- La página «Impresora» -----------------------------------------------------------


def _web(ws):
    from fastapi.testclient import TestClient
    from orchestrator.web.app import crear_app
    return TestClient(crear_app(ws))


def test_la_pagina_dice_que_valores_estan_sin_medir(tmp_path):
    html = _web(tmp_path).get("/impresora").text

    assert "ankermake_m5_plamas" in html
    assert "3.30" in html and "sin medir" in html


def test_un_valor_que_el_peine_no_tiene_no_se_preselecciona(tmp_path):
    """La holgura libre por defecto es 0.35 y el peine va de 0.1 en 0.1. El
    desplegable enseñaba la primera opción, +0.0, y se podía guardar sin
    haberla elegido (vista en el navegador, 2026-11-09)."""
    html = _web(tmp_path).get("/impresora").text

    libre = html.split('name="clearance_mm"', 1)[1].split("</select>", 1)[0]
    assert '<option value="" selected disabled>' in libre
    assert 'name="clearance_mm" required' in html


def test_desde_la_pagina_se_apunta_una_medida_con_su_foto(tmp_path):
    web = _web(tmp_path)
    foto = base64.b64encode(JPEG).decode()

    r = web.post("/api/impresora/medidas", json={
        "tipo": "tolerancias", "valores": HOLGURAS, "nota": "con el eje de 5",
        "fotos": [{"nombre": "peine.jpg", "datos": foto}]})

    assert r.status_code == 200, r.text
    html = web.get("/impresora").text
    assert "3.40" in html and "medido el" in html
    (r,) = registros(tmp_path, PERFIL)
    assert web.get(f"/impresora/fotos/{r['fotos'][0]}").content == JPEG


def test_una_medida_imposible_desde_la_pagina_dice_por_que(tmp_path):
    r = _web(tmp_path).post("/api/impresora/medidas", json={
        "tipo": "tolerancias", "valores": HOLGURAS | dict(press_mm=0.25), "fotos": []})

    assert r.status_code == 422
    assert "peine" in r.json()["detail"]


def test_una_foto_se_pide_por_su_nombre_y_nunca_por_una_ruta(tmp_path):
    web = _web(tmp_path)
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")

    for ruta in ("..%2F..%2Fsecreto.txt", "..%5Csecreto.txt", "no-existe.jpg"):
        assert web.get(f"/impresora/fotos/{ruta}").status_code == 404


def test_la_galeria_lleva_a_la_impresora(tmp_path):
    assert 'href="/impresora"' in _web(tmp_path).get("/").text


# --- Todo el diseño ve lo medido --------------------------------------------------------


def test_la_orden_disena_con_lo_medido():
    """Si un camino de la orden leyera el perfil sin el workspace, diseñaría
    con 3.3 aunque el usuario hubiera medido 3.4, y nada fallaría."""
    import re
    texto = Path("orchestrator/cli.py").read_text(encoding="utf-8")
    sin_medidas = re.findall(r"perfil_activo\(raiz\)", texto)
    assert sin_medidas == []


# --- Los tornillos que el perfil no tabula (F9.8 (métricas)) -----------------------------------
#
# El perfil solo trae M3 completo y M4 y M5 pasantes. Los dos SG90 del
# pan-tilt se sujetan con tornillos de 2 mm que roscan en la pieza, y el
# diseñador no tenía de dónde sacar ese diámetro: taladró Ø2.2 (corrida
# 1111-1342), por donde el tornillo pasa sin tocar. El número lo pone el
# usuario, midiendo: «la impresora la configura él».


def test_un_m2_de_rosca_apuntado_lo_devuelve_el_perfil_y_config_no_se_toca(tmp_path):
    antes = _huella(YAML)
    assert "M2_selftap_mm" not in perfil_activo(RAIZ).datos["holes"]

    registrar(tmp_path, PERFIL, "agujero", dict(metrica="M2", uso="rosca", mm=1.7),
              fotos=[("m2.jpg", JPEG)], fecha="2026-11-11")

    medido = perfil_activo(RAIZ, workspace=tmp_path)
    assert medido.impresora.hole_mm("M2_selftap") == 1.7
    assert medido.medido["holes.M2_selftap_mm"]["fecha"] == "2026-11-11"
    # Un agujero suelto no dice que las holguras estén medidas.
    assert medido.impresora.calibrated is False
    assert "M2_selftap_mm" not in perfil_activo(RAIZ).datos["holes"]
    assert _huella(YAML) == antes


def test_cada_tornillo_apuntado_se_suma_y_del_mismo_manda_el_ultimo(tmp_path):
    registrar(tmp_path, PERFIL, "agujero", dict(metrica="M2", uso="rosca", mm=1.7), fotos=[])
    registrar(tmp_path, PERFIL, "agujero", dict(metrica="M4", uso="tuerca", mm=7.2), fotos=[])
    registrar(tmp_path, PERFIL, "agujero", dict(metrica="M2", uso="rosca", mm=1.6), fotos=[])

    agujeros = perfil_activo(RAIZ, workspace=tmp_path).datos["holes"]
    assert (agujeros["M2_selftap_mm"], agujeros["M4_nut_af_mm"]) == (1.6, 7.2)
    assert len(registros(tmp_path, PERFIL)) == 3      # nada se borra


@pytest.mark.parametrize("valores, motivo", [
    # Un tornillo de 2 no rosca en un agujero de 2.2: es el fallo de la corrida.
    (dict(metrica="M2", uso="rosca", mm=2.2), "más estrecho"),
    # Ni pasa por uno de 2.
    (dict(metrica="M2", uso="pasante", mm=2.0), "más ancho"),
    # La tuerca M4 mide 7 entre caras (ISO 4032): en 6.8 no entra.
    (dict(metrica="M4", uso="tuerca", mm=6.8), "7"),
    (dict(metrica="M2", uso="rosca", mm=17), "más estrecho"),     # un 1.7 mal tecleado
    (dict(metrica="tres", uso="rosca", mm=2.5), "métrica"),
    (dict(metrica="M2", uso="pegado", mm=1.7), "pasante"),
    # Los tres de M3 salen de la pieza de calibración, que los prueba juntos.
    (dict(metrica="M3", uso="pasante", mm=3.4), "holguras"),
])
def test_un_agujero_que_no_puede_ser_no_se_apunta(tmp_path, valores, motivo):
    with pytest.raises(MedidaInvalida, match=motivo):
        registrar(tmp_path, PERFIL, "agujero", valores, fotos=[])
    assert registros(tmp_path, PERFIL) == []


def test_desde_la_pagina_se_apunta_un_tornillo_que_el_perfil_no_tenia(tmp_path):
    web = _web(tmp_path)
    html = web.get("/impresora").text
    assert 'data-tipo="agujero"' in html
    assert "Agujero M2 de rosca directa" not in html

    r = web.post("/api/impresora/medidas", json={
        "tipo": "agujero", "valores": {"metrica": "M2", "uso": "rosca", "mm": "1.7"},
        "fotos": []})

    assert r.status_code == 200, r.text
    html = web.get("/impresora").text
    fila = html.split("Agujero M2 de rosca directa", 1)[1].split("</tr>", 1)[0]
    assert "1.70 mm" in fila and "medido el" in fila
    # Los que el perfil ya traía sin medir también se ven: M4 pasante, 4.5.
    assert "4.50 mm" in html.split("Agujero M4 pasante", 1)[1].split("</tr>", 1)[0]
