"""Una pieza terminada es una ficha (F7.1 (fichar)).

Para diseñar por partes, la pieza siguiente se diseña contra la que ya está
hecha con la misma maquinaria que contra un 608ZZ comprado: `kit.componente`,
sus puntos con nombre y las sondas `componente_cabe` y `componente_entra`.
La ficha guarda el STEP CONSTRUIDO, no lo que el programa dijo haber hecho:
medir contra él no es el etiquetado circular de la ADR-011.

Los valores esperados están hechos a mano: una placa de 40 × 20 × 5 centrada
en el origen tiene su envolvente en (-20, -10, 0)–(20, 10, 5), y sus M3
pasantes son de Ø3.3 porque eso pone el perfil de la impresora.
"""

import pytest

from orchestrator.banco import ComponenteCabe, ComponenteEntra, medir_sondas
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd
from tests.test_sondas import MATERIAL, PERFIL

SOPORTE = """
def construir(kit):
    placa = kit.caja(40, 20, 5, en=(-20, -10, 0))
    for i, x in enumerate((-10, 10)):
        placa = placa.tornillo(f"m3_{i + 1}", "M3", en=(x, 0, 5), eje="-z")
    return placa
"""

TAPA = """
def construir(kit):
    soporte = kit.componente("soporte-impreso", en=(0, 0, {z}), entra_por="+z")
    tapa = kit.caja(40, 20, 3, en=(-20, -10, 5))
    for i in (1, 2):
        x, y, z = soporte.punto(f"m3_{{i}}")
        tapa = tapa.tornillo(f"m3_{{i}}", "M3", en=(x, y, 8), eje="-z")
    return tapa
"""
"""Una tapa atornillada encima del soporte, con los agujeros sacados de los
del soporte. Con z=1 el soporte sube 1 mm y se mete en la tapa."""

PASADOR = "def construir(kit):\n    return kit.cilindro(10, 15)\n"

BLOQUE = """
def construir(kit):
    bloque = kit.caja(30, 30, 20, en=(-15, -15, 0))
    return bloque.taladrar("alojamiento", 10.4, en=(0, 0, 0), eje="z", profundidad=15)
"""
"""Un agujero ciego de Ø10.4 desde abajo, 15 de fondo: por arriba le quedan
5 mm de tapa. El pasador de Ø10 cabe, entra desde abajo y no desde arriba."""


def _construir(codigo, carpeta, part):
    build_part(Programa(part=part, codigo=codigo), None, carpeta, _freecadcmd(), perfil=PERFIL)
    return carpeta


def _fichar(tmp_path, monkeypatch, codigo, id_, nombre):
    from orchestrator.obra import fichar
    fichas = tmp_path / "fichas"
    fichar(_construir(codigo, tmp_path / id_, id_), id_, nombre, fichas, proyecto="prueba")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", str(fichas))
    from orchestrator.componentes import cargar
    return cargar(id_)


def test_la_ficha_de_una_pieza_impresa_es_su_step_y_sus_agujeros(tmp_path, monkeypatch):
    from orchestrator.componentes import envolvente, resumen
    f = _fichar(tmp_path, monkeypatch, SOPORTE, "soporte-impreso", "Soporte impreso")
    assert f.origen == "impreso" and not f.verificado
    assert [c.step is not None for c in f.cuerpos] == [True]
    a, b = envolvente(f)
    assert a == pytest.approx([-20, -10, 0], abs=1e-3) and b == pytest.approx([20, 10, 5], abs=1e-3)
    assert {(h.nombre, h.diametro, tuple(h.en), h.eje) for h in f.fijacion} == {
        ("m3_1", 3.3, (-10, 0, 5), "-z"), ("m3_2", 3.3, (10, 0, 5), "-z")}
    assert "impresa en este proyecto" in resumen(f)


