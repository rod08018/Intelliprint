"""Banco de piezas reales (F6.1 (evaluación)): cómo se juzga cada encargo.

El banco es la medida de «usable». Cada encargo trae su oráculo escrito a
mano desde la petición literal; aquí se prueba el JUEZ con hechos
sintéticos —cilindros, envolvente, laminado— para que un fallo del banco
sea de la pieza y no del que la mide.
"""

from pathlib import Path

import pytest

from mech_toolkit.geometry import Cylinder
from orchestrator.banco import (
    Encargo, Hechos, cargar_encargos, informe, juzgar, nota)

ENCARGOS = Path("tests/banco/encargos")


def _agujero(x, y, d, eje=(0, 0, 1)):
    return Cylinder(radius=d / 2, axis=list(eje), point=[x, y, 2], length=4, internal=True)


def _hechos(cilindros=(), bbox=(60, 40, 5), soportes=False):
    return Hechos(cilindros=list(cilindros), bbox_mm=list(bbox), volumen_mm3=1000.0,
                  soportes=soportes)


def _asercion(**datos):
    return Encargo(nombre="x", categoria="robots", peticion="p",
                   oraculo=[datos]).oraculo[0]


# --- agujeros ---------------------------------------------------------------

RECTANGULO = [[0, 0], [49.5, 0], [0, 10], [49.5, 10]]


def test_un_patron_de_agujeros_se_reconoce_aunque_la_pieza_este_movida_y_girada():
    """El modelo elige su origen: el patrón se compara por distancias entre
    centros, que no dependen de dónde ni cómo se colocó la pieza."""
    import math
    a = math.radians(30)
    girados = [(7 + x * math.cos(a) - y * math.sin(a), -3 + x * math.sin(a) + y * math.cos(a))
               for x, y in RECTANGULO]
    hechos = _hechos([_agujero(x, y, 3.3) for x, y in girados] + [_agujero(100, 100, 5.5)])
    r = juzgar(_asercion(tipo="agujeros", diametro_mm=3.3, patron_mm=RECTANGULO), hechos)
    assert r.estado == "cumple", r.detalle


def test_un_patron_con_un_agujero_desplazado_no_cumple_y_dice_cuanto():
    """Lo que pasó con el sargento: la cota existía, pero en otro sitio."""
    puntos = [[0, 0], [49.5, 0], [0, 10], [46.5, 10]]
    hechos = _hechos([_agujero(x, y, 3.3) for x, y in puntos])
    r = juzgar(_asercion(tipo="agujeros", diametro_mm=3.3, patron_mm=RECTANGULO), hechos)
    assert r.estado == "no_cumple"
    assert "4" in r.detalle            # pide 4 agujeros en ese patrón


def test_un_agujero_de_otro_diametro_no_cuenta():
    """Ø6.7 en vez de Ø6.4 (sargento del 2026-10-27): el número estaba en la
    receta, pero el agujero era otro."""
    hechos = _hechos([_agujero(0, 0, 6.7), _agujero(30, 0, 6.7)])
    r = juzgar(_asercion(tipo="agujeros", diametro_mm=6.4, patron_mm=[[0, 0], [30, 0]]), hechos)
    assert r.estado == "no_cumple"
    assert "6.7" in r.detalle


def test_un_saliente_no_es_un_agujero():
    hechos = _hechos([Cylinder(radius=1.65, axis=[0, 0, 1], point=[x, y, 0], length=4,
                               internal=False) for x, y in RECTANGULO])
    r = juzgar(_asercion(tipo="agujeros", diametro_mm=3.3, patron_mm=RECTANGULO), hechos)
    assert r.estado == "no_cumple"


def test_las_dos_caras_de_un_mismo_agujero_cuentan_como_uno():
    """Un agujero partido por una cara (o con avellanado) da varias caras
    cilíndricas sobre el mismo eje: no son dos agujeros."""
    caras = [_agujero(0, 0, 5.5), _agujero(0, 0, 5.5), _agujero(20, 0, 5.5)]
    r = juzgar(_asercion(tipo="agujeros", diametro_mm=5.5, patron_mm=[[0, 0], [20, 0], [40, 0]]),
               _hechos(caras))
    assert r.estado == "no_cumple"


# --- cilindros con rango ------------------------------------------------------

def test_un_alojamiento_con_holgura_cumple_dentro_del_rango():
    hechos = _hechos([_agujero(0, 0, 32.4)])
    r = juzgar(_asercion(tipo="cilindro", interior=True, nominal_mm=32, diametro_min_mm=32.1,
                         diametro_max_mm=32.8), hechos)
    assert r.estado == "cumple"


def test_un_alojamiento_sin_holgura_no_cumple():
    """Un tubo de Ø32 no entra en un agujero de Ø32."""
    hechos = _hechos([_agujero(0, 0, 32.0)])
    r = juzgar(_asercion(tipo="cilindro", interior=True, nominal_mm=32, diametro_min_mm=32.1,
                         diametro_max_mm=32.8), hechos)
    assert r.estado == "no_cumple"
    assert "32" in r.detalle


# --- envolvente, cama y laminado ---------------------------------------------

def test_la_envolvente_se_compara_sin_importar_la_orientacion():
    r = juzgar(_asercion(tipo="envolvente", min_mm=[150, 20, 3]), _hechos(bbox=(25, 4, 160)))
    assert r.estado == "cumple"
    r = juzgar(_asercion(tipo="envolvente", min_mm=[150, 20, 3]), _hechos(bbox=(25, 4, 120)))
    assert r.estado == "no_cumple"


def test_una_pieza_que_pide_soportes_no_cumple_sin_soportes():
    """Las varillas en voladizo del sargento: «sin soportes» y los pedía."""
    assert juzgar(_asercion(tipo="sin_soportes"), _hechos(soportes=True)).estado == "no_cumple"
    assert juzgar(_asercion(tipo="sin_soportes"), _hechos(soportes=False)).estado == "cumple"


def test_sin_laminado_no_se_sabe_si_pide_soportes():
    assert juzgar(_asercion(tipo="sin_soportes"), _hechos(soportes=None)).estado == "sin_medir"


def test_lo_que_aun_no_se_sabe_medir_cuenta_como_sin_medir_no_como_cumple():
    """Pared mínima, carga, estética: hasta que exista el medidor, el banco
    lo dice. Contarlo como aprobado inflaría la nota."""
    r = juzgar(_asercion(tipo="pendiente", que="aguanta 5 kg en la punta", fase="F2.6 (dfm)"),
               _hechos())
    assert r.estado == "sin_medir"


# --- nota e informe ------------------------------------------------------------

def test_la_nota_es_lo_que_cumple_entre_todo_lo_exigido():
    """Lo no medido cuenta en el denominador: si no, una pieza de la que no se
    mide nada sacaría un 100 %."""
    from orchestrator.banco import Resultado
    rs = [Resultado(estado="cumple", detalle=""), Resultado(estado="no_cumple", detalle=""),
          Resultado(estado="sin_medir", detalle=""), Resultado(estado="cumple", detalle="")]
    assert nota(rs) == pytest.approx(0.5)


def test_el_informe_tiene_una_fila_por_encargo_y_la_nota_global():
    from orchestrator.banco import Resultado
    texto = informe({"soporte": [Resultado(estado="cumple", detalle="ok")],
                     "gancho": [Resultado(estado="no_cumple", detalle="mal")]},
                    modelo="deepseek", coste_usd=0.12)
    assert "soporte" in texto and "gancho" in texto
    assert "50" in texto            # 1 de 2
    assert "deepseek" in texto


def test_los_restos_de_un_intento_fallido_no_puntuan(tmp_path):
    """Primera corrida (2026-11-03): dos piezas no llegaron a construirse,
    pero había un STEP de un intento anterior y el banco lo midió."""
    import sys
    from orchestrator.banco import correr
    deja_un_step_y_falla = (
        "import os, pathlib, sys; "
        "p = pathlib.Path(os.environ['INTELLIPRINT_WORKSPACE']) / 'projects/a/parts/b'; "
        "p.mkdir(parents=True); (p / 'b.step').write_text('x'); "
        "print('ConstruccionFallida: 3 construcciones fallidas'); sys.exit(1)")
    encargo = cargar_encargos(ENCARGOS)[0]
    resultados, fallo = correr(encargo, tmp_path, [sys.executable, "-c", deja_un_step_y_falla],
                               "no-se-llama", {})
    assert {r.estado for r in resultados} == {"no_cumple"}
    assert "3 construcciones fallidas" in fallo


