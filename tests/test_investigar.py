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
    "componente": "Raspberry Pi 4", "que_falta": ["agujeros de montaje"],
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


def test_sin_internet_sigue_sin_datos_y_lo_dice():
    class SinRed(BuscadorFalso):
        def buscar(self, consulta, n=3):
            raise OSError("sin red")

    r = Investigador(Guion([FALTA_LA_PI]), SinRed({})).investigar("soporte para una Pi 4")
    assert r.datos == [] and "Raspberry Pi 4" in r.sin_encontrar[0]
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
