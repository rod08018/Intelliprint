"""Referencias para el diseñador: imágenes, textos y diseños que ya
funcionaron (F5.2 (adjuntos)).

Opcionales. Llegan por Telegram a Crafty o por la línea de órdenes, y el
Mechanism Designer las recibe junto a la petición. Adaptar algo que ya
funciona es mucho más fácil que inventarlo, y una foto dice de un trinquete
lo que no dicen tres párrafos.

Una referencia puede ser:

- una **imagen** (foto, boceto, captura): la ve el modelo, que acepta
  imágenes (comprobado el 2026-09-21 con deepseek-flash);
- un **texto** (.md, .txt, .json): notas, medidas, un diseño exportado;
- el **id de un proyecto** del workspace: entra su diseño y su petición.

La ruta la escribe un modelo a partir de lo que llegó por Telegram: es texto
ajeno. Sin límites, bastaría pedir /proc/self/environ para que la clave de
DeepSeek acabara dentro de un prompt. Por eso solo se acepta lo que está
dentro de carpetas permitidas, con un tipo conocido y un tamaño acotado, y
cada imagen se comprueba abriéndola de verdad.
"""

import base64
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

IMAGENES = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}
TEXTOS = {".md", ".txt", ".json"}
MAX_BYTES = 12 * 1024 * 1024
MAX_TEXTO = 60_000
LADO_MAXIMO = 1024
"""Una foto del móvil trae 4000 píxeles; para ver cómo es un mecanismo
sobran. Cada píxel de más son tokens que se pagan en cada ronda."""


class ReferenciaInvalida(ValueError):
    """Una referencia que no se puede o no se debe cargar."""


@dataclass
class Referencias:
    imagenes: list[str] = field(default_factory=list)
    """data URLs, listas para mandar al modelo."""
    textos: list[tuple[str, str]] = field(default_factory=list)
    """(de dónde viene, contenido)."""
    _originales: list[tuple[str, bytes]] = field(default_factory=list, repr=False)

    def __bool__(self) -> bool:
        return bool(self.imagenes or self.textos)

    def guardar(self, carpeta: Path) -> None:
        """Una copia dentro del proyecto: saber con qué referencias se
        diseñó es parte de por qué salió como salió."""
        if not self:
            return
        destino = Path(carpeta) / "referencias"
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, datos in self._originales:
            (destino / nombre).write_bytes(datos)
        for i, (titulo, contenido) in enumerate(self.textos, 1):
            (destino / f"texto_{i}.md").write_text(f"# {titulo}\n\n{contenido}\n", encoding="utf-8")


def _dentro(ruta: Path, raices: list[Path]) -> Path:
    real = ruta.resolve()
    if not any(real.is_relative_to(Path(r).resolve()) for r in raices):
        raise ReferenciaInvalida(
            f"{ruta} está fuera de las carpetas de las que se aceptan referencias")
    return real


def _imagen(real: Path) -> tuple[str, bytes]:
    from PIL import Image, UnidentifiedImageError

    datos = real.read_bytes()
    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()
    except (UnidentifiedImageError, OSError):
        raise ReferenciaInvalida(f"{real.name} dice ser una imagen y no se puede abrir como imagen")
    imagen = imagen.convert("RGB")
    imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(salida.getvalue()).decode(), datos


def _proyecto(nombre: str, proyectos: list[Path]) -> tuple[str, str] | None:
    """El diseño y la petición de un proyecto del workspace, por su id."""
    if not nombre or "/" in nombre or "\\" in nombre or nombre.startswith("."):
        return None
    for base in proyectos:
        carpeta = Path(base) / nombre
        diseno = carpeta / "mechanism.json"
        if carpeta.is_dir() and diseno.is_file():
            peticion = (carpeta / "request.md").read_text(encoding="utf-8").strip() \
                if (carpeta / "request.md").is_file() else ""
            rondas = json.loads((carpeta / "rounds.json").read_text(encoding="utf-8")) \
                if (carpeta / "rounds.json").is_file() else []
            salio = bool(rondas) and not rondas[-1].get("feedback")
            estado = ("salió: sin fallos en su última ronda" if salio
                      else "NO llegó a salir entero: úsalo como idea, no como modelo")
            return (f"proyecto {nombre} ({estado})",
                    f"Petición:\n{peticion}\n\nDiseño:\n{diseno.read_text(encoding='utf-8')}")
    return None


