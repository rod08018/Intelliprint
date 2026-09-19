"""Las referencias a tareas del plan apuntan a la tarea correcta.

Dos fallos reales: tests/README citaba F5.7 (consultas) para el test de
Telegram tras una renumeración (era F5.9 (seguridad)), y al renumerar la Fase 1 quedaron 15
referencias caducadas en el código. El comprobador de entonces solo
miraba que el ID EXISTIERA, y existían: apuntaban a otra tarea.

Por eso en el código todo ID lleva una palabra clave, "F1.10 (designer)",
y la palabra tiene que aparecer en la fila de esa tarea del plan.
"""

import re
import unicodedata
from pathlib import Path

PLAN = Path("PLAN_PROYECTO.md").read_text(encoding="utf-8")
FILAS = {m.group(1): m.group(0) for m in re.finditer(r"^\| (F\d+\.\d+) \|.*$", PLAN, re.M)}
PALABRA = r"[\wáéíóúñü]+"
CON_PALABRA = re.compile(rf"\b(F\d+\.\d+) \(({PALABRA})\)")
SUELTO = re.compile(rf"\bF\d+\.\d+\b(?! \({PALABRA}\))")

EXCLUIR = {".venv", "workspace", ".git"}


def _archivos(sufijos):
    return [p for p in Path(".").rglob("*") if p.suffix in sufijos
            and not EXCLUIR & set(p.parts) and p.is_file()]


def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def test_todo_id_citado_existe_en_el_plan():
    rotos = [
        f"{p}: {i}"
        for p in _archivos({".md", ".py", ".yaml", ".ini"})
        for i in set(re.findall(r"\bF\d+\.\d+\b", p.read_text(errors="ignore")))
        if i not in FILAS
    ]
    assert rotos == []


def test_en_el_codigo_todo_id_lleva_su_palabra_clave():
    """Un ID suelto puede quedar apuntando a otra tarea sin que nada falle."""
    sueltos = [
        f"{p}:{n}: {linea.strip()[:70]}"
        for p in _archivos({".py"})
        for n, linea in enumerate(p.read_text().splitlines(), 1)
        if SUELTO.search(linea)
    ]
    assert sueltos == [], "\n".join(sueltos)


def test_la_palabra_clave_corresponde_a_la_tarea():
    """Poner "designer" junto al ID de la validez del sólido fallaría."""
    malas = [
        f"{p}: {i} ({palabra}) — la fila de {i} no habla de '{palabra}'"
        for p in _archivos({".py", ".md"})
        for i, palabra in CON_PALABRA.findall(p.read_text(errors="ignore"))
        if i in FILAS and _normal(palabra) not in _normal(FILAS[i])
    ]
    assert malas == [], "\n".join(malas)