# --- el banco pide por el flujo de verdad (F6.11 (biblioteca)) -----------------------------

def test_el_banco_pide_por_el_flujo_de_pieza_con_el_concepto_aprobado():
    """Hasta el 2026-11-05 el banco pedía con `intelliprint new` (el grafo
    viejo): sin investigador, sin ingeniero y sin concepto. Su 95 % no decía
    nada del flujo que usa la web, y el soporte del HC-SR04 salió de ahí."""
    from orchestrator.cli import _parser, orden_del_banco
    orden = orden_del_banco()
    assert orden[-3:] == ["orchestrator.cli", "pieza", "--aprobar-concepto"]
    assert _parser().parse_args(["pieza", "--aprobar-concepto", "un gancho"]).aprobar_concepto


def test_una_pieza_con_defectos_tambien_se_juzga(tmp_path, monkeypatch):
    """`intelliprint pieza` sale con 1 si la pieza no cumple, pero la entrega
    (F6.8 (mejor)): el juez del banco tiene que medirla, no darle un cero."""
    import sys
    from orchestrator import banco
    monkeypatch.setattr(banco, "juzgar_pieza",
                        lambda e, c, f, m=None, laminar=None: [banco.Resultado(estado="cumple", detalle="medida")])
    entrega_con_defectos = (
        "import json, os, pathlib, sys; "
        "c = pathlib.Path(os.environ['INTELLIPRINT_WORKSPACE']) / 'projects/a'; "
        "(c / 'parts/b').mkdir(parents=True); (c / 'parts/b/b.step').write_text('x'); "
        "(c / 'pieza_report.json').write_text(json.dumps({'volumen_mm3': 1000.0})); "
        "print('✗ no cumple'); sys.exit(1)")
    encargo = cargar_encargos(ENCARGOS)[0]
    resultados, fallo = banco.correr(encargo, tmp_path,
                                     [sys.executable, "-c", entrega_con_defectos], "x", {})
    assert [r.detalle for r in resultados] == ["medida"] and fallo is None


def test_un_componente_que_la_pieza_no_coloca_no_se_da_por_bueno():
    """Sin decir dónde va el sensor no hay forma de comprobar que quepa: y lo
    que no se puede comprobar no se aprueba."""
    from orchestrator.banco import Componente, Hechos, juzgar_componente, sondas_de_componente
    a = Componente(tipo="componente", ficha="hc-sr04")
    assert sondas_de_componente(a, rasgos=[]) == []
    r = juzgar_componente(a, [], Hechos(cilindros=[], bbox_mm=[1, 1, 1], volumen_mm3=1))
    assert r.estado == "no_cumple" and "no dice dónde va" in r.detalle


def test_un_componente_colocado_se_mide_con_su_ficha():
    from orchestrator.banco import Componente, sondas_de_componente
    rasgos = [{"nombre": "sensor", "tipo": "componente", "ficha": "hc-sr04",
               "en": [1, 2, 3], "giros": [["z", 90]], "entra_por": "+y"}]
    cabe, entra = sondas_de_componente(Componente(tipo="componente", ficha="hc-sr04"), rasgos)
    assert cabe.tipo == "componente_cabe" and cabe.ficha["id"] == "hc-sr04"
    assert cabe.en == [1, 2, 3] and cabe.giros == [["z", 90]]
    assert entra.tipo == "componente_entra" and entra.entra_por == "+y"


def test_rejuzgar_reconoce_una_pieza_del_flujo_nuevo(tmp_path, monkeypatch):
    from orchestrator import banco
    monkeypatch.setattr(banco, "juzgar_pieza",
                        lambda e, c, f, m=None, laminar=None: [banco.Resultado(estado="cumple", detalle="ok")])
    e = banco.Encargo(nombre="x", categoria="casa", peticion="un gancho",
                      oraculo=[{"tipo": "sin_soportes"}])
    proyecto = tmp_path / "01" / "projects" / "p"
    (proyecto / "parts" / "p").mkdir(parents=True)
    (proyecto / "parts" / "p" / "p.step").write_text("x", encoding="utf-8")
    (proyecto / "pieza_report.json").write_text('{"volumen_mm3": 10.0}', encoding="utf-8")
    (tmp_path / "01" / "salida.txt").write_text("✗ no cumple", encoding="utf-8")
    resultados, fallos = banco.rejuzgar([e], tmp_path, freecadcmd="x")
    assert [r.estado for r in resultados["x"]] == ["cumple"] and not fallos


# --- los encargos ---------------------------------------------------------------

def test_los_encargos_del_banco_son_validos_y_cubren_robots_y_casa():
    encargos = cargar_encargos(ENCARGOS)
    assert len(encargos) >= 8
    assert {"robots", "casa"} <= {e.categoria for e in encargos}
    for e in encargos:
        assert e.oraculo, e.nombre


def test_cada_cota_del_oraculo_sale_de_la_peticion_literal():
    """El oráculo no puede inventar cotas: tiene que poder leerse en lo que
    pidió la persona. Si no, el banco mediría contra otra petición. Para un
    encargo que amplía otro (F9.10 (ampliar)), lo que pidió son las dos
    peticiones: la del invento y la de la función."""
    for e in cargar_encargos(ENCARGOS):
        for a in e.oraculo:
            for cota in a.cotas_de_la_peticion():
                assert f"{cota:g}" in e.peticion_entera, \
                    f"{e.nombre}: {cota:g} no está en la petición"


def test_rejuzgar_no_puntua_una_pieza_que_no_se_construyo(tmp_path):
    """Rejuzgar (F6.12 (techo)) reutiliza las piezas de una corrida para no
    gastar modelo al cambiar el juez. Un STEP sin el «Listo» de la orden
    puede ser de un intento fallido: no puntúa, igual que al correr."""
    from orchestrator.banco import Encargo, rejuzgar

    e = Encargo(nombre="x", categoria="casa", peticion="un gancho",
                oraculo=[{"tipo": "sin_soportes"}])
    pieza = tmp_path / "01" / "projects" / "p" / "parts" / "p"
    pieza.mkdir(parents=True)
    (pieza / "p.step").write_text("restos", encoding="utf-8")
    (tmp_path / "01" / "salida.txt").write_text("Traceback ...", encoding="utf-8")

    resultados, fallos = rejuzgar([e], tmp_path, freecadcmd="no-se-llama")
    assert [r.estado for r in resultados["x"]] == ["no_cumple"]
    assert "x" in fallos


def test_rejuzgar_reconoce_una_pieza_guardada_aunque_el_proceso_muriera_despues(tmp_path,
                                                                               monkeypatch):
    """La línea base del 2026-11-05 dio 0 % sin que nada estuviera mal en las
    piezas: el laminado reventó DESPUÉS de construirlas y de guardar su
    diseño, y el informe no llegó a escribirse. `recipe.json` solo se guarda
    cuando la construcción salió; un intento fallido no lo deja."""
    from orchestrator import banco
    monkeypatch.setattr(banco, "juzgar_pieza",
                        lambda e, c, f, m=None, laminar=None: [banco.Resultado(estado="cumple", detalle="ok")])
    e = banco.Encargo(nombre="x", categoria="casa", peticion="un gancho",
                      oraculo=[{"tipo": "sin_soportes"}])
    pieza = tmp_path / "01" / "projects" / "p" / "parts" / "p"
    pieza.mkdir(parents=True)
    (pieza / "p.step").write_text("x", encoding="utf-8")
    (pieza / "recipe.json").write_text("{}", encoding="utf-8")
    (tmp_path / "01" / "salida.txt").write_text(
        "Traceback ...\nLaminadoFallido: no encuentro el STL", encoding="utf-8")
    resultados, fallos = banco.rejuzgar([e], tmp_path, freecadcmd="x")
    assert [r.estado for r in resultados["x"]] == ["cumple"] and not fallos


