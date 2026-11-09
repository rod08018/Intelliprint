"""Proyectos por partes («obras», F7).

Un proyecto grande se diseña pieza a pieza, y cada pieza terminada se
convierte en una ficha (F7.1 (fichar)): la siguiente se diseña contra ella
con la misma maquinaria que contra un 608ZZ comprado. Así ninguna pieza se
pide de golpe junto con las demás, que es donde se murieron los mecanismos
grandes (la Ginebra, 2026-09-20: el razonador se cortó tres veces).
"""

import json
import shutil
from pathlib import Path

import yaml

from orchestrator.componentes import Ficha

_EJES = {(1, 0, 0): "+x", (-1, 0, 0): "-x", (0, 1, 0): "+y", (0, -1, 0): "-y",
         (0, 0, 1): "+z", (0, 0, -1): "-z"}


def _step_de(carpeta: Path) -> Path:
    propio = carpeta / f"{carpeta.name}.step"
    if propio.is_file():
        return propio
    steps = sorted(carpeta.glob("*.step"))
    if len(steps) != 1:
        raise ValueError(f"{carpeta}: no sé qué STEP fichar ({len(steps)} encontrados)")
    return steps[0]


def _agujeros(rasgos: list[dict]) -> list[dict]:
    """Los agujeros con nombre de la pieza, en su marco: con ellos la pieza
    siguiente se atornilla a esta con `componente.punto(nombre)`. Solo los
    de eje alineado, que son los que una ficha sabe girar."""
    salida = []
    for r in rasgos:
        if r.get("tipo") != "agujero" or not r.get("diametro_mm"):
            continue
        eje = _EJES.get(tuple(round(c) for c in r["eje"]))
        if eje is None or any(abs(c - round(c)) > 1e-6 for c in r["eje"]):
            continue
        salida.append({"nombre": r["nombre"], "diametro": float(r["diametro_mm"]),
                       "en": [round(float(c), 6) for c in r["entrada"]], "eje": eje})
    return salida


def fichar(carpeta: Path, id_: str, nombre: str, destino: Path, proyecto: str = "") -> Path:
    """La ficha de la pieza construida en `carpeta` (`parts/<pieza>/`), en
    `destino/<id_>.yaml`, con una copia de su STEP al lado. Es su forma
    CONSTRUIDA y sus agujeros con nombre, no lo que el programa dijo hacer:
    medir contra ella no es el etiquetado circular de la ADR-011."""
    carpeta, destino = Path(carpeta), Path(destino)
    envolvente = carpeta / "envolvente.json"
    if not envolvente.is_file():
        raise ValueError(f"{carpeta}: falta envolvente.json; vuelve a construir la pieza")
    caja = json.loads(envolvente.read_text(encoding="utf-8"))
    rasgos = (json.loads((carpeta / "rasgos.json").read_text(encoding="utf-8"))
              if (carpeta / "rasgos.json").is_file() else [])
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_step_de(carpeta), destino / f"{id_}.step")
    datos = {
        "id": id_, "nombre": nombre, "origen": "impreso", "proyecto": proyecto,
        "verificado": False,
        "fuentes": [{"url": f"proyecto {proyecto or carpeta.name}",
                     "cita": f"construida por Intelliprint ({carpeta.name})"}],
        "marco": "El de la pieza construida: el mismo origen y los mismos ejes que su programa.",
        "mira": "+z",
        "cuerpos": [{"nombre": nombre, "en": [0, 0, 0],
                     "step": {"ruta": f"{id_}.step", "min": caja["min"], "max": caja["max"]}}],
        "fijacion": _agujeros(rasgos),
    }
    Ficha(**datos)   # que no se guarde una ficha que luego no carga
    ruta = destino / f"{id_}.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ruta
