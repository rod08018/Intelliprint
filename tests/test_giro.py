"""El sitio de cada giro se mide mientras se diseña cada pieza
(F9.1 (barrido), F9.5 (parcial)).

El pan-tilt del banco 1110-0313 pasó cuatro de sus cinco comprobaciones y
falló «se mueve sin chocar». Sus tres piezas estaban dadas por buenas cuando
se movió entero por primera vez, y la corrección se le pidió a la
plataforma, que bajó de 68.4 a 37.7 mm de radio y no podía bajar más: el
soporte, que monta el servo de inclinación, solo había dejado 12.7 mm.

Aquí están esas mismas piezas, con sus rasgos y envolventes tal como
quedaron en la corrida. Las cifras esperadas son cuentas a mano:

- del eje de inclinación al SG90 de la base: 12.2 + 33.6 − 33.1 = 12.7 mm
  (ver `tests/test_conjunto.py`);
- la plataforma coloca el soporte en (−13.55, 5.6, 2.8), así que el eje, que
  en el soporte sale en (13.55, −5.6, 12.2) hacia +x, pasa en su marco por
  (0, 0, 15). Su caja va de y = −28 a 34.6 y de z = 0 a 30: la esquina más
  lejana queda a √(34.6² + 15²) = 37.7 mm del eje. Es la cifra que dio la
  verificación de la corrida.
"""

import json

import pytest

from orchestrator.banco import ZonaLibre, medir_sondas
from orchestrator.build import build_part
from orchestrator.conjunto import articulaciones, correcciones, giros_del_plan, leer_piezas
from orchestrator.medida import defectos_de_giro, sondas_de_giro
from orchestrator.schemas.obra import Obra
from orchestrator.schemas.programa import Programa
from tests.test_conjunto import _brazo_y_poste, _obra, _sg90, _sobre
from tests.test_generators import _freecadcmd
from tests.test_sondas import MATERIAL, PERFIL

BASE = ([], [_sg90((13.6, 8.8, 6.0))], ([0, 0, 0], [50, 30, 21.6]))
SOPORTE = (["base"], [_sobre("base", (-19.4, -15.0, -33.6)),
                      _sg90((-13.55, -11.4, 6.0), [("x", 90), ("z", 90)])],
           ([-18, -18, 0], [16, 18, 20]))
PLATAFORMA = (["soporte"], [_sobre("soporte", (-13.55, 5.6, 2.8))],
              ([2.5, -28, 0], [100, 34.6, 30]))


def _plan(radio_inclinar=25.0, radio_girar=30.0) -> dict:
    return {"titulo": "Pan-tilt", "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "x", "compra": ["sg90"]},
        {"id": "soporte", "nombre": "Soporte", "que_hace": "x", "compra": ["sg90"],
         "depende_de": ["base"]},
        {"id": "plataforma", "nombre": "Plataforma", "que_hace": "x",
         "depende_de": ["soporte"]},
        {"id": "conjunto", "nombre": "El conjunto", "tipo": "conjunto", "que_hace": "x",
         "depende_de": ["base", "soporte", "plataforma"]}],
        "uniones": [
            {"tipo": "gira", "id": "u2", "gira": "soporte", "sobre": "base",
             "componente": "sg90", "recorrido_grados": 180, "radio_libre_mm": radio_girar},
            {"tipo": "gira", "id": "u3", "gira": "plataforma", "sobre": "soporte",
             "componente": "sg90", "recorrido_grados": 180, "radio_libre_mm": radio_inclinar}]}


def _pan_tilt(tmp_path, plataforma=None, **plan):
    """Base y soporte construidos; la plataforma, solo si se pasa."""
    piezas = {"base": BASE, "soporte": SOPORTE}
    if plataforma is not None:
        piezas["plataforma"] = plataforma
    _obra(tmp_path, piezas)
    (tmp_path / "obra.json").write_text(json.dumps(_plan(**plan)), encoding="utf-8")
    return tmp_path


# --- la pieza que monta el actuador deja el sitio (F9.1 (barrido)) ---------------------------

