"""Añadir una función a un invento ya diseñado (F9.10 (ampliar)).

Hasta aquí un backlog solo se podía cambiar pieza a pieza: para ponerle una
pinza al pan-tilt había que pedirlo entero otra vez, y lo ya diseñado —y
pagado— no servía de nada. Ahora la ampliación se propone aparte
(`ampliacion.json`), la persona la ve y la aprueba, y solo entonces cambia
el plan: lo listo sigue listo, y de lo ya hecho solo se corrige lo que la
función nueva toca.

El ejemplo, escrito a mano: al pan-tilt de `tests/test_obra.py` se le añade
una pinza de dos piezas. La «mano» se atornilla al soporte de inclinación
con dos M3 y lleva un SG90; el «dedo» gira sobre ese servo. De las tres
piezas que había, la única que la pinza toca es el soporte de inclinación.
"""

import json

import pytest

from orchestrator.schemas.obra import Obra
from tests.test_obra import CONJUNTO, PANTILT, PLAN, UNIONES, Guion

PIDE = "añádele una pinza que abra 30 mm para coger una pelota de ping-pong"

MANO = {"id": "mano", "nombre": "Mano", "que_hace": "lleva el servo de la pinza y el dedo fijo",
        "compra": ["sg90"], "depende_de": ["inclinacion"]}
DEDO = {"id": "dedo", "nombre": "Dedo", "que_hace": "se cierra contra el dedo fijo",
        "depende_de": ["mano"]}
U3 = {"tipo": "fija", "id": "u3", "cabeza": "mano", "agarra": "inclinacion", "metrica": "M3",
      "cantidad": 2, "agarre": "rosca"}
U4 = {"tipo": "gira", "id": "u4", "gira": "dedo", "sobre": "mano", "componente": "sg90",
      "recorrido_grados": 90, "radio_libre_mm": 30}
CON_PINZA = {
    **PLAN,
    "nodos": [*PANTILT["nodos"], MANO, DEDO,
              {**CONJUNTO, "depende_de": [*CONJUNTO["depende_de"], "mano", "dedo"]}],
    "uniones": [*UNIONES, U3, U4],
}


def _con(**cambios) -> dict:
    return json.loads(json.dumps({**CON_PINZA, **cambios}))


# --- qué cambia, sin modelo ---------------------------------------------------------------

def test_la_diferencia_dice_lo_nuevo_y_la_unica_pieza_hecha_que_toca():
    """Contado a mano sobre el plan de arriba: dos piezas nuevas, dos uniones
    nuevas, y de las tres piezas que había solo el soporte de inclinación
    entra en una unión nueva (u3, los dos M3 de la mano)."""
    from orchestrator.ampliar import diferencia
    d = diferencia(Obra(**PLAN), Obra(**CON_PINZA))
    assert d.errores == []
    assert d.nuevos == ["mano", "dedo"]
    assert d.uniones == ["u3", "u4"]
    assert list(d.corregir) == ["inclinacion"]
    [motivo] = d.corregir["inclinacion"]
    assert "«Mano»" in motivo and "2 tornillos M3" in motivo


def test_montar_algo_nuevo_en_una_pieza_hecha_obliga_a_corregirla():
    """Si el servo de la pinza fuera en el soporte de inclinación y no en
    una pieza nueva, ese soporte ganaría un SG90 en `compra`: hay que
    corregirlo para alojarlo, y el motivo lo dice por su nombre de ficha."""
    from orchestrator.ampliar import diferencia
    plan = _con()
    plan["nodos"] = [n for n in plan["nodos"] if n["id"] not in ("mano", "dedo")]
    plan["nodos"][2]["compra"] = ["sg90"]
    plan["nodos"].insert(3, {**DEDO, "depende_de": ["inclinacion"]})
    plan["nodos"][-1]["depende_de"] = [*CONJUNTO["depende_de"], "dedo"]
    plan["uniones"] = [*UNIONES, {**U4, "sobre": "inclinacion"}]
    d = diferencia(Obra(**PLAN), Obra(**plan))
    assert d.errores == []
    assert list(d.corregir) == ["inclinacion"]
    assert any("Micro servo SG90" in m for m in d.corregir["inclinacion"])


