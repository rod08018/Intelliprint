"""Buscar en internet lo que la petición no dice (F3.21 (investigar)).

Va antes de los requisitos y del ingeniero, dentro de Intelliprint: así
sirve igual a quien pide desde la web que a quien pide por Telegram. Crafty
puede buscar por su cuenta, pero la web no tiene a nadie que lo haga.

Tres pasos, y solo el del medio no es del modelo:

1. El modelo dice qué componentes nombra la petición sin dar sus medidas, y
   con qué buscarlas.
2. El código busca (DuckDuckGo, sin clave) y lee las páginas.
3. El modelo saca los datos, cada uno con la URL y una cita LITERAL de la
   página. El código comprueba que la cita está y que el número está en la
   cita; si no, el error vuelve al modelo dentro del bucle de `structured`.

Fallo que lo motivó (2026-11-04): el soporte de la Raspberry Pi 4 salió con
el patrón de agujeros centrado en la placa, sacado de memoria. En la placa
real está a 3.5 mm de un extremo y a 23.5 del otro.
"""

import html as html_lib
import io
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import BaseModel

from orchestrator.llm.structured import LlmClient, structured

PROMPT_PATH = Path("config/agents/investigador.md")
SEPARADOR = "<!-- extraer -->"

MAX_RESULTADOS = 3
MAX_OTRAS = 2
"""Consultas de repuesto por componente, si la primera no da datos."""
MAX_CARACTERES = 12_000
"""Por página: un plano o una hoja de datos dice lo que importa al
principio, y tres páginas por componente caben en el contexto."""
ESPERA_S = 20.0
AGENTE = "Mozilla/5.0 (X11; Linux x86_64) Intelliprint/1.0"
"""Sin un User-Agent de navegador, DuckDuckGo y muchas webs contestan 403."""


# --- lo que el modelo devuelve ---------------------------------------------------------

class Faltante(BaseModel):
    componente: str
    que_falta: list[str]
    consulta: str
    """Lo que se escribe en el buscador, en inglés si la fuente buena es
    del fabricante («Raspberry Pi 4 mechanical drawing»)."""
    otras_consultas: list[str] = []
    """Por si la primera no da datos: con «Raspberry Pi 4 mechanical drawing»
    las páginas solo enlazaban al plano en PDF, una imagen sin texto, y no
    salió ni una medida (2026-11-05)."""


class Faltantes(BaseModel):
    faltan: list[Faltante] = []


class Dato(BaseModel):
    componente: str
    medida: str
    valor: float
    unidad: str = "mm"
    fuente: str
    cita: str
    """Fragmento LITERAL de la página en la que sale el valor."""

    def linea(self) -> str:
        return f"{self.componente}, {self.medida}: {self.valor:g} {self.unidad}"


class Datos(BaseModel):
    datos: list[Dato] = []
    sin_encontrar: list[str] = []


class Investigacion(BaseModel):
    datos: list[Dato] = []
    sin_encontrar: list[str] = []

    def texto_para_peticion(self) -> str:
        """Lo que reciben los requisitos, aparte de la petición: entra como
        `catalogo`, nunca como si lo hubiera dicho el usuario."""
        return "\n".join(f"- {d.linea()} (fuente: {d.fuente})" for d in self.datos)

    def texto_para_concepto(self) -> str:
        """Lo que la persona ve antes de aprobar: lo buscado se revisa ahí."""
        if not self.datos and not self.sin_encontrar:
            return ""
        lineas = ["**Datos buscados en internet** (compruébalos con un calibre antes de imprimir; "
                  "una hoja de datos puede no coincidir con tu unidad):"]
        lineas += [f"- {d.linea()}: «{d.cita}» ({d.fuente})" for d in self.datos]
        lineas += [f"- No encontré: {s}" for s in self.sin_encontrar]
        return "\n".join(lineas)


# --- la cita manda ---------------------------------------------------------------------

