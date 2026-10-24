"""Importar una calibración de eufyMake Studio a un perfil plano de
PrusaSlicer (F1.12 (laminado)).

El usuario calibra su M5 en eufyMake Studio, que es un PrusaSlicer
modificado. Su paquete de configuración (`Archivo → Exportar → Paquete de
configuración`) trae varios perfiles de impresión, de filamento y de
impresora, y claves que PrusaSlicer no entiende. Aquí se elige un trío, se
aplana en un solo .ini y se deja escrito qué se perdió por el camino: eso
es lo que puede hacer que una pieza no salga igual que en eufyMake.

Se ejecuta en el PC, no en el contenedor: `config/` está montado ahí en
solo lectura.

    python -m orchestrator.perfiles_laminado <paquete.ini> \\
        --impresion Precision --filamento "esun pla+" --salida <nombre>.ini
"""

import argparse
import configparser
import datetime as dt
import shutil
from pathlib import Path

CLAVES_PRUSASLICER = Path(__file__).resolve().parent.parent / "config" / "slicing" / "claves_prusaslicer.txt"

FUERA = {"inherits", "host_type", "print_host", "printhost_apikey", "printhost_cafile",
         "printhost_password", "printhost_user", "printhost_port"}
"""Claves que PrusaSlicer entiende pero que no deben viajar en un perfil
plano. `inherits`: no hay preset del que heredar. Las del host: son de la
máquina de cada uno, y `ankerlink` ni es un valor válido en PrusaSlicer."""

SECRETAS = ("printhost_apikey", "printhost_password")


class PresetDesconocido(KeyError):
    """El paquete no tiene un preset con ese nombre."""


class PaqueteInseguro(ValueError):
    """El paquete lleva una clave o contraseña: no se guarda en el repo."""


def leer_paquete(ruta: Path) -> configparser.RawConfigParser:
    # Sin interpolación («20%» es un valor, no una referencia) y respetando
    # mayúsculas (eufyMake tiene `overhangPerimeters_flow_ratio`).
    paquete = configparser.RawConfigParser(strict=False, interpolation=None)
    paquete.optionxform = str
    paquete.read(ruta, encoding="utf-8")
    return paquete


def claves_conocidas(ruta: Path = CLAVES_PRUSASLICER) -> set[str]:
    """Lo que PrusaSlicer guardó al cargar el paquete real: si no lo guarda,
    no lo entiende. Más fiable que `--help-fff`, que omite claves que sí
    acepta (`layer_gcode`, `idle_temperature`…)."""
    return {l.strip() for l in Path(ruta).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


def _seccion(paquete, tipo: str, nombre: str) -> dict[str, str]:
    seccion = f"{tipo}:{nombre}"
    if not paquete.has_section(seccion):
        hay = sorted(s.split(":", 1)[1] for s in paquete.sections() if s.startswith(tipo + ":"))
        raise PresetDesconocido(f"el paquete no tiene el {tipo} «{nombre}». Tiene: {hay}")
    return dict(paquete[seccion])


def aplanar(paquete, impresion: str, filamento: str, impresora: str,
            conocidas: set[str] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """El trío mezclado como lo junta PrusaSlicer, y lo que se quitó.

    Devuelve (plano, descartadas). En `descartadas` solo va lo que tenía
    valor: `nil` y vacío en eufyMake no fijan nada, y anotarlos haría creer
    que se pierde algo."""
    conocidas = claves_conocidas() if conocidas is None else conocidas
    junto: dict[str, str] = {}
    for tipo, nombre in (("printer", impresora), ("print", impresion), ("filament", filamento)):
        junto.update(_seccion(paquete, tipo, nombre))
    plano = {k: v for k, v in junto.items() if k in conocidas and k not in FUERA}
    descartadas = {k: v for k, v in junto.items()
                   if k not in conocidas and v not in ("nil", "")}
    return plano, descartadas


def escribir_ini(plano: dict[str, str], destino: Path, *, origen: str, trio: dict[str, str],
                 descartadas: dict[str, str]) -> Path:
    cabecera = [
        "Perfil de laminado de PrusaSlicer, importado de una calibración del usuario.",
        "Tarea F1.12 (laminado). Distinto de config/printers/*.yaml, que son HOLGURAS.",
        "",
        f"ORIGEN: {origen} (eufyMake Studio), importado el {dt.date.today().isoformat()}",
        f"  impresora: {trio['impresora']}",
        f"  impresión: {trio['impresion']}",
        f"  filamento: {trio['filamento']}",
        "Regenerar: python -m orchestrator.perfiles_laminado (ver su docstring).",
        "",
        "SIN VERIFICAR con un G-code de PrusaSlicer. La calibración se hizo",
        "imprimiendo con eufyMake Studio; PrusaSlicer no entiende las claves de",
        "abajo y las ignora, así que la pieza puede no salir igual. Pasa a",
        "verificado cuando una impresión hecha con ESTE perfil salga bien.",
        "",
        f"Claves de eufyMake que PrusaSlicer no entiende ({len(descartadas)}):",
        *(f"  {k} = {v}" for k, v in sorted(descartadas.items())),
    ]
    lineas = [("# " + l).rstrip() for l in cabecera] + [""]
    lineas += [f"{k} = {v}" for k, v in sorted(plano.items())]
    Path(destino).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return Path(destino)


def guardar_origen(ruta: Path, carpeta: Path, nombre: str | None = None) -> Path:
    """Copia el paquete original para poder regenerar el perfil. Si lleva
    la clave o la contraseña del host de la impresora, no se copia: el
    repositorio no es sitio para eso."""
    paquete = leer_paquete(ruta)
    for seccion in paquete.sections():
        for clave in SECRETAS:
            if paquete[seccion].get(clave, "").strip():
                raise PaqueteInseguro(
                    f"[{seccion}] trae {clave}: bórrala en eufyMake y vuelve a exportar")
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(ruta, Path(carpeta) / (nombre or Path(ruta).name)))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("paquete", type=Path)
    p.add_argument("--impresion", required=True)
    p.add_argument("--filamento", required=True)
    p.add_argument("--impresora", help="por defecto, la del [presets] del paquete")
    p.add_argument("--salida", required=True, help="nombre del .ini en config/slicing/")
    args = p.parse_args(argv)

    paquete = leer_paquete(args.paquete)
    trio = {"impresion": args.impresion, "filamento": args.filamento,
            "impresora": args.impresora or paquete.get("presets", "printer")}
    plano, descartadas = aplanar(paquete, **trio)
    slicing = CLAVES_PRUSASLICER.parent
    copia = guardar_origen(args.paquete, slicing / "origen",
                           nombre=Path(args.salida).stem + ".paquete_eufymake.ini")
    destino = escribir_ini(plano, slicing / args.salida, origen=f"config/slicing/origen/{copia.name}",
                           trio=trio, descartadas=descartadas)
    print(f"{destino}: {len(plano)} claves; {len(descartadas)} de eufyMake sin equivalente")


if __name__ == "__main__":
    main()