def _sin_base(plan):
    plan["nodos"] = [n for n in plan["nodos"] if n["id"] != "base"]
    plan["nodos"][0]["depende_de"] = []
    plan["nodos"][0]["compra"] = ["sg90", "sg90"]
    plan["nodos"][-1]["depende_de"].remove("base")
    plan["uniones"] = [u for u in plan["uniones"] if u["id"] != "u1"]


def _lo_viejo_depende_de_lo_nuevo(plan):
    plan["nodos"][1]["depende_de"] = ["base", "mano"]
    plan["nodos"][3]["depende_de"] = ["base"]
    plan["uniones"][2]["agarra"] = "base"


def _cambia_un_giro_aprobado(plan):
    plan["uniones"][0]["recorrido_grados"] = 90


def _nada(plan):
    plan.update(json.loads(json.dumps(PLAN)))
    plan["nodos"][0]["que_hace"] = "aloja el servo de giro y pesa más"


@pytest.mark.parametrize("estropea, dice", [
    (_sin_base, "«base»"),
    (_lo_viejo_depende_de_lo_nuevo, "«giro»"),
    (_cambia_un_giro_aprobado, "«u1»"),
    (_nada, "no añade nada"),
])
def test_una_ampliacion_no_quita_ni_cambia_lo_que_ya_estaba(estropea, dice):
    """Lo aprobado y diseñado no se toca por debajo: no se quita una pieza,
    una pieza hecha no pasa a depender de una nueva (habría que rediseñarla
    contra ella) y una unión aprobada no cambia. Y algo tiene que añadir."""
    from orchestrator.ampliar import diferencia
    plan = _con()
    estropea(plan)
    errores = diferencia(Obra(**PLAN), Obra(**plan)).errores
    assert errores and dice in " ".join(errores), errores


# --- la propuesta espera, y no toca el plan -------------------------------------------------

def _pantilt_hecho(carpeta):
    """El pan-tilt terminado: sus tres piezas construidas y dadas por buenas
    y el conjunto movido sin chocar. Sin FreeCAD: lo que deja cada paso en
    la carpeta, escrito a mano."""
    from orchestrator import obra as O
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "request.md").write_text("un pan-tilt con dos SG90 para una cámara\n",
                                        encoding="utf-8")
    O.guardar(carpeta, Obra(**PLAN), por="prueba")
    O.aprobar(carpeta, por="prueba")
    for i in ("base", "giro", "inclinacion"):
        nodo = carpeta / "nodos" / i
        parte = nodo / "parts" / i
        parte.mkdir(parents=True)
        (parte / "envolvente.json").write_text('{"min": [0, 0, 0], "max": [1, 1, 1]}',
                                               encoding="utf-8")
        (parte / "rasgos.json").write_text("[]", encoding="utf-8")
        (parte / f"{i}.step").write_text("STEP", encoding="utf-8")
        (parte / "programa.py").write_text(f"PROGRAMA DE {i}", encoding="utf-8")
        (nodo / "concepto_aprobado").write_text("{}", encoding="utf-8")
        (nodo / "lista.json").write_text('{"por": "prueba"}', encoding="utf-8")
        (carpeta / "fichas").mkdir(exist_ok=True)
        (carpeta / "fichas" / f"obra-{i}.yaml").write_text("id: x\n", encoding="utf-8")
    (carpeta / "nodos" / "pan-tilt").mkdir()
    (carpeta / "nodos" / "pan-tilt" / "verificacion.json").write_text(
        json.dumps({"ok": True, "choques": [], "resumen": []}), encoding="utf-8")
    assert set(O.estados(carpeta).values()) == {"lista", "verificado"}
    return O