def test_al_soporte_se_le_dice_que_no_deja_sitio_para_inclinar(tmp_path):
    """Con 25 mm pedidos y 12.7 medidos, el defecto es del soporte, en su
    propio bucle, con las dos cifras y lo que estorba."""
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path), "soporte")
    assert "12.7 mm" in defecto and "25 mm" in defecto
    assert "«Plataforma»" in defecto and "lo comprado que monta «Base»" in defecto
    assert "12.3 mm" in defecto, "y cuánto le falta: 25 − 12.7"


def test_si_el_soporte_deja_el_sitio_que_pide_el_plan_no_hay_defecto(tmp_path):
    assert defectos_de_giro(_pan_tilt(tmp_path, radio_inclinar=12.0), "soporte") == []


def test_a_la_base_no_le_estorba_nada_porque_no_tiene_nada_debajo(tmp_path):
    assert defectos_de_giro(_pan_tilt(tmp_path), "base") == []


def test_el_cilindro_libre_de_cada_actuador_se_sondea_en_la_pieza_que_lo_monta(tmp_path):
    """Lo de debajo se mide con cajas; el cuerpo de la propia pieza, con su
    forma real en FreeCAD: el actuador está dentro de su caja."""
    carpeta = _pan_tilt(tmp_path)
    [del_soporte] = sondas_de_giro(carpeta, "soporte")
    assert del_soporte.punto == pytest.approx([13.55, -5.6, 12.2])
    assert del_soporte.eje == pytest.approx([1, 0, 0]) and del_soporte.radio_mm == 25
    [de_la_base] = sondas_de_giro(carpeta, "base")
    assert de_la_base.punto == pytest.approx([19.4, 15.0, 33.1])
    assert de_la_base.eje == pytest.approx([0, 0, 1]) and de_la_base.radio_mm == 30
    assert sondas_de_giro(carpeta, "plataforma") == []


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
@pytest.mark.parametrize("y, dentro", [(-2, True), (20, False)])
def test_lo_que_la_pieza_mete_en_el_cilindro_libre_sale_en_mm3(tmp_path, y, dentro):
    """Un taco de 4 × 4 × 4 a 10 mm de la cara de salida. Centrado en el eje
    cabe entero en un cilindro de radio 10: invade 4·4·4 = 64 mm³. A 20 mm
    del eje queda fuera."""
    codigo = f"def construir(kit):\n    return kit.caja(4, 4, 4, en=(10, {y}, -2))\n"
    build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(), perfil=PERFIL)
    sonda = ZonaLibre(tipo="zona_libre", nombre="eje", punto=[0, 0, 0], eje=[1, 0, 0],
                      radio_mm=10)
    [r] = medir_sondas(tmp_path / "p.step", [sonda], _freecadcmd(), MATERIAL)
    assert r.estado == ("no_cumple" if dentro else "cumple"), r.detalle
    if dentro:
        assert "64 mm³" in r.detalle and "10 mm" in r.detalle


# --- la pieza que gira no pasa de su sitio ---------------------------------------------------

def test_a_la_plataforma_se_le_dice_que_se_sale_del_sitio_que_tiene(tmp_path):
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, PLATAFORMA), "plataforma")
    assert "37.7 mm" in defecto and "25 mm" in defecto and "«Soporte»" in defecto


def test_la_plataforma_que_cabe_en_su_sitio_no_tiene_defecto(tmp_path):
    carpeta = _pan_tilt(tmp_path, PLATAFORMA, radio_inclinar=40.0)
    assert defectos_de_giro(carpeta, "plataforma") == []


def test_lo_que_gira_va_por_delante_de_la_cara_de_salida(tmp_path):
    """El sitio reservado empieza en la cara por donde sale el eje. Una
    plataforma que vuelve 10 mm hacia atrás se mete donde está el servo y la
    pieza que lo sujeta. Radio: √(28² + 15²) = 31.8, dentro de 40."""
    atras = (PLATAFORMA[0], PLATAFORMA[1], ([-10, -28, 0], [60, 20, 30]))
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, atras, radio_inclinar=40.0), "plataforma")
    assert "10.0 mm por detrás" in defecto


