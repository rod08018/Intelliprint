"""Los módulos impresos (F10.6 (módulo), ADR-021).

Un módulo son varias piezas que salen de una fórmula con parámetros —una
reductora, con su disco, su carcasa y su salida—, más lo que hay que comprar
para montarlas. No lo dibuja ningún modelo: el modelo diseña la estructura y
coloca el módulo como coloca un servo, con `kit.componente`.

Para el backlog es un componente más: tiene ficha (lo que ocupa, dónde se
atornilla, qué mueve) y va en `compra` de la pieza que lo aloja. Lo que lo
distingue aparece al contar: nadie lo compra. Sus piezas se imprimen y lo
suyo comprado se suma a la lista (`materiales`), y sus piezas se construyen
dentro del proyecto para que entren en el zip (`construir`).

Cada módulo de la biblioteca es un archivo en `library/modulos/<id>.yaml`
que dice con qué generador se hace y con qué parámetros. El generador es
código, registrado en `GENERADORES`.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

BIBLIOTECA = Path(__file__).resolve().parents[1] / "library" / "modulos"
CARPETA = "modulos"
"""Dentro de un proyecto, donde quedan construidas las piezas de sus módulos."""


@dataclass(frozen=True)
class Modulo:
    id: str
    ficha: dict
    """Los datos de su `Ficha`, con `origen: modulo`: lo que ocupa montado."""
    piezas: dict[str, str]
    """{nombre de la pieza: su programa del kit}."""
    compras: dict[str, int] = field(default_factory=dict)
    """{id de una ficha comprada: cuántos lleva}."""
    otros: dict[str, int] = field(default_factory=dict)
    """Lo comprado que no tiene ficha, por su nombre: «Pasador Ø4 × 20»."""


GENERADORES: dict[str, Callable[..., Modulo]] = {}
"""{nombre: función que, con los parámetros del archivo, da el módulo}."""


def _carpetas() -> list[Path]:
    """La biblioteca y, con `INTELLIPRINT_MODULOS`, más carpetas (los tests)."""
    extra = [Path(p) for p in os.environ.get("INTELLIPRINT_MODULOS", "").split(os.pathsep) if p]
    return [BIBLIOTECA, *extra]


def _archivo(id_: str) -> Path | None:
    for carpeta in _carpetas():
        if (carpeta / f"{id_}.yaml").is_file():
            return carpeta / f"{id_}.yaml"
    return None


def ids() -> list[str]:
    return sorted({p.stem for c in _carpetas() if c.is_dir() for p in c.glob("*.yaml")})


def es_modulo(id_: str) -> bool:
    return _archivo(id_) is not None


def holgura_medida(perfil: dict | None) -> float | None:
    """La holgura con la que giran las transmisiones en la impresora del
    usuario, si la apuntó (F10.8 (calibrar)); None si no."""
    return ((perfil or {}).get("fits") or {}).get("transmision_mm")


def cargar(id_: str, holgura: float | None = None) -> Modulo:
    """Con `holgura`, las piezas se hacen con esa y no con la de fábrica del
    generador: la ficha no cambia, lo que ocupa es lo mismo."""
    ruta = _archivo(id_)
    if ruta is None:
        raise KeyError(f"no hay módulo «{id_}»; hay: {', '.join(ids()) or 'ninguno'}")
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    generador = _generador(datos.get("generador"))
    if generador is None:
        raise KeyError(f"el módulo «{id_}» pide el generador «{datos.get('generador')}», que "
                       f"no existe; hay: {', '.join(sorted({*GENERADORES, 'cicloidal'}))}")
    parametros = dict(datos.get("parametros") or {})
    if holgura is not None:
        import inspect
        if "holgura" in inspect.signature(generador).parameters:
            parametros["holgura"] = holgura
    return generador(**parametros)


def _generador(nombre: str) -> Callable[..., Modulo] | None:
    """Los de casa se importan al pedirlos: `cicloidal` importa este módulo."""
    if nombre in GENERADORES:
        return GENERADORES[nombre]
    if nombre == "cicloidal":
        from orchestrator import cicloidal
        return cicloidal.generar
    return None


def de_un_proyecto(carpeta: Path) -> list[str]:
    """Los módulos que lleva el backlog de `carpeta`, por lo que su plan
    pone en `compra`, sin repetir."""
    from orchestrator import obra as O
    carpeta = Path(carpeta)
    if not O.es_obra(carpeta):
        return []
    return [i for i in dict.fromkeys(c for n in O.cargar_obra(carpeta).nodos for c in n.compra)
            if es_modulo(i)]


def piezas_construidas(carpeta: Path) -> list[Path]:
    """Las STL de los módulos de un proyecto que ya están construidas."""
    return sorted((Path(carpeta) / CARPETA).glob("*/*/*.stl"))


def construir(carpeta: Path, freecadcmd: str, perfil: dict) -> list[Path]:
    """Construye las piezas de los módulos del proyecto que falten, en
    `<proyecto>/modulos/<módulo>/<pieza>/`, y devuelve las STL nuevas. Son
    siempre las mismas para los mismos parámetros: se hacen una vez."""
    from orchestrator.build import build_part
    from orchestrator.schemas.programa import Programa
    carpeta = Path(carpeta)
    nuevas = []
    for id_ in de_un_proyecto(carpeta):
        for nombre, programa in cargar(id_, holgura_medida(perfil)).piezas.items():
            destino = carpeta / CARPETA / id_ / nombre
            if (destino / f"{nombre}.stl").is_file():
                continue
            build_part(Programa(part=nombre, codigo=programa), None, destino, freecadcmd,
                       perfil=perfil)
            nuevas.append(destino / f"{nombre}.stl")
    return nuevas