def _proponer(carpeta, *respuestas):
    from orchestrator import ampliar
    from orchestrator.agents.desglosador import DesglosadorAgent
    guion = Guion([json.dumps(r) for r in respuestas])
    ampliar.proponer(carpeta, DesglosadorAgent(guion))
    return guion


def test_la_propuesta_espera_el_visto_bueno_sin_tocar_el_plan(tmp_path):
    """Con un modelo de guion. Hasta que la persona la aprueba, `obra.json`
    es byte a byte el de antes y las piezas siguen como estaban."""
    from orchestrator import ampliar
    from orchestrator.registry import estado_de
    O = _pantilt_hecho(tmp_path)
    plan = (tmp_path / "obra.json").read_bytes()

    ampliar.pedir(tmp_path, PIDE)
    assert ampliar.pendiente(tmp_path) == "pedida"
    guion = _proponer(tmp_path, CON_PINZA)

    assert ampliar.pendiente(tmp_path) == "propuesta"
    assert (tmp_path / "obra.json").read_bytes() == plan
    assert set(O.estados(tmp_path).values()) == {"lista", "verificado"}
    assert estado_de(tmp_path)["estado"] == "por aprobar"
    assert "ampliación" in estado_de(tmp_path)["motivo"]
    # Lo que la persona lee antes de aprobar: lo nuevo y lo que se le toca.
    md = (tmp_path / "ampliacion.md").read_text(encoding="utf-8")
    for parte in (PIDE, "**Mano**", "**Dedo**", "«Dedo» gira 90°", "Soporte de inclinación",
                  "2 tornillos M3"):
        assert parte in md, parte
    assert "**Base**" not in md.split("hay que corregir")[1].split("##")[0]
    # Y lo que vio el modelo: lo que se pide, el plan que hay y las reglas.
    assert PIDE in guion.prompts[0]
    assert '"id": "inclinacion"' in guion.prompts[0]
    assert "no puede pasar a depender" in guion.prompts[0]


def test_aprobarla_cambia_el_plan_y_lo_listo_sigue_listo(tmp_path):
    """El criterio de la fila: los nodos listos conservan su `lista.json` y
    el conjunto pasa a «por verificar». De las tres piezas hechas solo se
    corrige la que la pinza toca, partiendo de su programa; el plan de antes
    y la verificación del conjunto se archivan, no se borran."""
    from orchestrator import ampliar
    O = _pantilt_hecho(tmp_path)
    antes = (tmp_path / "obra.json").read_text(encoding="utf-8")
    ampliar.pedir(tmp_path, PIDE)
    _proponer(tmp_path, CON_PINZA)

    assert O.aprobar(tmp_path, por="web") == "ampliación"

    assert ampliar.pendiente(tmp_path) is None
    assert O.cargar_obra(tmp_path).orden() == ["base", "giro", "inclinacion", "mano", "dedo",
                                               "pan-tilt"]
    for i in ("base", "giro"):
        assert (tmp_path / "nodos" / i / "lista.json").is_file(), i
    assert O.estados(tmp_path) == {
        "base": "lista", "giro": "lista", "inclinacion": "corrigiendo",
        "mano": "bloqueado", "dedo": "bloqueado", "pan-tilt": "bloqueado"}
    retoque = json.loads((tmp_path / "nodos" / "inclinacion" / "retoque.json").read_text(
        encoding="utf-8"))
    assert retoque["programa"] == "PROGRAMA DE inclinacion"
    assert PIDE in retoque["cambio"] and "«Mano»" in retoque["cambio"]
    archivo = tmp_path / "archivo"
    assert antes in [p.read_text(encoding="utf-8") for p in archivo.rglob("obra.json")]
    assert list(archivo.rglob("verificacion.json")) and list(archivo.rglob("ampliacion.json"))
    assert PIDE in (tmp_path / "request.md").read_text(encoding="utf-8")

    # Con las piezas otra vez listas, el conjunto es lo que toca y se mueve
    # de nuevo: la verificación de antes era de un invento sin pinza.
    for i in ("inclinacion", "mano", "dedo"):
        (tmp_path / "nodos" / i).mkdir(exist_ok=True)
        (tmp_path / "nodos" / i / "retoque.json").unlink(missing_ok=True)
        (tmp_path / "nodos" / i / "lista.json").write_text('{"por": "prueba"}', encoding="utf-8")
    assert O.estados(tmp_path)["pan-tilt"] == "por verificar"


