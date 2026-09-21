"""Referencias para el diseñador: imágenes, textos y diseños que ya
funcionaron (F5.2 (adjuntos)).

Opcionales. Llegan por Telegram a Crafty o por la línea de órdenes, y el
Mechanism Designer las recibe junto a la petición: adaptar algo que ya
funciona es mucho más fácil que inventarlo.

La ruta de una referencia la escribe un modelo a partir de lo que llegó por
Telegram, así que es texto ajeno: sin límites, bastaría pedir
/proc/self/environ para que la clave de DeepSeek acabara en un prompt.
"""

import io
import json

import pytest
from PIL import Image

from orchestrator.mechanisms.referencias import ReferenciaInvalida, cargar_referencias


@pytest.fixture
def raiz(tmp_path):
    r = tmp_path / "workspace"
    (r / "projects" / "2026-09-19-bisagra").mkdir(parents=True)
    (r / "projects" / "2026-09-19-bisagra" / "mechanism.json").write_text(
        json.dumps({"title": "Bisagra de libro", "parts": [{"name": "hoja_a"}]}), encoding="utf-8")
    (r / "projects" / "2026-09-19-bisagra" / "request.md").write_text("una bisagra\n", encoding="utf-8")
    (r / "projects" / "2026-09-19-bisagra" / "rounds.json").write_text(
        json.dumps([{"number": 1, "title": "t", "feedback": ""}]), encoding="utf-8")
    return r


def _png(ruta, lado=64):
    Image.new("RGB", (lado, lado), (200, 20, 20)).save(ruta, "PNG")
    return ruta


def _cargar(entradas, raiz):
    return cargar_referencias(entradas, raices=[raiz], proyectos=[raiz / "projects"])


def test_una_imagen_se_carga_como_imagen(raiz):
    refs = _cargar([str(_png(raiz / "foto.png"))], raiz)
    assert len(refs.imagenes) == 1
    assert refs.imagenes[0].startswith("data:image/")


def test_una_imagen_grande_se_reduce(raiz):
    """Una foto del móvil pesa megas y tokens; el diseñador no necesita
    4000 píxeles para ver cómo es un trinquete."""
    refs = _cargar([str(_png(raiz / "grande.png", lado=3000))], raiz)
    import base64
    datos = base64.b64decode(refs.imagenes[0].split(",", 1)[1])
    assert max(Image.open(io.BytesIO(datos)).size) <= 1024


def test_un_proyecto_que_ya_salio_entra_con_su_diseno(raiz):
    refs = _cargar(["2026-09-19-bisagra"], raiz)
    (titulo, contenido), = refs.textos
    assert "2026-09-19-bisagra" in titulo
    assert "Bisagra de libro" in contenido and "una bisagra" in contenido


def test_un_texto_se_carga_como_texto(raiz):
    (raiz / "notas.md").write_text("el pawl tiene que ser de 3 mm", encoding="utf-8")
    refs = _cargar([str(raiz / "notas.md")], raiz)
    assert "3 mm" in refs.textos[0][1]


@pytest.mark.parametrize("ajena", ["/proc/self/environ", "/etc/passwd", "../../.env"])
def test_nada_fuera_de_las_carpetas_permitidas(raiz, ajena):
    with pytest.raises(ReferenciaInvalida):
        _cargar([ajena], raiz)


def test_un_rodeo_para_salirse_tampoco_vale(raiz, tmp_path):
    (tmp_path / "secreto.md").write_text("clave", encoding="utf-8")
    with pytest.raises(ReferenciaInvalida):
        _cargar([str(raiz / ".." / "secreto.md")], raiz)


def test_un_archivo_que_dice_ser_imagen_y_no_lo_es_se_rechaza(raiz):
    (raiz / "falsa.png").write_text("no soy una imagen", encoding="utf-8")
    with pytest.raises(ReferenciaInvalida, match="imagen"):
        _cargar([str(raiz / "falsa.png")], raiz)


def test_un_tipo_que_no_se_entiende_se_rechaza_diciendo_cuales_valen(raiz):
    (raiz / "pieza.stl").write_text("solid x\nendsolid x\n", encoding="utf-8")
    with pytest.raises(ReferenciaInvalida, match="png"):
        _cargar([str(raiz / "pieza.stl")], raiz)


def test_un_id_de_proyecto_que_no_existe_se_dice(raiz):
    with pytest.raises(ReferenciaInvalida, match="no-existe"):
        _cargar(["no-existe"], raiz)


def test_sin_referencias_no_pasa_nada(raiz):
    refs = _cargar([], raiz)
    assert refs.imagenes == [] and refs.textos == [] and not refs


def test_se_guardan_en_el_proyecto_para_saber_con_que_se_diseno(raiz, tmp_path):
    refs = _cargar([str(_png(raiz / "foto.png")), "2026-09-19-bisagra"], raiz)
    destino = tmp_path / "proyecto"
    refs.guardar(destino)
    guardados = sorted(p.name for p in (destino / "referencias").iterdir())
    assert any(n.endswith(".png") for n in guardados)
    assert any(n.endswith(".md") for n in guardados)


# --- Hasta el modelo ------------------------------------------------------------

URL = "data:image/jpeg;base64,/9j/AAAA"


def test_el_cliente_manda_las_imagenes_junto_al_texto():
    import httpx

    from orchestrator.llm.providers.deepseek import DeepSeekClient

    enviado = {}

    def responder(request):
        enviado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    DeepSeekClient(api_key="k", model="deepseek-reasoner",
                   transport=httpx.MockTransport(responder)).complete("mira esto", imagenes=[URL])
    contenido = enviado["messages"][0]["content"]
    assert {"type": "text", "text": "mira esto"} in contenido
    assert {"type": "image_url", "image_url": {"url": URL}} in contenido