def test_un_encargo_que_se_pasa_de_tiempo_no_tumba_el_banco(tmp_path, monkeypatch):
    """Banco `1106-1554` (2026-11-06): el soporte del MG996R pasó de los 30
    minutos, el TimeoutExpired salió de `correr` y la corrida entera murió
    en el primer encargo, sin juzgar los otros nueve. Se pierde ese
    encargo, no el banco."""
    import subprocess

    from orchestrator import banco

    def tarda(orden, **k):
        raise subprocess.TimeoutExpired(orden, k.get("timeout"), output=b"[Crafty] Pieza")

    monkeypatch.setattr(banco.subprocess, "run", tarda)
    e = banco.Encargo(nombre="x", categoria="casa", peticion="un gancho",
                      oraculo=[{"tipo": "sin_soportes"}])
    resultados, motivo = banco.correr(e, tmp_path / "01", ["intelliprint", "pieza"], "x", {})
    assert [r.estado for r in resultados] == ["no_cumple"]
    assert "tardó" in motivo
    assert "[Crafty] Pieza" in (tmp_path / "01" / "salida.txt").read_text(encoding="utf-8")


# --- obras: varias piezas y su conjunto (F7.5 (obras)) -------------------------------------

def _sg90(en, giros=()):
    return {"nombre": "sg90", "tipo": "componente", "ficha": "sg90", "en": list(en),
            "giros": [list(g) for g in giros], "entra_por": "+z"}


FICHA_BASE = """\
id: obra-base
nombre: Base
origen: impreso
fuentes: [{url: proyecto p, cita: construida por Intelliprint}]
marco: el de la pieza
mira: +z
cuerpos:
- {nombre: Base, en: [0, 0, 0], caja: [70, 34, 18.5], porque: la pieza}
"""


def _obra_construida(tmp_path, *, soportes=("base",), sg90s=2, verificacion=None,
                     encaje=True):
    """El pan-tilt hecho a mano: la base y el soporte de giro, cada uno con su
    SG90, el soporte colocado sobre la base, y el conjunto movido."""
    import json
    p = tmp_path / "projects" / "a"
    nodos = [{"id": "base", "nombre": "Base", "tipo": "pieza", "que_hace": "x"},
             {"id": "giro", "nombre": "Soporte de giro", "tipo": "pieza", "que_hace": "x",
              "depende_de": ["base"]},
             {"id": "pan-tilt", "nombre": "Conjunto", "tipo": "conjunto", "que_hace": "x",
              "depende_de": ["base", "giro"]}]
    p.mkdir(parents=True)
    (p / "obra.json").write_text(json.dumps({"titulo": "t", "nodos": nodos}), encoding="utf-8")
    (p / "fichas").mkdir()
    (p / "fichas" / "obra-base.yaml").write_text(FICHA_BASE, encoding="utf-8")
    rasgos = {"base": [_sg90((23.6, 6, 0))],
              "giro": ([_sg90((-5.8, 27.1, 18.8), [("x", 90)])] if sg90s == 2 else [])
              + ([{"nombre": "obra-base", "tipo": "componente", "ficha": "obra-base",
                   "en": [-29.4, -12.2, -27.6], "giros": [], "entra_por": "-z"}]
                 if encaje else [])}
    for i, r in rasgos.items():
        parte = p / "nodos" / i / "parts" / i
        parte.mkdir(parents=True)
        (parte / f"{i}.step").write_text("STEP", encoding="utf-8")
        (parte / "envolvente.json").write_text('{"min": [0,0,0], "max": [1,1,1]}')
        (parte / "rasgos.json").write_text(json.dumps(r), encoding="utf-8")
        (p / "nodos" / i / "fabrication").mkdir()
        (p / "nodos" / i / "fabrication" / "slicing_report.json").write_text(
            json.dumps({"needs_supports": i in soportes}))
    if verificacion is not None:
        (p / "nodos" / "pan-tilt").mkdir()
        (p / "nodos" / "pan-tilt" / "verificacion.json").write_text(json.dumps(verificacion))
    return tmp_path


GIRA_E_INCLINA = {"ok": True, "resumen": [], "choques": [], "articulaciones": [
    {"pieza": "giro", "eje_mundo": [0, 0, 1], "recorrido": [-90, 90]},
    {"pieza": "plataforma", "eje_mundo": [0, -1, 0], "recorrido": [-90, 90]}]}


def _juzgar_obra(carpeta, oraculo):
    """Los hechos de cada pieza, sintéticos: lo que diga su laminado, y todas
    las sondas cumplen. Devuelve los resultados y lo que se midió en cada STEP."""
    from orchestrator import banco
    medido = {}

    def hechos_de(step, freecadcmd, laminado, aserciones, material):
        import json
        medido[step.parent.name] = aserciones
        return Hechos(cilindros=[], bbox_mm=[1, 1, 1], volumen_mm3=1,
                      soportes=json.loads(laminado.read_text())["needs_supports"],
                      sondas={a.clave(): banco.Resultado(estado="cumple", detalle=a.tipo)
                              for a in aserciones if isinstance(a, banco._Sonda)})

    e = Encargo(nombre="pan-tilt", categoria="robots", obra=True,
                peticion="un pan-tilt que gira 180°", oraculo=oraculo)
    return banco.juzgar_obra(e, carpeta, "freecadcmd", hechos_de=hechos_de), medido


def test_lo_que_se_pide_a_una_pieza_se_mide_en_cada_pieza_de_la_obra(tmp_path):
    """Hasta ahora el banco juzgaba el primer STEP que encontraba: en una obra
    habría medido la base y dado por buena la obra entera."""
    carpeta = _obra_construida(tmp_path, soportes=("giro",))
    [r], medido = _juzgar_obra(carpeta, [{"tipo": "sin_soportes"}])
    assert set(medido) == {"base", "giro"}
    assert r.estado == "no_cumple" and "«Soporte de giro»" in r.detalle
    assert "«Base»" not in r.detalle


def test_los_componentes_de_una_obra_se_cuentan_en_todas_sus_piezas(tmp_path):
    """El pan-tilt lleva dos SG90, uno en la base y otro en el soporte: cada
    uno se mide en la pieza que lo aloja. Con uno solo, no cumple."""
    [r], _ = _juzgar_obra(_obra_construida(tmp_path),
                          [{"tipo": "componente", "ficha": "sg90", "cuantos": 2}])
    assert r.estado == "cumple", r.detalle
    [r], _ = _juzgar_obra(_obra_construida(tmp_path / "uno", sg90s=1),
                          [{"tipo": "componente", "ficha": "sg90", "cuantos": 2}])
    assert r.estado == "no_cumple" and "1" in r.detalle and "2" in r.detalle


def test_cada_pieza_cabe_y_entra_en_la_que_se_diseno_contra_ella(tmp_path):
    """El encaje entre nodos: la base construida (su ficha, la forma real)
    se sondea dentro del soporte de giro, donde él la colocó."""
    from orchestrator.banco import ComponenteCabe, ComponenteEntra
    [r], medido = _juzgar_obra(_obra_construida(tmp_path), [{"tipo": "encaje"}])
    sondas = [a for a in medido["giro"] if isinstance(a, (ComponenteCabe, ComponenteEntra))]
    assert {a.ficha["id"] for a in sondas} == {"obra-base"} and len(sondas) == 2
    assert r.estado == "cumple", r.detalle
    [r], _ = _juzgar_obra(_obra_construida(tmp_path / "suelta", encaje=False),
                          [{"tipo": "encaje"}])
    assert r.estado == "no_cumple"


@pytest.mark.parametrize("verificacion, estado, dice", [
    (GIRA_E_INCLINA, "cumple", "sin chocar"),
    ({**GIRA_E_INCLINA, "ok": False, "resumen": ["«Base» y «Plataforma» chocan si …"]},
     "no_cumple", "«Base» y «Plataforma» chocan"),
    (None, "no_cumple", "no se movió")])
def test_el_conjunto_de_la_obra_se_mueve_sin_chocar(tmp_path, verificacion, estado, dice):
    [r], _ = _juzgar_obra(_obra_construida(tmp_path, verificacion=verificacion),
                          [{"tipo": "conjunto_libre"}])
    assert r.estado == estado and dice in r.detalle, r.detalle


@pytest.mark.parametrize("articulaciones, estado", [
    (GIRA_E_INCLINA["articulaciones"], "cumple"),
    ([{**GIRA_E_INCLINA["articulaciones"][0], "recorrido": [-45, 45]},
      GIRA_E_INCLINA["articulaciones"][1]], "no_cumple"),
    (GIRA_E_INCLINA["articulaciones"][:1], "no_cumple")])
