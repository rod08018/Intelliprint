"""Buscar en internet lo que la petición no dice (F3.21 (investigar)).

La persona pide «un soporte para una Raspberry Pi 4» desde la web o desde
Telegram y no da las medidas de la placa. Hasta ahora el sistema las sacaba
de memoria, y de memoria se equivoca: el soporte de la Raspberry salió con
el patrón de agujeros centrado en la placa, y en la placa real está metido
hacia un extremo (2026-11-04). Crafty ya podía buscar, pero la web no: la
búsqueda tiene que estar en Intelliprint, antes del ingeniero, para que
sirva por los dos canales.

Lo que se busca entra con su fuente y con una cita LITERAL de la página,
que el código comprueba: un dato sin cita es un dato de memoria con una URL
pegada. Y entra como requisito de `catalogo`, nunca como si lo hubiera
dicho el usuario.
"""

import json

import pytest

from orchestrator.investigar import (Dato, Investigador, _resultados_ddg, _texto_de_html,
                                     errores_de_datos)
from orchestrator.schemas.spec import Requisito, errores_de_requisitos

URL = "https://www.raspberrypi.com/documentation/pi4-mecanico"
PAGINA = ("Raspberry Pi 4 Model B. Mounting holes: 4 x M2.5, hole diameter 2.7 mm, "
          "on a 58 x 49 mm rectangle. Board size 85 x 56 mm.")


def _dato(**cambios):
    d = {"componente": "Raspberry Pi 4", "medida": "diámetro de los agujeros de montaje",
         "valor": 2.7, "unidad": "mm", "fuente": URL, "cita": "hole diameter 2.7 mm"}
    return Dato(**{**d, **cambios})


# --- la cita manda ---------------------------------------------------------------------

def test_un_dato_con_su_cita_en_la_pagina_vale():
    assert errores_de_datos([_dato()], {URL: PAGINA}) == []


def test_una_cita_que_no_esta_en_la_pagina_no_vale():
    errores = errores_de_datos([_dato(cita="hole diameter 3.2 mm")], {URL: PAGINA})
    assert len(errores) == 1 and "no está" in errores[0]


def test_el_valor_tiene_que_estar_en_la_cita():
    """«2.5» está en la página (M2.5), pero la cita dice 2.7: el modelo tomó
    el número de otro sitio."""
    errores = errores_de_datos([_dato(valor=2.5)], {URL: PAGINA})
    assert len(errores) == 1 and "2.5" in errores[0]


def test_la_coma_decimal_cuenta_como_punto():
    pagina = "Durchmesser der Bohrungen: 2,7 mm"
    assert errores_de_datos([_dato(cita="Bohrungen: 2,7 mm")], {URL: pagina}) == []


def test_una_fuente_que_no_se_leyo_no_vale():
    errores = errores_de_datos([_dato(fuente="https://otra.example/pi")], {URL: PAGINA})
    assert len(errores) == 1 and "no se leyó" in errores[0]


# --- buscar y leer ---------------------------------------------------------------------

DDG = """
<div class="result"><h2 class="result__title">
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.raspberrypi.com%2Fdocumentation%2F&amp;rut=abc">Raspberry Pi <b>Documentation</b></a>
</h2><a class="result__snippet" href="x">Mechanical drawings of the <b>Raspberry Pi 4</b></a></div>
<div class="result"><h2 class="result__title">
<a rel="nofollow" class="result__a" href="https://datasheets.example/pi4.pdf">Pi 4 datasheet</a>
</h2></div>
"""


def test_los_resultados_de_duckduckgo_salen_con_su_url_real():
    """DuckDuckGo envuelve el enlace en una redirección (`uddg=`): la URL que
    vale es la de dentro."""
    r = _resultados_ddg(DDG)
    assert [x.url for x in r] == ["https://www.raspberrypi.com/documentation/",
                                  "https://datasheets.example/pi4.pdf"]
    assert r[0].titulo == "Raspberry Pi Documentation"


def test_el_texto_de_una_pagina_sin_guiones_ni_estilos():
    html = ("<html><head><style>p{color:red}</style><script>var x = 99;</script></head>"
            "<body><p>Hole diameter</p><p>2.7&nbsp;mm</p></body></html>")
    texto = _texto_de_html(html)
    assert "Hole diameter" in texto and "2.7 mm" in texto
    assert "99" not in texto and "color" not in texto