def cargar_referencias(entradas: list[str], *, raices: list[Path],
                       proyectos: list[Path]) -> Referencias:
    refs = Referencias()
    for entrada in entradas:
        entrada = (entrada or "").strip()
        if not entrada:
            continue
        de_proyecto = _proyecto(entrada, proyectos)
        if de_proyecto is not None:
            refs.textos.append(de_proyecto)
            continue
        ruta = Path(entrada)
        if not ruta.is_absolute() and len(ruta.parts) == 1 and ruta.suffix == "":
            raise ReferenciaInvalida(f"no hay ningún proyecto llamado «{entrada}»")
        real = _dentro(ruta if ruta.is_absolute() else Path(raices[0]) / ruta, raices)
        if not real.is_file():
            raise ReferenciaInvalida(f"no encuentro {entrada}")
        if real.stat().st_size > MAX_BYTES:
            raise ReferenciaInvalida(f"{real.name} pesa demasiado (máximo {MAX_BYTES // 2**20} MB)")
        extension = real.suffix.lower()
        if extension in IMAGENES:
            url, original = _imagen(real)
            refs.imagenes.append(url)
            refs._originales.append((f"imagen_{len(refs.imagenes)}{extension}", original))
        elif extension in TEXTOS:
            refs.textos.append((real.name, real.read_text(encoding="utf-8", errors="replace")[:MAX_TEXTO]))
        else:
            validos = ", ".join(sorted(e.strip(".") for e in (*IMAGENES, *TEXTOS)))
            raise ReferenciaInvalida(
                f"{real.name}: no sé usar ese tipo como referencia. Valen: {validos}, o el id "
                "de un proyecto que ya salió")
    return refs



def desde_el_entorno(entradas: list[str], workspace: Path, env) -> Referencias:
    """Carga con las carpetas permitidas de ESTA instalación: el workspace y
    las de `INTELLIPRINT_RAICES_REFERENCIAS` (en Docker, el estado de Crafty,
    donde OpenClaw guarda lo que llega por Telegram). Un solo sitio decide
    qué carpetas valen, para que la línea de órdenes y el MCP no discrepen."""
    extra = [Path(p) for p in (env.get("INTELLIPRINT_RAICES_REFERENCIAS") or "").split(os.pathsep) if p]
    workspace = Path(workspace)
    return cargar_referencias([_traducir(e, env) for e in entradas], raices=[workspace, *extra],
                              proyectos=[workspace / "projects", workspace / "archivo"])


def _traducir(entrada: str, env) -> str:
    """`INTELLIPRINT_ALIAS_REFERENCIAS=/ruta/de/crafty=/ruta/aqui`: Crafty
    pasa las rutas como las ve él, y aquí su estado está montado en otro
    sitio. Montarlo en la misma ruta y en solo lectura impedía montar el
    buzón dentro, y el contenedor no arrancaba (fallo real, 2026-09-21).

    Solo cambia el prefijo: lo que resulte se comprueba igual contra las
    raíces permitidas, así que un «..» no abre nada nuevo."""
    alias = env.get("INTELLIPRINT_ALIAS_REFERENCIAS") or ""
    if "=" not in alias:
        return entrada
    de, a = alias.split("=", 1)
    de = de.rstrip("/")
    if entrada == de or entrada.startswith(de + "/"):
        return a.rstrip("/") + entrada[len(de):]
    return entrada