def test_contestar_a_la_propuesta_pide_otra_que_parte_de_ella(tmp_path):
    from orchestrator import ampliar
    O = _pantilt_hecho(tmp_path)
    plan = (tmp_path / "obra.json").read_bytes()
    ampliar.pedir(tmp_path, PIDE)
    _proponer(tmp_path, CON_PINZA)

    O.aprobar(tmp_path, respuestas="que el dedo gire 60°, no 90", por="web")

    assert ampliar.pendiente(tmp_path) == "pedida"
    assert (tmp_path / "obra.json").read_bytes() == plan
    otra = _con()
    otra["uniones"][3]["recorrido_grados"] = 60
    guion = _proponer(tmp_path, otra)
    assert "que el dedo gire 60°, no 90" in guion.prompts[0] and PIDE in guion.prompts[0]
    assert '"id": "mano"' in guion.prompts[0]          # parte de lo que la persona vio
    assert "«Dedo» gira 60°" in (tmp_path / "ampliacion.md").read_text(encoding="utf-8")


def test_lo_que_el_modelo_estropea_le_vuelve_con_la_regla(tmp_path):
    """Si la propuesta quita la base, no llega a la persona: vuelve al
    modelo diciendo qué pieza falta, dentro de sus reintentos."""
    from orchestrator import ampliar
    _pantilt_hecho(tmp_path)
    ampliar.pedir(tmp_path, PIDE)
    mala = _con()
    _sin_base(mala)
    guion = _proponer(tmp_path, mala, CON_PINZA)
    assert "«base»" in guion.prompts[1].split("rechazado")[1]
    assert ampliar.pendiente(tmp_path) == "propuesta"


def test_no_se_amplia_lo_que_no_esta_aprobado_ni_dos_veces_a_la_vez(tmp_path):
    from orchestrator import ampliar
    from orchestrator import obra as O
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "request.md").write_text("un pan-tilt\n", encoding="utf-8")
    O.guardar(tmp_path / "a", Obra(**PLAN), por="prueba")
    with pytest.raises(ValueError, match="desglose"):
        ampliar.pedir(tmp_path / "a", PIDE)
    _pantilt_hecho(tmp_path / "b")
    with pytest.raises(ValueError, match="qué"):
        ampliar.pedir(tmp_path / "b", "  ")
    ampliar.pedir(tmp_path / "b", PIDE)
    with pytest.raises(ValueError, match="ya hay una ampliación"):
        ampliar.pedir(tmp_path / "b", "y una linterna")


def test_descartar_la_propuesta_la_archiva_y_todo_sigue_como_estaba(tmp_path):
    from orchestrator import ampliar
    O = _pantilt_hecho(tmp_path)
    plan = (tmp_path / "obra.json").read_bytes()
    ampliar.pedir(tmp_path, PIDE)
    _proponer(tmp_path, CON_PINZA)

    ampliar.descartar(tmp_path)

    assert ampliar.pendiente(tmp_path) is None
    assert (tmp_path / "obra.json").read_bytes() == plan
    assert set(O.estados(tmp_path).values()) == {"lista", "verificado"}
    assert list((tmp_path / "archivo").rglob("ampliacion.json")), "archivar no es borrar"


# --- la orden -------------------------------------------------------------------------------

