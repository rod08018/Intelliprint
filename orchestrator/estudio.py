"""El estudio de movimientos de un robot (F7.10 (estudio)).

«Lo que sí quiero es el estudio de movimientos, eso sí me lo debe dar» (el
usuario, 2026-11-10), al sacar ROS y Gazebo de Intelliprint: ¿aguanta el
servo?, ¿vuelca?, hasta dónde llega, cuánto tarda y cuánta carga aguanta.

Todo sale de lo que ya está construido y comprobado: las mallas de las
piezas, la cinemática con la que se barrieron los choques
(`conjunto.poses`), las fichas de lo comprado y la tornillería. Ninguna cifra
la dice un modelo.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

ACERO_G_CM3 = 7.85
G = 9.80665
CORRECCION_ESTIMADA = 1 / 0.80
"""La estimación sin laminar se queda corta. Contra 40 piezas del workspace
que sí se laminaron (2026-11-10), PrusaSlicer pesó entre 1.00 y 1.25 veces
lo estimado (mediana 1.10): perímetros que se solapan, el patrón del
relleno. Para decir si un servo aguanta o si algo vuelca, quedarse corto es
el error peligroso, así que se toma el peor caso medido."""


# --- las masas ------------------------------------------------------------------------------

@dataclass
class Malla:
    volumen_mm3: float
    lados_mm2: float
    arriba_mm2: float
    abajo_mm2: float
    centro: list


def malla(stl: Path) -> Malla:
    """Volumen, superficie y centro de una malla cerrada, por tetraedros con
    signo desde el origen: exacto para la malla, sin FreeCAD. La superficie
    se separa por la normal: lo que mira arriba o abajo se imprime con capas
    macizas; los lados, con perímetros."""
    import numpy as np
    from orchestrator.tornilleria import _triangulos
    stl = Path(stl)
    t = _triangulos(str(stl), stl.stat().st_mtime)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    v6 = np.einsum("ij,ij->i", a, np.cross(b, c))           # 6 × volumen con signo
    vol = v6.sum() / 6
    centro = ((a + b + c) * v6[:, None]).sum(0) / (4 * v6.sum()) if v6.sum() else a.mean(0)
    n = np.cross(b - a, c - a)
    if vol < 0:                       # triángulos al revés: las normales, también
        vol, n = -vol, -n
    area = np.linalg.norm(n, axis=1) / 2
    nz = np.divide(n[:, 2], 2 * area, out=np.zeros_like(area), where=area > 0)
    return Malla(float(vol), float(area[np.abs(nz) <= 0.7].sum()), float(area[nz > 0.7].sum()),
                 float(area[nz < -0.7].sum()), [float(x) for x in centro])


def laminado(raiz: Path) -> dict:
    """Las claves del .ini del perfil activo (`config/impresion.yaml`)."""
    from orchestrator.impresion import perfil_activo
    ini = Path(raiz) / "config" / "slicing" / perfil_activo(raiz).laminado
    claves = {}
    for linea in ini.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([a-z_]+)\s*=\s*(.*?)\s*$", linea)
        if m:
            claves[m[1]] = m[2]
    return claves


def _num(v, defecto: float) -> float:
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return defecto


def masa_impresa(m: Malla, lam: dict, densidad_g_cm3: float) -> float:
    """Cáscara maciza más el relleno del interior, sin laminar (el diseño no
    lamina: solo al abrir PrusaSlicer). La cáscara es la superficie por su
    grueso —perímetros en los lados, capas macizas arriba y abajo—; en una
    pieza fina se queda corta por las esquinas que cuenta dos veces, y por
    eso no pasa del volumen."""
    n = _num(lam.get("perimeters"), 2)
    ext = _num(lam.get("external_perimeter_extrusion_width"), 0.45)
    per = _num(lam.get("perimeter_extrusion_width"), 0.45)
    capa = _num(lam.get("layer_height"), 0.2)
    pared = ext + max(n - 1, 0) * per
    cascara = (m.lados_mm2 * pared + m.arriba_mm2 * capa * _num(lam.get("top_solid_layers"), 4)
               + m.abajo_mm2 * capa * _num(lam.get("bottom_solid_layers"), 4))
    cascara = min(cascara, m.volumen_mm3)
    relleno = _num(lam.get("fill_density"), 20) / 100
    return round((cascara + (m.volumen_mm3 - cascara) * relleno) / 1000 * densidad_g_cm3, 4)


@dataclass
class Masa:
    nombre: str
    g: float
    centro: list
    """En el marco de la pieza a la que va unida."""
    de: str
    """«PrusaSlicer», «estimada», «ficha», «acero» o «carga»."""
    pieza: str = ""


def masa_de_parte(parte: Path, lam: dict, densidad_g_cm3: float) -> Masa:
    """Una pieza impresa. Si se laminó, sus gramos de PrusaSlicer; si no,
    la estimación. El centro, el de la malla: el relleno se reparte por
    igual, así que no lo mueve mucho."""
    parte = Path(parte)
    stl = next(iter(sorted(parte.glob("*.stl"))))
    m = malla(stl)
    informe = parte.parent.parent / "fabrication" / "slicing_report.json"
    if informe.is_file():
        gramos = json.loads(informe.read_text(encoding="utf-8")).get("grams")
        if gramos:
            return Masa(parte.name, float(gramos), m.centro, "PrusaSlicer")
    return Masa(parte.name, round(masa_impresa(m, lam, densidad_g_cm3) * CORRECCION_ESTIMADA, 4),
                m.centro, "estimada")


# --- las respuestas -------------------------------------------------------------------------

def par_por_gravedad(masas, punto, eje) -> float:
    """N·m que pide el peso de `masas` [(g, centro en mm)] alrededor de la
    recta (`punto`, `eje`), con la gravedad hacia −z: el par del peso
    m·g·(−ẑ) en r − p, proyectado en el eje. El signo dice hacia dónde."""
    n = sum(e * e for e in eje) ** 0.5
    ex, ey, ez = (e / n for e in eje)
    tau = 0.0
    for g, c in masas:
        rx, ry = (c[0] - punto[0]) / 1000, (c[1] - punto[1]) / 1000
        # (r × F)·e con F = (0, 0, −m·g): (−ry·F, rx·F, 0)·e con F = m·g
        f = g / 1000 * G
        tau += -ry * f * ex + rx * f * ey
    return tau if abs(tau) > 1e-12 else 0.0


def carga_que_aguanta(par_disponible: float, par_propio: float, brazo_m: float) -> float:
    """Gramos que se pueden colgar a `brazo_m` del eje con el par que queda."""
    if brazo_m <= 1e-6:
        return float("inf")
    return max(0.0, (par_disponible - abs(par_propio)) / (G * brazo_m) * 1000)


def margen_de_vuelco(cdm, apoyo) -> float:
    """Distancia en planta del centro de masas al borde del polígono de
    apoyo (convexo): positiva dentro, negativa fuera, que es volcar."""
    from math import hypot
    x, y = cdm[0], cdm[1]
    n = len(apoyo)
    area2 = sum(apoyo[i][0] * apoyo[(i + 1) % n][1] - apoyo[(i + 1) % n][0] * apoyo[i][1]
                for i in range(n))
    signo = 1 if area2 > 0 else -1
    dentro, fuera = float("inf"), 0.0
    for i in range(n):
        (ax, ay), (bx, by) = apoyo[i], apoyo[(i + 1) % n]
        largo = hypot(bx - ax, by - ay)
        if largo < 1e-9:
            continue        # vértice repetido: su «lado» no tiene recta
        d = signo * ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / largo   # >0 a la izquierda
        dentro = min(dentro, d)
        if d < 0:
            # fuera: la distancia al segmento, no a la recta
            t = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / largo ** 2))
            fuera = max(fuera, hypot(x - ax - t * (bx - ax), y - ay - t * (by - ay)))
    return dentro if dentro >= 0 else -fuera


def tiempo_de_recorrido(grados: float, s_60: float, par: float, par_bloqueo: float) -> float:
    """Segundos para girar `grados` con la recta par-velocidad del servo,
    ω = ω₀·(1 − τ/τ_bloqueo): la aproximación de un motor de continua. A
    plena carga no se mueve."""
    libre = 1 - abs(par) / par_bloqueo if par_bloqueo else 1
    return float("inf") if libre <= 0 else abs(grados) / 60 * s_60 / libre


# --- el estudio de un conjunto --------------------------------------------------------------

MARGEN_SERVO = 0.5
"""Un servo aguanta si no pasa del 50 % de su par de bloqueo: la regla de
taller para que trabaje sin calentarse (decidido por el usuario, 2026-11-10)."""
RENDIMIENTO = {"correa": 0.9, "reductora": 0.65}
"""La parte del par del motor que llega al eje por cada transmisión
(F10.2 (transmisión)). **Son supuestos, no medidas**: nadie ha medido una correa
ni una reductora impresas en la impresora del usuario. Se toman del lado
bajo —una correa dentada bien tensada pierde menos— y van escritos junto
a cada carga que sale de ellos. El de la reductora es el que midió
howtomechatronics.com en una cicloidal impresa de 15:1 («efficiency of
around 66%»: 26 N a 10 cm con un motor de 26 N·cm), no en una de aquí
(F10.7 (cicloidal))."""
from orchestrator.conjunto import MAX_POSES  # noqa: E402
# Hasta cuántas poses se prueban todas las combinaciones. Caben tres giros
# de 180° con la rejilla de 10° (19³ = 6 859): con 5 000 se probaba cada giro
# por turno con los demás en 0°, y la peor pose de un brazo —estirado en
# horizontal— puede no estar ahí (F10.1 (serie)). Con cuatro giros ya no
# caben, y se prueba una rejilla más gruesa (F10.5 (muestreo)).
# Las direcciones de la gravedad que se prueban en cada pieza: todas van en
# una sola llamada a FreeCAD, pero cada una corta la pieza 30 veces.
MAX_GRAVEDADES = 24


def _centro_de_primitivas(prims) -> list | None:
    """El centro de las cajas y cilindros de una ficha, pesado por volumen."""
    import math
    total, suma = 0.0, [0.0, 0.0, 0.0]
    for p in prims:
        if "min" in p:
            v = math.prod(b - a for a, b in zip(p["min"], p["max"]))
            c = [(a + b) / 2 for a, b in zip(p["min"], p["max"])]
        else:
            r, ri = p["diametro"] / 2, (p.get("interior") or 0) / 2
            v = math.pi * (r * r - ri * ri) * p["alto"]
            c = [b + e * p["alto"] / 2 for b, e in zip(p["base"], p["eje"])]
        total += v
        suma = [s + v * x for s, x in zip(suma, c)]
    return [s / total for s in suma] if total else None


def _envolvente_convexa(pts) -> list:
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    abajo, arriba = [], []
    for p in pts:
        while len(abajo) >= 2 and giro(abajo[-2], abajo[-1], p) <= 0:
            abajo.pop()
        abajo.append(p)
    for p in reversed(pts):
        while len(arriba) >= 2 and giro(arriba[-2], arriba[-1], p) <= 0:
            arriba.pop()
        arriba.append(p)
    return abajo[:-1] + arriba[:-1]


def _apoyo(stl: Path, mundo) -> list:
    """La envolvente convexa, en planta, de lo que toca el suelo: los
    vértices de la base a menos de medio milímetro de su punto más bajo."""
    from orchestrator.tornilleria import _aplicar, _triangulos
    vs = [_aplicar(mundo, [float(x) for x in v]) for v in
          _triangulos(str(stl), stl.stat().st_mtime).reshape(-1, 3)]
    z0 = min(v[2] for v in vs)
    return _envolvente_convexa((round(v[0], 4), round(v[1], 4)) for v in vs if v[2] <= z0 + 0.5)


def apoyo_para_guardar(apoyo) -> list:
    """El apoyo redondeado a centésimas y vuelto a envolver: redondeado sin
    más deja de ser convexo, y `margen_de_vuelco` necesita que lo sea (el
    visor daba 5.1 mm en una pose del pan-tilt donde el estudio decía 5.4)."""
    return [list(p) for p in _envolvente_convexa((round(x, 2), round(y, 2)) for x, y in apoyo)]


def _distancia_a_la_recta(p, punto, eje) -> float:
    from orchestrator.tornilleria import _cruz, _norma, _resta, _unit
    return _norma(_cruz(_resta(p, punto), _unit(eje)))


def _stl(pieza) -> Path:
    return next(iter(sorted(pieza.step.parent.glob("*.stl"))))


def _masas(piezas, todos, lam, rho, fichas, avisos) -> list[Masa]:
    """Cada masa en el marco de su pieza: lo impreso, lo comprado y los
    tornillos (acero, caña más una cabeza Allen)."""
    import math
    from orchestrator.componentes import cargar
    masas = []
    for i, p in piezas.items():
        m = masa_de_parte(p.step.parent, lam, rho)
        masas.append(Masa(p.nombre, m.g, m.centro, m.de, i))
        for r in p.propios:
            ficha = cargar(r["ficha"], fichas)
            centro = _centro_de_primitivas([x for x in p.montados if x["de"] == r["nombre"]])
            if ficha.masa_g is None or centro is None:
                avisos.append(f"{ficha.nombre}: su ficha no da la masa, y no se cuenta.")
                continue
            masas.append(Masa(ficha.nombre, float(ficha.masa_g), centro, "ficha", i))
    for t in todos:
        largo = t.largo or t.largo_mm
        d = float(t.metrica.lstrip("Mm") or 3)
        vol = math.pi * (d / 2) ** 2 * largo + math.pi * (d * 0.9) ** 2 * d
        masas.append(Masa(f"tornillo {t.metrica}", round(vol / 1000 * ACERO_G_CM3, 3),
                          [c + e * largo / 2 for c, e in zip(t.cabeza, t.eje)], "acero", t.pieza))
    return masas


def _punto_de_carga(piezas, arts, todos, lam, rho):
    """Dónde va la carga: donde se atornilla lo de fuera en la última pieza
    de la cadena; si no hay dónde, su punto más lejos del eje que la mueve,
    que es el peor caso. Devuelve (pieza, punto en su marco, dónde)."""
    from orchestrator.conjunto import _hasta_la_raiz, _inversa
    from orchestrator.tornilleria import _aplicar, _girar, _triangulos
    hojas = [i for i in piezas if not any(q.padre == i for q in piezas.values())]
    hoja = max(hojas, key=lambda i: len(_hasta_la_raiz(piezas, i)))
    fuera = [t for t in todos if t.pieza == hoja and t.termina == "superficie"]
    if fuera:
        return (hoja, [sum(t.cabeza[k] for t in fuera) / len(fuera) for k in range(3)],
                f"en los {len(fuera)} tornillos para montar algo en «{piezas[hoja].nombre}»")
    a = arts.get(hoja)
    if a is None:
        return hoja, masa_de_parte(piezas[hoja].step.parent, lam, rho).centro, \
            f"en el centro de «{piezas[hoja].nombre}»"
    stl = _stl(piezas[hoja])
    t = _inversa(piezas[hoja].al_padre)
    punto, eje = _aplicar(t, a.punto), _girar(t, a.eje)
    vs = _triangulos(str(stl), stl.stat().st_mtime).reshape(-1, 3)
    lejos = max(([float(x) for x in v] for v in vs),
                key=lambda v: _distancia_a_la_recta(v, punto, eje))
    return hoja, lejos, f"en la punta de «{piezas[hoja].nombre}», lo más lejos de su eje"


def _carga_que_vuelca(cdm, M, pc, apoyo) -> float:
    """Los gramos en `pc` que llevan el centro de masas al borde del apoyo."""
    def margen(c):
        return margen_de_vuelco([(cdm[k] * M + c * pc[k]) / (M + c) for k in range(2)], apoyo)
    if margen(0) < 0:
        return 0.0
    lo, hi = 0.0, 1e6
    if margen(hi) >= 0:
        return float("inf")
    for _ in range(80):
        c = (lo + hi) / 2
        lo, hi = (c, hi) if margen(c) >= 0 else (lo, c)
    return lo


def estudiar(carpeta: Path, conjunto: str, raiz: Path | None = None) -> dict:
    """Las respuestas de F7.10 (estudio) para un conjunto, con la base
    apoyada como se imprimió (z hacia arriba) y sobre la rejilla con la que
    se barrieron los choques. La resistencia del material, que necesita
    FreeCAD, la añade `intelliprint estudio`."""
    import itertools
    import math
    from orchestrator import obra as O
    from orchestrator.componentes import cargar
    from orchestrator.conjunto import (PASO, VERIFICACION, _hasta_la_raiz,
                                       articulaciones_de, leer_piezas, muestreo_en_palabras,
                                       poses, rejilla_de_poses)
    from orchestrator.impresion import perfil_activo
    from orchestrator.tornilleria import _aplicar, _girar, tornillos

    carpeta = Path(carpeta)
    raiz = Path(raiz) if raiz else Path(__file__).resolve().parent.parent
    lam, rho = laminado(raiz), perfil_activo(raiz).densidad_g_cm3
    fichas = [O.carpeta_de_fichas(carpeta)]
    piezas = leer_piezas(carpeta, conjunto, solo_construidas=True)
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    ver = carpeta / O.NODOS / conjunto / VERIFICACION
    paso = (json.loads(ver.read_text(encoding="utf-8")).get("paso") if ver.is_file() else None) or PASO
    ob = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    avisos: list[str] = []

    # Una sola vez: cada tornillo traza rayos contra mallas de hasta 3
    # millones de triángulos (la plataforma del pan-tilt), y se pedían tres.
    todos = tornillos(carpeta, conjunto)
    masas = _masas(piezas, todos, lam, rho, fichas, avisos)
    hoja, carga, donde = _punto_de_carga(piezas, arts, todos, lam, rho)
    cadena = set(_hasta_la_raiz(piezas, hoja))

    # Lo que mueve cada giro: el motor de su transmisión, si el plan la dice
    # (F10.2 (transmisión)); si no, el propio componente que hace de eje.
    movidas = {u["gira"]: u["movido_por"] for u in ob.get("uniones") or []
               if u.get("tipo") == "gira" and u.get("movido_por")}
    servos_de = {}
    for j, a in arts.items():
        if j in movidas:
            servos_de[j] = cargar(movidas[j]["motor"], fichas)
            continue
        for r in piezas[a.padre].propios:
            if r["nombre"] == a.de:
                servos_de[j] = cargar(r["ficha"], fichas)
    # La tensión: la del invento, o la más baja de las hojas, del lado seguro.
    # Un paso a paso no la tiene: su par es el de retención.
    tension = ob.get("alimentacion_V")
    if tension is None:
        tensiones = [v for f in servos_de.values() if not f.par_retencion_mNm
                     for v in f.par_kgf_cm]
        tension = min(tensiones) if tensiones else None
        if tension is not None:
            avisos.append(f"El invento no dice con qué tensión van los servos: se toma "
                          f"{tension:g} V, la más baja de sus hojas.")
    # El par en el eje de cada giro, parado: el del motor por la relación y
    # por el rendimiento de su transmisión. Sin entrada si no se sabe.
    bloqueo: dict[str, float] = {}
    for j, f in servos_de.items():
        par = f.par_motor_Nm(tension)
        if par is None:
            continue
        t = movidas.get(j)
        bloqueo[j] = par * t["relacion"] * RENDIMIENTO[t["tipo"]] if t else par
    for tipo in dict.fromkeys(t["tipo"] for j, t in movidas.items() if j in bloqueo):
        avisos.append(f"El rendimiento de una {tipo} ({RENDIMIENTO[tipo]:.0%}) es un supuesto, "
                      "no una medida: de él salen el par disponible y la carga de lo que "
                      "mueve.")

    # Las poses: todas las combinaciones de la rejilla, si no son demasiadas;
    # si lo son, una más gruesa con los extremos de todos los giros. Antes se
    # movía cada giro por turno con los demás en 0°, y la peor pose de un
    # brazo puede no estar ahí (F10.5 (muestreo)).
    combos, sin_probar = rejilla_de_poses({j: a.recorrido for j, a in arts.items()}, paso,
                                          MAX_POSES)
    if sin_probar:
        texto = muestreo_en_palabras([sin_probar])
        avisos.append(texto[0].upper() + texto[1:] + ".")

    raiz_id = next(i for i, p in piezas.items() if p.padre is None)
    apoyo = _apoyo(_stl(piezas[raiz_id]), poses(piezas, {}, {})[raiz_id])
    # Atornillada a algo de fuera: a una mesa (el tornillo baja) o a un
    # tablero vertical (sale de lado). Solo contaba el que baja, y el hombro
    # del encargo 14b (corrida 1113-0605), fijado a un tablero vertical con
    # cuatro M3, «volcaba» con 212 g teniendo motor para 875; lo decidió el
    # usuario el 2026-11-13. El que sube desde debajo de la base no cuenta:
    # sujeta algo encima de ella. No se mide si los tornillos aguantan.
    atornillada = bool(any(t.pieza == raiz_id and t.termina == "superficie" and t.eje[2] < 0.1
                           for t in todos))

    estado = {j: {"par_max": 0.0, "angulo": 0.0, "carga": math.inf, "radio": 0.0,
                  "vertical": True} for j in arts}
    vuelco_min, vuelco_pose, vuelco_carga = math.inf, {}, math.inf
    radio_max, puntos = 0.0, []
    primera = next(iter(arts), None)
    for angulos in combos:
        mundo = poses(piezas, arts, angulos)
        mm = [(m.g, _aplicar(mundo[m.pieza], m.centro), m.pieza) for m in masas]
        pc = _aplicar(mundo[hoja], carga)
        puntos.append(pc)
        for j, a in arts.items():
            punto, eje = _aplicar(mundo[a.padre], a.punto), _girar(mundo[a.padre], a.eje)
            cuelga = [(g, c) for g, c, i in mm if j in _hasta_la_raiz(piezas, i)]
            tau = par_por_gravedad(cuelga, punto, eje)
            e = estado[j]
            if abs(tau) > e["par_max"] + 1e-12:
                e["par_max"], e["angulo"] = abs(tau), angulos[j]
            # El mismo umbral con el que el banco llama «vertical» a un eje.
            e["vertical"] = e["vertical"] and abs(eje[2]) > 0.99
            if j in cadena:
                e["radio"] = max(e["radio"], _distancia_a_la_recta(pc, punto, eje))
                por_gramo = par_por_gravedad([(1.0, pc)], punto, eje)
                if abs(por_gramo) > 1e-12 and j in bloqueo:
                    disp = MARGEN_SERVO * bloqueo[j]
                    # La carga suma o resta al par propio según de qué lado cuelgue.
                    hacia = 1 if por_gramo > 0 else -1
                    e["carga"] = min(e["carga"], max(0.0, (disp - hacia * tau) / abs(por_gramo)))
        if primera is not None:
            a = arts[primera]
            radio_max = max(radio_max, _distancia_a_la_recta(
                pc, _aplicar(mundo[a.padre], a.punto), _girar(mundo[a.padre], a.eje)))
        if len(apoyo) >= 3:
            M = sum(g for g, _, _ in mm)
            cdm = [sum(g * c[k] for g, c, _ in mm) / M for k in range(2)]
            margen = margen_de_vuelco(cdm, apoyo)
            if margen < vuelco_min:
                vuelco_min, vuelco_pose = margen, dict(angulos)
            vuelco_carga = min(vuelco_carga, _carga_que_vuelca(cdm, M, pc, apoyo))

    servos = []
    for j, a in arts.items():
        f, e = servos_de.get(j), estado[j]
        fila = {"pieza": j, "nombre": piezas[j].nombre, "servo": f.nombre if f else a.de,
                "par_max_Nm": round(e["par_max"], 6), "angulo_peor": e["angulo"],
                "recorrido": list(a.recorrido)}
        t = movidas.get(j)
        if t and f is not None:
            fila["servo"] = f"{f.nombre} por {t['tipo']} {t['relacion']:g}:1"
        if j in bloqueo:
            par = bloqueo[j]
            fila.update(
                par_bloqueo_Nm=round(par, 6), par_disponible_Nm=round(MARGEN_SERVO * par, 6),
                aguanta=bool(e["par_max"] <= MARGEN_SERVO * par),
                margen=round(1 - e["par_max"] / (MARGEN_SERVO * par), 3),
                carga_max_g=None if e["carga"] == math.inf else round(e["carga"], 2))
            if t:
                fila["transmision"] = {**t, "rendimiento": RENDIMIENTO[t["tipo"]],
                                       "par_motor_Nm": round(f.par_motor_Nm(tension), 6)}
            if not f.par_retencion_mNm:
                fila["tension_V"] = tension
            # La transmisión divide la velocidad por lo mismo que multiplica
            # el par. De un paso a paso no se da: depende de su controlador.
            s60 = None if f.par_retencion_mNm else f.velocidad(tension)
            if s60:
                s60 *= t["relacion"] if t else 1
                fila.update(
                    tiempo_s=round(tiempo_de_recorrido(a.recorrido[1] - a.recorrido[0], s60,
                                                       e["par_max"], par), 4),
                    velocidad_punta_mm_s=round(math.radians(60 / s60) * (1 - e["par_max"] / par)
                                               * e["radio"], 1))
        else:
            avisos.append(f"«{piezas[j].nombre}»: no se sabe el par de lo que la mueve "
                          f"({t['motor'] if t else a.de}).")
        servos.append(fila)

    limites = [(s["carga_max_g"], f"servo de «{s['nombre']}»") for s in servos
               if s.get("carga_max_g") is not None]
    if vuelco_carga != math.inf and not atornillada:
        limites.append((round(vuelco_carga, 2), "vuelco"))
    elif vuelco_carga != math.inf:
        # Atornillada a la mesa no vuelca: el vuelco se dice, pero no limita.
        avisos.append(f"Va atornillada: sin los tornillos volcaría con {vuelco_carga:.0f} g de carga.")
    g, limita = min(limites) if limites else (None, None)

    # El hombro: el primer giro, de la base a la punta, que levanta (su eje no
    # es vertical). El alcance de un brazo se mide de ahí, en perpendicular a
    # ese eje. Medido del primer giro, el primer brazo del banco (1112-0318)
    # «llegaba» a 233 mm con 120 de brazo: el tramo colgaba de un separador
    # de 105 mm a lo largo del eje del hombro, y lo que contaba era el
    # desvío. Si ningún giro levanta (un plato), se mide del primero.
    de_la_base_a_la_punta = [j for j in reversed(_hasta_la_raiz(piezas, hoja)) if j in arts]
    hombro = next((j for j in de_la_base_a_la_punta if not estado[j]["vertical"]),
                  de_la_base_a_la_punta[0] if de_la_base_a_la_punta else None)
    return {
        "conjunto": conjunto, "tension_V": tension, "paso": paso, "poses": len(combos),
        "masas": [m.__dict__ for m in masas],
        "masa_total_g": round(sum(m.g for m in masas), 2),
        "carga": {"punto": [round(x, 2) for x in carga], "pieza": hoja, "donde": donde},
        "servos": servos,
        "vuelco": {"margen_mm": None if vuelco_min == math.inf else round(vuelco_min, 2),
                   "pose": vuelco_pose, "atornillada": atornillada,
                   "apoyo": apoyo_para_guardar(apoyo),
                   "carga_max_g": None if vuelco_carga == math.inf else round(vuelco_carga, 2)},
        "alcance": {"radio_mm": round(radio_max, 2),
                    "del_hombro_mm": round(estado[hombro]["radio"], 2) if hombro else 0.0,
                    "hombro": None if hombro is None else {
                        "pieza": hombro, "nombre": piezas[hombro].nombre,
                        "levanta": not estado[hombro]["vertical"]},
                    "caja_mm": [[round(min(p[k] for p in puntos), 1) for k in range(3)],
                                [round(max(p[k] for p in puntos), 1) for k in range(3)]],
                    "puntos": [[round(x, 1) for x in p] for p in puntos]},
        "carga_max": {"g": g, "limita": limita},
        "avisos": avisos,
    }


# --- la carga que aguanta el material ---------------------------------------------------------

_TRAMOS = '''\
import json
import sys
sys.path.insert(0, {toolkit!r})
import Part
from mech_toolkit.sondas import carga_en_camino
forma = Part.read({step!r})
if len(forma.Solids) == 1:
    forma = forma.Solids[0]
material = json.loads({material!r})
salida = []
for t in json.loads({tramos!r}):
    try:
        salida.append(carga_en_camino(forma, t["desde"], t["hasta"], t["gravedad"], material))
    except Exception as e:
        salida.append({{"cumple": None, "N_max": None, "detalle": "la sonda falló: %s" % e}})
print("INTELLIPRINT_TRAMOS:" + json.dumps(salida))
'''


def resistencia_de_tramos(step: Path, tramos: list[dict], freecadcmd: str,
                          material: dict) -> list[dict]:
    """`sondas.carga_en_camino` en cada tramo de una pieza, en un freecadcmd."""
    import subprocess
    import tempfile

    import mech_toolkit
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "tramos.py"
        script.write_text(_TRAMOS.format(
            toolkit=str(Path(mech_toolkit.__file__).resolve().parent.parent), step=str(step),
            tramos=json.dumps(tramos), material=json.dumps(material)), encoding="utf-8")
        proceso = subprocess.run([freecadcmd, str(script)], capture_output=True, text=True,
                                 timeout=900)
    linea = next((x for x in proceso.stdout.splitlines() if x.startswith("INTELLIPRINT_TRAMOS:")),
                 None)
    if linea is None:
        motivo = ((proceso.stdout + proceso.stderr).strip().splitlines() or ["sin salida"])[-1]
        return [{"cumple": None, "N_max": None, "detalle": f"no corrió: {motivo}"} for _ in tramos]
    return json.loads(linea.split(":", 1)[1])


def carga_del_material(carpeta: Path, conjunto: str, e: dict, freecadcmd: str,
                       raiz: Path | None = None) -> list[dict]:
    """Cuánta carga aguanta cada pieza de la cadena que lleva a la carga,
    del eje que la mueve a donde cuelga lo siguiente, con la gravedad de
    través en la peor pose. A lo que aguanta se le resta lo que ya cuelga
    más allá y el peso de la propia pieza, llevado a la punta por momentos."""
    import itertools
    import math
    from orchestrator import obra as O
    from orchestrator.conjunto import (PASO, _hasta_la_raiz, _inversa, articulaciones_de,
                                       leer_piezas, poses, rejilla_de_poses)
    from orchestrator.impresion import perfil_activo
    from orchestrator.tornilleria import _aplicar, _girar, _punto, _resta, _unit

    raiz = Path(raiz) if raiz else Path(__file__).resolve().parent.parent
    material = perfil_activo(raiz).datos["resistencia"]
    piezas = leer_piezas(carpeta, conjunto, solo_construidas=True)
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    hoja, carga = e["carga"]["pieza"], e["carga"]["punto"]
    cadena = _hasta_la_raiz(piezas, hoja)          # de la hoja hacia la raíz
    combos, _ = rejilla_de_poses({j: a.recorrido for j, a in arts.items()},
                                 e.get("paso") or PASO, MAX_POSES)
    mundos = [poses(piezas, arts, c) for c in combos]
    filas = []
    for pos, k in enumerate(cadena):
        a = arts.get(k)
        if a is None:
            continue
        desde = _aplicar(_inversa(piezas[k].al_padre), a.punto)
        hijo = cadena[pos - 1] if pos else None
        hasta = carga if hijo is None else _aplicar(piezas[hijo].al_padre, [0.0, 0.0, 0.0])
        if hijo is not None and hijo in arts:
            hasta = arts[hijo].punto              # el eje del hijo, en el marco de k
        largo = math.dist(desde, hasta)
        n = _unit(_resta(hasta, desde)) if largo > 1e-6 else [0.0, 0.0, 1.0]
        # Cada dirección de la gravedad que ve la pieza en su marco. Una placa
        # no flexa igual de plano que de canto: con solo la más «de través»
        # salió que la plataforma del pan-tilt aguantaba 16 kg, flexando de
        # canto, que es justo como no se rompe (2026-11-10).
        gravedades: list[list[float]] = []
        for mundo in mundos:
            r = mundo[k][0]
            gl = [-r[2][j] for j in range(3)]
            if all(math.dist(gl, o) > 0.05 for o in gravedades):
                gravedades.append(gl)
        if len(gravedades) > MAX_GRAVEDADES:
            gravedades = gravedades[::math.ceil(len(gravedades) / MAX_GRAVEDADES)]
        mas_alla = sum(m["g"] for m in e["masas"]
                       if m["pieza"] != k and k in _hasta_la_raiz(piezas, m["pieza"]))
        propio = sum(m["g"] * min(1.0, max(0.0, _punto(_resta(m["centro"], desde), n) / largo))
                     for m in e["masas"] if m["pieza"] == k) if largo > 1e-6 else 0.0
        step = piezas[k].step
        res = resistencia_de_tramos(step, [{"desde": desde, "hasta": hasta, "gravedad": g}
                                           for g in gravedades], freecadcmd, material)
        flexan = [x for x in res if x.get("N_max")]
        r = min(flexan, key=lambda x: x["N_max"]) if flexan else res[0]
        fila = {"pieza": k, "nombre": piezas[k].nombre, "largo_mm": round(largo, 1),
                "detalle": r["detalle"], "carga_max_g": None}
        if r.get("N_max"):
            fila["carga_max_g"] = round(max(0.0, r["N_max"] / G * 1000 - mas_alla - propio), 1)
        filas.append(fila)
    return filas


def estudio_entero(carpeta: Path, conjunto: str, freecadcmd: str | None,
                   raiz: Path | None = None) -> dict:
    """El estudio con la resistencia del material si hay FreeCAD, y la carga
    máxima del sistema: la menor de todas. No escribe nada: el banco lo pide
    al juzgar una corrida ya hecha, y juzgar no cambia lo juzgado."""
    e = estudiar(carpeta, conjunto, raiz)
    if freecadcmd:
        e["material"] = carga_del_material(carpeta, conjunto, e, freecadcmd, raiz)
        cargas = [(m["carga_max_g"], f"material de «{m['nombre']}»") for m in e["material"]
                  if m["carga_max_g"] is not None]
        actual = [(e["carga_max"]["g"], e["carga_max"]["limita"])] if e["carga_max"]["g"] is not None else []
        if cargas + actual:
            g, limita = min(cargas + actual)
            e["carga_max"] = {"g": g, "limita": limita}
    else:
        e["avisos"].append("Sin FreeCAD no se mide la resistencia del material.")
    return e


def escribir_estudio(carpeta: Path, conjunto: str, freecadcmd: str | None,
                     raiz: Path | None = None) -> dict:
    """`nodos/<conjunto>/estudio.json` y su `estudio.md`."""
    from orchestrator import obra as O
    e = estudio_entero(carpeta, conjunto, freecadcmd, raiz)
    destino = Path(carpeta) / O.NODOS / conjunto / ESTUDIO
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    destino.with_suffix(".md").write_text(texto_del_estudio(e), encoding="utf-8")
    return e


ESTUDIO = "estudio.json"


def _g(x) -> str:
    return "—" if x is None else f"{x:.1f} g"


def texto_del_estudio(e: dict) -> str:
    """El `estudio.md`: las cinco preguntas de F7.10 (estudio), con cada
    cifra y de dónde sale, para leerlo sin abrir el json."""
    t = e.get("tension_V")
    l = [f"# Estudio de movimientos de «{e['conjunto']}»", "",
         f"La base apoyada como se imprimió, z hacia arriba; {e['poses']} poses "
         f"cada {e['paso']:g}°. Servos a {t:g} V." if t is not None else
         f"La base apoyada como se imprimió, z hacia arriba; {e['poses']} poses.",
         f"Masa del conjunto: {e['masa_total_g']:.1f} g. La carga útil va "
         f"{e['carga']['donde']}.", ""]
    l += ["## ¿Aguanta el servo?", "",
          f"Aguanta si el par por gravedad no pasa del {MARGEN_SERVO:.0%} del de bloqueo (en un "
          "paso a paso, del de retención), llevado al eje por su transmisión si la tiene.", "",
          "| Articulación | Servo | Par máximo | Disponible | ¿Aguanta? | Carga que admite |",
          "|---|---|---|---|---|---|"]
    for s in e["servos"]:
        ok = {True: "Sí", False: "**No**"}.get(s.get("aguanta"), "no se sabe")
        admite = _g(s.get("carga_max_g")) if s.get("carga_max_g") is not None else (
            "la gravedad no la frena" if s.get("aguanta") and s["par_max_Nm"] < 1e-6 else "—")
        disp = s.get("par_disponible_Nm")
        l.append(f"| {s['nombre']} | {s['servo']} | {s['par_max_Nm']:.4f} N·m a {s['angulo_peor']:g}° "
                 f"| {'—' if disp is None else f'{disp:.4f} N·m'} | {ok} | {admite} |")
    for s in e["servos"]:
        t = s.get("transmision")
        if t:
            l += ["", f"«{s['nombre']}»: {t['par_motor_Nm']:.3f} N·m del motor × {t['relacion']:g} "
                      f"de la {t['tipo']} × {t['rendimiento']:.0%} de rendimiento = "
                      f"{s['par_bloqueo_Nm']:.3f} N·m en el eje. El rendimiento es un supuesto, "
                      "no una medida."]
    v = e["vuelco"]
    l += ["", "## ¿Vuelca?", ""]
    if v["margen_mm"] is None:
        l.append("No se sabe: la base no tiene cara de apoyo.")
    else:
        l.append(f"Sin carga, el centro de masas queda a {v['margen_mm']:.1f} mm del borde del "
                 f"apoyo en la peor pose ({'dentro' if v['margen_mm'] >= 0 else '**fuera**'}).")
        if v["carga_max_g"] is not None:
            l.append(f"Con {_g(v['carga_max_g'])} en el punto de carga vuelca"
                     + (", pero va atornillada." if v["atornillada"] else "."))
    a = e["alcance"]
    l += ["", "## Alcance", "",
          f"El punto de carga llega a {a['radio_mm']:.1f} mm del primer eje; barre la caja "
          f"{a['caja_mm'][0]} → {a['caja_mm'][1]} mm."]
    h = a.get("hombro")
    if h and h["levanta"]:
        l.append(f"Del eje de «{h['nombre']}», el primer giro que lo levanta, está a "
                 f"{a['del_hombro_mm']:.1f} mm: eso es lo que mide el brazo.")
    l += ["", "## Velocidades y tiempos", "",
          "Con la recta par-velocidad del servo, ω = ω₀·(1 − τ/τ_bloqueo), en el peor par.", ""]
    for s in e["servos"]:
        if s.get("tiempo_s") is not None:
            l.append(f"- «{s['nombre']}»: recorre {s['recorrido'][1] - s['recorrido'][0]:g}° en "
                     f"{s['tiempo_s']:.2f} s; el punto de carga va a {s['velocidad_punta_mm_s']:.0f} mm/s.")
    c = e["carga_max"]
    l += ["", "## Carga máxima", ""]
    l.append(f"**{_g(c['g'])}**, la limita el {c['limita']}." if c["g"] is not None
             else "No se puede decir.")
    for m in e.get("material", []):
        l.append(f"- Material de «{m['nombre']}» ({m['largo_mm']:g} mm): "
                 + (f"{_g(m['carga_max_g'])}; {m['detalle']}." if m["carga_max_g"] is not None
                    else f"{m['detalle']}."))
    if e["avisos"]:
        l += ["", "## Avisos", ""] + [f"- {x}" for x in e["avisos"]]
    return "\n".join(l) + "\n"


def en_la_pose(carpeta: Path, conjunto: str, angulos: dict[str, float]) -> dict | None:
    """El par que pide la gravedad a cada servo y el margen de vuelco con
    las articulaciones a esos ángulos, para el visor. Con las masas del
    `estudio.json`: sacarlas de las mallas cuesta medio minuto. Sin carga
    útil: es lo que se ve al mover el deslizador."""
    from orchestrator import obra as O
    from orchestrator.conjunto import _hasta_la_raiz, articulaciones_de, leer_piezas, poses
    from orchestrator.tornilleria import _aplicar, _girar
    ruta = Path(carpeta) / O.NODOS / conjunto / ESTUDIO
    if not ruta.is_file():
        return None
    e = json.loads(ruta.read_text(encoding="utf-8"))
    piezas = leer_piezas(carpeta, conjunto, solo_construidas=True)
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    mundo = poses(piezas, arts, {j: v for j, v in angulos.items() if j in arts})
    mm = [(m["g"], _aplicar(mundo[m["pieza"]], m["centro"]), m["pieza"])
          for m in e["masas"] if m["pieza"] in mundo]
    disponible = {s["pieza"]: s.get("par_disponible_Nm") for s in e["servos"]}
    pares = {}
    for j, a in arts.items():
        punto, eje = _aplicar(mundo[a.padre], a.punto), _girar(mundo[a.padre], a.eje)
        tau = abs(par_por_gravedad([(g, c) for g, c, i in mm if j in _hasta_la_raiz(piezas, i)],
                                   punto, eje))
        d = disponible.get(j)
        pares[j] = {"Nm": round(tau, 7), "uso": round(tau / d, 4) if d else None}
    apoyo = [tuple(p) for p in e["vuelco"].get("apoyo") or []]
    vuelco = None
    if len(apoyo) >= 3 and mm:
        total = sum(g for g, _, _ in mm)
        vuelco = margen_de_vuelco([sum(g * c[k] for g, c, _ in mm) / total for k in range(2)], apoyo)
    return {"pares": pares, "vuelco_mm": vuelco}


def dibujo_del_alcance(e: dict) -> bytes:
    """Planta y alzado de por dónde pasa el punto de carga, con el apoyo de
    la base en la planta: se ve de un vistazo si se sale de la huella."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pts = e["alcance"].get("puntos") or []
    fig, (planta, alzado) = plt.subplots(1, 2, figsize=(8, 3.6), dpi=110)
    apoyo = e["vuelco"].get("apoyo") or []
    if apoyo:
        planta.fill([p[0] for p in apoyo], [p[1] for p in apoyo], color="#d9dde2",
                    label="apoyo de la base")
    for eje, (i, j), titulo in ((planta, (0, 1), "Planta (x, y)"), (alzado, (0, 2), "Alzado (x, z)")):
        eje.scatter([p[i] for p in pts], [p[j] for p in pts], s=6, color="#2563eb",
                    label="punto de carga")
        eje.set_title(titulo, fontsize=10)
        eje.set_aspect("equal", adjustable="datalim")
        eje.grid(True, color="#eceef1")
        eje.tick_params(labelsize=8)
    planta.legend(fontsize=7, loc="best")
    fig.tight_layout()
    salida = io.BytesIO()
    fig.savefig(salida, format="png")
    plt.close(fig)
    return salida.getvalue()
