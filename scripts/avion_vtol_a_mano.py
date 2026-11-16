"""El VTOL de la Fase 13, construido A MANO por el asistente con el kit (2026-11-16).

Él lo pidió así: «tú diseña y usa lo que habías dicho; quiero que se haga
rápido», y al ver la primera versión (cola en H, 8,7 kg): «quiero que lo
nuestro sea ligero». Esta es la segunda: un ala volante. Las cifras salen de
`scripts/avion_vtol_dimensionar.py` (AeroSandbox) y de su JSON,
`scripts/avion_vtol.json`; la forma de cada pieza, de `kit.avion_pieza`
(`mech_toolkit/avion.py`). **No es nota del sistema**: el asistente escribió
el dimensionado y las formas, y el modelo no ha dibujado nada.

Cada pieza se dibuja donde va montada (x hacia atrás, y hacia la derecha, z
arriba, en mm). Lo comprado (vigas y largueros de carbono, motores, hélices,
batería) no se imprime.

Uso, desde el repo:
    MSYS_NO_PATHCONV=1 docker compose run --rm -T --entrypoint python3 suite - \\
        /workspace/projects/<carpeta> < scripts/avion_vtol_a_mano.py
Con un segundo argumento (un id de pieza), construye solo esa, en /tmp.
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

from mech_toolkit import avion
from orchestrator import cli
from orchestrator import obra as O
from orchestrator.medida import no_cabe_en_la_impresora
from orchestrator.schemas.obra import Obra
from orchestrator.voladizos import como_imprimir, zona_en_palabras
from tests.test_revalidar import _lista

raiz = cli._raiz()
os.chdir(raiz)
P = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/avion")
SOLO = sys.argv[2] if len(sys.argv) > 2 else None
if P.exists() and not str(P).startswith("/tmp/"):
    raise SystemExit(f"{P} ya existe y no es temporal: no se toca")
shutil.rmtree(P, ignore_errors=True)
P.mkdir(parents=True)
os.environ["INTELLIPRINT_WORKSPACE"] = str(P.parent.parent)
D = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))
DISENO = D["diseno"]
CAMA = (235, 235, 250)

PIEZAS = avion.piezas(DISENO)
if SOLO:
    PIEZAS = [p for p in PIEZAS if p[0] == SOLO]

obra = Obra(titulo="VTOL de ala volante, a mano y sin modelo",
            nodos=[{"id": i, "nombre": n, "que_hace": q} for i, n, q in PIEZAS])
O.guardar(P, obra, por="mano")
if len(PIEZAS) > 1:
    O.aprobar(P, por="mano")

m, c, ro, eq = D["masa_kg"], D["crucero"], D["rotores"], D["equilibrio"]
rc = D["lo_que_cuestan_los_rotores"]
(P / "request.md").write_text(
    "VTOL de ala volante, «como el TerraHawk pero mejorado», ligero. **Diseñado a mano por "
    "el asistente el 2026-11-16, no por el modelo**: las cuentas con AeroSandbox "
    "(`scripts/avion_vtol_dimensionar.py`) y la forma de cada pieza con "
    "`kit.avion_pieza` (`mech_toolkit/avion.py`); cada programa es una línea.\n\n"
    f"- Envergadura {D['envergadura_m']} m, ala de {D['area_alar_m2']} m² con flecha de 25° y "
    "puntas levantadas; perfil MH 78 en el centro y MH 60 en el ala (autoestables).\n"
    f"- Peso al despegar {m['total']} kg, con {m['carga útil']} kg de carga (dos cámaras y un "
    f"lidar) y una batería 6S{D['bateria']['paralelo']}P de 21700 ({D['bateria']['Wh']} Wh).\n"
    f"- Crucero a {c['velocidad_m_s'] * 3.6:.0f} km/h: L/D {c['L_D']}, {c['potencia_W']} W. "
    f"Autonomía {D['autonomia_h']} h y {D['alcance_km']:.0f} km, con 15 % de reserva y "
    f"{D['vtol']['minutos']:.0f} min de vuelo vertical ({D['vtol']['potencia_W']:.0f} W).\n"
    f"- Lo que cuestan los cuatro rotores de sustentación: {rc['peso_kg']} kg, "
    f"{rc['potencia_crucero_W']} W de los {c['potencia_W']} del crucero (hélices paradas y "
    f"vigas) y {rc['energia_vertical_Wh']} Wh de despegue y aterrizaje.\n"
    f"- Hélices: cuatro de {ro['helice_vtol_pulg']}\" para subir y una de "
    f"{ro['helice_empuje_pulg']}\" de empuje; {ro['hueco_entre_discos_m'] * 1000:.0f} mm entre el "
    "disco de un rotor trasero y el de la de empuje, y "
    f"{ro['helice_empuje_sobre_el_suelo_m'] * 1000:.0f} mm de la de empuje al suelo.\n"
    f"- Centro de gravedad a {eq['cg_x_m'] * 1000:.0f} mm del morro del ala (margen estático "
    f"del {eq['margen'] * 100:.0f} %); estable en guiñada (Cn_β = {eq['Cn_beta']}).\n\n"
    "**Se compra:** dos vigas de carbono de Ø16 × 0,9 m; largueros de carbono de Ø10 y Ø6; "
    "cuatro motores de sustentación con hélices de 13\" y sus variadores; un motor de "
    "empuje de la clase 28xx con hélice plegable de 10\"; 36 celdas 21700 de 4,5 Ah; "
    "controladora, GPS, telemetría y dos servos de elevón. Son una propuesta del "
    "asistente, sin comprobar contra su tienda.\n\n"
    "**Lo que no está medido:** que vuele. Las masas de lo impreso y de lo comprado y los "
    "rendimientos son estimaciones del asistente; la aerodinámica es la de AeroSandbox, no "
    "un túnel.\n", encoding="utf-8")

hechas, fallos = [], []
for id_, nombre, _ in PIEZAS:
    t = time.time()
    codigo = (f"def construir(kit):\n    diseno = {json.dumps(DISENO)}\n"
              f"    return kit.avion_pieza(diseno, {id_!r})\n")
    try:
        _lista(P, id_, codigo)
    except Exception as e:  # noqa: BLE001
        fallos.append(id_)
        print(f"{id_}: NO SE CONSTRUYÓ: {type(e).__name__}: {str(e)[-800:]}", flush=True)
        continue
    parte = O._pieza_construida(P / O.NODOS / id_)
    env = json.loads((parte / "envolvente.json").read_text(encoding="utf-8"))
    mide = [round(b - a, 1) for a, b in zip(env["min"], env["max"])]
    cabe = not no_cabe_en_la_impresora(mide, CAMA)
    [stl] = list(parte.glob("*.stl"))
    postura, zonas = como_imprimir(stl, 45, 10)
    hechas.append(id_)
    print(f"{id_}: {time.time() - t:.0f} s, mide {mide}{'' if cabe else ' NO CABE'}; "
          f"{'sin soportes' if postura else 'PIDE SOPORTES'}", flush=True)
    if not postura:
        mejor = min(zonas, key=lambda q: sum(z.area_mm2 for z in zonas[q]))
        for z in zonas[mejor][:4]:
            print(f"    {mejor}: {zona_en_palabras(z)}", flush=True)

print(f"HECHAS {len(hechas)} de {len(PIEZAS)}; fallan: {fallos}", flush=True)
if not SOLO and hechas:
    from orchestrator.vista import dibujar_piezas
    stls = sorted(P.glob("nodos/*/parts/*/*.stl"))
    print("VISTA:", dibujar_piezas(stls, P / "vista.png", "VTOL de ala volante, a mano"))