def test_la_orden_propone_para_y_al_aprobar_corrige_la_pieza_tocada(tmp_path, monkeypatch,
                                                                    capsys):
    """`obra --ampliar` da un paso, como todo en un backlog: propone y para.
    Relanzada sin aprobar no vuelve a llamar al modelo. Con el visto bueno,
    lo siguiente es corregir el soporte de inclinación, en su carpeta."""
    from types import SimpleNamespace

    from orchestrator import cli
    from orchestrator import obra as O
    from orchestrator.agents import desglosador

    llamadas = []

    class Desglosador:
        def __init__(self, *a, **k):
            pass

        def desglosar(self, peticion, **k):
            llamadas.append((peticion, k))
            return Obra(**CON_PINZA)

    corregidas = []
    monkeypatch.setattr(desglosador, "DesglosadorAgent", Desglosador)
    monkeypatch.setattr(cli, "_pieza", lambda args, *a: corregidas.append(args.carpeta))
    monkeypatch.setattr(cli, "_cliente", lambda *a, **k: None)
    monkeypatch.setattr(cli.Router, "from_config_file", lambda *a, **k: None)
    monkeypatch.setenv("INTELLIPRINT_FICHAS", "")
    monkeypatch.setenv("INTELLIPRINT_AJENOS", "")
    monkeypatch.setenv("INTELLIPRINT_UNIONES", "")
    # Las fichas de `_pantilt_hecho` son de pega (las escribe FreeCAD): aquí
    # se mira qué pieza se lanza, no lo que el plan le dice de sus uniones.
    monkeypatch.setattr(O, "escribir_uniones", lambda carpeta, nodo: tmp_path / "uniones.json")
    _pantilt_hecho(tmp_path)

    cli._obra(SimpleNamespace(peticion=[PIDE], archivo=False, carpeta=str(tmp_path),
                              ampliar=True), cli._raiz(), {}, "prueba")
    salida = capsys.readouterr().out
    assert "**Mano**" in salida and "espera tu visto bueno" in salida
    [(peticion, k)] = llamadas
    assert PIDE in peticion and k["ampliar"].orden() == ["base", "giro", "inclinacion", "pan-tilt"]

    seguir = SimpleNamespace(peticion=["x"], archivo=False, carpeta=str(tmp_path))
    cli._obra(seguir, cli._raiz(), {}, "prueba")
    assert "espera tu visto bueno" in capsys.readouterr().out
    assert len(llamadas) == 1 and not corregidas

    O.aprobar(tmp_path, por="web")
    cli._obra(seguir, cli._raiz(), {}, "prueba")
    assert corregidas == [str(tmp_path / "nodos" / "inclinacion")]


# --- la web y Crafty ------------------------------------------------------------------------

ID = "2026-11-12-pan-tilt"


def test_anadir_funcion_desde_la_web_lanza_la_propuesta(ws):
    """«Añadir función» deja la ampliación pedida y relanza el backlog en su
    carpeta, que es quien la propone. A una pieza suelta no se le añade."""
    from orchestrator import ampliar
    from tests.test_interfaz_web import _esperar_registro, _ws_con_trabajos
    carpeta = ws / "projects" / ID
    _pantilt_hecho(carpeta)
    web = _ws_con_trabajos(ws)

    assert f'data-ampliar="{ID}"' in web.get(f"/p/{ID}").text

    r = web.post(f"/api/proyectos/{ID}/ampliar", json={"peticion": PIDE})
    assert r.status_code == 200, r.text
    assert ampliar.pendiente(carpeta) == "pedida"
    assert "--continuar" in _esperar_registro(carpeta)

    suelta = ws / "projects" / "2026-11-12-gancho"
    suelta.mkdir()
    (suelta / "request.md").write_text("un gancho\n", encoding="utf-8")
    r = web.post("/api/proyectos/2026-11-12-gancho/ampliar", json={"peticion": PIDE})
    assert r.status_code == 409


