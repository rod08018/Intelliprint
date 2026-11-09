"""Proyectos por partes: el desglose y el avance pieza a pieza (F7.2 (desglose)).

Un proyecto grande se parte en un árbol, la persona lo aprueba y se diseña
un nodo cada vez: su concepto, su visto bueno, su diseño y «está bien, la
siguiente», que lo congela como ficha para los que dependen de él. Una
petición pequeña da un solo nodo y se comporta como el flujo de pieza de
siempre, sin pasos extra.

El pan-tilt de dos SG90 es el piloto (decidido con el usuario, 2026-11-09):
una base, el soporte del servo de giro y el del de inclinación.
"""

import json
import sys
import time

import pytest

from orchestrator.schemas.obra import Obra

PANTILT = {
    "titulo": "Pan-tilt con dos SG90",
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "aloja el SG90 de giro",
         "compra": ["sg90"], "ofrece": ["eje de salida del SG90 de giro hacia +z"]},
        {"id": "giro", "nombre": "Soporte de giro", "que_hace": "va en el brazo del servo de "
         "giro y aloja el SG90 de inclinación", "compra": ["sg90"], "depende_de": ["base"],
         "necesita": ["eje de salida del SG90 de giro hacia +z"]},
        {"id": "inclinacion", "nombre": "Soporte de inclinación", "que_hace": "sostiene la "
         "cámara y gira con el servo de inclinación", "depende_de": ["giro"]},
    ],
}


def _obra(**cambios):
    return Obra(**{**PANTILT, **cambios})


# --- el esquema -------------------------------------------------------------------------

def test_el_orden_va_de_lo_que_no_depende_de_nada_a_lo_que_depende_de_todo():
    assert _obra().orden() == ["base", "giro", "inclinacion"]


@pytest.mark.parametrize("nodos, error", [
    ([{"id": "a", "nombre": "A", "que_hace": "x", "depende_de": ["z"]}], "«z»"),
    ([{"id": "a", "nombre": "A", "que_hace": "x", "depende_de": ["b"]},
      {"id": "b", "nombre": "B", "que_hace": "y", "depende_de": ["a"]}], "ciclo"),
    ([{"id": "a", "nombre": "A", "que_hace": "x"},
      {"id": "a", "nombre": "A2", "que_hace": "y"}], "repetido"),
    ([{"id": "Base Uno", "nombre": "A", "que_hace": "x"}], "id"),
])
def test_un_arbol_roto_no_se_acepta(nodos, error):
    with pytest.raises(ValueError, match=error):
        Obra(titulo="t", nodos=nodos)


# --- el desglosador ---------------------------------------------------------------------

class Guion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt, **_):
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


def test_el_desglosador_solo_compra_lo_que_tiene_ficha():
    from orchestrator.agents.desglosador import DesglosadorAgent
    malo = {**PANTILT, "nodos": [{**PANTILT["nodos"][0], "compra": ["sg91"]},
                                 *PANTILT["nodos"][1:]]}
    guion = Guion([json.dumps(malo), json.dumps(PANTILT)])
    obra = DesglosadorAgent(guion).desglosar("un pan-tilt con dos servos SG90 para una cámara")
    assert obra.orden() == ["base", "giro", "inclinacion"]
    assert "pan-tilt con dos servos SG90" in guion.prompts[0]
    assert "sg91" in guion.prompts[1] and "sg90" in guion.prompts[1]


def test_un_componente_comprado_no_es_un_nodo():
    """El primer pan-tilt de verdad (2026-11-09) salió con «Servo SG90 de
    giro» y «Servo SG90 de inclinación» como nodos: se habrían «diseñado» dos
    servos. Lo comprado va en `compra` de la pieza que lo aloja."""
    from orchestrator.agents.desglosador import DesglosadorAgent
    servo = {"id": "servo-giro", "nombre": "Servo SG90 de giro", "que_hace": "gira",
             "compra": ["sg90"], "depende_de": ["base"]}
    malo = {**PANTILT, "nodos": [PANTILT["nodos"][0], servo, *PANTILT["nodos"][1:]]}
    guion = Guion([json.dumps(malo), json.dumps(PANTILT)])
    DesglosadorAgent(guion).desglosar("un pan-tilt con dos SG90")
    assert "Servo SG90 de giro" in guion.prompts[1] and "compra" in guion.prompts[1]