def test_lo_que_gira_tiene_que_llegar_al_eje(tmp_path):
    """Colocada 50 mm más allá, su caja empieza a 2.5 + 63.55 − 13.55 = 52.5
    mm de la cara de salida: no se acopla a nada."""
    lejos = (["soporte"], [_sobre("soporte", (-63.55, 5.6, 2.8))], PLATAFORMA[2])
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, lejos, radio_inclinar=200.0), "plataforma")
    assert "52.5 mm" in defecto and "no llega" in defecto


def test_lo_que_gira_coloca_la_pieza_sobre_la_que_gira(tmp_path):
    suelta = (["soporte"], [], PLATAFORMA[2])
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, suelta), "plataforma")
    assert "obra-soporte" in defecto


def test_un_backlog_sin_uniones_no_mide_nada_de_esto(tmp_path):
    """Los de antes del 2026-11-10 siguen como estaban."""
    carpeta = _obra(tmp_path, {"base": BASE, "soporte": SOPORTE})
    assert defectos_de_giro(carpeta, "soporte") == []
    assert sondas_de_giro(carpeta, "soporte") == []


# --- solo gira lo que el plan dice (F9.5 (parcial)) -------------------------------------------

def test_solo_gira_lo_que_el_plan_dice_que_gira(tmp_path):
    """Una tapa que el plan atornilla a la base pero que queda a 0.5 mm del
    eje de su servo. Sin plan gira con él, por cercanía; con plan, solo si
    el plan lo dice, y sobre el componente que dice."""
    carpeta = _obra(tmp_path, {
        "base": ([], [_sg90((23.6, 6, 0))], ([0, 0, 0], [70, 34, 18.5])),
        "tapa": (["base"], [_sobre("base", (-29.4, -12.2, -27.6))],
                 ([-28, -17, 0], [28, 17, 31]))})
    piezas = leer_piezas(carpeta, "conjunto")
    assert len(articulaciones(piezas)) == 1
    assert articulaciones(piezas, giros={}) == []
    assert len(articulaciones(piezas, giros={"tapa": ("sg90", "eje")})) == 1
    assert articulaciones(piezas, giros={"tapa": ("608zz", "aro interior")}) == []


def test_los_giros_salen_del_plan_y_un_backlog_de_antes_no_tiene():
    assert giros_del_plan(Obra(**_plan())) == {"soporte": ("sg90", "eje"),
                                               "plataforma": ("sg90", "eje")}
    sin = {k: v for k, v in _plan().items() if k != "uniones"}
    assert giros_del_plan(Obra(**sin)) is None


# --- quién corrige un choque cuando hay plan ---------------------------------------------------

def test_si_falta_sitio_la_correccion_es_para_quien_monta_el_actuador(tmp_path):
    """El choque de la corrida: la plataforma contra el SG90 de la base.
    Sin plan, la corrección va a la plataforma, «la que va después». Con el
    plan pidiendo 25 mm y el soporte dejando 12.7, la culpa es del soporte.
    Y si el soporte hubiera dejado lo pedido (12), sería de la plataforma,
    que se sale."""
    carpeta = _pan_tilt(tmp_path, PLATAFORMA)
    piezas = leer_piezas(carpeta, "conjunto")
    arts = {a.pieza: a for a in articulaciones(piezas)}
    choques = [{"a": "base", "b": "plataforma", "solido_a": "base: montado",
                "solido_b": "plataforma", "angulos": {"plataforma": 0.0, "soporte": 0.0},
                "hueco_mm": -27.9}]
    assert list(correcciones(piezas, arts, choques)) == ["plataforma"]
    con_plan = correcciones(piezas, arts, choques, presupuestos={"plataforma": 25.0})
    assert list(con_plan) == ["soporte"]
    assert "12.7 mm" in con_plan["soporte"] and "25 mm" in con_plan["soporte"]
    assert list(correcciones(piezas, arts, choques,
                             presupuestos={"plataforma": 12.0})) == ["plataforma"]


# --- mover lo construido tras cada pieza (F9.5 (parcial)) --------------------------------------