def test_la_obra_gira_e_inclina_lo_que_dice_la_peticion(tmp_path, articulaciones, estado):
    """«Gira 180°»: un eje vertical y uno horizontal, de 180° cada uno.
    Cuentan los ejes en el mundo, en reposo, no en el marco de cada pieza."""
    verificacion = {**GIRA_E_INCLINA, "articulaciones": articulaciones}
    [r], _ = _juzgar_obra(_obra_construida(tmp_path, verificacion=verificacion),
                          [{"tipo": "articulaciones", "ejes": ["vertical", "horizontal"],
                            "recorrido_grados": 180}])
    assert r.estado == estado, r.detalle


@pytest.mark.parametrize("eje, recorrido, estado", [
    ([1, 0, 0], [0, 360], "cumple"),
    ([0, 0, 1], [0, 360], "cumple"),
    ([1, 0, 0], [0, 180], "no_cumple")])
def test_una_polea_que_gira_da_la_vuelta_entera_en_cualquier_eje(tmp_path, eje, recorrido,
                                                                 estado):
    """«Una polea que gira en ese rodamiento» no dice hacia dónde mira el
    eje (el soporte va a un perfil 2020, en cualquier postura): cuenta
    cualquier eje, pero la vuelta tiene que ser entera."""
    verificacion = {**GIRA_E_INCLINA, "articulaciones": [
        {"pieza": "polea", "eje_mundo": eje, "recorrido": recorrido}]}
    [r], _ = _juzgar_obra(_obra_construida(tmp_path, verificacion=verificacion),
                          [{"tipo": "articulaciones", "ejes": ["cualquiera"],
                            "recorrido_grados": "vuelta entera"}])
    assert r.estado == estado, r.detalle


def test_el_608zz_ya_no_queda_pendiente_de_su_giro():
    """La polea quedaba «pendiente» porque la ficha del 608ZZ no tenía
    salida. Ya la tiene (F7.4 (conjunto)): ahora su giro se mide, y es la
    vuelta entera que dice la petición."""
    [e] = [e for e in cargar_encargos(ENCARGOS)
           if e.nombre == "soporte_608zz_polea"]
    assert not [a for a in e.oraculo if a.tipo == "pendiente"]
    [giro] = [a for a in e.oraculo if a.tipo == "articulaciones"]
    assert giro.ejes == ["cualquiera"] and giro.recorrido_grados == "vuelta entera"


def test_el_banco_pide_una_obra_entera_sin_visto_bueno_de_nadie():
    from orchestrator.cli import _parser, orden_del_banco
    assert orden_del_banco(obra=True)[-3:] == ["orchestrator.cli", "obra", "--banco"]
    assert _parser().parse_args(["obra", "--banco", "un pan-tilt"]).banco


def test_una_obra_tiene_mas_tiempo_que_una_pieza(tmp_path, monkeypatch):
    """Una obra son varias piezas seguidas (el pan-tilt: desglose, tres
    conceptos, tres diseños y moverlo entero). Con la hora de una pieza, la
    mataría la guarda contra cuelgues sin que se haya colgado nada."""
    import subprocess

    from orchestrator import banco
    pedido = {}

    def tarda(orden, **k):
        pedido["timeout"] = k["timeout"]
        raise subprocess.TimeoutExpired(orden, k["timeout"])

    monkeypatch.setattr(banco.subprocess, "run", tarda)
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.correr(e, tmp_path / "01", ["intelliprint", "obra"], "x", {})
    assert pedido["timeout"] >= 3 * banco.LIMITE_S


# --- el juez lamina, el diseño no (2026-11-09) --------------------------------

def _laminador_falso(pide_soportes=()):
    """PrusaSlicer de mentira: dice que pide soportes la pieza cuyo STL se
    llama como alguna de `pide_soportes`, y apunta qué laminó."""
    from orchestrator.schemas.slicing_report import SlicingReport
    laminados = []

    def laminar(stl, gcode, postura="-z"):
        if postura == "-z":
            laminados.append(stl.stem)
        return SlicingReport(plate=1, filament_mm=10, grams=1, time_s=60,
                             needs_supports=stl.stem in pide_soportes, postura=postura)
    laminar.laminados = laminados
    return laminar


def _laminador_por_postura(sin_soportes=(), no_lamina=()):
    """PrusaSlicer de mentira que mira cómo se apoya la pieza: pide soportes
    salvo en las posturas de `sin_soportes`, y en las de `no_lamina` falla."""
    from orchestrator.schemas.slicing_report import SlicingReport
    from orchestrator.slicing import LaminadoFallido
    probadas = []

    def laminar(stl, gcode, postura="-z"):
        probadas.append(postura)
        if postura in no_lamina:
            raise LaminadoFallido("There is an object with no extrusions in the first layer.")
        pide = postura not in sin_soportes
        return SlicingReport(plate=1, filament_mm=10, grams=1, time_s=60, needs_supports=pide,
                             postura=postura, avisos=["Long bridging extrusions"] * pide)
    laminar.probadas = probadas
    return laminar


def _juzga_sin_soportes(tmp_path, laminar):
    import json
    from orchestrator import banco
    carpeta = _obra_construida(tmp_path)
    _sin_laminado_del_diseno(carpeta)
    # Una sola pieza, para leer en qué posturas se probó.
    plan = json.loads((carpeta / "projects" / "a" / "obra.json").read_text(encoding="utf-8"))
    plan["nodos"] = [n for n in plan["nodos"] if n["id"] != "giro"]
    plan["nodos"][-1]["depende_de"] = ["base"]
    (carpeta / "projects" / "a" / "obra.json").write_text(json.dumps(plan), encoding="utf-8")

    def hechos_de(step, freecadcmd, laminado, aserciones, material):
        return Hechos(cilindros=[], bbox_mm=[1, 1, 1], volumen_mm3=1,
                      **banco.del_laminado(laminado))

    e = Encargo(nombre="pan-tilt", categoria="robots", obra=True, peticion="p",
                oraculo=[{"tipo": "sin_soportes"}])
    [r] = banco.juzgar_obra(e, carpeta, "freecadcmd", hechos_de=hechos_de, laminar=laminar)
    return r


def test_el_juez_prueba_la_pieza_apoyada_en_cada_cara(tmp_path):
    """Decidido por el usuario el 2026-11-13. La muñeca del brazo mediano
    (banco 1113-1330) se quedó sin medir: el juez la laminaba como se
    dibuja, montada en el brazo, y así apoya en el canto de una polea. La
    postura se elige al laminar, como hace la persona en PrusaSlicer: se
    prueba como se dibuja y, si no vale, apoyada en cada una de sus otras
    caras, y se para en la primera que no pide soportes."""
    laminar = _laminador_por_postura(sin_soportes=("-x",), no_lamina=("-z",))
    r = _juzga_sin_soportes(tmp_path, laminar)
    assert r.estado == "cumple" and "cara -x" in r.detalle
    assert laminar.probadas == ["-z", "+z", "-x"]


def test_como_se_dibuja_va_primero_y_si_vale_no_se_prueba_mas(tmp_path):
    laminar = _laminador_por_postura(sin_soportes=("-z", "+y"))
    r = _juzga_sin_soportes(tmp_path, laminar)
    assert r.estado == "cumple" and laminar.probadas == ["-z"]
    assert "cara" not in r.detalle       # como se dibuja no hace falta decirlo


def test_si_pide_soportes_en_las_seis_posturas_no_cumple_y_dice_por_que(tmp_path):
    laminar = _laminador_por_postura()
    r = _juzga_sin_soportes(tmp_path, laminar)
    assert r.estado == "no_cumple" and "Long bridging extrusions" in r.detalle
    assert sorted(laminar.probadas) == ["+x", "+y", "+z", "-x", "-y", "-z"]


def test_si_no_se_lamina_en_ninguna_postura_queda_sin_medir(tmp_path):
    laminar = _laminador_por_postura(no_lamina=("+x", "+y", "+z", "-x", "-y", "-z"))
    r = _juzga_sin_soportes(tmp_path, laminar)
    assert r.estado == "sin_medir"


def _sin_laminado_del_diseno(carpeta):
    import shutil
    for f in carpeta.glob("projects/*/nodos/*/fabrication"):
        shutil.rmtree(f)


