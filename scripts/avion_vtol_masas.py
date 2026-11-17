"""Pesa lo impreso del ala volante en sus STL, para que el dimensionado no
lo estime (F13.3 (costillas)).

Por qué: el dimensionado contaba lo impreso como una piel de 0,6 mm por su
área mojada, × 1,4 por los nervios, a 0,75 g/cm³ (0,94 kg). Las piezas del
2026-11-16 eran macizas y pesaban, medidas, de 6 a 7 kg: nadie lo había
comparado. Ahora son huecas y esto las pesa; el dimensionado lee lo que
escribe (`scripts/avion_vtol_impreso.json`) en vez de su estimación.

Material, dicho por él el 2026-11-16: «las alas son de lw pla el resto de
petg», los dos de Prusament. Las alas son las raíces, los tramos y los
elevones; el cuerpo central, la panza, las tapas, las góndolas, los
pilones, las patas y las derivas son el resto. (Antes el asistente había
puesto en LW-PLA todo lo que era piel, cuerpo incluido, y en PLA el tren:
él lo corrigió.) El PETG de Prusament pesa 1,27 g/cm³ según su hoja técnica.

**Supuestos del asistente, sin medir:** el LW-PLA espumado a 0,6 g/cm³ (no
se encontró la cifra de Prusament; otras marcas dan de 0,4 a 0,7 según la
temperatura, y 1,24 sin espumar), y la cáscara y el relleno, los del perfil
de impresión activo.

Uso, desde el repo (en el PC o en el contenedor):
    python scripts/avion_vtol_masas.py <carpeta del proyecto> [salida.json]
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from orchestrator.estudio import laminado, malla, masa_impresa  # noqa: E402

PETG_G_CM3 = 1.27          # Prusament PETG, su hoja técnica (ISO 1183)
LWPLA_G_CM3 = 0.6          # espumado: supuesto del asistente
ALAS = ("raiz", "ala", "elevon")


def material(id_: str) -> tuple[str, float]:
    return ("LW-PLA", LWPLA_G_CM3) if id_.split("-")[0] in ALAS else ("PETG", PETG_G_CM3)


def pesar(proyecto: Path) -> dict:
    lam = laminado(RAIZ)
    piezas = {}
    for stl in sorted(Path(proyecto).glob("nodos/*/parts/*/*.stl")):
        id_ = stl.parent.parent.parent.name
        nombre, densidad = material(id_)
        m = malla(stl)
        piezas[id_] = {"material": nombre, "volumen_cm3": round(m.volumen_mm3 / 1000, 1),
                       "masa_kg": round(masa_impresa(m, lam, densidad) / 1000, 6),
                       "centro_mm": [round(float(v), 1) for v in m.centro]}
    if not piezas:
        raise SystemExit(f"{proyecto}: no hay STL en nodos/*/parts/*/")
    total = sum(p["masa_kg"] for p in piezas.values())
    centro = [sum(p["masa_kg"] * p["centro_mm"][k] for p in piezas.values()) / total
              for k in range(3)]
    por = {}
    for id_, p in piezas.items():
        clave = f'{id_.split("-")[0]} ({p["material"]})'
        por[clave] = round(por.get(clave, 0) + p["masa_kg"], 6)
    return {"proyecto": Path(proyecto).name, "piezas_contadas": len(piezas),
            "masa_kg": round(total, 6), "centro_mm": [round(v, 1) for v in centro],
            "por_tipo_kg": por,
            "supuestos": {"lwpla_g_cm3": LWPLA_G_CM3, "petg_g_cm3": PETG_G_CM3,
                          "lwpla": list(ALAS)},
            "piezas": piezas}


if __name__ == "__main__":
    r = pesar(Path(sys.argv[1]))
    texto = json.dumps(r, ensure_ascii=False, indent=1)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(texto + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items() if k != "piezas"}, ensure_ascii=False, indent=1))
