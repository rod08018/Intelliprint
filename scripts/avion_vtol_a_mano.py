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
En el workspace hace falta `-e CAMBIO="…"`: lo que cambia esta versión.
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
# Cada carpeta es una VERSIÓN del avión, con lo que cambia en `CAMBIO`. Él,
# el 2026-11-17, al ver siete inventos en la portada: «¿por qué hay 6
# inventos de avión y no un avión con 6 versiones?». Se pide antes de
# construir nada: sin ella, la carpeta sale como un invento más.
AVION = "2026-11-16-vtol-a-mano-sin-modelo"
CAMBIO = os.environ.get("CAMBIO", "").strip()
if not str(P).startswith("/tmp/") and not CAMBIO:
    raise SystemExit("falta CAMBIO: qué cambia esta versión del avión "
                     "(docker compose run -e CAMBIO=\"…\" …)")
if P.exists() and not str(P).startswith("/tmp/"):
    raise SystemExit(f"{P} ya existe y no es temporal: no se toca")
shutil.rmtree(P, ignore_errors=True)
P.mkdir(parents=True)
os.environ["INTELLIPRINT_WORKSPACE"] = str(P.parent.parent)
if CAMBIO and not str(P).startswith("/tmp/"):
    from orchestrator.web.versiones import marcar_version
    print("VERSIÓN de", marcar_version(P.parent.parent, P, AVION, CAMBIO), flush=True)
D = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))
DISENO = D["diseno"]
CAMA = (235, 235, 250)

PIEZAS = avion.piezas(DISENO)
if SOLO:
    PIEZAS = [p for p in PIEZAS if p[0] == SOLO]

obra = Obra(titulo="VTOL de ala volante con LiPo 6S y lo comprado en Amazon, a mano y sin modelo",
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
    f"lidar) y una LiPo {D['bateria']['serie']}S de {D['bateria']['mAh']} mAh "
    f"({D['bateria']['Wh']} Wh). Los cuatro rotores levantan {D['vtol']['empuje_sobre_peso']} "
    "veces su peso.\n"
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
    f"- Centro de gravedad a {eq['cg_x_m'] * 1000:.0f} mm del morro del ala, con la carga y "
    f"sin ella (margen estático del {eq['con_carga']['margen'] * 100:.0f} % y del "
    f"{eq['sin_carga']['margen'] * 100:.0f} %); estable en guiñada (Cn_β = {eq['Cn_beta']}).\n"
    "- Dentro: la carga (dos cámaras y un lidar) en el centro de gravedad, mirando abajo por "
    "tres ventanas, para que ponerla o quitarla no lo mueva; la batería justo encima, bajo "
    "los largueros, en una bandeja; la controladora y el ordenador de a bordo en el morro. "
    "Los variadores de sustentación, en las góndolas.\n"
    "- Dos elevones por lado, cada uno con su servo (cuatro): el interior es un trozo y el "
    "exterior, dos pegados con una varilla de carbono de Ø2. Los servos van en un hueco por "
    "debajo del ala, y sus cables por un canal de Ø6 hasta el fuselaje.\n\n"
    "**Se compra en Amazon** (él: «usemos motores y bateria que pueda comprar en amazon»; "
    "elegido por el asistente, con las cifras de cada anuncio, sin medir):\n\n"
    + "".join(f"- {c['cantidad']} × [{c['que']}]({c['url']})\n" for c in D["compras"])
    + "\nY lo que no tiene anuncio aquí: el receptor de su radio, tornillos M3, velcro de 20 mm, "
    "cinta de bisagra, epoxi y CA. Los tubos de carbono se venden de 1000 mm: "
    + ", ".join(f"{k} de {v:g} mm" for k, v in D["tubos_mm"].items()) + ".\n\n"
    "- **Por dentro, hueco** (él: «las alas son de lw pla el resto de petg», Prusament): el "
    "ala, de piel de 0,6 mm "
    "con un alma al 72 % de la cuerda, nervios en zigzag a 50° y fundas de 1,2 mm en los "
    "largueros; el fuselaje, de 1,2 mm. La batería, la carga y la electrónica entran por la "
    "panza, que se atornilla con cuatro M3: el larguero de atrás cruza el fuselaje sobre la "
    "batería y por arriba no se puede. Cada hueco de servo lleva su tapa.\n"
    f"- Lo impreso pesa {m.get('impreso, pesado en sus STL', '?')} kg, pesado en sus STL "
    "(`scripts/avion_vtol_masas.py`): las alas (raíces, tramos y elevones) en LW-PLA "
    "espumado a 0,6 g/cm³ y el resto (cuerpo central, panza, tapas, góndolas, pilones, patas "
    "y derivas) en PETG de 1,27 g/cm³, con el relleno del perfil.\n\n"
    "**Puntos débiles, sin calcular:** el pilón descarga en la piel de 0,6 mm de LW-PLA (no "
    "hay un refuerzo debajo); los M3 de la panza roscan en PETG de 1,2 mm; la bandeja de la batería "
    "es de 3 mm y aguanta 2,7 kg en los aterrizajes.\n\n"
    "**Lo que no está medido:** que vuele, ni que aguante. La densidad del LW-PLA, las masas "
    "de lo comprado y los rendimientos son estimaciones del asistente; la aerodinámica es la "
    "de AeroSandbox, no un túnel.\n", encoding="utf-8")

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

# Lo de dentro, para verlo en su sitio en las fotos y en la simulación. No son
# nodos: no se imprimen.
if not SOLO:
    from orchestrator.build import build_part
    from orchestrator.schemas.programa import Programa
    from tests.test_sondas import PERFIL
    ques = [c["id"] for c in DISENO["dentro"] if c.get("caja")] + ["canal-d", "canal-i"]
    for q in ques:
        codigo = (f"def construir(kit):\n    diseno = {json.dumps(DISENO)}\n"
                  f"    return kit.avion_dentro(diseno, {q!r})\n")
        build_part(Programa(part=q, codigo=codigo), None, P / "dentro" / q,
                   os.environ["FREECADCMD"], perfil=PERFIL)
        print(f"dentro: {q}", flush=True)
if not SOLO and hechas:
    # Lo que pesa lo construido, para el dimensionado (que lee
    # `scripts/avion_vtol_impreso.json`, copia de esto si es el avión de hoy).
    import importlib.util
    _spec = importlib.util.spec_from_file_location("masas", "scripts/avion_vtol_masas.py")
    masas = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(masas)
    pesado = masas.pesar(P)
    (P / "masas.json").write_text(json.dumps(pesado, ensure_ascii=False, indent=1) + "\n",
                                  encoding="utf-8")
    print(f"PESA {pesado['masa_kg']:.3f} kg lo impreso; centro {pesado['centro_mm']}", flush=True)
    # Montado, con las vigas, los motores y las hélices: sin ellos las
    # góndolas y las derivas salían sueltas («no se entiende qué son», 2026-11-17).
    from orchestrator.vista import dibujar_montado, guardar_comprado
    guardar_comprado(P, avion.comprado_a_la_vista(DISENO))
    print("VISTA:", dibujar_montado(P, P / "vista.png"))