def test_sin_el_laminado_del_diseno_el_juez_lamina_cada_pieza(tmp_path):
    """El diseño ya no lamina: no se sabe en qué impresora se va a imprimir
    (decidido por el usuario, 2026-11-09). «Sin soportes» lo sigue diciendo
    PrusaSlicer, un oráculo que no es el propio sistema, laminando el juez."""
    from orchestrator import banco
    carpeta = _obra_construida(tmp_path)
    _sin_laminado_del_diseno(carpeta)
    laminar = _laminador_falso(pide_soportes=("giro",))

    def hechos_de(step, freecadcmd, laminado, aserciones, material):
        import json
        return Hechos(cilindros=[], bbox_mm=[1, 1, 1], volumen_mm3=1,
                      soportes=json.loads(laminado.read_text())["needs_supports"])

    e = Encargo(nombre="pan-tilt", categoria="robots", obra=True, peticion="p",
                oraculo=[{"tipo": "sin_soportes"}])
    [r] = banco.juzgar_obra(e, carpeta, "freecadcmd", hechos_de=hechos_de, laminar=laminar)
    assert sorted(laminar.laminados) == ["base", "giro"]
    assert r.estado == "no_cumple" and "«Soporte de giro»" in r.detalle


def test_si_no_se_pide_sin_soportes_el_juez_no_lamina(tmp_path):
    from orchestrator import banco
    carpeta = _obra_construida(tmp_path)
    _sin_laminado_del_diseno(carpeta)
    laminar = _laminador_falso()
    e = Encargo(nombre="pan-tilt", categoria="robots", obra=True, peticion="p",
                oraculo=[{"tipo": "componente", "ficha": "sg90", "cuantos": 2}])
    banco.juzgar_obra(e, carpeta, "freecadcmd", laminar=laminar,
                      hechos_de=lambda *a: Hechos(cilindros=[], bbox_mm=[1, 1, 1],
                                                  volumen_mm3=1))
    assert laminar.laminados == []


# --- reanudar: solo la pieza que falló (2026-11-10) ----------------------------

def _con_informes(carpeta, resueltos):
    """Cada pieza dada por lista por el banco, con su informe: resuelta o no."""
    import json
    p = carpeta / "projects" / "a"
    for i, resuelto in resueltos.items():
        (p / "nodos" / i / "lista.json").write_text('{"por": "banco"}', encoding="utf-8")
        (p / "nodos" / i / "pieza_report.json").write_text(
            json.dumps({"titulo": i, "resuelto": resuelto}), encoding="utf-8")
    return p


@pytest.mark.parametrize("resueltos, rehacer", [
    ({"base": True, "giro": False}, "giro"),
    ({"base": False, "giro": False}, "base"),
    # Con las dos bien y el conjunto sin mover, no hay nada que rehacer.
    ({"base": True, "giro": True}, None)])
def test_se_rehace_la_primera_pieza_que_no_salio_bien(tmp_path, resueltos, rehacer):
    """Un backlog de la corrida 1110-0128 tenía la base y el soporte bien y la
    plataforma sin hacer; relanzarlo entero repetía hora y media para volver
    a la plataforma. Una pieza dada por lista con defectos tampoco salió bien."""
    from orchestrator.banco import nodo_a_rehacer
    assert nodo_a_rehacer(_con_informes(_obra_construida(tmp_path), resueltos)) == rehacer


CHOCA = {"ok": False, "choques": [{"a": "base", "b": "giro"}], "resumen": ["chocan"],
         "articulaciones": [], "correcciones": {"giro": "despégala 0.5 mm de la carcasa"}}


def test_un_conjunto_que_choca_corrige_la_pieza_que_lo_causa(tmp_path):
    """Hasta el 2026-11-10 un choque «no decía qué pieza rehacer» y el banco
    se paraba: el pan-tilt 1110-0313 quedó así, con las tres piezas bien. La
    verificación ya dice quién choca (F7.7 (culpable))."""
    from orchestrator.banco import nodo_a_rehacer
    p = _con_informes(_obra_construida(tmp_path, verificacion=CHOCA),
                      {"base": True, "giro": True})
    assert nodo_a_rehacer(p) == "giro"


def test_reanudar_corrige_la_pieza_que_choca_partiendo_de_ella(tmp_path, monkeypatch):
    """Se corrige la pieza que hay con el texto del choque, como hizo la
    persona en la web el 9 de noviembre (y salió), en vez de diseñarla de
    cero. Otra pieza que también choca y se diseñó contra ella lleva su
    propia corrección: desde F9.9 (revalidar) ya no se archiva solo por ir
    encima, así que sin pedírsela seguiría chocando. Aquí no tiene programa
    del que partir y se rehace, con la corrección apuntada para el ingeniero."""
    import json
    from orchestrator import banco
    corrida = tmp_path / "corrida"
    verificacion = {**CHOCA, "correcciones": {"base": "más baja", "giro": "despégala"}}
    p = _con_informes(_obra_construida(corrida / "01", verificacion=verificacion),
                      {"base": True, "giro": True})
    (p / "nodos" / "base" / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (p / "nodos" / "base" / "parts" / "base" / "programa.py").write_text("PROGRAMA",
                                                                        encoding="utf-8")

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    assert json.loads((p / "nodos" / "base" / "retoque.json").read_text(encoding="utf-8"))         == {"programa": "PROGRAMA", "cambio": "más baja"}
    assert "despégala" in (p / "nodos" / "giro" / "cambios.md").read_text(encoding="utf-8")


def test_reanudar_archiva_la_pieza_y_sigue_el_backlog_en_su_carpeta(tmp_path, monkeypatch):
    """Lo hecho se queda: se archiva la pieza que falló (y lo que se diseñó
    contra ella), se sigue el backlog en su carpeta y se juzga otra vez."""
    from orchestrator import banco
    corrida = tmp_path / "corrida"
    p = _con_informes(_obra_construida(corrida / "01"), {"base": True, "giro": False})
    (corrida / "01" / "salida.txt").write_text("la primera vuelta", encoding="utf-8")
    pedido = {}

    class Hecho:
        stdout, stderr, returncode = "segunda vuelta", "", 0

    def lanza(orden, **k):
        pedido["orden"], pedido["env"] = orden, k["env"]
        return Hecho()

    monkeypatch.setattr(banco.subprocess, "run", lanza)
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    assert banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {}) \
        == ({"x": []}, {})
    assert pedido["orden"] == ["intelliprint", "obra", "--banco", "--carpeta", str(p),
                               "un pan-tilt"]
    assert pedido["env"]["INTELLIPRINT_WORKSPACE"] == str(corrida / "01")
    assert (p / "nodos" / "base" / "lista.json").is_file()
    assert not (p / "nodos" / "giro").exists()
    assert next(p.glob("archivo/*/nodos/giro/pieza_report.json"), None) is not None
    assert (corrida / "01" / "salida-anterior.txt").read_text(encoding="utf-8") \
        == "la primera vuelta"
    assert "segunda vuelta" in (corrida / "01" / "salida.txt").read_text(encoding="utf-8")


