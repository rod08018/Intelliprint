"""Configuración de entorno."""

import os
import re
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
            clave, _, resto = linea.partition("=")
            valores[clave.strip()] = _valor(resto)
    valores.update(os.environ if base is None else base)
    return valores


_COMENTARIO = re.compile(r"(^|\s)#")


def _valor(resto: str) -> str:
    """El valor de `CLAVE=resto`, con la misma regla que Docker Compose.

    Entre comillas, todo es literal y lo de después se ignora. Sin
    comillas, un `#` precedido de espacio abre un comentario; pegado al
    texto, es parte del valor (una contraseña puede llevar `#`).

    Tiene que coincidir con Compose porque los dos leen EL MISMO archivo.
    Fallo real: la plantilla trae `TELEGRAM_BOT_TOKEN=   # SECRETO: ...`, y
    al pegar el token delante del comentario este lector entregaba el token
    con el comentario detrás —103 caracteres en vez de 46— mientras Compose
    lo leía bien. En el contenedor funcionaba; nativo, 401 sin explicación.
    """
    limpio = resto.strip()
    if limpio[:1] in ("\"", "'"):
        cierre = limpio.find(limpio[0], 1)
        if cierre != -1:
            return limpio[1:cierre]
    m = _COMENTARIO.search(resto)
    return (resto[:m.start()] if m else resto).strip()