def test_la_web_ensena_la_propuesta_con_su_visto_bueno_y_se_puede_descartar(ws):
    from orchestrator import ampliar
    from tests.test_interfaz_web import _ws_con_trabajos
    carpeta = ws / "projects" / ID
    _pantilt_hecho(carpeta)
    ampliar.pedir(carpeta, PIDE)
    _proponer(carpeta, CON_PINZA)
    web = _ws_con_trabajos(ws)

    html = web.get(f"/p/{ID}").text
    for parte in ("Mano", "Dedo", "hay que corregir", "Soporte de inclinación",
                  f'data-aprobar="{ID}"', "Aprobar la ampliación",
                  f'data-descartar-ampliacion="{ID}"'):
        assert parte in html, parte
    # Con una propuesta esperando no se pide otra.
    assert 'data-ampliar="' not in html

    r = web.post(f"/api/proyectos/{ID}/ampliacion/descartar")
    assert r.status_code == 200, r.text
    assert ampliar.pendiente(carpeta) is None


def test_crafty_puede_pedir_la_ampliacion_y_ensenar_la_propuesta(ws):
    """Por Telegram no hay página: la herramienta la pide, y el estado trae
    la propuesta para enseñarla antes del visto bueno."""
    import orchestrator.mcp_server as servidor
    from orchestrator import ampliar
    from tests.test_interfaz_web import _esperar_registro
    carpeta = ws / "projects" / ID
    _pantilt_hecho(carpeta)

    r = servidor.ampliar_proyecto(ID, PIDE)
    assert "error" not in r, r
    assert ampliar.pendiente(carpeta) == "pedida"
    assert "--continuar" in _esperar_registro(carpeta)

    _proponer(carpeta, CON_PINZA)
    estado = servidor.estado_proyecto(ID)
    assert estado["estado"] == "por aprobar"
    assert "**Mano**" in estado["ampliacion"]

    assert "error" in servidor.ampliar_proyecto(ID, "y una linterna")


from tests.test_mcp_proyectos import ws  # noqa: E402, F401 (la fixture)


# --- el banco -------------------------------------------------------------------------------

def _encargos():
    from pathlib import Path

    from orchestrator.banco import cargar_encargos
    todos = {e.nombre: e for e in cargar_encargos(Path("tests/banco/encargos"))}
    return todos["pan_tilt_con_pinza"], todos["pan_tilt_sg90"]


def test_el_encargo_de_la_pinza_amplia_el_pan_tilt_del_banco():
    """«El pan-tilt con una pinza» no se pide de una vez: es el encargo del
    pan-tilt y, encima, la función. Lo que su oráculo cuenta sale de las dos
    peticiones: 2 + 1 servos, y por cada uno sus dos tornillos."""
    from orchestrator.banco import Componente, Conserva, Tornillos
    pinza, base = _encargos()
    assert pinza.amplia == base.nombre and pinza.obra
    assert base.peticion.strip() in pinza.peticion_entera
    assert pinza.peticion.strip() in pinza.peticion_entera
    [servos] = [a for a in pinza.oraculo if isinstance(a, Componente)]
    [tornillos] = [a for a in pinza.oraculo if isinstance(a, Tornillos)]
    [base_servos] = [a for a in base.oraculo if isinstance(a, Componente)]
    assert servos.cuantos == base_servos.cuantos + 1 == 3
    assert tornillos.cuantos == 2 * servos.cuantos
    assert [a for a in pinza.oraculo if isinstance(a, Conserva)]


class _Hecho:
    stdout, stderr, returncode = "hecho", "", 0