def test_reanudar_corrige_con_lo_medido_la_pieza_que_salio_con_defectos(tmp_path, monkeypatch):
    """F9.5 (parcial). Una pieza construida que no cumple —el soporte que no
    deja sitio para inclinar— no se diseña de cero al reanudar: se corrige
    la que hay con lo que se le midió, que trae las cifras. Rehacerla volvía
    a pedir concepto y salía otra pieza, sin saber por qué falló la primera."""
    import json
    from orchestrator import banco
    corrida = tmp_path / "corrida"
    p = _con_informes(_obra_construida(corrida / "01"), {"base": True, "giro": False})
    medido = "sitio para girar (unión u3): necesita 25 mm libres y solo hay 12.7 mm"
    (p / "nodos" / "giro" / "pieza_report.json").write_text(json.dumps(
        {"titulo": "giro", "resuelto": False, "motivo": medido}), encoding="utf-8")
    (p / "nodos" / "giro" / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (p / "nodos" / "giro" / "parts" / "giro" / "programa.py").write_text("PROGRAMA",
                                                                        encoding="utf-8")

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    retoque = json.loads((p / "nodos" / "giro" / "retoque.json").read_text(encoding="utf-8"))
    assert retoque["programa"] == "PROGRAMA" and "12.7 mm" in retoque["cambio"]
    assert (p / "nodos" / "giro" / "concepto_aprobado").is_file(), "el concepto se queda"


def test_reanudar_corrige_tambien_la_de_encima_que_tampoco_salio(tmp_path, monkeypatch):
    """Brazo mediano, banco 1113-1330, tercera reanudación: el antebrazo y la
    muñeca habían salido con defectos. Se corrigió el antebrazo, y la muñeca
    —que nunca cumplió— se comprobó contra él y se dio por «sigue valiendo:
    no se toca», porque la corrección de abajo no la había estropeado más.
    Costó una vuelta entera, 48 minutos, volver a saber que no valía. La de
    encima que tampoco salió lleva su corrección en la misma vuelta."""
    import json
    from orchestrator import banco, revalidar
    corrida = tmp_path / "corrida"
    p = _con_informes(_obra_construida(corrida / "01"), {"base": False, "giro": False})
    medido = {"base": "pared: la pared más fina mide 0.46 mm",
              "giro": "no se puede meter viniendo desde +y"}
    for i, motivo in medido.items():
        (p / "nodos" / i / "pieza_report.json").write_text(json.dumps(
            {"titulo": i, "resuelto": False, "motivo": motivo}), encoding="utf-8")
        (p / "nodos" / i / "concepto_aprobado").write_text("{}", encoding="utf-8")
        (p / "nodos" / i / "parts" / i / "programa.py").write_text(f"PROGRAMA de {i}",
                                                                  encoding="utf-8")

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    for i, motivo in medido.items():
        retoque = json.loads((p / "nodos" / i / "retoque.json").read_text(encoding="utf-8"))
        assert retoque == {"programa": f"PROGRAMA de {i}", "cambio": motivo}
    # No espera a revalidarse: se corrige cuando la de abajo esté.
    assert revalidar.pendientes(p) == []


def test_reanudar_rehace_con_su_motivo_la_pieza_que_no_orienta_lo_que_lleva(
        tmp_path, monkeypatch):
    """F9.14 (orienta). El pan-tilt 1111-1342 tenía todas sus piezas
    resueltas y el conjunto sin chocar, así que al reanudar no había nada
    que rehacer; pero su plataforma era un disco en el eje, que no inclina.
    Es un fallo de concepto: la pieza se rehace desde su concepto (no se
    retoca la que hay), con lo que midió el juez apuntado para el ingeniero.

    En la obra de muestra, el soporte de giro gira sobre el SG90 de la base,
    de eje vertical: es la pieza que la exigencia mira."""
    import json
    from orchestrator import banco
    corrida = tmp_path / "corrida"
    bien = {"ok": True, "choques": [], "resumen": [], "articulaciones": [], "correcciones": {}}
    p = _con_informes(_obra_construida(corrida / "01", verificacion=bien),
                      {"base": True, "giro": True})
    medido = ("ninguna cara plana cambia de orientación al girar: la mayor (1662 mm²) "
              "mira a lo largo del eje y gira sobre sí misma")
    monkeypatch.setattr(banco, "medir_sondas", lambda *a, **k: [
        banco.Resultado(estado="no_cumple", detalle=medido)])

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    lanzado = []
    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: lanzado.append(orden) or Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"},
                               {"tipo": "se_orienta", "eje": "vertical", "cabe_mm": [25, 24]}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})

    assert lanzado, "había algo que reanudar"
    cambios = (p / "nodos" / "giro" / "cambios.md").read_text(encoding="utf-8")
    assert "1662 mm²" in cambios and "25 × 24" in cambios
    assert "perpendicular al eje" in cambios
    assert not (p / "nodos" / "giro" / "parts").exists(), "se rehace desde el concepto"
    assert next(p.glob("archivo/*/nodos/giro/pieza_report.json"), None) is not None
    assert (p / "nodos" / "base" / "lista.json").is_file(), "lo demás se queda"

    # Si orienta, no hay nada que reanudar.
    monkeypatch.setattr(banco, "medir_sondas", lambda *a, **k: [
        banco.Resultado(estado="cumple", detalle="tiene una cara plana de 960 mm²")])
    lanzado.clear()
    otra = tmp_path / "otra"
    _con_informes(_obra_construida(otra / "01", verificacion=bien), {"base": True, "giro": True})
    banco.reanudar([e], otra, ["intelliprint", "obra", "--banco"], "fc", {})
    assert lanzado == []


def test_si_ya_se_rehizo_por_no_orientar_la_segunda_vez_se_corrige_la_que_hay(
        tmp_path, monkeypatch):
    """Corrida 1111-1342, primera reanudación: el ingeniero rehízo el
    concepto bien —una escuadra con una placa de 32 × 22 (704 mm²)— y el
    diseñador le talló una ceja que dejó un rebaje de 28 × 18: 450 mm², y
    una cámara de 25 × 24 no cabe. Ya no es un fallo de concepto: rehacerlo
    otra vez tiraría un concepto bueno. Se corrige la pieza construida con
    lo medido, como cualquier otro defecto."""
    import json
    from orchestrator import banco
    corrida = tmp_path / "corrida"
    bien = {"ok": True, "choques": [], "resumen": [], "articulaciones": [], "correcciones": {}}
    p = _con_informes(_obra_construida(corrida / "01", verificacion=bien),
                      {"base": True, "giro": True})
    nodo = p / "nodos" / "giro"
    (nodo / "cambios.md").write_text(
        banco.NO_ORIENTA + ", y como está no lo orienta: … mide 47 mm² …\n", encoding="utf-8")
    (nodo / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (nodo / "parts" / "giro" / "programa.py").write_text("PROGRAMA", encoding="utf-8")
    monkeypatch.setattr(banco, "medir_sondas", lambda *a, **k: [banco.Resultado(
        estado="no_cumple",
        detalle="en la mayor cara plana que cambia de orientación al girar (31 × 21 mm) no "
                "cabe un rectángulo de 25 × 24")])

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "se_orienta", "eje": "vertical", "cabe_mm": [25, 24]}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})

    retoque = json.loads((nodo / "retoque.json").read_text(encoding="utf-8"))
    assert retoque["programa"] == "PROGRAMA"
    assert "31 × 21 mm" in retoque["cambio"] and "redondeos" in retoque["cambio"]
    assert (nodo / "concepto_aprobado").is_file(), "el concepto, que ya era bueno, se queda"


def test_la_carpeta_de_un_encargo_se_busca_por_su_nombre(tmp_path):
    """Las carpetas de una corrida van numeradas por el puesto del encargo
    en la lista con la que se lanzó. La 1110-0313 se lanzó solo con los dos
    backlogs: su `01` es el pan-tilt, el encargo 11. Rejuzgada o reanudada
    con otra lista, el puesto apunta a la carpeta de otro encargo."""
    from orchestrator.banco import carpeta_del_encargo, marcar_carpeta
    marcar_carpeta(tmp_path / "01", "pan_tilt_sg90")
    assert carpeta_del_encargo(tmp_path, 11, "pan_tilt_sg90") == tmp_path / "01"
    # El primero de la lista entera no es el de esa carpeta: no se construyó.
    assert not carpeta_del_encargo(tmp_path, 1, "soporte_mg996r_2020").exists()
    # Una corrida de antes, sin marcas, se sigue leyendo por el puesto.
    (tmp_path / "vieja" / "02").mkdir(parents=True)
    assert carpeta_del_encargo(tmp_path / "vieja", 2, "lo_que_sea") == tmp_path / "vieja" / "02"


def test_el_banco_se_reanuda_desde_la_orden(tmp_path, monkeypatch):
    """`banco --reanudar <corrida>` sigue esa corrida y deja su informe al lado
    del original, sin pisarlo: es la evidencia de cada vuelta."""
    from orchestrator import banco, cli
    llamado = {}

    def reanudar(encargos, corrida, orden, *a, **k):
        llamado["orden"], llamado["encargos"] = orden, [e.nombre for e in encargos]
        return {e.nombre: [] for e in encargos}, {}

    monkeypatch.setattr(banco, "reanudar", reanudar)
    monkeypatch.setattr(cli, "_perfil", lambda *a: type("P", (), {
        "datos": {"resistencia": {}}, "cama_mm": (235, 235, 250)}))
    monkeypatch.setattr(cli, "_freecadcmd", lambda env: "freecadcmd")
    monkeypatch.setattr(cli, "elegir_laminador", lambda *a: None)
    args = cli._parser().parse_args(["banco", "--reanudar", str(tmp_path),
                                     "--solo", "pan_tilt_sg90"])
    cli._banco(args, Path("."), {}, "Crafty")
    cli._banco(args, Path("."), {}, "Crafty")
    assert llamado["orden"] == cli.orden_del_banco(obra=True)
    assert llamado["encargos"] == ["pan_tilt_sg90"]
    assert (tmp_path / "banco_reanudado.md").is_file()
    assert (tmp_path / "banco_reanudado-2.md").is_file()