@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_la_pieza_que_gira_se_mueve_contra_lo_construido_sin_esperar_al_conjunto(tmp_path):
    """El brazo y el poste de `tests/test_conjunto.py`, con una tercera pieza
    del backlog que aún no existe. A mano (allí está la cuenta): chocan a
    80° y a 90°. Se sabe al construir el brazo, sin verificación del
    conjunto ni animación."""
    from orchestrator.conjunto import mover_lo_construido
    carpeta = _brazo_y_poste(tmp_path, x0=-5, y0=30)
    obra = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    obra["nodos"].insert(2, {"id": "remate", "nombre": "Remate", "que_hace": "x",
                             "depende_de": ["brazo"]})
    obra["nodos"][-1]["depende_de"].append("remate")
    (carpeta / "obra.json").write_text(json.dumps(obra), encoding="utf-8")

    v = mover_lo_construido(carpeta, "brazo", _freecadcmd(), min_gap_mm=0.2)
    assert sorted({c["angulos"]["brazo"] for c in v["choques"]}) == [80, 90]
    assert "80°" in v["correccion"] and "Pieza base" in v["correccion"]
    assert not (carpeta / "nodos" / "conjunto").exists()

    (tmp_path / "libre").mkdir()
    libre = _brazo_y_poste(tmp_path / "libre", x0=-5, y0=60)
    assert mover_lo_construido(libre, "brazo", _freecadcmd(), min_gap_mm=0.2) == {
        "choques": [], "correccion": ""}


# --- un pan-tilt hecho a mano, de punta a punta y sin modelo -------------------------------------

BASE_A_MANO = """
def construir(kit):
    servo = kit.componente("sg90", en=(13.6, 8.8, 6.0), entra_por="+z")
    return kit.caja(50, 30, 21.6).quitar("alojamiento", servo.hueco())
"""

SOPORTE_A_MANO = """
def construir(kit):
    kit.componente("obra-base", en=(-19.4, -15.0, -33.6), entra_por="-z")
    servo = kit.componente("sg90", en=(-13.55, -11.4, {z}), girar=[("x", 90), ("z", 90)],
                           entra_por="+z")
    return kit.caja({ancho}, 36, {alto}, en=(-18, -18, 0)).quitar("alojamiento", servo.hueco())
"""
"""El soporte de la corrida 1110-0313 (z = 6, 34 de ancho, 20 de alto) y uno
que deja sitio: el servo 20 mm más arriba y el cuerpo entero por detrás de
la cara de salida (x = 13.55)."""

PLATAFORMA_A_MANO = """
def construir(kit):
    kit.componente("obra-soporte", en=(-13.55, 5.6, -32.2), entra_por="-x")
    return kit.caja(4, 20, {bajo} + 10, en=(4, -10, -{bajo})) + kit.caja(34, 20, 4, en=(6, -10, -{bajo}))
"""
"""Una L acoplada al eje, que pasa por su origen hacia +x: una placa a 4 mm
de la cara de salida, que baja hasta z = −`bajo`, y una repisa en su pie. Con
`bajo` = 14, su esquina más lejana queda a √(10² + 14²) = 17.2 mm del eje."""