def test_una_pieza_que_nombra_su_componente_si_es_un_nodo():
    from orchestrator.agents.desglosador import DesglosadorAgent
    soporte = {"titulo": "soporte", "nodos": [
        {"id": "soporte", "nombre": "Soporte del SG90", "que_hace": "aloja un SG90",
         "compra": ["sg90"]}]}
    obra = DesglosadorAgent(Guion([json.dumps(soporte)])).desglosar("un soporte para un SG90")
    assert obra.orden() == ["soporte"]


# --- el avance --------------------------------------------------------------------------

def _empezar(tmp_path, obra=None, peticion="un pan-tilt con dos SG90 para una cámara"):
    from orchestrator import obra as O
    (tmp_path / "request.md").write_text(peticion + "\n", encoding="utf-8")
    O.guardar(tmp_path, obra or _obra(), por="prueba")
    return O


def test_una_peticion_pequena_es_un_nodo_y_no_espera_otro_visto_bueno(tmp_path):
    O = _empezar(tmp_path, Obra(titulo="gancho", nodos=[
        {"id": "gancho", "nombre": "Gancho", "que_hace": "cuelga una mochila"}]),
        peticion="un gancho de pared para una mochila de 3 kg")
    assert O.aprobada(tmp_path)
    assert O.siguiente(tmp_path) == "gancho"
    # Y su petición es la de la persona, tal cual: como el flujo de pieza de hoy.
    assert O.peticion_del_nodo(tmp_path, "gancho").strip() == \
        "un gancho de pared para una mochila de 3 kg"


def test_un_arbol_de_varias_piezas_espera_el_visto_bueno_al_desglose(tmp_path):
    from orchestrator.registry import estado_de
    O = _empezar(tmp_path)
    assert not O.aprobada(tmp_path)
    assert estado_de(tmp_path)["estado"] == "por aprobar"
    assert "desglose" in estado_de(tmp_path)["motivo"]


def test_contestar_al_desglose_lo_archiva_y_pide_otro(tmp_path):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, respuestas="la cámara pesa 40 g", por="web")
    assert not (tmp_path / "obra.json").exists()
    assert list((tmp_path / "archivo").rglob("obra.json")), "archivar no es borrar"
    assert "la cámara pesa 40 g" in (tmp_path / "request.md").read_text(encoding="utf-8")


def test_lo_que_depende_de_algo_sin_terminar_esta_bloqueado(tmp_path):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    assert O.estados(tmp_path) == {"base": "pendiente", "giro": "bloqueado",
                                   "inclinacion": "bloqueado"}
    assert O.siguiente(tmp_path) == "base"


def test_el_concepto_de_un_nodo_se_aprueba_o_se_contesta_en_su_carpeta(tmp_path):
    from orchestrator.registry import estado_de
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    nodo = tmp_path / "nodos" / "base"
    nodo.mkdir(parents=True)
    (nodo / "concepto.json").write_text("{}", encoding="utf-8")
    assert O.estados(tmp_path)["base"] == "concepto por aprobar"
    assert estado_de(tmp_path)["estado"] == "por aprobar"
    assert "Base" in estado_de(tmp_path)["motivo"]

    O.aprobar(tmp_path, respuestas="que se atornille con M2", por="web")
    assert not (nodo / "concepto.json").exists()
    assert "que se atornille con M2" in O.peticion_del_nodo(tmp_path, "base")

    (nodo / "concepto.json").write_text("{}", encoding="utf-8")
    O.aprobar(tmp_path, por="web")
    assert (nodo / "concepto_aprobado").exists()


SOPORTE = """
def construir(kit):
    placa = kit.caja(40, 20, 5, en=(-20, -10, 0))
    for i, x in enumerate((-10, 10)):
        placa = placa.tornillo(f"m3_{i + 1}", "M3", en=(x, 0, 5), eje="-z")
    return placa
"""