# --- los tornillos de lo comprado (F9.6 (previsto)) -------------------------------------------

def _con_guias(carpeta, d_base, d_giro):
    """Un agujero guía ciego bajo cada oreja de los dos SG90 de
    `_obra_construida`. A mano, con las muescas de la ficha en (-2.95, 6.2,
    18.5) y (25.75, 6.2, 18.5) y la oreja de 2.9 de grueso:

    - base, servo en (23.6, 6, 0) sin girar: muescas en (20.65, 12.2) y
      (49.35, 12.2); bajo la oreja, z = 18.5 - 2.9 = 15.6, hacia -z;
    - soporte, servo en (-5.8, 27.1, 18.8) girado 90° sobre x, que lleva
      (x, y, z) a (x, -z, y): muescas en (-8.75, 8.6, 25) y (19.95, 8.6, 25),
      tornillo hacia +y; tras la oreja, y = 8.6 + 2.9 = 11.5."""
    import json

    def guia(nombre, en, eje, d):
        return {"nombre": nombre, "tipo": "agujero", "diametro_mm": d, "entrada": list(en),
                "eje": list(eje), "profundidad_mm": 8, "lagrima": False, "avellanado_mm": None}

    nuevos = {"base": [guia("guia_eje", (20.65, 12.2, 15.6), (0, 0, -1), d_base),
                       guia("guia_cable", (49.35, 12.2, 15.6), (0, 0, -1), d_base)],
              "giro": [guia("guia_eje", (-8.75, 11.5, 25.0), (0, 1, 0), d_giro),
                       guia("guia_cable", (19.95, 11.5, 25.0), (0, 1, 0), d_giro)]}
    for nodo, agujeros in nuevos.items():
        ruta = carpeta / "projects" / "a" / "nodos" / nodo / "parts" / nodo / "rasgos.json"
        ruta.write_text(json.dumps(json.loads(ruta.read_text(encoding="utf-8")) + agujeros),
                        encoding="utf-8")
    return carpeta


def test_los_tornillos_de_los_servos_se_cuentan_y_tienen_que_agarrar(tmp_path):
    """Dos SG90, dos orejas cada uno, un tornillo M2 por oreja: 4 (la ficha).
    El pan-tilt de la corrida 1111-1342 pasó seis comprobaciones de seis con
    el servo de la base sin un agujero bajo las orejas y el del soporte con
    dos de Ø2.2, por donde un tornillo de 2 pasa sin tocar."""
    pide = [{"tipo": "tornillos", "sujetan": "sg90", "metrica": "M2", "cuantos": 4}]
    [r], _ = _juzgar_obra(_obra_construida(tmp_path / "sin"), pide)
    assert r.estado == "no_cumple" and "0 de 4" in r.detalle

    [r], _ = _juzgar_obra(_con_guias(_obra_construida(tmp_path / "con"), 1.7, 1.7), pide)
    assert r.estado == "cumple", r.detalle

    [r], _ = _juzgar_obra(_con_guias(_obra_construida(tmp_path / "flojos"), 1.7, 2.2), pide)
    assert r.estado == "no_cumple" and "2 de 4" in r.detalle
    assert "Ø2.2" in r.detalle and "«Soporte de giro»" in r.detalle
    assert "«Base»" not in r.detalle


def test_el_encargo_del_pan_tilt_pide_los_cuatro_tornillos_de_sus_servos():
    from pathlib import Path

    from orchestrator.banco import Tornillos, cargar_encargos
    [pan_tilt] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
                  if e.nombre == "pan_tilt_sg90"]
    [pide] = [a for a in pan_tilt.oraculo if isinstance(a, Tornillos)]
    assert (pide.sujetan, pide.metrica, pide.cuantos) == ("sg90", "M2", 4)


def _con_sus_servos_en_el_plan(p):
    """`_obra_construida` no dice qué compra cada pieza; el plan sí."""
    import json
    plan = json.loads((p / "obra.json").read_text(encoding="utf-8"))
    for n in plan["nodos"]:
        if n["tipo"] == "pieza":
            n["compra"] = ["sg90"]
    (p / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    return p


def test_reanudar_corrige_la_primera_pieza_que_no_sujeta_su_servo(tmp_path, monkeypatch):
    """F9.6 (previsto). La corrida 1111-1342 tiene sus piezas resueltas, no
    choca y orienta: al reanudar no había nada que hacer, y sin embargo su
    base lleva el servo suelto. Se corrige la pieza que hay, con lo que le
    falta dicho en cifras: 2 tornillos de 2 (la ficha del SG90)."""
    import json
    from orchestrator import banco
    bien = {"ok": True, "choques": [], "resumen": [], "articulaciones": [], "correcciones": {}}
    pide = [{"tipo": "tornillos", "sujetan": "sg90", "metrica": "M2", "cuantos": 4}]
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=pide)

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    lanzado = []
    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: lanzado.append(orden) or Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))

    corrida = tmp_path / "corrida"
    p = _con_sus_servos_en_el_plan(_con_informes(
        _obra_construida(corrida / "01", verificacion=bien), {"base": True, "giro": True}))
    (p / "nodos" / "base" / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (p / "nodos" / "base" / "parts" / "base" / "programa.py").write_text("PROGRAMA",
                                                                        encoding="utf-8")
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    assert lanzado, "había algo que reanudar"
    retoque = json.loads((p / "nodos" / "base" / "retoque.json").read_text(encoding="utf-8"))
    assert retoque["programa"] == "PROGRAMA"
    assert "Micro servo SG90" in retoque["cambio"] and "faltan 2" in retoque["cambio"]

    # Con los cuatro tornillos en su sitio no hay nada que reanudar.
    lanzado.clear()
    otra = tmp_path / "otra"
    _con_sus_servos_en_el_plan(_con_informes(
        _con_guias(_obra_construida(otra / "01", verificacion=bien), 1.7, 1.7),
        {"base": True, "giro": True}))
    banco.reanudar([e], otra, ["intelliprint", "obra", "--banco"], "fc", {})
    assert lanzado == []


def test_reanudar_corrige_la_punta_que_no_llega(tmp_path, monkeypatch):
    """Brazo mediano, banco 1113-1330, cuarta reanudación: todas las piezas
    resueltas, el conjunto sin chocar y el alcance en 340 mm de 350. Al
    reanudar no había nada que hacer: nadie buscaba qué pieza no llega. Se
    le mide otra vez a cada una, sin modelo, y se corrige la que no llega
    con lo medido."""
    import json
    from orchestrator import banco, medida
    bien = {"ok": True, "choques": [], "resumen": [], "articulaciones": [], "correcciones": {}}
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un brazo", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    lanzado = []
    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: lanzado.append(orden) or Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    corrida = tmp_path / "corrida"
    p = _con_informes(_obra_construida(corrida / "01", verificacion=bien),
                      {"base": True, "giro": True})
    (p / "nodos" / "giro" / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (p / "nodos" / "giro" / "parts" / "giro" / "programa.py").write_text("PROGRAMA",
                                                                        encoding="utf-8")
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    assert lanzado == [], "si todas llegan no hay nada que reanudar"

    falta = "alcance (unión u2): los tornillos quedan a 70.0 mm y tienen que quedar a 80"
    monkeypatch.setattr(medida, "defectos_de_alcance",
                        lambda carpeta, nodo: [falta] if nodo == "giro" else [])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    assert lanzado, "había algo que reanudar"
    assert json.loads((p / "nodos" / "giro" / "retoque.json").read_text(encoding="utf-8")) \
        == {"programa": "PROGRAMA", "cambio": falta}


def test_reanudar_corrige_todas_las_piezas_a_las_que_les_faltan_tornillos(tmp_path, monkeypatch):
    """F9.9 (revalidar). Antes bastaba corregir la primera: las de encima se
    rehacían de cero y contaban sus tornillos al dibujarse. Ahora se quedan
    si siguen valiendo, así que cada una que no sujeta su servo se corrige
    por lo suyo. Repetida sin modelo la corrección de la base de la
    1111-1342, el soporte se quedaba con sus dos agujeros de Ø2.2: habría
    hecho falta otra reanudación solo para él.

    Aquí la base y el soporte de giro llevan un SG90 cada uno y ninguno de
    los dos tiene agujeros: a cada uno le faltan sus 2 (la ficha del SG90)."""
    import json
    from orchestrator import banco
    bien = {"ok": True, "choques": [], "resumen": [], "articulaciones": [], "correcciones": {}}
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "tornillos", "sujetan": "sg90", "metrica": "M2",
                                "cuantos": 4}])

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    corrida = tmp_path / "corrida"
    p = _con_sus_servos_en_el_plan(_con_informes(
        _obra_construida(corrida / "01", verificacion=bien), {"base": True, "giro": True}))
    for i in ("base", "giro"):
        (p / "nodos" / i / "concepto_aprobado").write_text("{}", encoding="utf-8")
        (p / "nodos" / i / "parts" / i / "programa.py").write_text(f"PROGRAMA DE {i}",
                                                                   encoding="utf-8")

    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})

    for i in ("base", "giro"):
        retoque = json.loads((p / "nodos" / i / "retoque.json").read_text(encoding="utf-8"))
        assert retoque["programa"] == f"PROGRAMA DE {i}", i
        assert "Micro servo SG90" in retoque["cambio"] and "faltan 2" in retoque["cambio"], i