def _normal(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _numeros(texto: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", texto)]


def errores_de_datos(datos: list[Dato], paginas: dict[str, str]) -> list[str]:
    """Lo que el modelo no puede saltarse: un dato sin cita en la página que
    dice es un dato de memoria con una URL pegada."""
    errores = []
    for d in datos:
        if d.fuente not in paginas:
            errores.append(f"«{d.linea()}»: la fuente {d.fuente} no se leyó. Usa una de: "
                           + ", ".join(paginas))
            continue
        if _normal(d.cita) not in _normal(paginas[d.fuente]):
            errores.append(f"«{d.linea()}»: la cita «{d.cita}» no está en {d.fuente}. "
                           "Copia el fragmento tal cual o quita el dato.")
            continue
        if not any(abs(n - d.valor) < 1e-6 for n in _numeros(d.cita)):
            errores.append(f"«{d.linea()}»: {d.valor:g} no aparece en la cita «{d.cita}». "
                           "El número tiene que salir de la cita.")
    return errores


# --- buscar y leer ---------------------------------------------------------------------

class Resultado(BaseModel):
    titulo: str
    url: str


def _resultados_ddg(pagina: str) -> list[Resultado]:
    """Los enlaces de la página de resultados de DuckDuckGo (versión HTML).
    Vienen envueltos en una redirección (`/l/?uddg=`): vale la URL de dentro."""
    resultados = []
    for href, titulo in re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S):
        href = html_lib.unescape(href)
        destino = parse_qs(urlparse(href).query).get("uddg")
        url = unquote(destino[0]) if destino else href
        if url.startswith("//"):
            url = "https:" + url
        titulo = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", titulo))).strip()
        resultados.append(Resultado(titulo=titulo, url=url))
    return resultados


class _Texto(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._fuera = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._fuera += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._fuera:
            self._fuera -= 1

    def handle_data(self, data):
        if not self._fuera:
            self.partes.append(data)


def _texto_de_html(pagina: str) -> str:
    p = _Texto()
    p.feed(pagina)
    return re.sub(r"\s+", " ", " ".join(p.partes).replace("\xa0", " ")).strip()


class BuscadorBloqueado(RuntimeError):
    """El buscador contestó con su página antibots. No se intenta saltar:
    hace falta un buscador con API."""


class BuscadorDeepSeek:
    """La búsqueda de la API de DeepSeek (api-docs.deepseek.com/guides/search),
    con la clave que ya usan los agentes: ningún servicio ni cuenta más, y
    0.75 USD por cada 1000 búsquedas que devuelven algo. La propuso el
    usuario cuando DuckDuckGo nos bloqueó y no quería pagar otro servicio
    (2026-11-05).

    Con `need_content` cada resultado trae el texto de su página: leer lo
    encontrado no cuesta otra llamada. Lo que no lo trae se lee con su API
    de lectura, que devuelve Markdown."""

    BASE = "https://api.deepseek.com/v1/tools"
    MAX_CONSULTA = 128
    """Lo más larga que la API admite una consulta."""

    def __init__(self, api_key: str, cliente=None) -> None:
        import httpx

        self._http = cliente or httpx.Client(timeout=60.0)
        self._cabeceras = {"Authorization": f"Bearer {api_key}"}
        self._contenido: dict[str, str] = {}

    def _pedir(self, ruta: str, cuerpo: dict) -> dict:
        r = self._http.post(f"{self.BASE}/{ruta}", json=cuerpo, headers=self._cabeceras)
        if r.status_code == 402:
            raise BuscadorBloqueado("la cuenta de DeepSeek no tiene saldo")
        r.raise_for_status()
        return r.json()

    def buscar(self, consulta: str, n: int = MAX_RESULTADOS) -> list[Resultado]:
        # Se piden de más y se leen los de más autoridad: las cotas de la
        # Raspberry Pi 4 salieron de una oferta de Upwork (2026-11-05). La API
        # puntúa la fuente de 0 a 4 (-1 si no lo sabe). El orden es estable:
        # a igual autoridad, el de la API.
        datos = self._pedir("search", {"query": consulta[:self.MAX_CONSULTA], "count": 2 * n,
                                       "need_content": True})
        crudos = sorted(datos.get("results") or [],
                        key=lambda x: -(x.get("authority") if x.get("authority") is not None
                                        else -1))
        resultados = []
        for x in crudos:
            if len(resultados) == n:
                break
            if not x.get("url"):
                continue
            if x.get("content"):
                self._contenido[x["url"]] = x["content"]
            resultados.append(Resultado(titulo=x.get("title") or "", url=x["url"]))
        return resultados

    def leer(self, url: str) -> str:
        texto = self._contenido.get(url) or self._pedir("fetch", {"url": url}).get("content", "")
        return texto[:MAX_CARACTERES]


class BuscadorWeb:
    """DuckDuckGo en su versión HTML, sin clave: la misma elección que Crafty
    (OpenClaw no trae otro buscador sin cuenta en la versión fijada).

    Desde el contenedor DuckDuckGo contesta 202 con su página antibots
    (2026-11-05): queda como respaldo, y el bloqueo se dice."""

    def __init__(self, cliente=None) -> None:
        import httpx

        self._http = cliente or httpx.Client(timeout=ESPERA_S, follow_redirects=True,
                                             headers={"User-Agent": AGENTE})

    def buscar(self, consulta: str, n: int = MAX_RESULTADOS) -> list[Resultado]:
        r = self._http.post("https://html.duckduckgo.com/html/", data={"q": consulta})
        r.raise_for_status()
        resultados = _resultados_ddg(r.text)
        # Fallo real (2026-11-05): 202 y la página antibots a cada búsqueda.
        # Sin esto salía «no encontré» de la Raspberry Pi 4.
        if not resultados and (r.status_code == 202 or "anomaly" in r.text):
            raise BuscadorBloqueado("DuckDuckGo contestó con su página antibots")
        return resultados[:n]

    def leer(self, url: str) -> str:
        r = self._http.get(url)
        r.raise_for_status()
        tipo = r.headers.get("content-type", "")
        if "pdf" in tipo or url.lower().endswith(".pdf"):
            from pypdf import PdfReader

            texto = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
            return re.sub(r"\s+", " ", texto).strip()[:MAX_CARACTERES]
        return _texto_de_html(r.text)[:MAX_CARACTERES]


# --- el investigador -------------------------------------------------------------------

class Investigador:
    def __init__(self, client: LlmClient, buscador, prompt_path: Path = PROMPT_PATH,
                 log=print) -> None:
        self._client = client
        self._buscador = buscador
        texto = prompt_path.read_text(encoding="utf-8")
        self._que_falta, _, self._extraer = texto.partition(SEPARADOR)
        self._log = log

    def investigar(self, peticion: str) -> Investigacion:
        faltan = structured(self._client, f"{self._que_falta}\n## Petición\n\n{peticion}",
                            Faltantes).faltan
        resultado = Investigacion()
        for f in faltan:
            # Con el porqué: «no encontré» de la Raspberry Pi 4 parecía que no
            # existiera, y era el buscador bloqueado (2026-11-05).
            pendiente = [f"{f.componente} ({', '.join(f.que_falta)})"]
            for consulta in [f.consulta, *f.otras_consultas[:MAX_OTRAS]]:
                self._log(f"  investigación: busco «{consulta}»…")
                self._motivo = "ninguna página se dejó leer"
                paginas = self._leer(consulta)
                if not paginas:
                    pendiente = [f"{f.componente} ({', '.join(f.que_falta)}): {self._motivo}"]
                    continue
                datos = self._extraer_de(f, paginas)
                pendiente = datos.sin_encontrar
                if datos.datos:
                    resultado.datos += datos.datos
                    break
            resultado.sin_encontrar += pendiente
        return resultado

    def _extraer_de(self, f: Faltante, paginas: dict[str, str]) -> Datos:
        fuentes = "\n\n".join(f"### {url}\n\n{texto}" for url, texto in paginas.items())
        return structured(
            self._client,
            f"{self._extraer}\n## Componente\n\n{f.componente}: {', '.join(f.que_falta)}"
            f"\n\n## Páginas\n\n{fuentes}",
            Datos,
            extra_validation=lambda d: _rechazar(errores_de_datos(d.datos, paginas)))

    def _leer(self, consulta: str) -> dict[str, str]:
        """Las páginas que se dejan leer; una caída o un 403 no paran nada."""
        try:
            resultados = self._buscador.buscar(consulta)
        except Exception as e:   # sin red, o el buscador cambió su página
            self._log(f"  investigación: no pude buscar ({type(e).__name__}: {e})")
            self._motivo = f"no pude buscar ({e})"
            return {}
        if not resultados:
            self._motivo = "el buscador no devolvió nada"
        paginas = {}
        for r in resultados:
            try:
                texto = self._buscador.leer(r.url)
            except Exception as e:
                self._log(f"  investigación: no pude leer {r.url} ({type(e).__name__})")
                continue
            if texto.strip():
                paginas[r.url] = texto
        return paginas


def _rechazar(errores: list[str]) -> None:
    if errores:
        raise ValueError("datos sin respaldo en las páginas:\n- " + "\n- ".join(errores))