def _del_giro(defectos) -> list[str]:
    return [d for d in defectos if d.startswith(("sitio para girar", "giro", "Choca",
                                                 "No deja sitio"))]


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_un_pan_tilt_hecho_a_mano_se_mide_pieza_a_pieza_y_luego_se_mueve_entero(
        tmp_path, monkeypatch):
    """El camino entero de un backlog con plan, con programas escritos a
    mano en vez de un modelo: cada pieza se construye, se le miden sus giros
    como en su bucle de diseño, se ficha, y al final se mueve el conjunto.

    - El soporte de la corrida 1110-0313 no vale: 12.7 mm contra 25, y su
      cuerpo asoma por delante de la cara de salida.
    - Con el servo 20 mm más arriba el eje queda a 12.7 + 20 = 32.7 mm del
      SG90 de la base: vale.
    - Una plataforma que baja hasta z = −40 llega a √(10² + 40²) = 41.2
      mm del eje: no vale. Con la repisa a 14, sí.
    - Y el conjunto de las tres se mueve entero sin chocar, con un giro
      vertical y otro horizontal: lo que pide el encargo 11 del banco."""
    from orchestrator import obra as O
    from orchestrator.conjunto import verificar_conjunto
    from orchestrator.medida import defectos_de_la_pieza

    (tmp_path / "obra.json").write_text(json.dumps(_plan(radio_inclinar=25.0, radio_girar=30.0)),
                                        encoding="utf-8")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", str(O.carpeta_de_fichas(tmp_path)))
    # `cli._paso_de_obra` la deja puesta en el proceso: si un test de
    # `test_obra.py` corre antes que este, el kit rechaza el SG90 de la base
    # como si fuera de otro backlog (visto al correrlos en otro orden).
    monkeypatch.delenv("INTELLIPRINT_AJENOS", raising=False)

    def disenar(nodo, codigo):
        parte = tmp_path / "nodos" / nodo / "parts" / nodo
        monkeypatch.setenv("INTELLIPRINT_UNIONES", str(O.escribir_uniones(tmp_path, nodo)))
        resultado = build_part(Programa(part=nodo, codigo=codigo), None, parte, _freecadcmd(),
                               perfil=PERFIL)
        return _del_giro(defectos_de_la_pieza(
            [], resultado, parte / f"{nodo}.step", _freecadcmd(), MATERIAL,
            holgura_al_moverse_mm=0.1))

    def fichar(nodo):
        O.fichar(tmp_path / "nodos" / nodo / "parts" / nodo, O.id_de_ficha(nodo), nodo,
                 O.carpeta_de_fichas(tmp_path), proyecto="prueba")

    assert disenar("base", BASE_A_MANO) == []
    fichar("base")

    del_banco = disenar("soporte", SOPORTE_A_MANO.format(z=6.0, ancho=34, alto=20))
    assert any("solo hay 12.7 mm" in d for d in del_banco), del_banco
    assert any("mm³ en el sitio" in d for d in del_banco), del_banco
    assert disenar("soporte", SOPORTE_A_MANO.format(z=26.0, ancho=31, alto=40)) == []
    fichar("soporte")
    # Con su ficha hecha, a la plataforma se le dice cómo se llama su eje.
    [de_la_plataforma] = O.uniones_del_nodo(tmp_path, "plataforma")
    assert de_la_plataforma["salidas"] == ["sg90: eje"]

    [grande] = disenar("plataforma", PLATAFORMA_A_MANO.format(bajo=40))
    assert "41.2 mm" in grande and "25 mm" in grande
    assert disenar("plataforma", PLATAFORMA_A_MANO.format(bajo=14)) == []

    v = verificar_conjunto(tmp_path, "conjunto", _freecadcmd(), min_gap_mm=0.1, animar=False)
    assert v["ok"], v["resumen"]
    ejes = sorted(abs(round(a["eje_mundo"][2])) for a in v["articulaciones"])
    assert ejes == [0, 1], "un giro horizontal y uno vertical"
    assert [a["recorrido"] for a in v["articulaciones"]] == [[-90, 90], [-90, 90]]


# --- lo que inclina cambia de orientación (F9.14 (orienta)) -------------------------------------

DISCO = "def construir(kit):\n    return kit.cilindro(46, 9, en=(4, 0, 0), eje='x')\n"
"""La plataforma de la corrida 1111-1342: un disco de Ø46 centrado en el eje
de inclinación (+x). Sus dos caras planas miden π·23² = 1662 mm² y miran a
lo largo del eje: al girar, giran sobre sí mismas."""

ESCUADRA = """
def construir(kit):
    return (kit.caja(4, {ancho}, {ancho}, en=(4, -{ancho} / 2, 0))
            + kit.caja({largo}, {ancho}, 4, en=(6, -{ancho} / 2, 0)))
"""
"""Una placa contra el cuerno (x de 4 a 8) y una repisa que sale de su pie
(x de 6 a 6 + largo). La cara de abajo es un rectángulo de (largo + 2) ×
ancho, y mira hacia −z: perpendicular al eje, así que al inclinar cambia de
orientación."""


