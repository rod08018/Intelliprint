"""La correa de un giro, en el plan y en lo construido (F10.3 (correa), ADR-021).

El plan dice que un giro lo mueve un motor por una correa con cierta
relación (`movido_por`). De ahí sale todo lo demás sin que lo decida ningún
modelo: en el eje del motor va una polea comprada de 20 dientes, la pieza
que gira lleva una de 20 × relación hecha por el kit (`kit.polea_gt2`), y
los dos ejes van a la distancia que pide una correa cerrada.

Sin tensor: los ejes van fijos, a la distancia justa de una correa. El plan
de la fase decía tensar con una colisa; un motor sobre colisas pide cuatro
agujeros alargados y un hueco alargado para su resalte, y eso no se le
puede pedir todavía a un diseñador que acaba de fallar la pinza. Queda
dicho en `PLAN_PROYECTO.md` como lo que falta.
"""

import json
import math
from pathlib import Path

from mech_toolkit import transmisiones as T

from orchestrator.schemas.obra import Gira

TOLERANCIA_ENTRE_EJES = 0.2
"""Lo que puede desviarse la distancia entre ejes de la que pide la correa.
Manual de SDP/SI, tabla 15 «Center Distance Tolerances»: ± .20 mm para
correas de hasta 254 mm, ± .23 hasta 381. Es la de un montaje mecanizado:
si una pieza impresa la da lo dirá F10.8 (calibrar)."""
ENTRE_POLEAS = 2.0
"""Lo menos que se separan las dos poleas, de pestaña a pestaña. Es un
criterio, no una medida: lo justo para que no se rocen."""
POLEA_DEL_MOTOR = "polea-gt2-20"
DE_CUANTO_EN_CUANTO = 5
"""Las correas que se ofrecen van de 5 en 5 dientes (10 mm): las cerradas
se venden en muchos largos, pero no en todos, y nadie ha comprobado cuáles
tiene la tienda del usuario. El plan lo avisa."""
ANCHO_DE_CORREA = 6.0
ASOMA = 8.5
"""Lo que el eje del motor tiene que salir por delante de la cara del
rodamiento por la que sale la pieza que gira: ahí va su polea, y la del
motor tiene que quedar frente a ella. Es la pestaña de la polea (1,5), el
ancho de la correa (6) y 1 mm de holgura con la cara."""


def con_correa(obra, nodo: str | None = None) -> list[Gira]:
    """Los giros del plan que van por correa; con `nodo`, los suyos."""
    return [u for u in obra.uniones if isinstance(u, Gira) and u.movido_por
            and u.movido_por.tipo == "correa" and (nodo is None or nodo in u.nodos())]


def dientes(u: Gira) -> tuple[int, int]:
    """(los de la polea del motor, los de la que lleva la pieza que gira)."""
    return T.DIENTES_DEL_MOTOR, T.dientes_de_la_conducida(T.DIENTES_DEL_MOTOR,
                                                          u.movido_por.relacion)


def _diametro_de_la_del_motor() -> float:
    from orchestrator.componentes import cargar, envolvente
    a, b = envolvente(cargar(POLEA_DEL_MOTOR))
    return b[0] - a[0]


def minimo_entre_ejes(z2: int) -> float:
    """Con menos, la polea grande (con sus pestañas) y la del motor se tocan."""
    return ((T.diametro_exterior(z2) + 2 * T.PESTANA) / 2 + _diametro_de_la_del_motor() / 2
            + ENTRE_POLEAS)


def distancias_posibles(z1: int, z2: int, cuantas: int = 4) -> list[dict]:
    """Las primeras correas, de las que se ofrecen, con las que las poleas no
    se tocan: [{"dientes", "largo_mm", "entre_ejes_mm"}], de corta a larga."""
    minimo = minimo_entre_ejes(z2)
    n = math.ceil(T.largo_de_correa(z1, z2, minimo) / T.PASO / DE_CUANTO_EN_CUANTO) \
        * DE_CUANTO_EN_CUANTO
    salida = []
    while len(salida) < cuantas:
        c = T.distancia_entre_ejes(z1, z2, n)
        if c is not None and c >= minimo:
            salida.append({"dientes": n, "largo_mm": n * T.PASO, "entre_ejes_mm": c})
        n += DE_CUANTO_EN_CUANTO
    return salida


