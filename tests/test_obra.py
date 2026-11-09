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

from orchestrator.pieza import _de_la_vuelta_anterior
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
    assert "que se atornille con M2" in _de_la_vuelta_anterior(nodo)["cambios"]

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


def test_corregir_una_pieza_disenada_parte_de_ella_y_no_de_cero(tmp_path):
    """La base del pan-tilt (2026-11-09) tenía la tuerca 2 mm demasiado
    cerca de una cara, y «rehacer» volvía a pedir especificación, concepto,
    visto bueno y un diseño nuevo: salió otra pieza. Corregir guarda la spec
    y el concepto aprobados y deja el programa construido como punto de
    partida; lo construido se archiva, y lo que se diseñó contra su ficha
    también, porque la ficha va a cambiar."""
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    _disenar_nodo(tmp_path, "base")
    nodo = tmp_path / "nodos" / "base"
    (nodo / "parts" / "base" / "programa.py").write_text(SOPORTE, encoding="utf-8")
    (nodo / "spec.yaml").write_text("title: base\n", encoding="utf-8")
    O.dar_por_lista(tmp_path, "base", por="web")
    _disenar_nodo(tmp_path, "giro")

    rehechos = O.corregir(tmp_path, "base", cambio="la tuerca, 2 mm más adentro")

    assert rehechos == ["base", "giro"]
    for queda in ("spec.yaml", "concepto.json", "concepto_aprobado"):
        assert (nodo / queda).exists(), queda
    assert not (nodo / "parts").exists() and not (nodo / "pieza_report.json").exists()
    assert O.estados(tmp_path)["base"] == "corrigiendo"
    assert json.loads((nodo / "retoque.json").read_text(encoding="utf-8")) == {
        "programa": SOPORTE, "cambio": "la tuerca, 2 mm más adentro"}
    assert list((tmp_path / "archivo").rglob("base/parts/base/programa.py"))
    assert not (tmp_path / "fichas" / "obra-base.yaml").exists()
    assert O.estados(tmp_path)["giro"] == "bloqueado"


def test_rehacer_conserva_las_respuestas_de_la_persona(tmp_path):
    """Que el cable del SG90 sale por un lado corto lo dijo la persona una
    vez; rehacer la pieza por otra cosa no lo vuelve falso."""
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    _concepto_visto(tmp_path / "nodos" / "base", "brida en U")
    O.aprobar(tmp_path, respuestas="el cable sale por un lado corto, abajo", por="web")

    O.rehacer(tmp_path, "base", cambio="más alta")

    assert "lado corto" in _de_la_vuelta_anterior(tmp_path / "nodos" / "base")["cambios"]


def test_contestar_al_concepto_guarda_el_contestado_como_anterior(tmp_path):
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    nodo = tmp_path / "nodos" / "base"
    _concepto_visto(nodo, "brida en U")

    O.aprobar(tmp_path, respuestas="el cable sale por un lado corto, abajo", por="web")

    anterior = json.loads((nodo / "concepto_anterior.json").read_text(encoding="utf-8"))
    assert anterior["concepto"]["idea"] == "brida en U"
    assert "lado corto" in _de_la_vuelta_anterior(nodo)["cambios"]


def test_contestar_al_concepto_no_crea_requisitos(tmp_path):
    """Al soporte de giro del pan-tilt (2026-11-09) se le contestó citando
    el cuerno de la ficha («cubo de Ø6.9») y diciendo que 4 mm no bastaban.
    El agente de requisitos sacó «R7: un agujero de Ø6.9» y «R9: 4 mm», y la
    pieza falló por no tener un agujero que nadie quería. Contestar es hablar
    con el ingeniero: va al concepto, no a la petición."""
    O = _empezar(tmp_path)
    O.aprobar(tmp_path, por="web")
    nodo = tmp_path / "nodos" / "base"
    _concepto_visto(nodo, "placa en el cuerno")
    O.aprobar(tmp_path, respuestas="el rebaje para el cubo de Ø6.9 del cuerno; 4 mm no bastan",
              por="web")
    assert "Ø6.9" not in O.peticion_del_nodo(tmp_path, "base")
    assert "Ø6.9" in _de_la_vuelta_anterior(nodo)["cambios"]


# --- el conjunto (F7.4 (conjunto)) ---------------------------------------------------------

