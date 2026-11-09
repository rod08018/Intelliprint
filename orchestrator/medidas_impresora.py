"""Lo que el usuario midió en su impresora, con las fotos (F2.21 (impresora)).

`config/printers/` trae valores por defecto: holguras de una boquilla de 0.4
y una resistencia estimada, sin ensayar. El usuario configura y calibra su
impresora él mismo (2026-11-09), imprime las pruebas y apunta lo que midió.
Eso vive aquí, en `workspace/impresoras/<perfil>/`, y manda sobre el perfil:

- **tolerancias**: lo que encajó en la pieza de F2.18 (calibración);
- **resistencia**: con cuánto rompió la barra de flexión, tumbada (`xy`) o
  de pie (`z`), convertido a MPa con el cálculo del voladizo;
- **referencia**: una prueba suya (Printables u otra), con foto y nota.
  No cambia ningún número: no sabemos qué mide.

Los números los escribe la persona. Una foto no enseña si un eje entra
justo o con juego: es la evidencia de lo apuntado, no la medida.

Nada se borra: cada medida se añade al historial y manda la última de su
tipo. La anterior explica por qué se cambió.

¿Por qué no en `config/`? Dentro del contenedor es de solo lectura, a
propósito (ADR-014), y apuntar las holguras solo se podía hacer desde el PC.
"""

import copy
import datetime as dt
import os
import re
from pathlib import Path

import yaml

from orchestrator.calibracion import CalibracionInvalida, mpa_de_barra, validar_holguras

TIPOS = ("tolerancias", "resistencia", "referencia")
MAX_FOTOS = 8
MAX_MB = 10
# Por la cabecera, no por el nombre: el nombre lo pone el navegador.
_FIRMAS = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"))
_HOLGURAS = ("press_mm", "slide_mm", "clearance_mm",
             "m3_through_mm", "m3_selftap_mm", "m3_insert_mm")
# De la clave apuntada a dónde va en el perfil.
_EN_EL_PERFIL = {"press_mm": ("fits", "press_mm"), "slide_mm": ("fits", "slide_mm"),
                 "clearance_mm": ("fits", "clearance_mm"),
                 "m3_through_mm": ("holes", "M3_through_mm"),
                 "m3_selftap_mm": ("holes", "M3_selftap_mm"),
                 "m3_insert_mm": ("holes", "M3_insert_mm")}


class MedidaInvalida(ValueError):
    """Lo apuntado no puede ser una medida: no se guarda nada."""


def carpeta(workspace: Path, perfil: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", perfil):
        raise MedidaInvalida(f"{perfil!r} no es el nombre de un perfil")
    return Path(workspace) / "impresoras" / perfil


def registros(workspace: Path, perfil: str) -> list[dict]:
    ruta = carpeta(workspace, perfil) / "medidas.yaml"
    if not ruta.is_file():
        return []
    return (yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}).get("registros", [])


def _numero(valor, que: str) -> float:
    if isinstance(valor, bool):
        raise MedidaInvalida(f"{que}: {valor!r} no es un número")
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise MedidaInvalida(f"{que}: {valor!r} no es un número")


def _validar(tipo: str, valores: dict) -> dict:
    if tipo == "tolerancias":
        limpios = {k: _numero(valores.get(k), k) for k in _HOLGURAS}
        try:
            validar_holguras(**limpios)
        except CalibracionInvalida as e:
            raise MedidaInvalida(str(e))
        return limpios
    if tipo == "resistencia":
        orientacion = valores.get("orientacion")
        if orientacion not in ("xy", "z"):
            raise MedidaInvalida(
                f"orientación {orientacion!r}: tiene que ser «xy» (tumbada) o «z» (de pie)")
        carga = _numero(valores.get("carga_kg"), "carga_kg")
        if not 0 < carga < 200:
            raise MedidaInvalida(f"carga_kg: {carga} kg no es un peso con el que rompa una barra")
        return {"orientacion": orientacion, "carga_kg": carga,
                "MPa": round(mpa_de_barra(carga), 2)}
    if tipo == "referencia":
        titulo = str(valores.get("titulo") or "").strip()
        if not titulo:
            raise MedidaInvalida("una prueba tuya necesita un título que diga qué es")
        return {"titulo": titulo[:120]}
    raise MedidaInvalida(f"{tipo!r} no es ningún tipo de medida: {list(TIPOS)}")


