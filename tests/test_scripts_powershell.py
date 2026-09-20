"""Los .ps1 del repo se pueden ejecutar en el Windows PowerShell de serie
(F0.4 (proxy)).

Windows PowerShell 5.1 —el que trae Windows— lee un .ps1 sin BOM como
cp1252, no como UTF-8. Cualquier carácter fuera de ASCII se lee mal, y
algunos rompen el script entero.

Pasó de verdad con start-host-mcps.ps1: un guion largo (—) en un mensaje de
error. En UTF-8 son tres bytes, E2 80 94, y el último, 0x94, en cp1252 es
una COMILLA DOBLE. PowerShell la tomó por el final de la cadena y el script
no llegó ni a arrancar: "Unexpected token", "Missing closing '}'".

La regla que lo evita no es "guarda con BOM" —un editor la quita sin
avisar—, sino que un .ps1 sea ASCII puro. Sin tildes: "maquina", no
"máquina".
"""

from pathlib import Path

import pytest

SCRIPTS = sorted(Path(".").glob("**/*.ps1"))


def test_hay_scripts_que_comprobar():
    """Si nadie encuentra ninguno, los demás tests pasan sin probar nada."""
    assert SCRIPTS, "no encuentro ningún .ps1"


@pytest.mark.parametrize("script", SCRIPTS, ids=str)
def test_un_ps1_es_ascii_puro(script):
    malos = [
        f"línea {n}: {linea.strip()[:60]!r}"
        for n, linea in enumerate(script.read_text(encoding="utf-8").splitlines(), 1)
        if not linea.isascii()
    ]
    assert malos == [], (
        f"{script} tiene caracteres fuera de ASCII; Windows PowerShell 5.1 "
        "los lee como cp1252 y pueden romper el script:\n" + "\n".join(malos))