# --- lo que se le dice a quien diseña ---------------------------------------------------------

def para_quien_monta(u: Gira, gira: str, motor: str) -> str:
    """A la pieza que lleva el rodamiento y el motor."""
    z1, z2 = dientes(u)
    donde = "; ".join(f"{c['entre_ejes_mm']:.1f} mm (correa de {c['dientes']} dientes)"
                      for c in distancias_posibles(z1, z2))
    return (f" La correa es una GT2 de {ANCHO_DE_CORREA:g} mm: en el eje del {motor} va una "
            f"polea comprada de {z1} dientes (un cilindro de Ø{_diametro_de_la_del_motor():g} "
            f"× 16 mm metido en el eje) y {gira} llevará en el eje del {u.componente} una de "
            f"{z2}, de Ø{T.diametro_exterior(z2) + 2 * T.PESTANA:.1f} mm. Los dos ejes salen "
            "hacia el mismo lado de la pieza, y de eje a eje tiene que haber justo una de "
            f"estas distancias, que son las que dan correas cerradas: {donde}. Vale "
            f"±{TOLERANCIA_ENTRE_EJES:g} mm. Las dos poleas van por delante de la cara del "
            f"{u.componente} por la que sale {gira}: el eje del motor tiene que asomar al "
            f"menos {ASOMA:g} mm por delante de esa cara (si el motor va detrás de una pared, "
            "que sea fina, o su eje no llega). Entre las dos poleas pasa la correa: no "
            "pongas nada ahí. Al construir se mide.")


def para_quien_gira(u: Gira, sobre: str) -> str:
    """A la pieza que gira: lleva la polea grande."""
    _, z2 = dientes(u)
    return (f" La mueve una correa GT2 {u.movido_por.relacion:g}:1: esta pieza lleva la "
            f"polea de {z2} dientes. Hazla con `kit.polea_gt2(\"polea\", {z2}, en=..., "
            f"eje=...)`, con su eje en el del {u.componente} (el `punto` y el `eje` de su "
            "salida), y únela a la pieza con `+`; no dibujes tú los dientes. La correa viene "
            f"recta desde el eje del motor de {sobre} (`componente.salidas()` trae también "
            f"«{u.movido_por.motor}: eje»): los dientes de la polea tienen que quedar a su "
            "altura, a lo largo del eje.")


# --- lo que se mide en lo construido ----------------------------------------------------------