def test_el_banco_amplia_partiendo_de_una_corrida_ya_hecha(tmp_path, monkeypatch):
    """Para medir la ampliación no hay que pagar otra vez el pan-tilt: se
    copia el de una corrida anterior y solo se pide la función. La corrida
    de la que se parte no se toca."""
    from orchestrator import banco
    pinza, base = _encargos()
    vieja = tmp_path / "1111-1342" / "01"
    _pantilt_hecho(vieja / "projects" / "p")
    banco.marcar_carpeta(vieja, base.nombre)
    antes = sorted(str(f.relative_to(vieja)) for f in vieja.rglob("*"))
    ordenes = []

    def run(orden, **k):
        ordenes.append((orden, k["env"]["INTELLIPRINT_WORKSPACE"]))
        return _Hecho()

    monkeypatch.setattr(banco.subprocess, "run", run)
    monkeypatch.setattr(banco, "juzgar_obra", lambda *a, **k: ["juzgado"])
    nueva = tmp_path / "nueva" / "01"

    r, fallo = banco.correr(pinza, nueva, ["intelliprint", "obra", "--banco"], "fc", {},
                            base=base, partir_de=tmp_path / "1111-1342")

    assert (r, fallo) == (["juzgado"], None)
    proyecto = nueva / "projects" / "p"
    assert (proyecto / "obra.json").is_file()
    assert ordenes == [(["intelliprint", "obra", "--banco", "--ampliar", "--carpeta",
                         str(proyecto), pinza.peticion], str(nueva))]
    assert sorted(str(f.relative_to(vieja)) for f in vieja.rglob("*")) == antes


def test_sin_corrida_de_la_que_partir_el_banco_pide_primero_el_invento(tmp_path, monkeypatch):
    from orchestrator import banco
    pinza, base = _encargos()
    carpeta = tmp_path / "01"
    ordenes = []

    def run(orden, **k):
        ordenes.append(orden)
        if len(ordenes) == 1:
            _pantilt_hecho(carpeta / "projects" / "p")
        return _Hecho()

    monkeypatch.setattr(banco.subprocess, "run", run)
    monkeypatch.setattr(banco, "juzgar_obra", lambda *a, **k: [])
    banco.correr(pinza, carpeta, ["intelliprint", "obra", "--banco"], "fc", {}, base=base)
    assert ordenes[0] == ["intelliprint", "obra", "--banco", base.peticion]
    assert ordenes[1][3:5] == ["--ampliar", "--carpeta"] and ordenes[1][-1] == pinza.peticion


def test_si_la_corrida_no_tiene_el_invento_no_se_pide_nada(tmp_path, monkeypatch):
    from orchestrator import banco
    pinza, base = _encargos()
    monkeypatch.setattr(banco.subprocess, "run",
                        lambda *a, **k: pytest.fail("no hay de dónde partir: no se gasta"))
    (tmp_path / "vacia").mkdir()
    r, fallo = banco.correr(pinza, tmp_path / "01", ["x"], "fc", {}, base=base,
                            partir_de=tmp_path / "vacia")
    assert "pan_tilt_sg90" in fallo
    assert all(x.estado == "no_cumple" for x in r) and len(r) == len(pinza.oraculo)


def test_aprobar_la_ampliacion_apunta_como_estaban_las_piezas(tmp_path):
    """La huella de cada pieza antes de tocar nada: con ella el banco sabe
    después cuáles siguen idénticas. La de un STEP que dice «STEP»,
    calculada aquí con hashlib."""
    import hashlib

    from orchestrator import ampliar
    O = _pantilt_hecho(tmp_path)
    ampliar.pedir(tmp_path, PIDE)
    _proponer(tmp_path, CON_PINZA)
    O.aprobar(tmp_path, por="web")
    [hecha] = json.loads((tmp_path / ampliar.HECHAS).read_text(encoding="utf-8"))
    huella = hashlib.sha256(b"STEP").hexdigest()
    assert hecha["antes"] == {"base": huella, "giro": huella, "inclinacion": huella}
    assert hecha["peticion"] == PIDE and hecha["corregidas"] == ["inclinacion"]
    assert hecha["nuevos"] == ["mano", "dedo"]