CON_TALADRO = ESCUADRA.format(ancho=30, largo=30).rstrip() + """.taladrar(
        "paso_del_cable", 6, en=(20, 0, 4), eje="-z")
"""
"""La misma escuadra con un taladro de Ø6 en medio de la repisa: la cámara
lo tapa, y sigue cabiendo."""


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
@pytest.mark.parametrize("codigo, cumple, cifra", [
    (DISCO, False, "1662 mm²"),
    # La cara de abajo mide (30 + 2) × 30: cabe una cámara de 25 × 24.
    (ESCUADRA.format(ancho=30, largo=30), True, "32 × 30"),
    (CON_TALADRO, True, "32 × 30"),
    # (18 + 2) × 20: mira de lado, pero no cabe.
    (ESCUADRA.format(ancho=20, largo=18), False, "20 × 20"),
    # La placa de la corrida 1111-1342 tras dos reanudaciones: 32 × 22. Son
    # 704 mm², más que los 600 de 25 × 24, y la cámara no cabe: 22 < 24.
    (ESCUADRA.format(ancho=22, largo=30), False, "32 × 22"),
])
def test_la_pieza_que_inclina_tiene_donde_llevar_algo_que_cambie_de_orientacion(
        tmp_path, codigo, cumple, cifra):
    """«Inclina una plataforma para una cámara pequeña» (el encargo 11). Una
    cámara pequeña de verdad mide 25 × 24 mm (el módulo de Raspberry Pi:
    «Around 25 × 24 × 9 mm», raspberrypi.com/documentation/accessories/
    camera.html): tiene que caber ese rectángulo en una cara plana cuya
    normal sea perpendicular al eje. El pan-tilt de la corrida 1111-1342
    pasó las cinco comprobaciones del banco con un disco coaxial: una cámara
    montada en él rodaría sobre su eje óptico en vez de cabecear.

    Primero se midió el área (600 mm²). Dos reanudaciones después la placa
    era de 32 × 22: con taladros y ranuras daba 534 mm² y no pasaba, pero
    por el motivo equivocado; maciza habría pasado con 704 y la cámara
    seguiría sin caber. Lo que hay que medir es si cabe."""
    from orchestrator.banco import CaraQueSeOrienta
    build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(), perfil=PERFIL)
    sonda = CaraQueSeOrienta(tipo="cara_que_se_orienta", eje=[1, 0, 0], cabe_mm=[25, 24])
    [r] = medir_sondas(tmp_path / "p.step", [sonda], _freecadcmd(), MATERIAL)
    assert r.estado == ("cumple" if cumple else "no_cumple"), r.detalle
    assert cifra in r.detalle, r.detalle


def test_la_pieza_que_inclina_es_la_que_gira_sobre_el_eje_horizontal(tmp_path):
    """En el pan-tilt de la corrida 1110-0313 la plataforma gira sobre el eje
    del SG90 del soporte, que en su marco sale hacia +x; el soporte gira
    sobre el de la base, vertical."""
    from orchestrator.banco import la_que_gira
    carpeta = _pan_tilt(tmp_path, PLATAFORMA)
    pieza, eje = la_que_gira(carpeta, "horizontal")
    assert pieza == "plataforma" and eje == pytest.approx([1, 0, 0])
    pieza, eje = la_que_gira(carpeta, "vertical")
    assert pieza == "soporte" and eje == pytest.approx([0, 0, 1])
    # Sin la plataforma construida no hay giro horizontal que mirar.
    (tmp_path / "otro").mkdir()
    assert la_que_gira(_pan_tilt(tmp_path / "otro"), "horizontal") is None


def test_el_encargo_del_pan_tilt_pide_que_la_plataforma_incline_de_verdad():
    from pathlib import Path

    from orchestrator.banco import SeOrienta, cargar_encargos
    [pan_tilt] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
                  if e.nombre == "pan_tilt_sg90"]
    [pide] = [a for a in pan_tilt.oraculo if isinstance(a, SeOrienta)]
    assert pide.eje == "horizontal" and list(pide.cabe_mm) == [25, 24]


# --- un giro se barre lo que el plan pide, no lo que da el servo (banco 1112-1359) ------------

def _base_y_tapa(tmp_path):
    return leer_piezas(_obra(tmp_path, {
        "base": ([], [_sg90((23.6, 6, 0))], ([0, 0, 0], [70, 34, 18.5])),
        "tapa": (["base"], [_sobre("base", (-29.4, -12.2, -27.6))],
                 ([-28, -17, 0], [28, 17, 31]))}), "conjunto")


