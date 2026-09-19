"""Mide el criterio de aceptación de F1.3 (estructurada): ≥ 90 % de salidas válidas en 20.

Hace llamadas REALES al proveedor del perfil activo, así que no forma
parte de la suite de tests. Se ejecuta a mano:

    .venv/bin/python scripts/eval_structured_output.py [n]

Ojo con leer los resultados: con el perfil `dev` esto mide DeepSeek, que
sigue esquemas mejor que `qwen3.8`. Es un suelo optimista (ADR-007b).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.llm.providers.deepseek import DeepSeekClient  # noqa: E402
from orchestrator.llm.structured import SalidaInvalida, structured  # noqa: E402
from orchestrator.schemas.recipe import (  # noqa: E402
    GeneratorCatalog,
    GeneratorSpec,
    Recipe,
)

CATALOGO = GeneratorCatalog(
    [
        GeneratorSpec(
            name="generate_bolt_pattern",
            required_params={"screw_id", "count", "pcd_mm", "fit"},
        ),
        GeneratorSpec(
            name="generate_bearing_housing",
            required_params={"bearing_id", "fit"},
        ),
        GeneratorSpec(
            name="generate_plate",
            required_params={"length_mm", "width_mm", "thickness_mm"},
        ),
    ]
)

PROMPT = """Eres el Part Designer de un sistema de diseño para impresión 3D.

NO escribes Python. Emites una RECETA: una lista de llamadas a generadores.

Generadores disponibles y sus parámetros obligatorios:
- generate_plate(length_mm, width_mm, thickness_mm)
- generate_bolt_pattern(screw_id, count, pcd_mm, fit)
- generate_bearing_housing(bearing_id, fit)

Tarea: pieza `base_nema17`, una placa de 60x60x6 mm con un patrón de
4 tornillos M3 en PCD 31 con ajuste de holgura (fit: clearance).

Devuelve SOLO este JSON:
{"part": "<nombre>", "steps": [{"generator": "<nombre>", "params": {...}}]}
"""


def _clave() -> str:
    for linea in Path(".env").read_text(encoding="utf-8").splitlines():
        if linea.startswith("DEEPSEEK_API_KEY="):
            return linea.split("=", 1)[1].strip()
    raise SystemExit("DEEPSEEK_API_KEY vacía en .env")


def main(n: int = 20) -> None:
    cliente = DeepSeekClient(api_key=_clave())
    resultados: Counter[str] = Counter()
    intentos_usados: list[int] = []

    for i in range(1, n + 1):
        contador = {"n": 0}

        class Contado:
            def complete(self, prompt: str) -> str:
                contador["n"] += 1
                # temperatura > 0 para que las 20 muestras no sean idénticas
                return cliente.complete(prompt, temperature=0.7)

        try:
            receta = structured(Contado(), PROMPT, Recipe)
            receta.validate_against(CATALOGO)
            resultados["ok" if contador["n"] == 1 else "ok_tras_reintento"] += 1
            intentos_usados.append(contador["n"])
            marca = "." if contador["n"] == 1 else "r"
        except SalidaInvalida:
            resultados["esquema_invalido"] += 1
            marca = "X"
        except Exception as e:  # receta inválida contra el catálogo
            resultados[type(e).__name__] += 1
            marca = "C"
        print(marca, end="", flush=True)

    print(f"\n\n--- {n} pruebas ---")
    for clave, valor in resultados.most_common():
        print(f"{clave:20s} {valor:3d}  ({valor / n:.0%})")

    validas = resultados["ok"] + resultados["ok_tras_reintento"]
    print(f"\nVálidas totales: {validas}/{n} = {validas / n:.0%}  (criterio F1.3 (estructurada): ≥ 90 %)")
    if intentos_usados:
        print(f"Intentos por éxito: media {sum(intentos_usados)/len(intentos_usados):.2f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