@pytest.mark.parametrize("minimo, estado, dice", [
    (1, "cumple", "1 de 2"),
    (2, "no_cumple", "«Pieza soporte»"),
])
def test_el_banco_cuenta_las_piezas_que_la_ampliacion_no_toco(tmp_path, monkeypatch, minimo,
                                                              estado, dice):
    """Lo listo sigue listo, medido en lo construido: una pieza cuenta si su
    STEP es byte a byte el de antes de ampliar. Aquí, a mano, el brazo es el
    mismo y del soporte se apuntó otra huella: 1 de 2."""
    import hashlib

    from orchestrator import ampliar
    from tests.test_banco import _juzgar_brazo
    from tests.test_estudio import _brazo_en_voladizo

    def ampliado(p):
        _brazo_en_voladizo(p)
        brazo = p / "nodos" / "brazo" / "parts" / "brazo" / "brazo.step"
        (p / ampliar.HECHAS).write_text(json.dumps([{
            "peticion": "una pinza", "nuevos": [], "corregidas": ["soporte"],
            "antes": {"brazo": hashlib.sha256(brazo.read_bytes()).hexdigest(),
                      "soporte": "otra-huella"}}]), encoding="utf-8")

    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "conserva", "minimo": minimo}],
                        "un brazo", brazo=ampliado)
    assert r.estado == estado, r.detalle
    assert dice in r.detalle


def test_sin_ampliacion_no_hay_nada_que_conservar(tmp_path, monkeypatch):
    from tests.test_banco import _juzgar_brazo
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "conserva", "minimo": 1}], "un brazo")
    assert r.estado == "no_cumple" and "no se amplió" in r.detalle


def test_la_orden_del_banco_pasa_la_corrida_de_la_que_se_parte(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from orchestrator import banco, cli
    visto = {}

    def correr(encargo, carpeta, orden, *a, base=None, partir_de=None, **k):
        visto.update(encargo=encargo.nombre, base=base and base.nombre, partir_de=partir_de,
                     orden=orden)
        carpeta.mkdir(parents=True)   # la de verdad la deja marcada
        return [], None

    monkeypatch.setattr(banco, "correr", correr)
    monkeypatch.setattr(cli, "_freecadcmd", lambda env: "freecadcmd")
    args = SimpleNamespace(solo=["pan_tilt_con_pinza"], rejuzgar=None, reanudar=None,
                           partir_de=str(tmp_path / "1111-1342"))
    cli._banco(args, cli._raiz(), {"INTELLIPRINT_WORKSPACE": str(tmp_path)}, "prueba")
    assert visto["encargo"] == "pan_tilt_con_pinza" and visto["base"] == "pan_tilt_sg90"
    assert visto["partir_de"] == tmp_path / "1111-1342"
    assert visto["orden"][-2:] == ["obra", "--banco"]


def test_se_orienta_puede_mirar_el_primer_giro_horizontal_y_no_el_ultimo(tmp_path):
    """Con una pinza encima, la última pieza que gira sobre un eje
    horizontal es el dedo, y la cámara va en la plataforma. A mano: un
    soporte con un SG90 tumbado (eje en x = 0), la plataforma que gira sobre
    él y lleva otro tumbado 60 mm más allá, y el dedo sobre ese."""
    from orchestrator.banco import la_que_gira
    from tests.test_conjunto import _obra, _sg90, _sobre
    tumbado = [("x", 90)]
    carpeta = _obra(tmp_path, {
        "soporte": ([], [_sg90((-5.8, 27.1, 18.8), tumbado)], ([-28, -17, 0], [28, 17.5, 31.5])),
        "plataforma": (["soporte"], [_sobre("soporte", (0, 0, 0)),
                                     _sg90((54.2, 27.1, 18.8), tumbado)],
                       ([0, -40, 20], [100, -1, 30])),
        "dedo": (["plataforma"], [_sobre("plataforma", (0, 0, 0))],
                 ([55, -40, 20], [90, -1, 30])),
    })
    assert la_que_gira(carpeta, "horizontal")[0] == "dedo"
    assert la_que_gira(carpeta, "horizontal", primera=True)[0] == "plataforma"
