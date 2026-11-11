"""Revalidar en vez de rehacer (F9.9 (revalidar)).

Corregir una pieza archivaba todo lo que se había diseñado contra ella,
valiera o no. En el pan-tilt 1111-1342 (2026-11-11) a la base le faltaban
dos agujeros de Ø1.7 bajo las orejas del servo: corregirla tiró el soporte y
la plataforma, que no tenían nada que ver con esos agujeros, y la plataforma
nueva salió de 30 × 28.5, donde ya no cabía la cámara que sí cabía en la
archivada (32 × 27). Costó 47 minutos y 0,53 USD dejarlo igual de mal.

Ahora lo diseñado contra la pieza corregida se queda y se comprueba contra
su ficha nueva. Solo se vuelve a diseñar lo que deja de valer.

Los valores esperados están hechos a mano, con las piezas de F7.1 (fichar):
un soporte de 40 × 20 × 5 con dos M3 en x = ±10 y una tapa de 3 mm encima.

- El mismo soporte, o con un agujero más donde la tapa no tiene nada: la
  tapa sigue valiendo.
- El agujero m3_1 movido de x = -10 a x = -9: la tapa taladró en -10; ya no
  vale.
- Un resalte de 4 × 4 × 2 sobre el soporte, donde está la tapa: se mete
  4 · 4 · 2 = 32 mm³ en ella.
- Una peana que baja de 5 a 3 mm de alto: lo de encima, que apoyaba en ella,
  queda a 5 - 3 = 2 mm.
"""

import json
from pathlib import Path

import pytest

from orchestrator.build import build_part
from orchestrator.schemas.obra import Obra
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
CON_OTRO_AGUJERO = SOPORTE.replace(
    "return placa",
    'return placa.taladrar("guia", 2, en=(0, 5, 0), eje="+z", profundidad=3)')
"""Lo que le pasó a la base del pan-tilt: gana un agujero por debajo, donde
la tapa no tiene nada."""
AGUJERO_MOVIDO = SOPORTE.replace("(-10, 10)", "(-9, 10)")
CON_RESALTE = SOPORTE.replace(
    "return placa", "return placa + kit.caja(4, 4, 2, en=(-2, -2, 5))")

TAPA = """
def construir(kit):
    soporte = kit.componente("obra-soporte", en=(0, 0, 0), entra_por="-z")
    tapa = kit.caja(40, 20, 3, en=(-20, -10, 5))
    for i in (1, 2):
        x, y, z = soporte.punto(f"m3_{i}")
        tapa = tapa.tornillo(f"m3_{i}", "M3", en=(x, y, 8), eje="-z")
    return tapa
"""
REMATE = """
def construir(kit):
    kit.componente("obra-tapa", en=(0, 0, 0), entra_por="-z")
    return kit.caja(10, 10, 2, en=(-5, -5, 8))
"""

PEANA = "def construir(kit):\n    return kit.caja(40, 20, {alto}, en=(-20, -10, 0))\n"
ENCIMA = """
def construir(kit):
    kit.componente("obra-soporte", en=(0, 0, 0), entra_por="-z")
    return kit.caja(40, 20, 3, en=(-20, -10, 5))
"""

NODOS = [
    {"id": "soporte", "nombre": "Soporte", "que_hace": "se atornilla a la mesa"},
    {"id": "tapa", "nombre": "Tapa", "que_hace": "cierra el soporte", "depende_de": ["soporte"]},
    {"id": "remate", "nombre": "Remate", "que_hace": "va sobre la tapa", "depende_de": ["tapa"]},
]


@pytest.fixture
def backlog(tmp_path, monkeypatch):
    from orchestrator import obra as O
    (tmp_path / "request.md").write_text("un soporte con su tapa\n", encoding="utf-8")
    O.guardar(tmp_path, Obra(titulo="Soporte con tapa", nodos=NODOS), por="prueba")
    O.aprobar(tmp_path, por="prueba")
    # Las piezas siguientes se construyen contra las fichas del backlog.
    monkeypatch.setenv("INTELLIPRINT_FICHAS", str(O.carpeta_de_fichas(tmp_path)))
    # `cli._paso_de_obra` la deja puesta en el proceso (ver `test_giro.py`).
    monkeypatch.delenv("INTELLIPRINT_AJENOS", raising=False)
    monkeypatch.delenv("INTELLIPRINT_UNIONES", raising=False)
    return tmp_path