# --- el investigador -------------------------------------------------------------------

class Guion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt, **_):
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


class BuscadorFalso:
    def __init__(self, paginas):
        self.paginas = paginas
        self.consultas = []

    def buscar(self, consulta, n=3):
        from orchestrator.investigar import Resultado
        self.consultas.append(consulta)
        return [Resultado(titulo="t", url=u) for u in self.paginas]

    def leer(self, url):
        return self.paginas[url]


FALTA_LA_PI = json.dumps({"faltan": [{
    "componente": "Raspberry Pi 5", "que_falta": ["agujeros de montaje"],
    "consulta": "Raspberry Pi 4 mechanical drawing mounting holes"}]})


def test_busca_lo_que_falta_y_lo_devuelve_citado():
    datos = json.dumps({"datos": [_dato().model_dump()], "sin_encontrar": []})
    buscador = BuscadorFalso({URL: PAGINA})
    r = Investigador(Guion([FALTA_LA_PI, datos]), buscador).investigar(
        "soporte para una Raspberry Pi 4 en un perfil 2020")
    assert buscador.consultas == ["Raspberry Pi 4 mechanical drawing mounting holes"]
    assert [d.valor for d in r.datos] == [2.7]
    assert URL in r.texto_para_concepto() and "calibre" in r.texto_para_concepto()


def test_una_cita_inventada_vuelve_al_modelo_con_el_error():
    inventada = json.dumps({"datos": [_dato(cita="hole diameter 3.2 mm").model_dump()],
                            "sin_encontrar": []})
    buena = json.dumps({"datos": [_dato().model_dump()], "sin_encontrar": []})
    guion = Guion([FALTA_LA_PI, inventada, buena])
    r = Investigador(guion, BuscadorFalso({URL: PAGINA})).investigar("soporte para una Pi 4")
    assert "no está" in guion.prompts[-1]
    assert [d.cita for d in r.datos] == ["hole diameter 2.7 mm"]


def test_si_no_falta_nada_no_busca():
    buscador = BuscadorFalso({URL: PAGINA})
    r = Investigador(Guion([json.dumps({"faltan": []})]), buscador).investigar(
        "una placa de 80 x 50 x 4 con 4 agujeros de 3.3 mm")
    assert buscador.consultas == [] and r.datos == [] and r.texto_para_peticion() == ""


def test_si_preguntan_por_unas_medidas_no_vale_decir_que_no_falta_nada():
    # Crafty preguntó «¿cuánto mide una tuerca M5?» y el modelo contestó
    # `faltan: []`, como si fuera una petición que ya trae sus medidas
    # (2026-11-04): la herramienta devolvió «No hizo falta buscar nada».
    datos = json.dumps({"datos": [_dato().model_dump()], "sin_encontrar": []})
    guion = Guion([json.dumps({"faltan": []}), FALTA_LA_PI, datos])
    buscador = BuscadorFalso({URL: PAGINA})
    r = Investigador(guion, buscador).medidas_de("Raspberry Pi 4")
    assert "pregunta" in guion.prompts[1]
    assert buscador.consultas == ["Raspberry Pi 4 mechanical drawing mounting holes"]
    assert [d.valor for d in r.datos] == [2.7]


def test_sin_internet_sigue_sin_datos_y_lo_dice():
    class SinRed(BuscadorFalso):
        def buscar(self, consulta, n=3):
            raise OSError("sin red")

    r = Investigador(Guion([FALTA_LA_PI]), SinRed({})).investigar("soporte para una Pi 4")
    assert r.datos == [] and "Raspberry Pi 5" in r.sin_encontrar[0]
    assert "sin red" in r.sin_encontrar[0]   # el porqué, no solo «no encontré»


# --- y entra como catálogo, no como palabra del usuario -------------------------------