def _disenar_nodo(tmp_path, id_):
    """Lo que deja el flujo de pieza en la carpeta del nodo: la pieza
    construida y su informe."""
    from orchestrator.build import build_part
    from orchestrator.schemas.programa import Programa
    from tests.test_generators import _freecadcmd
    from tests.test_sondas import PERFIL
    nodo = tmp_path / "nodos" / id_
    build_part(Programa(part=id_, codigo=SOPORTE), None, nodo / "parts" / id_, _freecadcmd(),
               perfil=PERFIL)
    (nodo / "concepto.json").write_text("{}", encoding="utf-8")
    (nodo / "concepto_aprobado").write_text("{}", encoding="utf-8")
    (nodo / "pieza_report.json").write_text(json.dumps(
        {"titulo": id_, "pieza": id_, "resuelto": True}), encoding="utf-8")
    (nodo / "rounds.json").write_text("[{}]", encoding="utf-8")


def test_esta_bien_la_siguiente_congela_el_nodo_y_desbloquea_lo_que_depende_de_el(
        tmp_path, monkeypatch):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    _disenar_nodo(tmp_path, "base")
    assert O.estados(tmp_path)["base"] == "diseñada"

    O.dar_por_lista(tmp_path, "base", por="web")
    assert O.estados(tmp_path) == {"base": "lista", "giro": "pendiente",
                                   "inclinacion": "bloqueado"}
    assert (tmp_path / "fichas" / "obra-base.yaml").exists()
    texto = O.peticion_del_nodo(tmp_path, "giro")
    for parte in ("Soporte de giro", "obra-base", "sg90", "eje de salida del SG90",
                  "Pan-tilt con dos SG90"):
        assert parte in texto, parte
    # La petición de toda la obra NO va: el ingeniero exigiría en cada pieza
    # los componentes que nombra, y sus cifras saldrían de requisitos.
    assert "para una cámara" not in texto

    O.marcar_impresa(tmp_path, "base", nota="entró justo")
    assert O.lista(tmp_path, "base")["impresa"] is True


def test_rehacer_un_nodo_archiva_tambien_lo_que_se_diseno_contra_el(tmp_path):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    _disenar_nodo(tmp_path, "base")
    O.dar_por_lista(tmp_path, "base", por="web")
    _disenar_nodo(tmp_path, "giro")

    rehechos = O.rehacer(tmp_path, "base", cambio="más alta")
    assert rehechos == ["base", "giro"]
    assert O.estados(tmp_path) == {"base": "pendiente", "giro": "bloqueado",
                                   "inclinacion": "bloqueado"}
    assert not (tmp_path / "fichas" / "obra-base.yaml").exists()
    archivado = tmp_path / "archivo"
    assert list(archivado.rglob("obra-base.yaml")) and list(archivado.rglob("giro.step"))
    assert "más alta" in (tmp_path / "nodos" / "base" / "cambios.md").read_text(encoding="utf-8")


# --- de una vuelta a otra no se pierde nada ----------------------------------------------
# La base del pan-tilt (2026-11-09) se rehízo dos veces y cada concepto salió
# de cero: cuatro M3 para fijarla, luego dos M4, luego dos M3, luego ninguno,
# sin que nadie lo pidiera. El segundo «rehacer» borró el primer cambio, y el
# agente de requisitos leyó «separada por un bloque macizo de unos 8 mm» —la
# descripción del defecto— como una cota de 8 mm que había que cumplir.

def _concepto_visto(nodo, idea):
    nodo.mkdir(parents=True, exist_ok=True)
    (nodo / "concepto.json").write_text(json.dumps({"concepto": {
        "idea": idea, "camino_de_carga": "c", "orientacion": "o",
        "fijaciones": ["2 tornillos M4 avellanados para fijar la base"]}}), encoding="utf-8")