def test_la_ficha_lleva_montado_lo_que_la_pieza_aloja(tmp_path, monkeypatch):
    """La base del pan-tilt (2026-11-09) se fichó sin su SG90: el soporte de
    giro, que se apoya en el cuerno de ese servo, no veía su carcasa ni su
    eje, y puso el cubo 1.1 mm dentro de la carcasa sin que nada lo viera. La
    pieza siguiente se diseña contra la pieza montada, no contra la pieza
    vacía. El SG90 va en (23.6, 6, 0), como en la base."""
    import json

    from orchestrator.componentes import cargar
    from orchestrator.obra import fichar
    carpeta = tmp_path / "base"
    carpeta.mkdir()
    (carpeta / "base.step").write_text("STEP", encoding="utf-8")
    (carpeta / "envolvente.json").write_text(json.dumps({"min": [0, 0, 0], "max": [70, 34, 18.5]}),
                                             encoding="utf-8")
    (carpeta / "rasgos.json").write_text(json.dumps([
        {"nombre": "sg90", "tipo": "componente", "ficha": "sg90", "en": [23.6, 6.0, 0.0],
         "giros": [], "entra_por": "+z"}]), encoding="utf-8")
    fichar(carpeta, "obra-base", "Base", tmp_path / "fichas", proyecto="prueba")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", str(tmp_path / "fichas"))
    f = cargar("obra-base")

    servo = cargar("sg90")
    cuerpo = next(c for c in f.cuerpos if c.nombre == "sg90: cuerpo")
    assert cuerpo.en == pytest.approx([23.6, 6.0, 0.0])
    assert cuerpo.caja == pytest.approx(next(c for c in servo.cuerpos if c.nombre == "cuerpo").caja)
    eje = next(c for c in f.despejar if c.nombre == "sg90: eje_y_cubo_del_cuerno")
    assert eje.en == pytest.approx([23.6 + 5.8, 6.0 + 6.2, 27.1])
    assert eje.cilindro.eje == "+z" and eje.cilindro.diametro == 6.9


@pytest.mark.parametrize("z, cabe", [(0, True), (1, False)])
def test_la_pieza_siguiente_se_disena_contra_la_ficha(tmp_path, monkeypatch, z, cabe):
    f = _fichar(tmp_path, monkeypatch, SOPORTE, "soporte-impreso", "Soporte impreso")
    resultado = build_part(Programa(part="tapa", codigo=TAPA.format(z=z)), None,
                           tmp_path / "tapa", _freecadcmd(), perfil=PERFIL)
    agujeros = sorted(r["entrada"][0] for r in resultado.rasgos if r["tipo"] == "agujero")
    assert agujeros == pytest.approx([-10, 10])
    [m] = medir_sondas(tmp_path / "tapa" / "tapa.step", [ComponenteCabe(
        tipo="componente_cabe", ficha=f.model_dump(), en=[0, 0, z])], _freecadcmd(), MATERIAL)
    assert (m.estado == "cumple") == cabe, m.detalle
    if not cabe:
        assert "Soporte impreso" in m.detalle


@pytest.mark.parametrize("entra_por, entra", [("-z", True), ("+z", False)])
def test_una_pieza_impresa_entra_solo_por_donde_hay_camino(tmp_path, monkeypatch,
                                                           entra_por, entra):
    f = _fichar(tmp_path, monkeypatch, PASADOR, "pasador", "Pasador impreso")
    _construir(BLOQUE, tmp_path / "bloque", "bloque")
    cabe, mete = medir_sondas(tmp_path / "bloque" / "bloque.step", [
        ComponenteCabe(tipo="componente_cabe", ficha=f.model_dump(), en=[0, 0, 0]),
        ComponenteEntra(tipo="componente_entra", ficha=f.model_dump(), en=[0, 0, 0],
                        entra_por=entra_por)], _freecadcmd(), MATERIAL)
    assert cabe.estado == "cumple", cabe.detalle
    assert (mete.estado == "cumple") == entra, mete.detalle