def _con_conjunto(tmp_path):
    conjunto = {"id": "pan-tilt", "nombre": "Conjunto pan-tilt", "tipo": "conjunto",
                "que_hace": "gira e inclina", "depende_de": ["base", "giro", "inclinacion"]}
    O = _empezar(tmp_path, _obra(nodos=[*PANTILT["nodos"], conjunto]))
    O.aprobar(tmp_path, por="web")
    for i in ("base", "giro", "inclinacion"):
        (tmp_path / "nodos" / i).mkdir(parents=True)
        (tmp_path / "nodos" / i / "lista.json").write_text('{"por": "web"}', encoding="utf-8")
    return O


def test_con_sus_piezas_listas_el_conjunto_es_lo_siguiente_y_espera_verificarse(tmp_path):
    """Antes se quedaba «sin verificar» para siempre y la obra salía terminada."""
    O = _con_conjunto(tmp_path)
    assert O.estados(tmp_path)["pan-tilt"] == "por verificar"
    assert O.siguiente(tmp_path) == "pan-tilt"


@pytest.mark.parametrize("ok, estado, siguiente", [(True, "verificado", None),
                                                    (False, "con choques", "pan-tilt")])
def test_el_conjunto_queda_como_dijo_su_verificacion(tmp_path, ok, estado, siguiente):
    O = _con_conjunto(tmp_path)
    (tmp_path / "nodos" / "pan-tilt").mkdir()
    (tmp_path / "nodos" / "pan-tilt" / "verificacion.json").write_text(
        json.dumps({"ok": ok, "choques": [], "resumen": []}), encoding="utf-8")
    assert O.estados(tmp_path)["pan-tilt"] == estado
    assert O.siguiente(tmp_path) == siguiente


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
                       os.environ.get("INTELLIPRINT_FICHAS", ""),
                       os.environ.get("INTELLIPRINT_AJENOS", "")))

    monkeypatch.setattr(desglosador, "DesglosadorAgent", Desglosador)
    monkeypatch.setattr(cli, "_pieza", pieza)
    monkeypatch.setattr(cli, "_cliente", lambda *a, **k: None)
    monkeypatch.setattr(cli.Router, "from_config_file", lambda *a, **k: None)
    # setenv y no delenv: la orden la cambia, y así se deshace al terminar.
    monkeypatch.setenv("INTELLIPRINT_FICHAS", "")
    monkeypatch.setenv("INTELLIPRINT_AJENOS", "")
    args = SimpleNamespace(peticion=["un pan-tilt con dos SG90 para una cámara"],
                           archivo=False, carpeta=str(tmp_path))

    cli._obra(args, cli._raiz(), {}, "prueba")
    assert "desglose listo" in capsys.readouterr().out and not vistos

    O.aprobar(tmp_path, por="web")
    cli._obra(args, cli._raiz(), {}, "prueba")
    [(carpeta, peticion, fichas, ajenos)] = vistos
    assert carpeta == str(tmp_path / "nodos" / "base")
    assert peticion.startswith("Base: aloja el SG90 de giro")
    assert fichas.split(os.pathsep)[0] == str(tmp_path / "fichas")
    # El kit que construye la base solo deja colocar UN sg90: el otro es del
    # soporte de giro.
    assert json.loads(ajenos)["sg90"]["cuantos"] == 1


def test_la_orden_obra_mueve_el_conjunto_con_la_holgura_de_la_impresora(
        tmp_path, monkeypatch, capsys):
    """Con las piezas del pan-tilt listas (2026-11-09), la orden reventó al
    pedir la holgura al perfil en vez de a su impresora: ningún test pasaba
    por ahí. El hueco mínimo es media holgura «slide» del perfil."""
    from types import SimpleNamespace

    from orchestrator import cli, conjunto
    _con_conjunto(tmp_path)
    pedido = {}

    def verificar(carpeta, nodo, freecadcmd, min_gap_mm):
        pedido.update(nodo=nodo, min_gap_mm=min_gap_mm)
        return {"ok": True, "articulaciones": [], "resumen": []}

    monkeypatch.setattr(conjunto, "verificar_conjunto", verificar)
    monkeypatch.setattr(cli, "_freecadcmd", lambda env: "freecadcmd")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", "")
    args = SimpleNamespace(peticion=["un pan-tilt"], archivo=False, carpeta=str(tmp_path))
    cli._obra(args, cli._raiz(), {}, "prueba")

    holgura = cli._perfil(cli._raiz(), {}).impresora.fit_mm("slide")
    assert pedido == {"nodo": "pan-tilt", "min_gap_mm": holgura / 2}
    assert "se mueve sin chocar" in capsys.readouterr().out