def _punto(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _ejes(piezas, u: Gira) -> tuple[dict | None, dict | None]:
    """(la salida del rodamiento, la del motor), en el marco de `u.sobre`."""
    from orchestrator.componentes import cargar
    from orchestrator.plan import salida_de
    sobre = piezas.get(u.sobre)
    if sobre is None:
        return None, None
    nombre = salida_de(u, cargar(u.componente)).nombre
    giro = [s for s in sobre.salidas if s.get("ficha") == u.componente and s["nombre"] == nombre]
    motor = [s for s in sobre.salidas if s.get("ficha") == u.movido_por.motor]
    return (giro[0] if giro else None), (motor[0] if motor else None)


def _poleas_de(carpeta: Path, nodo: str) -> list[dict]:
    from orchestrator import obra as O
    try:
        parte = O._pieza_construida(Path(carpeta) / O.NODOS / nodo)
    except ValueError:
        return []
    rasgos = parte / "rasgos.json"
    if not rasgos.is_file():
        return []
    return [r for r in json.loads(rasgos.read_text(encoding="utf-8"))
            if r.get("tipo") == "polea_gt2"]


def medir(carpeta: Path, u: Gira, piezas: dict) -> dict:
    """La correa de la unión `u`, medida en las piezas construidas:
    {"z1", "z2", "hechos", "entre_ejes_mm", "correa", "sobre", "gira"}.
    `hechos`: los dientes de la polea que la pieza que gira lleva en su eje
    (None si no la lleva); `sobre` y `gira`: los defectos de cada pieza,
    escritos para quien la diseña."""
    from orchestrator.conjunto import _a_la_recta
    from orchestrator.tornilleria import _aplicar, _girar

    z1, z2 = dientes(u)
    m = {"z1": z1, "z2": z2, "hechos": None, "entre_ejes_mm": None, "correa": None,
         "sobre": [], "gira": []}
    giro, motor = _ejes(piezas, u)
    alineados = False
    if giro is not None and motor is not None:
        paralelos = _punto(giro["eje"], motor["eje"])
        alineados = paralelos >= 0.999
        if alineados:
            # A lo largo del eje, desde donde empieza el rodamiento: dónde
            # acaba él y hasta dónde llega el eje del motor.
            cara = giro.get("largo") or 0.0
            punta = max(_punto([c + e * t - o for c, e, o in zip(motor["punto"], motor["eje"],
                                                                 giro["punto"])], giro["eje"])
                        for t in (0.0, motor.get("largo") or 0.0))
            if punta - cara < ASOMA - 0.05:
                cuanto = (f"asoma {punta - cara:.1f} mm" if punta > cara else
                          f"se queda {cara - punta:.1f} mm antes de ella, sin asomar")
                m["sobre"].append(
                    f"correa (unión {u.id}): el eje del {motor['de']} tiene que asomar al "
                    f"menos {ASOMA:g} mm por delante de la cara del {giro['de']} por la que "
                    f"sale la pieza que gira, y {cuanto}. Ahí va la polea de la pieza que "
                    "gira, y la del motor tiene que quedar frente a ella: adelanta el motor, "
                    "o adelgaza la pared que tiene delante")
        if abs(paralelos) < 0.999:
            m["sobre"].append(
                f"correa (unión {u.id}): el eje del {motor['de']} no va paralelo al del "
                f"{giro['de']}. Una correa no tuerce: gira el {motor['de']} hasta que su eje "
                "apunte hacia donde apunta el otro")
        elif paralelos < 0:
            m["sobre"].append(
                f"correa (unión {u.id}): el eje del {motor['de']} sale hacia el lado "
                f"contrario al del {giro['de']}. Las dos poleas van del mismo lado de la "
                "pieza: dale la vuelta al motor")
        else:
            c = _a_la_recta(motor["punto"], giro["punto"], giro["eje"])
            m["entre_ejes_mm"] = c
            minimo = minimo_entre_ejes(z2)
            if c < minimo - 0.05:
                m["sobre"].append(
                    f"correa (unión {u.id}): del eje del {motor['de']} al del {giro['de']} hay "
                    f"{c:.1f} mm y las dos poleas no caben con menos de {minimo:.1f}. "
                    "Sepáralos a "
                    + " o ".join(f"{x['entre_ejes_mm']:.1f} mm" for x in distancias_posibles(z1, z2)[:2]))
            else:
                m["correa"] = T.correa_para(z1, z2, c, TOLERANCIA_ENTRE_EJES)
                if m["correa"] is None:
                    justa = T.largo_de_correa(z1, z2, c) / T.PASO
                    cerca = [T.distancia_entre_ejes(z1, z2, n)
                             for n in (math.floor(justa), math.ceil(justa))]
                    m["sobre"].append(
                        f"correa (unión {u.id}): del eje del {motor['de']} al del "
                        f"{giro['de']} hay {c:.1f} mm, y con esa distancia no hay correa que "
                        "quede justa: las más cercanas piden "
                        + " y ".join(f"{x:.1f} mm" for x in cerca if x is not None)
                        + f" (vale ±{TOLERANCIA_ENTRE_EJES:g}). Mueve el motor a una de "
                        "esas, sin tocar el rodamiento")
    yo = piezas.get(u.gira)
    if yo is None or yo.padre != u.sobre:
        return m
    poleas = _poleas_de(carpeta, u.gira)
    como = (f"`kit.polea_gt2(\"polea\", {z2}, en=..., eje=...)`, con su eje en el del "
            f"{u.componente}, unida a la pieza con `+`")
    if not poleas:
        m["gira"].append(
            f"correa (unión {u.id}): esta pieza no lleva la polea por la que la mueve la "
            f"correa. Hazla con {como}")
        return m
    # En el marco de la pieza de abajo, que es donde están los dos ejes.
    en_eje = []
    for p in poleas:
        centro, eje = _aplicar(yo.al_padre, p["centro"]), _girar(yo.al_padre, p["eje"])
        fuera = _a_la_recta(centro, giro["punto"], giro["eje"]) if giro else 0.0
        torcida = giro is not None and abs(_punto(eje, giro["eje"])) < 0.999
        en_eje.append((fuera, torcida, p, centro, eje))
    fuera, torcida, p, centro, eje = min(en_eje, key=lambda x: (x[1], x[0]))
    if torcida or fuera > 0.1:
        m["gira"].append(
            f"correa (unión {u.id}): la polea «{p['nombre']}» no está en el eje del giro: "
            + ("su eje no es paralelo al" if torcida else f"su centro queda a {fuera:.1f} mm del")
            + f" eje del {u.componente}, y cabecearía al girar. Ponla con el `punto` y el "
            "`eje` de la salida sobre la que gira esta pieza")
        return m
    m["hechos"] = p["dientes"]
    if p["dientes"] != z2:
        m["gira"].append(
            f"correa (unión {u.id}): la polea «{p['nombre']}» tiene {p['dientes']} dientes y "
            f"la relación {u.movido_por.relacion:g}:1 pide {z2} (la del motor tiene {z1}). "
            f"Hazla con {como}")
    if giro is not None and motor is not None and alineados:
        # Los dientes de la polea y el eje del motor, a lo largo del eje del giro.
        pie = (p["alto_mm"] - p["ancho_mm"]) / 2
        a = [_punto([c + e * t - o for c, e, o in zip(centro, eje, giro["punto"])], giro["eje"])
             for t in (pie, pie + p["ancho_mm"])]
        b = [_punto([c + e * t - o for c, e, o in zip(motor["punto"], motor["eje"],
                                                      giro["punto"])], giro["eje"])
             for t in (0.0, motor.get("largo") or 0.0)]
        comun = min(max(a), max(b)) - max(min(a), min(b))
        correa = p.get("correa_mm") or ANCHO_DE_CORREA
        if comun < correa - 0.05:
            m["gira"].append(
                f"correa (unión {u.id}): los dientes de la polea «{p['nombre']}» no quedan a "
                f"la altura del eje del {motor['de']}: a lo largo del eje del giro, los "
                f"dientes van de {min(a):.1f} a {max(a):.1f} mm y el eje del motor de "
                f"{min(b):.1f} a {max(b):.1f} (contado desde donde sale el del "
                f"{u.componente}), y la correa necesita {correa:g} mm en común; hay "
                f"{max(comun, 0.0):.1f}. Corre la polea a lo largo de su eje hasta que sus "
                "dientes queden frente al eje del motor")
    return m


def defectos_de_transmision(carpeta: Path, nodo: str) -> list[str]:
    """Lo que la pieza construida de `nodo` no cumple de las correas del
    plan: el motor paralelo al rodamiento y a la distancia de una correa, si
    es la que los monta; la polea con sus dientes, en su eje y frente al del
    motor, si es la que gira."""
    from orchestrator import obra as O
    from orchestrator.conjunto import leer_piezas
    carpeta = Path(carpeta)
    uniones = con_correa(O.cargar_obra(carpeta), nodo)
    if not uniones:
        return []
    piezas = leer_piezas(carpeta, solo_construidas=True)
    return [d for u in uniones
            for d in medir(carpeta, u, piezas)["sobre" if u.sobre == nodo else "gira"]]


def medidas(carpeta: Path) -> list[tuple[Gira, dict]]:
    """Cada correa del plan con lo que mide en lo construido."""
    from orchestrator import obra as O
    from orchestrator.conjunto import leer_piezas
    carpeta = Path(carpeta)
    uniones = con_correa(O.cargar_obra(carpeta))
    if not uniones:
        return []
    piezas = leer_piezas(carpeta, solo_construidas=True)
    return [(u, medir(carpeta, u, piezas)) for u in uniones]
