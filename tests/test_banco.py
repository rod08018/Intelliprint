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
                        lambda e, c, f, m=None: [banco.Resultado(estado="cumple", detalle="medida")])
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
                        lambda e, c, f, m=None: [banco.Resultado(estado="cumple", detalle="ok")])
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
    pidió la persona. Si no, el banco mediría contra otra petición."""
    for e in cargar_encargos(ENCARGOS):
        for a in e.oraculo:
            for cota in a.cotas_de_la_peticion():
                assert f"{cota:g}" in e.peticion, f"{e.nombre}: {cota:g} no está en la petición"


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
                        lambda e, c, f, m=None: [banco.Resultado(estado="cumple", detalle="ok")])
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
