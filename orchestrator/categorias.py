"""Las categorías con las que se ordena la galería (F5.5 (web)).

El usuario quería «una app ordenada que se pueda ver por categorías»
(2026-10-26). La lista vive en config/categorias.yaml; aquí se lee y se
normaliza lo que diga el modelo, que puede escribirla con mayúscula o
inventarse otra."""

from pathlib import Path

import yaml

RUTA = Path(__file__).resolve().parent.parent / "config" / "categorias.yaml"

CATEGORIAS: list[str] = yaml.safe_load(RUTA.read_text(encoding="utf-8"))

OTROS = "otros"


def normalizar(categoria: str | None) -> str:
    c = (categoria or "").strip().lower()
    return c if c in CATEGORIAS else OTROS
