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


def test_fichar_una_pieza_que_coloca_otra_de_la_obra_no_necesita_el_entorno(tmp_path, monkeypatch):
    """«Está bien» al soporte de giro (2026-11-09) reventó en la web: el
    soporte coloca la base debajo, y la web, sin `INTELLIPRINT_FICHAS`, no
    encontraba la ficha de la base. La de la obra está donde se ficha."""
    import json

    from orchestrator.obra import fichar
    monkeypatch.delenv("INTELLIPRINT_FICHAS", raising=False)
    fichas = tmp_path / "fichas"
    fichas.mkdir()
    (fichas / "obra-base.yaml").write_text(
        "id: obra-base\nnombre: Base\norigen: impreso\nfuentes: [{url: p, cita: construida}]\n"
        "marco: el suyo\nmira: '+z'\ncuerpos: [{nombre: base, caja: [70, 34, 18.5], "
        "en: [0, 0, 0]}]\n", encoding="utf-8")
    carpeta = tmp_path / "giro"
    carpeta.mkdir()
    (carpeta / "giro.step").write_text("STEP", encoding="utf-8")
    (carpeta / "envolvente.json").write_text(json.dumps({"min": [0, 0, 0], "max": [56, 34, 31]}),
                                             encoding="utf-8")
    (carpeta / "rasgos.json").write_text(json.dumps([
        {"nombre": "base", "tipo": "componente", "ficha": "obra-base", "en": [-29.4, -12.2, -27.6],
         "giros": [], "entra_por": "-z"}]), encoding="utf-8")
    assert fichar(carpeta, "obra-giro", "Giro", fichas, proyecto="prueba").is_file()


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


ENCIMA = """
def construir(kit):
    soporte = kit.componente("soporte-impreso", en=(0, 0, 0), entra_por="+z")
    bloque = kit.caja(40, 20, 20, en=(-20, -10, 5))
    return bloque.quitar("soporte", soporte.hueco(holgura=0.4))
"""
"""Un bloque apoyado encima del soporte, que le resta su hueco."""


def test_el_hueco_de_una_pieza_impresa_es_su_forma_y_no_su_envolvente_barrida(
        tmp_path, monkeypatch):
    """La plataforma del pan-tilt (2026-11-09) restó el hueco del soporte de
    giro, y el hueco era la envolvente del soporte barrida hasta el infinito
    por `entra_por`: le cortó el cuello a 17 mm del cuerno, que está dentro de
    esa envolvente. Lo que ocupa una pieza vecina es su forma, con holgura.

    A mano: la placa ocupa z 0..5 y su forma crecida 0.2 (la mitad de 0.4)
    le quita al bloque 40 × 20 × 0.2 = 160 mm³ de abajo, menos los dos M3
    de Ø3.3, que crecidos quedan de Ø2.9 y dejan 2 × π·1.45²·0.2 = 2.6 mm³.
    Con la envolvente barrida no quedaba bloque."""
    _fichar(tmp_path, monkeypatch, SOPORTE, "soporte-impreso", "Soporte impreso")
    r = build_part(Programa(part="bloque", codigo=ENCIMA), None, tmp_path / "bloque",
                   _freecadcmd(), perfil=PERFIL)
    assert r.volume_mm3 == pytest.approx(16000 - 160 + 2.6, abs=5)


ACABADO = SOPORTE.replace("return placa", "return placa.acabar(radio=1.0)")
"""El soporte con sus aristas redondeadas, como sale cualquier pieza: con
ellas OCC ya no crece la forma movida (la placa a secas sí)."""

DENTRO = """
def construir(kit):
    soporte = kit.componente("soporte-acabado", en={en}, girar={girar}, entra_por="+z")
    x, y, z = {en}
    cubo = kit.caja(50, 50, 50, en=(x - 25, y - 25, z - 25))
    return cubo.quitar("soporte", soporte.hueco(holgura=0.4))
"""
"""Un cubo de 50 centrado donde va el soporte, que lo encierra entero en
cualquier giro de cuarto de vuelta: el hueco que le deja es el mismo."""


def test_el_hueco_de_una_pieza_impresa_no_cambia_al_moverla_ni_girarla(tmp_path, monkeypatch):
    """Banco 1109-2349: el soporte de giro del pan-tilt no se construyó en
    cinco intentos (FreeCAD pasaba de 180 s). OCC no sabe crecer una forma
    leída de un STEP una vez movida o girada —ni con una traslación—, y el
    hueco caía a unir seis copias desplazadas: 114 s con la base, dos veces,
    y una forma rota al final. Mover una pieza no cambia lo que ocupa, así
    que su hueco tiene que restar lo mismo esté donde esté."""
    _fichar(tmp_path, monkeypatch, ACABADO, "soporte-acabado", "Soporte acabado")
    volumenes = [
        build_part(Programa(part=f"cubo{i}", codigo=DENTRO.format(en=en, girar=girar)), None,
                   tmp_path / f"cubo{i}", _freecadcmd(), perfil=PERFIL).volume_mm3
        for i, (en, girar) in enumerate([((0, 0, 0), []), ((7, 3, 2), []),
                                         ((7, 3, 2), [("x", 90)])])]
    assert volumenes[1] == pytest.approx(volumenes[0], abs=0.5)
    assert volumenes[2] == pytest.approx(volumenes[0], abs=0.5)


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