def _extension(nombre: str, datos: bytes) -> str:
    if len(datos) > MAX_MB * 1_000_000:
        raise MedidaInvalida(f"la foto {nombre!r} pasa de {MAX_MB} MB")
    for firma, extension in _FIRMAS:
        if datos.startswith(firma):
            return extension
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return ".webp"
    raise MedidaInvalida(f"{nombre!r} no es una foto JPEG, PNG ni WebP")


def registrar(workspace: Path, perfil: str, tipo: str, valores: dict,
              fotos: list[tuple[str, bytes]], fecha: str | None = None,
              nota: str = "") -> dict:
    """Valida todo y, solo si todo vale, guarda las fotos y añade el registro.
    `fotos`: (nombre que trajo el navegador, bytes). El nombre solo se usa
    en los mensajes: el del archivo lo pone esta función."""
    destino = carpeta(workspace, perfil)
    limpios = _validar(tipo, valores)
    if len(fotos) > MAX_FOTOS:
        raise MedidaInvalida(f"como mucho {MAX_FOTOS} fotos por medida")
    extensiones = [_extension(nombre, datos) for nombre, datos in fotos]
    fecha = fecha or dt.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise MedidaInvalida(f"{fecha!r} no es una fecha AAAA-MM-DD")

    previos = registros(workspace, perfil)
    numero = len(previos) + 1
    (destino / "fotos").mkdir(parents=True, exist_ok=True)
    nombres = []
    for i, ((_, datos), extension) in enumerate(zip(fotos, extensiones), 1):
        nombre = f"{fecha}-{numero:03d}-{i}{extension}"
        (destino / "fotos" / nombre).write_bytes(datos)
        nombres.append(nombre)
    registro = {"numero": numero, "fecha": fecha, "tipo": tipo, "valores": limpios,
                "nota": str(nota or "").strip()[:1000], "fotos": nombres}
    # Se escribe aparte y se cambia de golpe: un corte a medias no deja
    # el historial roto.
    temporal = destino / "medidas.yaml.tmp"
    temporal.write_text(yaml.safe_dump({"perfil": perfil, "registros": [*previos, registro]},
                                       allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.replace(temporal, destino / "medidas.yaml")
    return registro


def vigentes(workspace: Path, perfil: str) -> dict[str, dict]:
    """La última medida de cada cosa: `tolerancias`, `resistencia_xy`, `resistencia_z`."""
    ultimas: dict[str, dict] = {}
    for r in registros(workspace, perfil):
        if r["tipo"] == "tolerancias":
            ultimas["tolerancias"] = r
        elif r["tipo"] == "resistencia":
            ultimas[f"resistencia_{r['valores']['orientacion']}"] = r
    return ultimas


def aplicar(datos: dict, workspace: Path, perfil: str) -> tuple[dict, dict[str, dict]]:
    """El YAML de la impresora con lo medido encima, y de qué registro sale
    cada valor cambiado (clave del perfil → registro)."""
    datos = copy.deepcopy(datos)
    origen: dict[str, dict] = {}
    ultimas = vigentes(workspace, perfil)
    if "tolerancias" in ultimas:
        r = ultimas["tolerancias"]
        for clave, (seccion, destino) in _EN_EL_PERFIL.items():
            datos.setdefault(seccion, {})[destino] = r["valores"][clave]
            origen[f"{seccion}.{destino}"] = r
        datos["calibrated"] = True
    for orientacion in ("xy", "z"):
        r = ultimas.get(f"resistencia_{orientacion}")
        if r:
            datos.setdefault("resistencia", {})[f"{orientacion}_MPa"] = r["valores"]["MPa"]
            origen[f"resistencia.{orientacion}_MPa"] = r
    return datos, origen