def test_un_dato_buscado_cuenta_como_cota_pero_no_como_dicho_por_el_usuario():
    externos = "- Raspberry Pi 4, diámetro de los agujeros de montaje: 2.7 mm"
    usuario = Requisito(id="R1", tipo="agujero", texto="agujeros de montaje: 2.7 mm",
                        valor=2.7, origen="usuario")
    catalogo = usuario.model_copy(update={"origen": "catalogo"})
    peticion = "soporte para una Raspberry Pi 4"

    assert errores_de_requisitos([catalogo], peticion, externos) == []
    assert any("no está en la petición" in e
               for e in errores_de_requisitos([usuario], peticion, externos))
    # Y el dato buscado hay que cubrirlo: si no, nadie lo mide.
    assert any("2.7" in e for e in errores_de_requisitos([], peticion, externos))


def test_si_el_buscador_nos_bloquea_se_dice_y_no_parece_que_no_haya_nada():
    """Fallo real (2026-11-05): DuckDuckGo contestó 202 con su página
    antibots a cada búsqueda, el lector no encontraba resultados y el
    concepto decía «no encontré» de la Raspberry Pi 4, que está en todas
    partes. Un bloqueo es un error, no una búsqueda vacía."""
    import httpx

    from orchestrator.investigar import BuscadorBloqueado, BuscadorWeb

    antibots = '<html><body><form id="challenge-form">anomaly-modal</form></body></html>'
    cliente = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(202, text=antibots)))
    with pytest.raises(BuscadorBloqueado):
        BuscadorWeb(cliente).buscar("Raspberry Pi 4 mechanical drawing")


# --- el buscador de DeepSeek -----------------------------------------------------------

def _deepseek(respuestas, vistas):
    """Un DeepSeek de mentira con la forma de su API de búsqueda
    (api-docs.deepseek.com/guides/search)."""
    import httpx

    from orchestrator.investigar import BuscadorDeepSeek

    def responder(request):
        vistas.append((request.url.path, json.loads(request.content),
                       request.headers.get("authorization")))
        return respuestas[request.url.path](request)

    return BuscadorDeepSeek("sk-prueba", httpx.Client(transport=httpx.MockTransport(responder)))


def test_deepseek_busca_con_contenido_y_lo_lee_sin_otra_llamada():
    """DeepSeek busca desde su API con la clave que ya tenemos y devuelve el
    texto de cada página (`need_content`): leer lo encontrado no cuesta otra
    llamada. Lo propuso el usuario cuando DuckDuckGo nos bloqueó y no quería
    pagar otro servicio (2026-11-05)."""
    import httpx

    vistas = []
    resultados = {"results": [
        {"title": "Raspberry Pi 4 mechanical", "url": URL, "content": PAGINA, "summary": "s"},
        {"title": "Otra", "url": "https://otra.example/pi", "content": "", "summary": "resumen"}]}
    b = _deepseek({"/v1/tools/search": lambda r: httpx.Response(200, json=resultados)}, vistas)

    r = b.buscar("Raspberry Pi 4 mechanical drawing", n=3)

    assert [x.url for x in r] == [URL, "https://otra.example/pi"]
    ruta, cuerpo, clave = vistas[0]
    assert ruta == "/v1/tools/search" and clave == "Bearer sk-prueba"
    assert cuerpo["query"] == "Raspberry Pi 4 mechanical drawing"
    assert cuerpo["need_content"] is True
    assert b.leer(URL) == PAGINA and len(vistas) == 1


def test_deepseek_lee_con_su_api_lo_que_la_busqueda_no_trajo():
    import httpx

    vistas = []
    b = _deepseek({
        "/v1/tools/search": lambda r: httpx.Response(200, json={"results": [
            {"title": "t", "url": URL, "content": "", "summary": ""}]}),
        "/v1/tools/fetch": lambda r: httpx.Response(200, json={"title": "t", "content": PAGINA}),
    }, vistas)
    b.buscar("pi 4")
    assert b.leer(URL) == PAGINA
    assert vistas[-1][:2] == ("/v1/tools/fetch", {"url": URL})


def test_deepseek_sin_saldo_se_dice():
    import httpx

    from orchestrator.investigar import BuscadorBloqueado

    b = _deepseek({"/v1/tools/search": lambda r: httpx.Response(402, json={})}, [])
    with pytest.raises(BuscadorBloqueado, match="saldo"):
        b.buscar("pi 4")


def test_la_consulta_no_pasa_de_128_caracteres():
    """El límite de la API: más larga, la rechaza."""
    import httpx

    vistas = []
    b = _deepseek({"/v1/tools/search": lambda r: httpx.Response(200, json={"results": []})},
                  vistas)
    b.buscar("x" * 300)
    assert len(vistas[0][1]["query"]) == 128