def test_sin_imagenes_el_mensaje_sigue_siendo_texto_plano():
    import httpx

    from orchestrator.llm.providers.deepseek import DeepSeekClient

    enviado = {}

    def responder(request):
        enviado.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    DeepSeekClient(api_key="k", model="deepseek-chat",
                   transport=httpx.MockTransport(responder)).complete("hola")
    assert enviado["messages"][0]["content"] == "hola"


class _Anota:
    def __init__(self, respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def complete(self, prompt, imagenes=None):
        self.llamadas.append(imagenes)
        return self.respuestas.pop(0)


def test_las_imagenes_van_en_cada_intento_tambien_al_reintentar():
    from pydantic import BaseModel

    from orchestrator.llm.structured import structured

    class P(BaseModel):
        a: int

    cliente = _Anota(['{"b": 1}', '{"a": 1}'])
    structured(cliente, "x", P, imagenes=[URL])
    assert cliente.llamadas == [[URL], [URL]]


def test_sin_imagenes_structured_no_toca_la_llamada():
    """Los clientes que no saben de imágenes (y los de los tests) siguen
    funcionando: sin referencias no se les pasa nada nuevo."""
    from pydantic import BaseModel

    from orchestrator.llm.structured import structured

    class P(BaseModel):
        a: int

    class SoloTexto:
        def complete(self, prompt):
            return '{"a": 1}'

    assert structured(SoloTexto(), "x", P).a == 1


def test_el_disenador_recibe_los_textos_en_el_prompt_y_las_imagenes_aparte(raiz):
    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
    from tests.test_mechanism_flow import PERFIL, _spec

    _png(raiz / "foto.png")
    refs = _cargar([str(raiz / "foto.png"), "2026-09-19-bisagra"], raiz)
    prompts = []

    class Modelo:
        def complete(self, prompt, imagenes=None):
            prompts.append((prompt, imagenes))
            return json.dumps(_spec(0.5))

    MechanismDesignerAgent(Modelo(), CATALOGO, PERFIL, (235, 235, 250), 0.1).design(
        "un brazo", referencias=refs)
    prompt, imagenes = prompts[0]
    assert "Referencias" in prompt and "Bisagra de libro" in prompt
    assert len(imagenes) == 1 and imagenes[0].startswith("data:image/")


# --- La cadena: Crafty → MCP → trabajo → línea de órdenes → flujo -----------


def test_el_trabajo_pasa_las_referencias_a_la_linea_de_ordenes(tmp_path):
    import sys
    import time

    from orchestrator.jobs import JobStore

    store = JobStore(tmp_path, comando=[sys.executable, "-c", "import sys; print(sys.argv)"])
    job = store.start("un trinquete", referencias=["/w/foto.jpg", "2026-09-19-bisagra"])
    limite = time.time() + 20
    while store.status(job)["estado"] != "terminado" and time.time() < limite:
        time.sleep(0.1)
    registro = (tmp_path / job / "run.log").read_text(encoding="utf-8")
    assert "'--adjunto', '/w/foto.jpg'" in registro
    assert "'--adjunto', '2026-09-19-bisagra'" in registro


def test_la_linea_de_ordenes_acepta_varias_referencias():
    from orchestrator.cli import _parser

    args = _parser().parse_args(
        ["mecanismo", "un trinquete", "--adjunto", "a.jpg", "--adjunto", "b.md"])
    assert args.adjunto == ["a.jpg", "b.md"]
    # `--referencia` ya significaba otra cosa (la disposición fija de la
    # biela-manivela) y sigue significándolo.
    assert args.referencia is False


def test_una_referencia_mala_se_rechaza_antes_de_lanzar_nada(raiz, monkeypatch):
    """Crafty tiene que enterarse al momento, no diez minutos después en el
    registro de un trabajo que murió al arrancar."""
    import orchestrator.mcp_server as servidor

    monkeypatch.setenv("INTELLIPRINT_WORKSPACE", str(raiz))
    lanzados = []
    monkeypatch.setattr(servidor, "_store", lambda: type("S", (), {
        "start": lambda self, *a, **k: lanzados.append((a, k)) or "job",
        "current": lambda self: None})())

    respuesta = servidor.disenar_mecanismo("un trinquete", referencias=["/proc/self/environ"])
    assert "error" in respuesta and lanzados == []

    ok = servidor.disenar_mecanismo("un trinquete", referencias=["2026-09-19-bisagra"])
    assert ok.get("proyecto") == "job"
    assert lanzados[-1][1]["referencias"] == ["2026-09-19-bisagra"]


@pytest.mark.skipif(__import__("tests.test_generators", fromlist=["_freecadcmd"])._freecadcmd() is None,
                    reason="freecadcmd no disponible")
def test_el_flujo_guarda_las_referencias_en_el_proyecto(raiz, tmp_path):
    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.mechanisms.flow import design_mechanism
    from tests.test_generators import _freecadcmd
    from tests.test_mechanism_flow import PERFIL, DisenadorDePiezas, _spec

    refs = _cargar([str(_png(raiz / "foto.png"))], raiz)

    class Modelo:
        def complete(self, prompt, imagenes=None):
            return json.dumps(_spec(0.5))

    carpeta = tmp_path / "proyecto"
    design_mechanism("un brazo", MechanismDesignerAgent(Modelo(), CATALOGO, PERFIL, (235, 235, 250), 0.1),
                     PartDesignerAgent(DisenadorDePiezas(), CATALOGO), carpeta, _freecadcmd(),
                     min_gap_mm=0.1, animar=False, referencias=refs)
    assert any(p.suffix == ".png" for p in (carpeta / "referencias").iterdir())