def test_rehacer_parte_del_concepto_aprobado_y_acumula_los_cambios(tmp_path):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    nodo = tmp_path / "nodos" / "base"
    _concepto_visto(nodo, "brida con tuerca cautiva")
    (nodo / "concepto_aprobado").write_text("{}", encoding="utf-8")

    O.rehacer(tmp_path, "base", cambio="la tuerca, más adentro")
    _concepto_visto(nodo, "brida con la tuerca más adentro")
    O.rehacer(tmp_path, "base", cambio="la ranura de la brida, abierta al servo")

    anterior = json.loads((nodo / "concepto_anterior.json").read_text(encoding="utf-8"))
    assert anterior["concepto"]["idea"] == "brida con la tuerca más adentro"
    cambios = (nodo / "cambios.md").read_text(encoding="utf-8")
    assert "la tuerca, más adentro" in cambios and "abierta al servo" in cambios
    # Los cambios no van a la petición: de ella salen los requisitos.
    peticion = O.peticion_del_nodo(tmp_path, "base")
    assert "más adentro" not in peticion and "abierta al servo" not in peticion


def test_contestar_al_concepto_guarda_el_contestado_como_anterior(tmp_path):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    nodo = tmp_path / "nodos" / "base"
    _concepto_visto(nodo, "brida en U")

    O.aprobar(tmp_path, respuestas="el cable sale por un lado corto, abajo", por="web")

    anterior = json.loads((nodo / "concepto_anterior.json").read_text(encoding="utf-8"))
    assert anterior["concepto"]["idea"] == "brida en U"
    # La respuesta sí es un dato de la pieza: va a la petición.
    assert "lado corto" in O.peticion_del_nodo(tmp_path, "base")


# --- la orden -----------------------------------------------------------------------------

def test_la_orden_obra_para_en_el_desglose_y_luego_disena_el_nodo_que_toca(
        tmp_path, monkeypatch, capsys):
    """Un paso por lanzamiento: el desglose y para; con el visto bueno, el
    flujo de pieza del nodo que toca, en su carpeta, con su petición y con
    las fichas de la obra a la vista."""
    import os
    from types import SimpleNamespace

    from orchestrator import cli
    from orchestrator import obra as O
    from orchestrator.agents import desglosador

    class Desglosador:
        def __init__(self, *a, **k):
            pass

        def desglosar(self, peticion):
            return _obra()

    vistos = []

    def pieza(args, raiz, env, nombre):
        vistos.append((args.carpeta, open(args.peticion[0], encoding="utf-8").read(),
                       os.environ.get("INTELLIPRINT_FICHAS", "")))

    monkeypatch.setattr(desglosador, "DesglosadorAgent", Desglosador)
    monkeypatch.setattr(cli, "_pieza", pieza)
    monkeypatch.setattr(cli, "_cliente", lambda *a, **k: None)
    monkeypatch.setattr(cli.Router, "from_config_file", lambda *a, **k: None)
    # setenv y no delenv: la orden la cambia, y así se deshace al terminar.
    monkeypatch.setenv("INTELLIPRINT_FICHAS", "")
    args = SimpleNamespace(peticion=["un pan-tilt con dos SG90 para una cámara"],
                           archivo=False, carpeta=str(tmp_path))

    cli._obra(args, cli._raiz(), {}, "prueba")
    assert "desglose listo" in capsys.readouterr().out and not vistos

    O.aprobar(tmp_path, por="web")
    cli._obra(args, cli._raiz(), {}, "prueba")
    [(carpeta, peticion, fichas)] = vistos
    assert carpeta == str(tmp_path / "nodos" / "base")
    assert peticion.startswith("Base: aloja el SG90 de giro")
    assert fichas.split(os.pathsep)[0] == str(tmp_path / "fichas")


# --- el gestor de trabajos ----------------------------------------------------------------

def _esperar(store, job):
    for _ in range(100):
        if store.current() is None:
            return
        time.sleep(0.1)


def test_aprobar_una_obra_sigue_con_su_orden(tmp_path):
    from orchestrator import obra as O
    from orchestrator.jobs import JobStore
    orden = [sys.executable, "-c", "print('orden obra')"]
    store = JobStore(tmp_path, comando=["mecanismo"], comando_pieza=["pieza"])
    job = store.start("un pan-tilt con dos SG90", comando=orden)
    _esperar(store, job)
    O.guardar(tmp_path / job, _obra(), por="prueba")

    store.aprobar(job, por="web")
    _esperar(store, job)
    assert O.aprobada(tmp_path / job)
    assert (tmp_path / job / "run.log").read_text().count("orden obra") == 2