def _disenar(carpeta: Path, nodo: str, codigo: str) -> None:
    """Lo que deja el flujo de pieza en la carpeta del nodo: la pieza
    construida, su informe y el concepto aprobado."""
    dir_nodo = carpeta / "nodos" / nodo
    build_part(Programa(part=nodo, codigo=codigo), None, dir_nodo / "parts" / nodo,
               _freecadcmd(), perfil=PERFIL)
    (dir_nodo / "concepto.json").write_text("{}", encoding="utf-8")
    (dir_nodo / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (dir_nodo / "spec.yaml").write_text(f"title: {nodo}\n", encoding="utf-8")
    (dir_nodo / "pieza_report.json").write_text(json.dumps(
        {"titulo": nodo, "pieza": nodo, "resuelto": True}), encoding="utf-8")
    (dir_nodo / "rounds.json").write_text("[{}]", encoding="utf-8")


def _lista(carpeta: Path, nodo: str, codigo: str) -> None:
    from orchestrator import obra as O
    _disenar(carpeta, nodo, codigo)
    O.dar_por_lista(carpeta, nodo, por="prueba")


def _corregido(carpeta: Path, soporte=SOPORTE, despues=SOPORTE, tapa=TAPA, remate=None) -> None:
    """El soporte y lo que va encima, listos; el soporte se corrige y vuelve
    a darse por bueno con el programa `despues`."""
    from orchestrator import obra as O
    _lista(carpeta, "soporte", soporte)
    _lista(carpeta, "tapa", tapa)
    if remate:
        _lista(carpeta, "remate", remate)
    O.corregir(carpeta, "soporte", cambio="lo que sea")
    _lista(carpeta, "soporte", despues)


# --- corregir ya no archiva lo que hay encima --------------------------------------------

def test_corregir_una_pieza_deja_lo_que_se_diseno_contra_ella_y_lo_marca(backlog):
    from orchestrator import obra as O
    from orchestrator import revalidar as R
    _lista(backlog, "soporte", SOPORTE)
    _lista(backlog, "tapa", TAPA)

    rehechos = O.corregir(backlog, "soporte", cambio="dos agujeros más")

    assert rehechos == ["soporte"], "lo archivado es solo lo que se corrige"
    assert (backlog / "nodos" / "tapa" / "parts" / "tapa" / "tapa.step").is_file()
    assert (backlog / "nodos" / "tapa" / "lista.json").is_file()
    assert R.pendientes(backlog) == ["tapa"]
    # Con qué se hizo: sin esto no habría con qué comparar la ficha nueva.
    assert (backlog / "nodos" / "tapa" / "contra" / "obra-soporte.yaml").is_file()
    assert (backlog / "nodos" / "tapa" / "contra" / "obra-soporte.step").is_file()
    # Mientras el soporte se corrige, la tapa espera; no está «lista».
    assert O.estados(backlog) == {"soporte": "corrigiendo", "tapa": "bloqueado",
                                  "remate": "bloqueado"}

    _lista(backlog, "soporte", SOPORTE)
    assert O.estados(backlog)["tapa"] == "por revalidar"
    assert O.siguiente(backlog) == "tapa"
    assert "por revalidar" in O.SE_LANZAN, "no espera a la persona: se comprueba sola"


def test_lo_que_no_llego_a_construirse_se_archiva_como_antes(backlog):
    """De una pieza que solo tiene concepto no hay nada que comprobar, y su
    concepto se pensó contra la ficha vieja."""
    from orchestrator import obra as O
    from orchestrator import revalidar as R
    _lista(backlog, "soporte", SOPORTE)
    (backlog / "nodos" / "tapa").mkdir(parents=True)
    (backlog / "nodos" / "tapa" / "concepto.json").write_text("{}", encoding="utf-8")

    assert O.corregir(backlog, "soporte", cambio="más alto") == ["soporte", "tapa"]
    assert not (backlog / "nodos" / "tapa").exists()
    assert list((backlog / "archivo").rglob("tapa/concepto.json")), "archivar no es borrar"
    assert R.pendientes(backlog) == []


# --- revalidar: lo que sigue valiendo se queda --------------------------------------------

@pytest.mark.parametrize("despues", [SOPORTE, CON_OTRO_AGUJERO],
                         ids=["igual", "con otro agujero"])
def test_la_tapa_sigue_lista_si_no_cambio_nada_suyo(backlog, despues):
    from orchestrator import obra as O
    from orchestrator import revalidar as R
    _corregido(backlog, despues=despues)
    step = backlog / "nodos" / "tapa" / "parts" / "tapa" / "tapa.step"
    antes = step.read_bytes()

    assert R.resolver(backlog, "tapa", _freecadcmd(), MATERIAL) == []

    assert O.estados(backlog)["tapa"] == "lista"
    assert step.read_bytes() == antes, "la pieza es la misma: no se reconstruye"
    assert R.pendientes(backlog) == []
    assert not (backlog / "nodos" / "tapa" / "retoque.json").exists()
    # Queda dicho que se comprobó, y contra qué.
    hecha = json.loads((backlog / "nodos" / "tapa" / "revalidada.json").read_text(
        encoding="utf-8"))
    assert hecha["contra"] == ["obra-soporte"] and hecha["por"] == ["soporte"]


def test_con_un_agujero_movido_1_mm_la_tapa_vuelve_a_disenarse_partiendo_de_ella(backlog):
    from orchestrator import obra as O
    from orchestrator import revalidar as R
    _corregido(backlog, despues=AGUJERO_MOVIDO)

    motivos = R.resolver(backlog, "tapa", _freecadcmd(), MATERIAL)

    [m] = [m for m in motivos if "m3_1" in m]
    assert "«Soporte»" in m and "(-10, 0, 5)" in m and "(-9, 0, 5)" in m, m
    assert not any("m3_2" in m for m in motivos), "el otro no se movió"
    # Se corrige la que hay: su concepto y su programa siguen siendo el punto
    # de partida. Rehacerla de cero es lo que rompió la plataforma buena.
    assert O.estados(backlog)["tapa"] == "corrigiendo"
    retoque = json.loads((backlog / "nodos" / "tapa" / "retoque.json").read_text(
        encoding="utf-8"))
    assert retoque["programa"] == TAPA
    assert "(-9, 0, 5)" in retoque["cambio"] and "Soporte" in retoque["cambio"]
    assert (backlog / "nodos" / "tapa" / "concepto_aprobado").is_file()
    assert list((backlog / "archivo").rglob("tapa/parts/tapa/tapa.step")), "archivada, no borrada"


def test_si_la_pieza_corregida_se_mete_en_la_de_encima_esta_no_vale(backlog):
    from orchestrator import revalidar as R
    _corregido(backlog, despues=CON_RESALTE)
    motivos = R.revalidar(backlog, "tapa", _freecadcmd(), MATERIAL)
    assert any("32.0 mm³" in m and "Soporte" in m for m in motivos), motivos


def test_si_la_pieza_corregida_deja_de_tocar_a_la_de_encima_esta_no_vale(backlog):
    """Nada choca y ningún agujero se movió: sin mirar la distancia, lo de
    encima se quedaría flotando a 2 mm y pasaría por bueno."""
    from orchestrator import revalidar as R
    _corregido(backlog, soporte=PEANA.format(alto=5), despues=PEANA.format(alto=3), tapa=ENCIMA)
    motivos = R.revalidar(backlog, "tapa", _freecadcmd(), MATERIAL)
    assert any("2.0 mm" in m and "Soporte" in m for m in motivos), motivos


# --- en cadena -------------------------------------------------------------------------

def test_lo_que_va_sobre_una_pieza_que_sigue_valiendo_tampoco_se_toca(backlog):
    """La plataforma del pan-tilt va sobre el soporte, no sobre la base: si
    el soporte sigue valiendo, su ficha es la misma y no hay nada que medir."""
    from orchestrator import obra as O
    from orchestrator import revalidar as R
    _corregido(backlog, despues=CON_OTRO_AGUJERO, remate=REMATE)
    assert R.pendientes(backlog) == ["tapa", "remate"]
    assert O.estados(backlog)["remate"] == "bloqueado"

    assert R.resolver(backlog, "tapa", _freecadcmd(), MATERIAL) == []
    assert O.estados(backlog)["remate"] == "por revalidar"
    # Con la ficha de la tapa intacta no hace falta ni abrir FreeCAD.
    assert R.resolver(backlog, "remate", "no-hay-freecad", MATERIAL) == []
    assert set(O.estados(backlog).values()) == {"lista"}


def test_lo_que_va_sobre_una_pieza_que_se_corrige_espera_a_la_nueva(backlog):
    from orchestrator import obra as O
    from orchestrator import revalidar as R
    _corregido(backlog, despues=AGUJERO_MOVIDO, remate=REMATE)

    assert R.resolver(backlog, "tapa", _freecadcmd(), MATERIAL)

    assert O.estados(backlog) == {"soporte": "lista", "tapa": "corrigiendo",
                                  "remate": "bloqueado"}
    assert R.pendientes(backlog) == ["remate"]
    assert (backlog / "nodos" / "remate" / "parts" / "remate" / "remate.step").is_file()
    # Y se comparará con la tapa contra la que se hizo, no con la que salga.
    assert (backlog / "nodos" / "remate" / "contra" / "obra-tapa.yaml").is_file()


# --- lo que cambia de una ficha a otra, sin FreeCAD -----------------------------------------

def _ficha(**cambios):
    from orchestrator.componentes import Ficha
    base = {
        "id": "obra-base", "nombre": "Base", "origen": "impreso",
        "fuentes": [{"url": "proyecto p", "cita": "construida"}], "marco": "el suyo",
        "mira": "+z",
        "cuerpos": [{"nombre": "Base", "en": [0, 0, 0], "caja": [70, 34, 18.5]},
                    {"nombre": "sg90: cuerpo", "en": [23.6, 6, 0], "caja": [22.8, 12.4, 22.7],
                     "monta": "sg90"}],
        "despejar": [{"nombre": "sg90: cable", "en": [20, 6, 0], "caja": [4, 12, 5]}],
        "fijacion": [{"nombre": "m3_1", "diametro": 3.3, "en": [5, 5, 18.5], "eje": "-z",
                      "tornillo": "M3"}],
        "salidas": [{"nombre": "sg90: eje", "en": [29.4, 12.2, 27.1], "eje": "+z",
                     "recorrido": [-90, 90]}],
    }
    return Ficha(**{**base, **cambios})


def test_anadir_no_cambia_la_interfaz():
    from orchestrator.revalidar import interfaz_cambiada
    antes = _ficha()
    ahora = _ficha(
        cuerpos=[{"nombre": "Base", "en": [0, 0, 0], "caja": [70, 34, 20]},   # su forma: se sondea
                 antes.cuerpos[1].model_dump()],
        fijacion=[antes.fijacion[0].model_dump(),
                  {"nombre": "oreja_1", "diametro": 1.7, "en": [21, 12, 16], "eje": "-z"}])
    assert interfaz_cambiada(antes, ahora) == []


@pytest.mark.parametrize("cambios, dice", [
    ({"fijacion": []}, ["«m3_1»", "ya no está"]),
    ({"fijacion": [{"nombre": "m3_1", "diametro": 4.3, "en": [5, 5, 18.5], "eje": "-z"}]},
     ["«m3_1»", "Ø3.3", "Ø4.3"]),
    ({"fijacion": [{"nombre": "m3_1", "diametro": 3.3, "en": [5, 5, 18.5], "eje": "+x"}]},
     ["«m3_1»", "-z", "+x"]),
    ({"salidas": [{"nombre": "sg90: eje", "en": [29.4, 12.2, 29.1], "eje": "+z",
                   "recorrido": [-90, 90]}]},
     ["«sg90: eje»", "(29.4, 12.2, 27.1)", "(29.4, 12.2, 29.1)"]),
    ({"cuerpos": [{"nombre": "Base", "en": [0, 0, 0], "caja": [70, 34, 18.5]},
                  {"nombre": "sg90: cuerpo", "en": [23.6, 6, 2], "caja": [22.8, 12.4, 22.7],
                   "monta": "sg90"}]},
     ["«sg90: cuerpo»", "(23.6, 6, 0)", "(23.6, 6, 2)"]),
    ({"despejar": []}, ["«sg90: cable»", "ya no está"]),
])
def test_lo_que_se_mueve_o_desaparece_si_cambia_la_interfaz(cambios, dice):
    from orchestrator.revalidar import interfaz_cambiada
    [motivo] = interfaz_cambiada(_ficha(), _ficha(**cambios))
    for parte in dice:
        assert parte in motivo, (parte, motivo)


# --- lo que ya fallaba antes no es culpa de la corrección -----------------------------------

def test_un_defecto_del_plan_que_ya_tenia_no_la_hace_rehacerse(backlog, monkeypatch):
    """El soporte del pan-tilt 1111-1342 ya tenía sus agujeros de Ø2.2 antes
    de corregir la base. Es un defecto suyo, y se corrige cuando le toque:
    aquí solo se pregunta si la corrección de la base lo estropeó."""
    from orchestrator import revalidar as R
    medido = iter([["el Ø2.2 no rosca"], ["el Ø2.2 no rosca", "ya no llega al eje"]])
    monkeypatch.setattr(R, "_del_plan", lambda carpeta, nodo: next(medido))
    _corregido(backlog, despues=SOPORTE)
    assert R.revalidar(backlog, "tapa", _freecadcmd(), MATERIAL) == ["ya no llega al eje"]


# --- el paso del backlog y el banco ---------------------------------------------------------

def test_el_backlog_revalida_solo_y_sin_modelo(backlog, capsys):
    from orchestrator import cli
    from orchestrator import obra as O
    _corregido(backlog, despues=CON_OTRO_AGUJERO, remate=REMATE)
    raiz = Path(__file__).resolve().parents[1]
    # Sin clave de ningún modelo: si intentara llamar a uno, reventaría.
    env = {"FREECADCMD": _freecadcmd(), "INTELLIPRINT_WORKSPACE": str(backlog / "ws")}

    cli._paso_de_obra(backlog, "un soporte con su tapa", raiz, env, "prueba")

    assert set(O.estados(backlog).values()) == {"lista"}
    salida = capsys.readouterr().out
    assert "«Tapa» sigue valiendo" in salida and "«Remate» sigue valiendo" in salida
    assert "backlog terminado" in salida


def test_reanudar_no_rehace_lo_que_solo_espera_a_revalidarse(tmp_path, monkeypatch):
    """Si la orden se corta con una pieza por revalidar, reanudar la sigue:
    no hay nada que archivar."""
    from orchestrator import banco
    from tests.test_banco import _con_informes, _obra_construida
    corrida = tmp_path / "corrida"
    p = _con_informes(_obra_construida(corrida / "01"), {"base": True, "giro": True})
    (p / "nodos" / "giro" / "revalidar.json").write_text(
        json.dumps({"por": ["base"], "antes": []}), encoding="utf-8")
    lanzadas = []

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: lanzadas.append(orden) or Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})

    assert len(lanzadas) == 1, "se sigue el backlog"
    assert not (p / "archivo").exists(), "sin archivar nada"
    assert (p / "nodos" / "giro" / "parts" / "giro" / "giro.step").is_file()