def test_si_la_primera_busqueda_no_da_datos_prueba_las_otras():
    """Fallo real (2026-11-05): con «Raspberry Pi 4 mechanical drawing» las
    páginas solo enlazaban al plano en PDF, que es una imagen sin texto, y
    no salió ni una medida. Otra consulta da con páginas que sí las
    escriben."""
    falta = json.dumps({"faltan": [{
        "componente": "Raspberry Pi 5", "que_falta": ["agujeros de montaje"],
        "consulta": "Raspberry Pi 4 mechanical drawing",
        "otras_consultas": ["Raspberry Pi 4 mounting hole spacing mm"]}]})
    nada = json.dumps({"datos": [], "sin_encontrar": ["agujeros de montaje"]})
    algo = json.dumps({"datos": [_dato().model_dump()], "sin_encontrar": []})
    buscador = BuscadorFalso({URL: PAGINA})

    r = Investigador(Guion([falta, nada, algo]), buscador).investigar("soporte para una Pi 4")

    assert buscador.consultas == ["Raspberry Pi 4 mechanical drawing",
                                  "Raspberry Pi 4 mounting hole spacing mm"]
    assert [d.valor for d in r.datos] == [2.7] and r.sin_encontrar == []


def test_deepseek_se_queda_con_las_fuentes_de_mas_autoridad():
    """Fallo real (2026-11-05): las cotas de la Raspberry Pi 4 salieron de una
    oferta de trabajo de Upwork. La API puntúa la autoridad de cada fuente
    (0-4, -1 si no la sabe): se piden más resultados y se leen los mejores."""
    import httpx

    def r(url, autoridad):
        return {"title": url, "url": url, "content": "x", "authority": autoridad}

    vistas = []
    b = _deepseek({"/v1/tools/search": lambda q: httpx.Response(200, json={"results": [
        r("https://upwork.example", 1), r("https://foro.example", -1),
        r("https://raspberrypi.com", 4), r("https://tienda.example", 2),
        r("https://wiki.example", 3)]})}, vistas)

    urls = [x.url for x in b.buscar("pi 4", n=3)]

    assert urls == ["https://raspberrypi.com", "https://wiki.example", "https://tienda.example"]
    assert vistas[0][1]["count"] > 3


def test_lo_que_tiene_ficha_en_la_biblioteca_no_se_busca():
    """F6.11 (biblioteca): el HC-SR04 se diseñó con el PCB de 43 y el Ø8 de una
    tienda. Con ficha, sus medidas salen de ella y no se convierten en
    requisitos sueltos; lo demás se sigue buscando."""
    faltan = json.dumps({"faltan": [
        {"componente": "HC-SR04", "que_falta": ["medidas del PCB"], "consulta": "HC-SR04 size"},
        json.loads(FALTA_LA_PI)["faltan"][0]]})
    datos = json.dumps({"datos": [_dato().model_dump()], "sin_encontrar": []})
    buscador = BuscadorFalso({URL: PAGINA})
    r = Investigador(Guion([faltan, datos]), buscador).investigar(
        "soporte para un HC-SR04 y una Raspberry Pi 5")
    assert buscador.consultas == ["Raspberry Pi 4 mechanical drawing mounting holes"]
    assert r.de_la_biblioteca == ["hc-sr04"]
    assert "HC-SR04" not in r.texto_para_peticion()


def test_la_tornilleria_de_un_componente_con_ficha_no_se_busca():
    """Proyecto del 608ZZ (2026-11-06): la tuerca en T se buscó y sus cifras
    acabaron de requisitos de la pieza."""
    faltan = json.dumps({"faltan": [
        {"componente": "Tuerca en T de 2020 para M5", "que_falta": ["ancho", "espesor"],
         "consulta": "M5 T-nut 2020 dimensions"}]})
    buscador = BuscadorFalso({URL: PAGINA})
    r = Investigador(Guion([faltan]), buscador).investigar(
        "soporte atornillado a un perfil 2020 con tornillos M5")
    assert buscador.consultas == []
    assert r.de_la_biblioteca == ["perfil-2020"]