# --- backlogs: hasta dónde llega y cuánto levanta (F10.1 (serie)) ---------------------------

def _juzgar_brazo(tmp_path, monkeypatch, oraculo, peticion, material=(), brazo=None):
    """El brazo en voladizo de `tests/test_estudio.py`, hecho a mano y con sus
    cifras calculadas a mano allí, juzgado como un backlog: la punta a
    100.1 mm del eje; el SG90 deja colgar 80.0 g y vuelca con 8.4 g."""
    from orchestrator import banco, estudio
    from tests.test_estudio import _brazo_en_voladizo
    p = tmp_path / "projects" / "a"
    p.mkdir(parents=True)
    (brazo or _brazo_en_voladizo)(p)
    # La resistencia del material la mide FreeCAD: aquí llega ya medida.
    monkeypatch.setattr(estudio, "carga_del_material", lambda *a, **k: list(material))
    e = Encargo(nombre="brazo", categoria="robots", obra=True, peticion=peticion,
                oraculo=oraculo)
    return banco.juzgar_obra(
        e, tmp_path, "freecadcmd",
        hechos_de=lambda *a: Hechos(cilindros=[], bbox_mm=[1, 1, 1], volumen_mm3=1))


@pytest.mark.parametrize("pide, estado, dice", [
    (100, "cumple", "100.1 mm"),
    (120, "no_cumple", "llega a 100.1 mm y se piden 120"),
])
def test_el_banco_pide_que_el_brazo_llegue(tmp_path, monkeypatch, pide, estado, dice):
    """La punta del brazo está a √(100² + 5²) = 100.1 mm del eje del servo
    (calculado en `test_el_estudio_dice_alcance_y_tiempos`). El pan-tilt pasó
    todo lo que se le pedía sin que nadie mirara a dónde llega: un brazo de
    20 mm con tres servos habría pasado igual."""
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "alcance", "minimo_mm": pide}],
                        f"un brazo que llegue a {pide} mm")
    assert r.estado == estado, r.detalle
    assert dice in r.detalle


@pytest.mark.parametrize("pide, estado, dice", [
    (100, "cumple", "100.1 mm"),
    (120, "no_cumple", "llega a 100.1 mm y se piden 120"),
])
def test_un_desvio_a_lo_largo_del_hombro_no_cuenta_como_alcance(tmp_path, monkeypatch,
                                                                pide, estado, dice):
    """El primer brazo del banco (1112-0318) pasó «llega a 120 mm» con 233:
    su tramo colgaba de un separador a lo largo del eje del hombro, y se
    medía la distancia al eje de la base. El usuario decidió (2026-11-12)
    que el alcance se mida del hombro a la punta.

    El mismo brazo de 100.1 mm, girado por una base y desviado 200 mm a lo
    largo del eje del hombro, está a más de 224 mm del eje de la base
    (`test_el_alcance_de_un_brazo_se_mide_desde_el_hombro`): no llega a 120."""
    from tests.test_estudio import _brazo_que_gira_y_se_desvia
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "alcance", "minimo_mm": pide}],
                        f"un brazo que llegue a {pide} mm", brazo=_brazo_que_gira_y_se_desvia)
    assert r.estado == estado, r.detalle
    assert dice in r.detalle and "Pieza brazo" in r.detalle


@pytest.mark.parametrize("pide, estado, dice", [
    (8, "cumple", "8.4 g"),
    (20, "no_cumple", "levanta 8.4 g y se piden 20"),
])
def test_el_banco_pide_que_el_brazo_levante_la_carga(tmp_path, monkeypatch, pide, estado, dice):
    """Sin atornillar, el brazo en voladizo vuelca con 8.36 g en la punta
    antes de que el servo ceda, que aguantaría 80.0
    (`test_el_estudio_de_un_brazo_en_voladizo`, a mano). Lo que levanta es lo
    menor, y el banco dice qué lo limita."""
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "carga", "minimo_g": pide}],
                        f"un brazo que levante {pide} g")
    assert r.estado == estado, r.detalle
    assert dice in r.detalle and "vuelco" in r.detalle


def test_la_carga_cuenta_lo_que_aguanta_el_material(tmp_path, monkeypatch):
    """Si el plástico del brazo rompe con 5 g, eso es lo que levanta, aunque
    el servo y el vuelco den para más."""
    material = [{"pieza": "brazo", "nombre": "Pieza brazo", "largo_mm": 100.0,
                 "detalle": "flexa", "carga_max_g": 5.0}]
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "carga", "minimo_g": 8}],
                        "un brazo que levante 8 g", material)
    assert r.estado == "no_cumple"
    assert "levanta 5 g y se piden 8" in r.detalle and "material" in r.detalle


def test_sin_medir_el_material_la_carga_queda_sin_medir(tmp_path, monkeypatch):
    """Si FreeCAD no corrió, no se sabe si el brazo aguanta: decir «cumple»
    con el servo solo sería aprobar por medir menos."""
    material = [{"pieza": "brazo", "nombre": "Pieza brazo", "largo_mm": 100.0,
                 "detalle": "no corrió: sin salida", "carga_max_g": None}]
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "carga", "minimo_g": 8}],
                        "un brazo que levante 8 g", material)
    assert r.estado == "sin_medir"
    assert "no corrió" in r.detalle


def test_sin_saber_el_par_de_lo_que_mueve_la_carga_queda_sin_medir(tmp_path, monkeypatch):
    """Un giro sobre algo cuya ficha no da el par (un rodamiento, el NEMA 17
    de hoy): el vuelco solo no dice que el brazo levante la carga."""
    from orchestrator import componentes
    de_verdad = componentes.cargar
    monkeypatch.setattr(componentes, "cargar", lambda i, extra=():
                        de_verdad(i, extra).model_copy(update={"par_kgf_cm": {}}))
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "carga", "minimo_g": 8}],
                        "un brazo que levante 8 g")
    assert r.estado == "sin_medir"
    assert "par" in r.detalle and "Pieza brazo" in r.detalle


def test_tres_giros_de_180_se_estudian_en_todas_sus_combinaciones():
    """Con la rejilla de 10°, tres giros de 180° son 19³ = 6 859 poses. Con el
    tope en 5 000 el estudio probaba cada giro por turno con los demás en 0°,
    y la peor pose de un brazo —estirado en horizontal— puede no estar ahí."""
    from orchestrator import estudio
    assert estudio.MAX_POSES >= 19 ** 3


def test_reanudar_sigue_un_backlog_que_se_corto_al_mover_el_conjunto(tmp_path, monkeypatch):
    """Banco 1112-0318, el primer brazo: las cuatro piezas salieron bien y
    la orden murió moviendo el conjunto (FreeCAD pasó de los 600 s). Quedó
    «por verificar», sin verificación: no hay pieza que rehacer ni choque
    que corregir, y reanudar se la saltaba sin hacer nada. Lo que falta es
    seguir, que no gasta modelo. Y no se archiva nada de lo hecho."""
    from orchestrator import banco, obra
    corrida = tmp_path / "corrida"
    p = _con_informes(_obra_construida(corrida / "01"), {"base": True, "giro": True})
    assert obra.estados(p)["pan-tilt"] == "por verificar"
    lanzado = []

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run",
                        lambda orden, **k: lanzado.append(orden) or Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})
    assert len(lanzado) == 1 and "--carpeta" in lanzado[0]
    assert not (p / "archivo").exists()
    assert all((p / "nodos" / i / "lista.json").is_file() for i in ("base", "giro"))