def test_el_banco_recorre_la_obra_entera_sin_nadie_que_de_el_visto_bueno(
        tmp_path, monkeypatch):
    """F7.5 (obras): en el banco no hay persona. El desglose, cada concepto y
    cada «está bien» los da el banco, como con `pieza --aprobar-concepto`, y
    una pieza con fallos también sigue: se entrega y se juzga (F6.8 (mejor)).
    Lo que se mide es lo que sale tal como lo propuso el sistema."""
    from types import SimpleNamespace

    from orchestrator import cli, conjunto
    from orchestrator import obra as O
    from orchestrator.agents import desglosador
    from orchestrator.pieza import APROBADO, CONCEPTO

    conjunto_ = {"id": "pan-tilt", "nombre": "Conjunto", "tipo": "conjunto",
                 "que_hace": "gira e inclina", "depende_de": ["base", "giro", "inclinacion"]}

    class Desglosador:
        def __init__(self, *a, **k):
            pass

        def desglosar(self, peticion):
            return _obra(nodos=[*PANTILT["nodos"], conjunto_])

    disenadas = []

    def pieza(args, raiz, env, nombre):
        nodo = tmp_path / "nodos" / args.carpeta.rsplit("nodos", 1)[1].strip("/\\")
        if not (nodo / CONCEPTO).is_file():
            (nodo / CONCEPTO).write_text("{}", encoding="utf-8")
            return
        assert (nodo / APROBADO).is_file()
        disenadas.append(nodo.name)
        parte = nodo / "parts" / nodo.name
        parte.mkdir(parents=True)
        (parte / "envolvente.json").write_text('{"min": [0,0,0], "max": [1,1,1]}')
        resuelto = nodo.name != "giro"   # una con fallos: el banco sigue igual
        (nodo / "pieza_report.json").write_text(json.dumps({"resuelto": resuelto}))
        if not resuelto:
            sys.exit(1)

    def verificar(carpeta, nodo, freecadcmd, min_gap_mm):
        (carpeta / "nodos" / nodo).mkdir(parents=True, exist_ok=True)
        (carpeta / "nodos" / nodo / "verificacion.json").write_text('{"ok": true}')
        return {"ok": True, "articulaciones": [], "resumen": []}

    monkeypatch.setattr(desglosador, "DesglosadorAgent", Desglosador)
    monkeypatch.setattr(cli, "_pieza", pieza)
    monkeypatch.setattr(cli, "_cliente", lambda *a, **k: None)
    monkeypatch.setattr(cli.Router, "from_config_file", lambda *a, **k: None)
    monkeypatch.setattr(O, "fichar", lambda *a, **k: None)
    monkeypatch.setattr(conjunto, "verificar_conjunto", verificar)
    monkeypatch.setattr(cli, "_freecadcmd", lambda env: "freecadcmd")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", "")
    args = SimpleNamespace(peticion=["un pan-tilt"], archivo=False, carpeta=str(tmp_path),
                           banco=True)

    cli._obra(args, cli._raiz(), {}, "prueba")

    assert disenadas == ["base", "giro", "inclinacion"]
    assert O.estados(tmp_path) == {"base": "lista", "giro": "lista", "inclinacion": "lista",
                                   "pan-tilt": "verificado"}
    assert O.lista(tmp_path, "giro")["por"] == "banco"


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


def test_lo_que_ya_monta_otra_pieza_no_se_vuelve_a_colocar(tmp_path):
    """Banco 1109-1949 (2026-11-09): la plataforma del pan-tilt colocó un
    SG90 propio para tallar el hueco del cuerno, encima del que ya monta el
    soporte de giro. El juez contó tres servos y el conjunto chocó 7920 mm³
    contra el de verdad. La ficha del soporte ya traía ese servo, su eje y
    lo que hay que dejar libre: la petición lo dice y el kit no deja otro."""
    O = _empezar(tmp_path)
    texto = O.peticion_del_nodo(tmp_path, "inclinacion")
    assert "ya lleva" in texto and "no coloques otro sg90" in texto
    ajenos = O.ajenos(tmp_path, "inclinacion")
    assert ajenos["sg90"]["cuantos"] == 0 and "«Soporte de giro»" in ajenos["sg90"]["mensaje"]
    assert O.ajenos(tmp_path, "giro")["sg90"]["cuantos"] == 1
    # Lo que no compra nadie del backlog se puede colocar: no hay con qué chocar.
    assert "608zz" not in ajenos