@pytest.mark.parametrize("pedido, recorrido", [(60, (-30, 30)), (180, (-90, 90)),
                                               (None, (-90, 90))])
def test_un_giro_se_barre_lo_que_pide_el_plan(tmp_path, pedido, recorrido):
    """El dedo de la pinza del banco 1112-1359 tenía que girar 60° y se
    barrió los 180° del SG90: una pinza no puede dar media vuelta junto a su
    dedo fijo. Lo que el plan pide va repartido a los dos lados de como se
    dibujó la pieza: 60° son de -30° a 30°. Sin cifra del plan (un backlog
    de antes), lo que dé la ficha."""
    recorridos = {"tapa": pedido} if pedido else None
    [a] = articulaciones(_base_y_tapa(tmp_path), giros={"tapa": ("sg90", "eje")},
                         recorridos=recorridos)
    assert a.recorrido == pytest.approx(recorrido)


def test_el_plan_no_puede_pedir_mas_de_lo_que_da_el_servo(tmp_path):
    """Eso lo rechaza `validar_plan`; si aun así llega, manda la ficha."""
    [a] = articulaciones(_base_y_tapa(tmp_path), giros={"tapa": ("sg90", "eje")},
                         recorridos={"tapa": 270})
    assert a.recorrido == pytest.approx((-90, 90))


def test_los_recorridos_salen_del_plan_y_un_backlog_de_antes_no_tiene():
    from orchestrator.conjunto import recorridos_del_plan
    assert recorridos_del_plan(Obra(**_plan())) == {"soporte": 180, "plataforma": 180}
    sin = {k: v for k, v in _plan().items() if k != "uniones"}
    assert recorridos_del_plan(Obra(**sin)) is None


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_lo_que_estorba_fuera_del_recorrido_pedido_no_es_un_choque(tmp_path):
    """El brazo de `test_conjunto` choca con el poste a 80° y a 90°. Si el
    plan solo le pide 60° (de -30° a 30°), nunca llega hasta ahí."""
    from orchestrator.conjunto import verificar_conjunto
    carpeta = _brazo_y_poste(tmp_path, x0=-5, y0=30)
    (carpeta / "obra.json").write_text(json.dumps({"titulo": "t", "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "x", "compra": ["sg90"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "x", "depende_de": ["base"]},
        {"id": "conjunto", "nombre": "El conjunto", "tipo": "conjunto", "que_hace": "x",
         "depende_de": ["base", "brazo"]}],
        "uniones": [{"tipo": "gira", "id": "u1", "gira": "brazo", "sobre": "base",
                     "componente": "sg90", "recorrido_grados": 60, "radio_libre_mm": 60}]}),
        encoding="utf-8")
    v = verificar_conjunto(carpeta, "conjunto", _freecadcmd(), min_gap_mm=0.2, animar=False)
    assert v["ok"], v["resumen"]
    assert [a["recorrido"] for a in v["articulaciones"]] == [[-30, 30]]


def test_a_quien_disena_un_giro_corto_se_le_dice_desde_donde_se_cuenta(tmp_path):
    """Con 60° de un servo de 180°, hay que saber qué 60° son: la mitad a
    cada lado de como se dibuja. Con los 180° enteros no hay nada que
    aclarar, y el texto que ya se midió en el banco no cambia."""
    from orchestrator import obra as O
    carpeta = _pan_tilt(tmp_path, PLATAFORMA)
    textos = {u["papel"]: u["texto"] for u in O.uniones_del_nodo(carpeta, "soporte")}
    assert "a cada lado" not in textos["gira"] + textos["sobre"]
    plan = _plan()
    plan["uniones"][1]["recorrido_grados"] = 60
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    [gira] = O.uniones_del_nodo(carpeta, "plataforma")
    assert "30° a cada lado" in gira["texto"]
    sobre = {u["papel"]: u["texto"] for u in O.uniones_del_nodo(carpeta, "soporte")}["sobre"]
    assert "30° a cada lado" in sobre
