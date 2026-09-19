"""Mide el criterio de F1.4 (requirements): 10 pedidos → spec válida y clase correcta.

Llamadas REALES al proveedor del perfil activo. No es parte de la suite.

    .venv/bin/python scripts/eval_requirements.py

Con el perfil `dev` esto mide DeepSeek, no `qwen3.8` (ADR-007b).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.agents.requirements import RequirementsAgent  # noqa: E402
from orchestrator.llm.providers.deepseek import DeepSeekClient  # noqa: E402

# (petición, clase esperada, campos que SÍ dijo la persona y NO deben
#  aparecer como estimados)
CASOS = [
    ("algo que sujete un vaso en el carruaje de mi hijo, el tubo mide 68 mm de diámetro", "static_part", set()),
    ("soporte para motor NEMA17 atornillable a un perfil 2020, en PLA", "static_part", {"material"}),
    ("una caja para guardar tornillos M3, con tapa que cierre a presión", "static_part", set()),
    ("adaptador para montar una GoPro en el manillar de la bici", "static_part", set()),
    ("una garra para levantar una lata de refresco, accionada por un servo MG996R", "mechanism", set()),
    ("una bisagra motorizada para la puerta del gallinero", "mechanism", set()),
    ("un cerrojo que se abra con un servo SG90", "mechanism", set()),
    ("brazo robótico de 3 ejes, alcance 40 cm, carga 500 g", "robot", {"payload_g", "reach_mm"}),
    ("un brazo de 6 ejes que alcance 60 cm y levante 1 kg", "robot", {"payload_g", "reach_mm"}),
    ("un pórtico CNC de 3 ejes, área de 300x300 mm, cabezal de 2 kg", "robot", {"payload_g"}),
]


def _clave() -> str:
    for linea in Path(".env").read_text(encoding="utf-8").splitlines():
        if linea.startswith("DEEPSEEK_API_KEY="):
            return linea.split("=", 1)[1].strip()
    raise SystemExit("DEEPSEEK_API_KEY vacía en .env")


def main() -> None:
    agente = RequirementsAgent(DeepSeekClient(api_key=_clave()))
    aciertos = 0
    validas = 0

    procedencia_ok = 0
    for peticion, esperada, dichos in CASOS:
        try:
            spec = agente.draft(peticion)
            validas += 1
            ok = spec.product_class == esperada
            aciertos += ok
            marca = "OK " if ok else "MAL"
            extra = ""
            if spec.payload_g is not None:
                extra += f" payload={spec.payload_g:g}g"
            if spec.reach_mm is not None:
                extra += f" reach={spec.reach_mm:g}mm"
            mal_marcados = dichos & set(spec.estimated)
            procedencia_ok += not mal_marcados
            extra += f"  estimados={spec.estimated}"
            if spec.estimated_critical:
                extra += f"  PREGUNTAR={spec.estimated_critical}"
            if mal_marcados:
                extra += f"  ERROR: marcó como estimado lo que dijo el usuario {sorted(mal_marcados)}"
            print(f"{marca} {spec.product_class:12s} (esperado {esperada:12s}){extra}")
            if not ok:
                print(f"     └─ {peticion[:70]}")
        except Exception as e:
            print(f"ERR  {type(e).__name__}: {str(e)[:90]}")
            print(f"     └─ {peticion[:70]}")

    n = len(CASOS)
    print(f"\nSpecs válidas:    {validas}/{n}")
    print(f"Clase correcta:   {aciertos}/{n}   (criterio F1.4 (requirements): 10/10)")
    print(f"Procedencia bien: {procedencia_ok}/{n}   (lo dicho por el usuario no sale como estimado)")


if __name__ == "__main__":
    main()
