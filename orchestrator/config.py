"""Configuración de entorno."""

import os
from pathlib import Path
from typing import Mapping


def load_env(path: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Lee un .env. Las variables del entorno real ganan a las del archivo,
    para poder cambiar algo una vez sin editarlo."""
    valores: dict[str, str] = {}
    if Path(path).exists():
        for linea in Path(path).read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            valores[clave.strip()] = valor
    valores.update(os.environ if base is None else base)
    return valores
