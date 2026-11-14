"""El kit de geometría (F5.18 (kit)): con lo que el diseñador escribe la pieza.

El catálogo cerrado de generadores (ADR-002) solo tenía cajas, cilindros y
prismas en Z: la escuadra de repisa con nervio salió maciza (121 g), las V
del sargento con 63 cajas en escalera y los hexágonos cuadrados. Aquí el
diseñador escribe `construir(kit)` en Python con estas operaciones, y lo que
hace la ejecución segura es `sandbox.validar` (lista blanca) más medir lo
que sale, no que el código lo escriba una persona. Ver ADR-002, enmienda.

Tres reglas del kit:

- **Todo en milímetros y en la orientación de impresión**: z = 0 es la cama.
- **Cada agujero, tornillo o hueco lleva nombre** y queda registrado como
  rasgo (ADR-011): es lo que después se mide contra los requisitos.
- **La tornillería y las holguras salen del perfil activo**, nunca de
  memoria: `tornillo("pared_1", "M3", ...)` usa `M3_through_mm` del perfil.

Este módulo se importa sin FreeCAD (el validador lee de aquí qué nombres
existen); `Part` solo hace falta al construir, dentro de `freecadcmd`.
"""

import inspect
import math
import time
import traceback

try:   # dentro de freecadcmd
    import FreeCAD
    import Part
except ImportError:   # en el orquestador: solo se lee la API
    FreeCAD = Part = None

TOL = 1e-6
BASE_MM = 0.25
ACABADO_MAX_S = 40.0
"""Lo más que se gasta buscando en qué aristas cabe un acabado que no cabe
en todas: el resto queda vivo. FreeCAD entero tiene 180 s."""
LARGO = 2000.0
"""Lo que mide una broca pasante: más que cualquier pieza de la cama."""


def convexa(forma, arista) -> bool:
    """Si la arista es una esquina hacia fuera (el sólido ocupa un cuadrante
    a su alrededor) y no un rincón (ocupa tres). Se mira un punto junto a la
    arista en la dirección n1 − n2: fuera del sólido en una esquina, dentro
    de la pared en un rincón. Con n1 + n2, como se hacía, los dos casos caen
    fuera y todo parecía esquina (2026-11-04).

    Importa porque redondear un rincón AÑADE material: en el soporte del SG90
    del banco rellenó las cuatro esquinas de la ventana y el servo ya no
    entraba."""
    caras = forma.ancestorsOfType(arista, Part.Face)
    if len(caras) != 2:
        return False
    p = arista.valueAt((arista.FirstParameter + arista.LastParameter) / 2)
    n1, n2 = (c.normalAt(*c.Surface.parameter(p)) for c in caras)
    d = n1 - n2
    if d.Length < 1e-6:
        return False   # caras tangentes: no hay esquina
    return not forma.isInside(p + d.normalize() * 0.05, 1e-6, True)


def prisma_de_chaflan(forma, arista, lado):
    """El chaflán de 45° de una arista recta y convexa entre dos caras planas,
    como el prisma que hay que RESTAR: un triángulo con un cateto de `lado`
    sobre cada cara, a lo largo de toda la arista. None si la arista no es
    de esas o es casi plana (la sonda solo cuenta las de 60° o más).

    Es el respaldo de `acabar()`: un corte booleano sale donde el redondeo
    de OCC no. En el banco `1105-2120` (2026-11-05) cinco piezas quedaron
    con entre un 18 % y un 43 % de aristas vivas: OCC no redondea junto a
    escalones de 0.1 mm ni el cuadrado del NEMA 17 sobre la cama."""
    if arista.Curve.TypeId != "Part::GeomLine" or len(arista.Vertexes) != 2:
        return None
    caras = forma.ancestorsOfType(arista, Part.Face)
    if len(caras) != 2 or any(c.Surface.TypeId != "Part::GeomPlane" for c in caras):
        return None
    if not convexa(forma, arista):
        return None
    a, b = (v.Point for v in arista.Vertexes)
    if (b - a).Length < TOL:
        return None
    u = (b - a).normalize()
    medio = arista.valueAt((arista.FirstParameter + arista.LastParameter) / 2)
    n1, n2 = (c.normalAt(*c.Surface.parameter(medio)) for c in caras)
    if n1.dot(n2) > 0.5:
        return None
    # Sobre cada cara, la dirección que se aleja de la arista: perpendicular
    # a ella, dentro del plano, y hacia el lado contrario a la otra normal.
    t1, t2 = u.cross(n1), u.cross(n2)
    if t1.dot(n2) > 0:
        t1 = t1 * -1
    if t2.dot(n1) > 0:
        t2 = t2 * -1
    # Una centésima por fuera de cada cara: un corte con caras coplanarias
    # es justo lo que OCC resuelve mal.
    e = 0.01
    triangulo = [a + (n1 + n2) * e, a + t1 * lado + n1 * e, a + t2 * lado + n2 * e]
    return Part.Face(Part.makePolygon([*triangulo, triangulo[0]])).extrude(b - a)


class KitError(ValueError):
    """Un error en el uso del kit, escrito para que el diseñador lo corrija."""


def _v(p) -> "FreeCAD.Vector":
    if len(p) != 3:
        raise KitError(f"un punto son tres coordenadas (x, y, z), no {p!r}")
    return FreeCAD.Vector(float(p[0]), float(p[1]), float(p[2]))


_EJES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1),
         "-x": (-1, 0, 0), "-y": (0, -1, 0), "-z": (0, 0, -1),
         # Con signo, como `entra_por`: el soporte de giro del pan-tilt
         # (banco 1109-2349) taladró «+z» y la pieza se perdió en ese error.
         "+x": (1, 0, 0), "+y": (0, 1, 0), "+z": (0, 0, 1)}


def _eje(eje) -> "FreeCAD.Vector":
    if isinstance(eje, str):
        if eje not in _EJES:
            raise KitError(f"eje {eje!r} desconocido: usa uno de {sorted(_EJES)} o un vector")
        return FreeCAD.Vector(*_EJES[eje])
    v = _v(eje)
    if v.Length < TOL:
        raise KitError("el eje no puede ser el vector nulo")
    return v.normalize()


def _perpendiculares(d):
    """Dos vectores unitarios perpendiculares a `d` y entre sí."""
    ref = FreeCAD.Vector(1, 0, 0) if abs(d.x) < 0.9 else FreeCAD.Vector(0, 1, 0)
    u = d.cross(ref).normalize()
    return u, d.cross(u).normalize()


def _valido(forma, que):
    """Cada operación se comprueba al hacerse, no al final.

    Fallo real del banco (2026-11-04): FreeCAD extruye un polígono con lados
    que se cruzan, o redondea, devolviendo un sólido NO válido sin lanzar
    ningún error, y el fallo salía al final, sin operación ni línea: tres
    construcciones gastadas en adivinar."""
    if not forma.isValid():
        raise KitError(f"{que} dio un sólido no válido. Suele ser por caras que coinciden "
                       "exactamente (solapa 0.5 mm o sepáralas) o por un perfil cuyos lados "
                       "se cruzan")
    return forma


def _sin_repetidos(p3) -> list:
    """El contorno sin los puntos que repiten al anterior, ni el último si
    repite al primero. El modelo genera sus contornos con bucles y cierra el
    polígono «por si acaso»: la carcasa del encargo 16 (banco 1114-0023)
    perdió así un intento, con un «OCCError: Both points are equal» que no
    le decía nada."""
    limpio = []
    for p in p3:
        if not limpio or (p - limpio[-1]).Length > TOL:
            limpio.append(p)
    if len(limpio) > 1 and (limpio[0] - limpio[-1]).Length <= TOL:
        limpio.pop()
    return limpio


def _cruces(p3) -> list:
    """Pares de lados del polígono que se tocan sin ser contiguos."""
    n = len(p3)
    lados = [Part.LineSegment(p3[i], p3[(i + 1) % n]).toShape() for i in range(n)]
    pares = []
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if lados[i].distToShape(lados[j])[0] < 1e-7:
                pares.append((i + 1, j + 1))
    return pares


def _cara(p3):
    """La cara de un polígono cerrado, comprobando que sus lados no se cruzan:
    FreeCAD la construye igual y el sólido sale no válido."""
    p3 = _sin_repetidos(p3)
    if len(p3) < 3:
        raise KitError("un polígono necesita al menos tres puntos distintos")
    cruces = _cruces(p3)
    if cruces:
        lados = ", ".join(f"{i} y {j}" for i, j in cruces[:4])
        raise KitError(f"el polígono tiene lados que se cruzan (lados {lados}, contando "
                       "desde el primer punto): ordena los puntos siguiendo el contorno")
    try:
        return Part.Face(Part.makePolygon(p3 + [p3[0]]))
    except Exception:
        raise KitError("el polígono no forma una cara: ¿puntos repetidos?") from None


def _un_solido(forma):
    """Una operación booleana devuelve a menudo un compuesto de un solo
    sólido; se desenvuelve. Varios sólidos se dejan: el epílogo los
    rechaza diciendo dónde está cada trozo."""
    if forma.ShapeType == "Compound" and len(forma.Solids) == 1:
        return forma.Solids[0]
    return forma


def _caja(forma):
    """La caja ajustada de una forma. `BoundBox` es holgada en las
    superficies curvas (la saca de sus polos): la carcasa de la prueba a mano
    del 2026-11-13, vaciada por secciones, «empezaba» 1 mm por debajo de su
    base, y `acabar` no encontraba ninguna arista en ella."""
    try:
        return forma.optimalBoundingBox(True)
    except Exception:
        return forma.BoundBox


def _plano_de(d):
    """Los dos ejes (u, v) del plano perpendicular a `d` en los que se dibuja
    una sección, los mismos que usa `extruir`: a lo largo de z, (x, y); de y,
    (x, z); de x, (y, z). Para un eje inclinado, dos perpendiculares."""
    x, y, z = (FreeCAD.Vector(1, 0, 0), FreeCAD.Vector(0, 1, 0), FreeCAD.Vector(0, 0, 1))
    if abs(abs(d.z) - 1) < TOL:
        return x, y
    if abs(abs(d.y) - 1) < TOL:
        return x, z
    if abs(abs(d.x) - 1) < TOL:
        return y, z
    return _perpendiculares(d)


class Seccion:
    """Un contorno cerrado y plano, dibujado en (u, v) alrededor de su centro.
    No es un cuerpo: `kit.transicion` y `kit.barrer` le dan volumen. Guarda
    cómo dibujarse, porque el plano lo pone quien la usa (ADR-022: el modelo
    da los puntos; la curva y la superficie las hace el código)."""

    def __init__(self, hacer) -> None:
        self._hacer = hacer

    def _alambre(self, centro, u, v):
        return self._hacer(centro, u, v)


class Cuerpo:
    """Un sólido. Se combinan con `+` (unir), `-` (restar) y `&` (intersecar)."""

    def __init__(self, forma, kit: "Kit") -> None:
        self._forma = forma
        self._kit = kit
        # Los rasgos con nombre que ya lleva este cuerpo: ver `_sin_rasgos`.
        self._suyos: tuple = ()
        # Cómo se hizo, si es una transición recién hecha: ver `vaciar`.
        self._receta = None

    def _nuevo(self, forma, que="la operación") -> "Cuerpo":
        nuevo = Cuerpo(_valido(_un_solido(forma), que), self._kit)
        nuevo._suyos = self._suyos
        return nuevo

    def _con(self, nombre) -> "Cuerpo":
        self._suyos = (*self._suyos, nombre)
        return self

    def _sin_rasgos(self, que) -> None:
        """Girar o mover un cuerpo no lleva consigo lo que ya tiene nombre:
        el agujero y el componente se quedan medidos donde estaban. El brazo
        superior del brazo mediano (banco 1113-1330) acabó con un `girar` y
        un `mover` al centro de la cama, para dejarlo como se imprime, y todo
        salió «a 377 mm» de la pieza."""
        if self._suyos:
            nombres = ", ".join(f"«{n}»" for n in self._suyos[:3])
            raise KitError(
                f"`{que}` después de {nombres}: lo que ya tiene nombre no se mueve con ella "
                "y quedaría medido donde estaba. Coloca y gira los cuerpos ANTES de "
                "taladrarlos o de quitarles un hueco. Si era para dejarla como se imprime, "
                "no hace falta: la pieza se dibuja donde va montada, y la postura de "
                "impresión se elige al laminar")

    def vaciar(self, grosor, abierta="+z") -> "Cuerpo":
        """Deja el cuerpo en una cáscara de `grosor` mm, hueca y abierta por
        su cara plana que mira hacia `abierta` («+z», «-z», «+x»…). Por fuera
        mide lo mismo. Para carcasas y tapas: dibuja la forma maciza —con
        `transicion`, por ejemplo— y vacíala al final, antes de taladrar."""
        d = _eje(abierta)
        planas = [c for c in self._forma.Faces if c.Surface.TypeId == "Part::GeomPlane"
                  and c.normalAt(*c.Surface.parameter(c.CenterOfMass)).dot(d) > 0.99]
        if not planas:
            raise KitError(f"`vaciar` abre el cuerpo por una cara plana que mire hacia "
                           f"{abierta}, y este no tiene ninguna: elige otro lado en `abierta` "
                           "o córtale antes una cara plana")
        cara = max(planas, key=lambda c: c.CenterOfMass.dot(d))

        def vale(forma):
            return (forma is not None and not forma.isNull() and forma.isValid()
                    and 0 < forma.Volume < self._forma.Volume)
        try:
            forma = self._forma.makeThickness([cara], -float(grosor), 1e-3)
        except Exception:
            forma = None
        if not vale(forma):
            # El «thickness» de FreeCAD no puede con una transición lisa de
            # tres secciones (un carenado: prueba a mano del 2026-11-13).
            forma = self._vaciada_por_secciones(float(grosor), d)
        if not vale(forma):
            raise KitError(f"no se pudo vaciar a {grosor:g} mm: la pared no cabe en alguna "
                           "parte de la forma. Prueba con menos grosor, con curvas más "
                           "abiertas o con secciones más separadas. Una transición se vacía "
                           "recién hecha, antes de unirle nada")
        return self._nuevo(forma, "vaciar")

    def _vaciada_por_secciones(self, grosor, d):
        """La transición de `_receta` menos otra igual, más pequeña, por
        dentro: cada sección encogida el grosor —algo más donde la pared se
        inclina, para que no adelgace— y la punta cerrada, un grosor antes.
        None si este cuerpo no es una transición recién hecha o no se puede."""
        if self._receta is None:
            return None
        tramos, eje, base, u, v, recta = self._receta
        hacia = d.dot(eje)
        if abs(abs(hacia) - 1) > 1e-6:
            return None
        alambres = [(sec._alambre(base + eje * h, u, v), h) for sec, h in tramos]

        def medio(w, k):
            caja = w.BoundBox
            return max(abs((p - base).dot(k)) for p in (
                FreeCAD.Vector(caja.XMin, caja.YMin, caja.ZMin),
                FreeCAD.Vector(caja.XMax, caja.YMax, caja.ZMax)))

        def inclinacion(i, j):
            (a, ha), (b, hb) = alambres[i], alambres[j]
            return max(abs(medio(a, k) - medio(b, k)) for k in (u, v)) / abs(hb - ha)

        n = len(alambres)
        cerrada = 0 if hacia > 0 else n - 1
        dentro = []
        for i, (w, h) in enumerate(alambres):
            vecinas = [inclinacion(i, j) for j in (i - 1, i + 1) if 0 <= j < n]
            encoge = grosor * math.sqrt(1 + max(vecinas) ** 2)
            if i == cerrada:
                # La punta cerrada se queda un grosor más adentro, y ahí la
                # forma de fuera ya ha cambiado lo que cambia en ese grosor.
                encoge += max(vecinas) * grosor
                h += grosor if hacia > 0 else -grosor
            try:
                menor = w.makeOffset2D(-encoge)
            except Exception:
                return None
            if menor.isNull() or not menor.isClosed():
                return None
            menor.translate(eje * (h - alambres[i][1]))
            dentro.append((menor, h))
        if any(b[1] <= a[1] for a, b in zip(dentro, dentro[1:])):
            return None
        # Por la punta abierta el hueco sale 1 mm, para que corte limpio.
        abierta = dentro[-1] if hacia > 0 else dentro[0]
        fuera = abierta[0].copy()
        fuera.translate(eje * (1.0 if hacia > 0 else -1.0))
        dentro = dentro + [(fuera, 0)] if hacia > 0 else [(fuera, 0)] + dentro
        try:
            hueco = Part.makeLoft([w for w, _ in dentro], True, bool(recta))
            if hueco.Volume < 0:
                hueco.reverse()
            return _un_solido(self._forma.cut(hueco))
        except Exception:
            return None

    def __add__(self, otro: "Cuerpo") -> "Cuerpo":
        nuevo = self._nuevo(self._forma.fuse(otro._forma).removeSplitter(), "la unión (+)")
        nuevo._suyos = (*self._suyos, *otro._suyos)
        return nuevo

    def __sub__(self, otro: "Cuerpo") -> "Cuerpo":
        return self._nuevo(self._forma.cut(_herramienta(otro, self)).removeSplitter(),
                           "la resta (-)")

    def __and__(self, otro: "Cuerpo") -> "Cuerpo":
        return self._nuevo(self._forma.common(otro._forma).removeSplitter(),
                           "la intersección (&)")

    # --- colocar --------------------------------------------------------------

    def mover(self, dx=0.0, dy=0.0, dz=0.0) -> "Cuerpo":
        """Copia desplazada."""
        self._sin_rasgos("mover")
        f = self._forma.copy()
        f.translate(FreeCAD.Vector(dx, dy, dz))
        return self._nuevo(f)

    def girar(self, grados, eje="z", centro=(0, 0, 0)) -> "Cuerpo":
        """Copia girada `grados` alrededor de `eje` (que pasa por `centro`)."""
        self._sin_rasgos("girar")
        f = self._forma.copy()
        f.rotate(_v(centro), _eje(eje), float(grados))
        return self._nuevo(f)

    def espejo(self, plano="yz", por=(0, 0, 0), conservar=True) -> "Cuerpo":
        """Simetría respecto a un plano (`yz` refleja la x). Con `conservar`,
        devuelve el original unido a su reflejo: así salen las piezas simétricas."""
        normal = {"yz": (1, 0, 0), "xz": (0, 1, 0), "xy": (0, 0, 1)}.get(plano)
        if normal is None:
            raise KitError("el plano del espejo es `yz`, `xz` o `xy`")
        reflejo = self._nuevo(self._forma.mirror(_v(por), FreeCAD.Vector(*normal)))
        return self + reflejo if conservar else reflejo

    def caja_envolvente(self) -> tuple:
        """(xmin, ymin, zmin, xmax, ymax, zmax) del cuerpo, para colocar lo siguiente."""
        b = _caja(self._forma)
        return (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)

    # --- acabado ----------------------------------------------------------------

    def _aristas(self, aristas, dentro):
        b = _caja(self._forma)
        elegidas = []
        for i, e in enumerate(self._forma.Edges):
            eb = e.BoundBox
            recta = len(e.Vertexes) == 2 and e.Curve.TypeId == "Part::GeomLine"
            d = (e.Vertexes[1].Point - e.Vertexes[0].Point) if recta else None
            if d is not None and d.Length > TOL:
                d = d.normalize()
            if aristas == "todas":
                ok = True
            elif aristas == "verticales":
                ok = recta and abs(abs(d.z) - 1) < 1e-6
            elif aristas == "horizontales":
                ok = recta and abs(d.z) < 1e-6
            elif aristas == "base":
                ok = eb.ZMax <= b.ZMin + 1e-4
            elif aristas == "casi base":
                # Lo que queda a menos de una capa del fondo sin estar en él.
                ok = b.ZMin + 1e-4 < eb.ZMax <= b.ZMin + BASE_MM
            elif aristas == "arriba":
                ok = eb.ZMin >= b.ZMax - 1e-4
            else:
                raise KitError("`aristas` es «todas», «verticales», «horizontales», "
                               f"«base» o «arriba», no {aristas!r}")
            if ok and dentro is not None:
                (x0, y0, z0), (x1, y1, z1) = dentro
                ok = (eb.XMin >= x0 - 1e-4 and eb.XMax <= x1 + 1e-4 and eb.YMin >= y0 - 1e-4
                      and eb.YMax <= y1 + 1e-4 and eb.ZMin >= z0 - 1e-4 and eb.ZMax <= z1 + 1e-4)
            if ok:
                elegidas.append(i)
        if not elegidas:
            donde = f" dentro de {dentro}" if dentro else ""
            raise KitError(f"ninguna arista «{aristas}»{donde}: no hay nada que redondear")
        return elegidas

    def _acabar(self, operacion, medida, elegidas, aristas, respaldo=False) -> "Cuerpo":
        """Redondeo o chaflán, y si no cabe en todas las aristas a la vez, en
        las que se pueda: las demás quedan vivas, con un aviso.

        Fallo real del banco (2026-11-04): el soporte del MG996R y el clip se
        construían con todos sus agujeros y morían en el redondeo de acabado,
        porque R1 no cabía en alguna arista. El acabado es estética; la
        función manda, y una pieza buena no se tira por una arista."""
        nombre = "makeFillet" if operacion == "redondear" else "makeChamfer"
        limite = time.monotonic() + ACABADO_MAX_S

        def hacer(aristas):
            """`aristas` son índices. Cada intento trabaja sobre su propia
            COPIA de la forma: OCC ajusta tolerancias de la forma sobre la que
            redondea, y en la escuadra de repisa los intentos sobre la misma
            forma estropeaban uno que ya había salido válido (2026-11-04)."""
            base = self._forma.copy()
            try:
                f = _un_solido(getattr(base, nombre)(float(medida),
                                                     [base.Edges[i] for i in aristas]))
            except Exception:
                return None
            # Lo mismo que comprueba `_nuevo` después: un compuesto válido
            # puede envolver un sólido que no lo es (la escuadra de repisa).
            return f if f.isValid() else None

        def caben_de(aristas):
            """(aristas que admiten el acabado, la forma ya acabada), partiendo
            por la mitad lo que falla: de una en una eran 90 s en la escuadra
            de repisa, y FreeCAD pasaba de su tiempo (2026-11-04). Se guarda la
            forma y no solo las aristas: rehacer el mismo chaflán dio una vez
            un sólido no válido (OCC no siempre es determinista)."""
            if not aristas or time.monotonic() > limite:
                return [], None
            forma = hacer(aristas)
            if forma is not None:
                return list(aristas), forma
            if len(aristas) == 1:
                return [], None
            mitad = len(aristas) // 2
            a, fa = caben_de(aristas[:mitad])
            b, fb = caben_de(aristas[mitad:])
            juntas = hacer(a + b) if a and b else None
            if juntas is not None:
                return a + b, juntas
            return (a, fa) if len(a) >= len(b) else (b, fb)

        forma = hacer(elegidas)
        if forma is not None and forma.isValid():
            return Cuerpo(forma, self._kit)
        caben, forma = caben_de(elegidas)
        # Se vuelve a mirar al final: en la escuadra de repisa, un chaflán que
        # salió válido durante la búsqueda ya no lo era al terminarla, tras
        # más intentos sobre la misma forma (2026-11-04). El acabado nunca
        # rompe la pieza: si no queda válido, no se aplica.
        hecha = next((c for c in (forma, hacer(caben) if caben else None)
                      if c is not None and c.isValid()), None)
        if hecha is None:
            caben = []
        faltan = [i for i in elegidas if i not in set(caben)]
        cortadas = []
        if respaldo and faltan:
            hecha, cortadas = self._chaflan_por_corte(hecha or self._forma, faltan, medida)
        if hecha is None:
            self._kit._avisos.append(
                f"{operacion} {medida:g} mm en las aristas «{aristas}»: no se pudo aplicar sin "
                "romper la pieza, y se omite")
            return self
        vivas = len(faltan) - len(cortadas)
        en_su_lugar = (f"{len(cortadas)} llevan en su lugar un chaflán de {medida:g} mm, "
                       if cortadas else "")
        self._kit._avisos.append(
            f"{operacion} {medida:g} mm: {len(faltan)} de {len(elegidas)} aristas «{aristas}» "
            f"no lo admitían; {en_su_lugar}{vivas} quedaron vivas")
        return Cuerpo(hecha, self._kit)

    def _chaflan_por_corte(self, sobre, indices, lado):
        """Resta de `sobre` el prisma del chaflán de cada arista `indices` de
        ESTA forma (ver `prisma_de_chaflan`): todos a la vez y, si eso no
        sale, de uno en uno. Devuelve (forma, índices que se cortaron); la
        forma es None si `sobre` lo era y no salió ninguno."""
        prismas = {}
        for i in indices:
            prisma = prisma_de_chaflan(self._forma, self._forma.Edges[i], float(lado))
            if prisma is not None:
                prismas[i] = prisma

        def cortar(forma, ps):
            try:
                herramienta = ps[0] if len(ps) == 1 else ps[0].multiFuse(ps[1:])
                r = _un_solido(forma.cut(herramienta).removeSplitter())
            except Exception:
                return None
            if r.ShapeType != "Solid" or not r.isValid():
                return None
            # Un corte que se lleva más que sus prismas ha partido la pieza.
            if forma.Volume - r.Volume > sum(p.Volume for p in ps) + 1e-6:
                return None
            return r

        if sobre is None or not prismas:
            return sobre, []
        todas = cortar(sobre, list(prismas.values()))
        if todas is not None:
            return todas, list(prismas)
        limite = time.monotonic() + ACABADO_MAX_S
        hechas = []
        for i, prisma in prismas.items():
            if time.monotonic() > limite:
                break
            r = cortar(sobre, [prisma])
            if r is not None:
                sobre, hechas = r, [*hechas, i]
        return sobre, hechas

    def redondear(self, radio, aristas="verticales", dentro=None) -> "Cuerpo":
        """Redondea con `radio` las aristas elegidas: «todas», «verticales»,
        «horizontales», «base» (las que tocan la cama) o «arriba». `dentro`
        acota a una caja ((x0, y0, z0), (x1, y1, z1)). Si el radio no cabe en
        alguna arista, esa queda viva y se avisa."""
        return self._acabar("redondear", radio, self._aristas(aristas, dentro), aristas)

    def achaflanar(self, distancia, aristas="base", dentro=None) -> "Cuerpo":
        """Chaflán de `distancia` en las aristas elegidas (como `redondear`).
        0.5 mm en la «base» evita la pata de elefante."""
        return self._acabar("achaflanar", distancia, self._aristas(aristas, dentro), aristas)

    def acabar(self, radio=1.0, chaflan_base=0.5) -> "Cuerpo":
        """El acabado de producto, en una llamada, AL FINAL: chaflán de
        `chaflan_base` en las aristas que tocan la cama (contra la pata de
        elefante; un redondeo abajo sería un voladizo) y redondeo de `radio`
        en todas las demás. Donde OCC no puede, la arista recta lleva un
        chaflán por corte del mismo tamaño, y si tampoco, queda viva; todo
        con un aviso. En el banco (2026-11-04) entre el 36 % y el 63 % de las
        aristas quedaban vivas: se redondeaban las verticales y nada más."""
        # Con respaldo: lo que OCC no acaba se achaflana con un corte (ver
        # `prisma_de_chaflan`). Solo aquí: `redondear` y `achaflanar` hacen
        # lo que se les pide o avisan, sin cambiar un redondeo por otra cosa.
        pieza = (self._acabar("achaflanar", chaflan_base, self._aristas("base", None), "base",
                              respaldo=True) if chaflan_base else self)
        # Y la base que queda a menos de una capa del fondo, aparte: la
        # carcasa del encargo 16 (banco 1114-0023) apoyaba en un borde fino y
        # el resto de su base, 0,18 mm más arriba por la holgura con el
        # soporte, se quedaba sin chaflán ni redondeo: «quedan vivas» en
        # veinte intentos. Juntas, FreeCAD no achaflana ninguna.
        if chaflan_base:
            try:
                casi = pieza._aristas("casi base", None)
            except KitError:
                casi = []
            if casi:
                pieza = pieza._acabar("achaflanar", chaflan_base, casi, "base", respaldo=True)
        z0 = _caja(pieza._forma).ZMin + BASE_MM
        # Todas menos las que quedan ENTERAS en la franja del chaflán. Con una
        # caja «por encima del chaflán» se quedaban fuera las verticales, que
        # empiezan justo en él (test de la escalera, 2026-11-04).
        franja = z0 + (chaflan_base or 0) + 0.05
        # Y solo las esquinas: redondear un rincón añade material y estrecha
        # las ventanas y los encajes (ver `convexa`).
        forma = pieza._forma
        elegidas = [i for i, e in enumerate(forma.Edges)
                    if e.BoundBox.ZMax > franja and convexa(forma, e)]
        if not elegidas:
            return pieza
        return pieza._acabar("redondear", radio, elegidas, "todas menos la base",
                             respaldo=True)

    def _cortar(self, nombre, herramienta) -> "Cuerpo":
        """Quita un rasgo con nombre, comprobando que de verdad quita algo.

        Fallo real del banco (2026-11-04): el gancho taladraba a 40 mm en una
        placa de 30 de alto; un agujero caía fuera y la pieza salía sin él,
        en silencio. Un rasgo que no toca la pieza es un error de posición."""
        resultado = self._forma.cut(herramienta).removeSplitter()
        if self._forma.Volume - resultado.Volume < 1e-6:
            b = self._forma.BoundBox
            raise KitError(
                f"«{nombre}» no toca la pieza: no quita material. La pieza ocupa x de "
                f"{b.XMin:.4g} a {b.XMax:.4g}, y de {b.YMin:.4g} a {b.YMax:.4g}, z de "
                f"{b.ZMin:.4g} a {b.ZMax:.4g}; revisa `en` y `eje`")
        return self._nuevo(resultado, f"«{nombre}»")._con(nombre)

    # --- rasgos con nombre --------------------------------------------------------

    def taladrar(self, nombre, diametro, en, eje="-z", profundidad=None,
                 lagrima=False, avellanado=None, _tornillo=None, _uso=None) -> "Cuerpo":
        """Agujero de `diametro` que entra por el punto `en` y avanza en la
        dirección `eje`. Sin `profundidad` atraviesa todo lo que encuentra.
        `lagrima=True` para agujeros horizontales: se imprimen sin soporte.
        `avellanado`: diámetro de la cabeza del tornillo, para que quede enrasada."""
        d = _eje(eje)
        base = _v(en)
        r = float(diametro) / 2
        largo = LARGO if profundidad is None else float(profundidad)
        # Un milímetro hacia atrás: el corte empieza fuera de la cara y no deja
        # caras coincidentes, que es de donde salen los sólidos defectuosos.
        broca = Part.makeCylinder(r, largo + 1, base - d * 1, d)
        if lagrima:
            arriba = FreeCAD.Vector(0, 0, 1)
            if abs(d.dot(arriba)) > 0.99:
                raise KitError(f"«{nombre}»: la lágrima es para agujeros horizontales, "
                               "y este es vertical")
            # La punta mira hacia +z, perpendicular al eje del agujero: el
            # techo del agujero se imprime a 45° en vez de en puente.
            hacia = (arriba - d * arriba.dot(d)).normalize()
            lado = d.cross(hacia).normalize()
            c = base - d * 1
            k = r / math.sqrt(2)
            puntos = [c, c + lado * k + hacia * k, c + hacia * (r * math.sqrt(2)),
                      c - lado * k + hacia * k, c]
            broca = broca.fuse(Part.Face(Part.makePolygon(puntos)).extrude(d * (largo + 1)))
        if avellanado is not None:
            D = float(avellanado)
            if D <= diametro:
                raise KitError(f"«{nombre}»: el avellanado ({D:g}) tiene que ser mayor que "
                               f"el agujero ({diametro:g})")
            alto = (D - float(diametro)) / 2   # cono de 90°
            broca = broca.fuse(Part.makeCone(D / 2 + 1, r, alto + 1, base - d * 1, d))
        self._kit._registrar(nombre, "agujero", diametro_mm=float(diametro),
                             entrada=list(base), eje=list(d),
                             profundidad_mm=None if profundidad is None else float(profundidad),
                             lagrima=bool(lagrima), avellanado_mm=avellanado,
                             **({"tornillo": str(_tornillo)} if _tornillo else {}),
                             **({"uso": _uso} if _uso else {}))
        return self._cortar(nombre, broca)

    def tornillo(self, nombre, metrica, en, eje="-z", tipo="pasante", profundidad=None,
                 lagrima=False, avellanado=None) -> "Cuerpo":
        """Agujero para un tornillo con el diámetro DEL PERFIL: `tipo` es
        «pasante» (`<M>_through_mm`), «rosca» (rosca directa en plástico,
        `<M>_selftap_mm`) o «inserto» (inserto térmico, `<M>_insert_mm`)."""
        sufijo = {"pasante": "through", "rosca": "selftap", "inserto": "insert"}.get(tipo)
        if sufijo is None:
            raise KitError(f"«{nombre}»: `tipo` es «pasante», «rosca» o «inserto», no {tipo!r}")
        d = self._kit.agujero_mm(f"{metrica}_{sufijo}")
        # La métrica va en el rasgo: con ella se comprueba que la cabeza
        # llega (proyecto del 608ZZ, 2026-11-09). Y para qué es: un agujero
        # de inserto y uno de rosca son dos ciegos que solo se distinguen
        # por el diámetro, y el plan aprobó uno de los dos (F9.6 (previsto)).
        return self.taladrar(nombre, d, en, eje=eje, profundidad=profundidad,
                             lagrima=lagrima, avellanado=avellanado, _tornillo=metrica,
                             _uso=tipo)

    def tuerca(self, nombre, metrica, en, eje="-z", profundidad=None) -> "Cuerpo":
        """Alojamiento hexagonal para una tuerca cautiva, con la entrecaras del
        perfil (`<M>_nut_af_mm`). Entra por `en` y avanza en `eje`;
        `profundidad` por defecto, el alto de una tuerca (0.8 × métrica)."""
        entrecaras = self._kit.agujero_mm(f"{metrica}_nut_af")
        if profundidad is None:
            try:
                profundidad = 0.8 * float(str(metrica).lstrip("Mm"))
            except ValueError:
                raise KitError(f"«{nombre}»: di la `profundidad` de la tuerca {metrica}") from None
        hueco = self._kit._prisma_hexagonal(entrecaras, float(profundidad) + 1,
                                            _v(en) - _eje(eje) * 1, _eje(eje))
        # Con su métrica: la tornillería la leía del rasgo y el rasgo no la
        # llevaba, así que una tuerca sola no decía de qué tornillo era.
        self._kit._registrar(nombre, "tuerca", entrecaras_mm=entrecaras, entrada=list(_v(en)),
                             eje=list(_eje(eje)), profundidad_mm=float(profundidad),
                             metrica=str(metrica))
        return self._cortar(nombre, hueco)

    def colisa(self, nombre, ancho, desde, hasta, eje="-z", profundidad=None) -> "Cuerpo":
        """Agujero alargado entre `desde` y `hasta` (los centros de los
        extremos), de `ancho`: para tornillos que necesitan ajuste."""
        d = _eje(eje)
        a, b = _v(desde), _v(hasta)
        u = b - a
        u = u - d * u.dot(d)
        if u.Length < TOL:
            raise KitError(f"«{nombre}»: `desde` y `hasta` tienen que separarse en el plano "
                           "perpendicular al eje")
        largo = LARGO if profundidad is None else float(profundidad)
        n = d.cross(u).normalize() * (float(ancho) / 2)
        a0, b0 = a - d * 1, a - d * 1 + u
        rect = Part.Face(Part.makePolygon([a0 + n, b0 + n, b0 - n, a0 - n, a0 + n]))
        hueco = rect.extrude(d * (largo + 1))
        for c in (a0, b0):
            hueco = hueco.fuse(Part.makeCylinder(float(ancho) / 2, largo + 1, c, d))
        self._kit._registrar(nombre, "colisa", ancho_mm=float(ancho), desde=list(a),
                             hasta=list(a + u), eje=list(d))
        return self._cortar(nombre, hueco)

    def quitar(self, nombre, herramienta: "Cuerpo") -> "Cuerpo":
        """Resta `herramienta` y lo registra como un hueco con nombre (una
        ventana para un servo, una cajera): así se puede medir después."""
        forma = _herramienta(herramienta, self)
        b = forma.BoundBox
        self._kit._registrar(nombre, "hueco", desde=[b.XMin, b.YMin, b.ZMin],
                             hasta=[b.XMax, b.YMax, b.ZMax])
        forma = _recortada(forma, self._forma)
        # Un componente que solo se apoya en la pieza (la Pi sobre sus
        # separadores) no le quita nada, y está bien. Uno que ni la toca sí
        # es un error de posición, como cualquier rasgo.
        # Una pieza vecina de la obra puede ir al lado sin tocar, como admite
        # la sonda: la polea del 608ZZ (banco 1110-0128) va 4 mm sobre el
        # soporte, le pedían quitar su hueco, fallaba aquí, y en cinco
        # intentos acabó sin colocarlo y metida en él.
        if isinstance(herramienta, Hueco) and (
                herramienta._componente._toca(self._forma)
                or herramienta._componente._ficha.get("origen") == "impreso"):
            resultado = self._forma.cut(forma).removeSplitter()
            if self._forma.Volume - resultado.Volume < 1e-6:
                return self._nuevo(self._forma)._con(nombre)
        return self._cortar(nombre, forma)


def _recortada(herramienta, pieza):
    """Lo que de `herramienta` cae cerca de `pieza` (su caja y 1 mm): restar
    eso es restar lo mismo. Banco 1110-0313: el hueco del soporte de giro
    lleva el camino de entrada de su SG90, de 2 m, y restarlo de la
    plataforma, de 40 mm, daba «Null shape» en OCC, también con tolerancia;
    recortado, la resta sale exacta. Si recortar falla, la entera."""
    b, m = pieza.BoundBox, 1.0
    caja = Part.makeBox(b.XLength + 2 * m, b.YLength + 2 * m, b.ZLength + 2 * m,
                        FreeCAD.Vector(b.XMin - m, b.YMin - m, b.ZMin - m))
    try:
        cerca = herramienta.common(caja)
        if not cerca.isNull() and cerca.isValid():
            return cerca
    except Exception:   # OCC lanza Part.OCCError o RuntimeError según la versión
        pass
    return herramienta


class Hueco(Cuerpo):
    """El hueco de un componente (`Componente.hueco`). Restado de una pieza
    con `quitar` o `-`, se rehace contra ELLA: sin holgura en las caras con
    que el componente solo se apoya en la pieza (ver `Componente._lados`).
    Movido o combinado, es un cuerpo como cualquier otro."""

    def __init__(self, forma, kit, componente, holgura) -> None:
        super().__init__(forma, kit)
        self._componente, self._holgura = componente, holgura


def _herramienta(cuerpo, pieza):
    if isinstance(cuerpo, Hueco):
        return cuerpo._componente._forma_hueco(cuerpo._holgura, pieza._forma)
    return cuerpo._forma


class Componente:
    """Un componente comprado colocado en la pieza (F6.11 (biblioteca)).

    Su forma sale de la ficha de la biblioteca, no del programa: el soporte
    del HC-SR04 (2026-11-05) dibujó el sensor con cajas y números de una
    tienda, y el sensor real no entraba. Aquí el programa solo dice dónde va
    y por dónde entra."""

    def __init__(self, ficha: dict, en, giros, entra_por, kit) -> None:
        self._ficha, self._en, self._giros = ficha, [float(c) for c in en], giros
        self._entra_por, self._kit = entra_por, kit

    def hueco(self, holgura="slide") -> "Cuerpo":
        """Lo que hay que quitar a la pieza para que el componente quepa, se
        pueda meter viniendo desde `entra_por` y quede libre lo que su ficha
        pide (cable, haz, enchufes). `holgura`: «press», «slide», «clearance»
        (del perfil, en diámetro) o un número en mm. Úsalo con
        `pieza.quitar("nombre", componente.hueco())`. Un rodamiento sale
        macizo: si lleva eje impreso, añádelo después de quitar el hueco."""
        h = float(holgura) if isinstance(holgura, (int, float)) else self._kit.holgura(holgura)
        return Hueco(self._forma_hueco(h), self._kit, self, h)

    def _forma_hueco(self, h, pieza=None):
        """El hueco con holgura `h` (en diámetro). Con `pieza`, sin holgura
        en las caras de apoyo (`_lados`)."""
        from mech_toolkit.componentes import EJES, barrido, primitivas, solido

        d = EJES[self._entra_por]
        formas = []
        for c in primitivas(self._ficha, self._en, self._giros, "cuerpos"):
            if c["tipo"] == "step":
                # Una pieza impresa deja el hueco de su FORMA con holgura, sin
                # barrer. Era su envolvente barrida por `entra_por`, y a la
                # plataforma del pan-tilt (2026-11-09) le cortó el cuello a
                # 17 mm del cuerno, que está dentro de la envolvente del
                # soporte. Si la pieza entra de verdad lo mide
                # `componente_entra`, con la forma real paso a paso.
                formas.append(solido(c, crecer=h / 2))
                continue
            lados = self._lados(c, h, pieza)
            if c["tipo"] == "caja":
                c = {**c, "min": [a - lo for a, (lo, _) in zip(c["min"], lados)],
                     "max": [b + hi for b, (_, hi) in zip(c["max"], lados)]}
            else:
                (lo, hi), = lados
                c = {**c, "interior": None, "diametro": c["diametro"] + h,
                     "alto": c["alto"] + lo + hi,
                     "base": [b - e * lo for b, e in zip(c["base"], c["eje"])]}
            formas.append(barrido(c, d, LARGO))
        # Las caras de lo que gira (`gira_con`) no se tallan: tallar las de los
        # dos aros dejaría el rodamiento sin apoyo; cuál se libra lo decide
        # el diseño, y la sonda lo comprueba.
        formas += [solido({**c, "interior": None})
                   for c in primitivas(self._ficha, self._en, self._giros, "despejar")
                   if not c.get("gira_con")]
        forma = formas[0]
        for f in formas[1:]:
            forma = forma.fuse(f)
        return forma.removeSplitter()

    def _toca(self, pieza) -> bool:
        """Si algún cuerpo del componente toca la pieza o se mete en ella."""
        from mech_toolkit.componentes import primitivas, solido

        return any(pieza.distToShape(solido({**c, "interior": None}))[0] < 1e-3
                   for c in primitivas(self._ficha, self._en, self._giros, "cuerpos"))

    @staticmethod
    def _lados(c, h, pieza):
        """La holgura de cada cara de la primitiva `c`: [(menos, más)] por eje
        de la caja, o [(base, punta)] a lo largo del eje del cilindro (en el
        radio siempre lleva). h/2 en todas, salvo en las caras de APOYO: la
        primitiva queda entera fuera de la pieza y la toca por ese lado.

        Ahí la holgura no ajusta nada: talla un rebaje de h/2 que no se
        imprime y cuyas aristas OCC no sabe redondear. Banco `1105-2120`
        (2026-11-05): 0.1 mm bajo el NEMA 17, en la cara de la cama, y en el
        respaldo contra el perfil 2020 del HC-SR04. Una primitiva que se mete
        en la pieza (el resalte del motor en su alojamiento, un PCB entre
        guías) talla su propio hueco y lleva holgura en todas sus caras."""
        from mech_toolkit.componentes import solido

        mitad = h / 2
        caja = c["tipo"] == "caja"
        todas = [(mitad, mitad)] * (3 if caja else 1)
        if pieza is None or h <= 0:
            return todas
        if pieza.common(solido({**c, "interior": None})).Volume > 1e-3:
            return todas

        def toca(lamina):
            return pieza.common(solido(lamina)).Volume > 1e-4

        if caja:
            lados = []
            for n in range(3):
                bajo = {**c, "max": [c["min"][k] if k == n else c["max"][k] for k in range(3)],
                        "min": [c["min"][k] - mitad if k == n else c["min"][k]
                                for k in range(3)]}
                alto = {**c, "min": [c["max"][k] if k == n else c["min"][k] for k in range(3)],
                        "max": [c["max"][k] + mitad if k == n else c["max"][k]
                                for k in range(3)]}
                lados.append((0.0 if toca(bajo) else mitad, 0.0 if toca(alto) else mitad))
            return lados
        e = c["eje"]
        base = {**c, "interior": None, "alto": mitad,
                "base": [b - k * mitad for b, k in zip(c["base"], e)]}
        punta = {**c, "interior": None, "alto": mitad,
                 "base": [b + k * c["alto"] for b, k in zip(c["base"], e)]}
        return [(0.0 if toca(base) else mitad, 0.0 if toca(punta) else mitad)]

    def agujeros(self) -> list:
        """Los agujeros de fijación de la ficha, ya colocados en la pieza:
        [{"nombre", "diametro", "en", "eje", "tornillo", "dentro_mm"}]. `en`
        es el centro del agujero en la cara del componente; `eje`, hacia
        dónde va el tornillo; `tornillo`, su métrica si la ficha la dice
        («M2») y `dentro_mm`, cuánto de él queda dentro del componente
        desde `en` (el grueso de la oreja de un servo)."""
        from mech_toolkit.componentes import colocar, orientar

        return [{"nombre": a["nombre"], "diametro": float(a["diametro"]),
                 "en": tuple(colocar(a["en"], self._en, self._giros)),
                 "eje": tuple(orientar(a["eje"], self._giros)),
                 "tornillo": a.get("tornillo") or "",
                 "dentro_mm": float(a.get("dentro_mm") or 0.0)}
                for a in self._ficha.get("fijacion") or []]

    def punto(self, nombre) -> tuple:
        """Dónde queda en la pieza el agujero de fijación `nombre` de la ficha."""
        for a in self.agujeros():
            if a["nombre"] == nombre:
                return a["en"]
        raise KitError(f"{self._ficha['id']} no tiene un agujero «{nombre}»; tiene: "
                       f"{', '.join(a['nombre'] for a in self.agujeros()) or 'ninguno'}")

    def salidas(self) -> list:
        """Lo que el componente mueve (el eje de un servo, el aro de un
        rodamiento), ya colocado en la pieza: [{"nombre", "punto", "eje",
        "recorrido", "largo", "acople"}]. `punto` es donde el eje sale del
        componente y `eje`, hacia dónde sale: lo que se acople a él gira
        alrededor de esa recta. Una pieza del backlog ya terminada trae las
        de lo que monta, con el nombre de su componente delante («sg90:
        eje»). `acople` es aquello a lo que se atornilla lo que gira (el
        cuerno de un servo), o None: {"nombre", "cubo_diametro",
        "cubo_alto", "grosor", "brazos", "de_punta_a_punta", "agujeros":
        [{"radio", "diametro"}]}. Cada agujero está a `radio` del eje, en
        cada brazo; los brazos van en la dirección que elijas, repartidos
        por igual alrededor del eje."""
        from mech_toolkit.componentes import colocar, orientar

        return [{"nombre": s["nombre"],
                 "punto": tuple(colocar(s["en"], self._en, self._giros)),
                 "eje": tuple(orientar(s["eje"], self._giros)),
                 "recorrido": tuple(s["recorrido"]), "largo": float(s.get("largo") or 0.0),
                 "acople": s.get("acople")}
                for s in self._ficha.get("salidas") or []]

    def salida(self, nombre=None) -> dict:
        """Una salida del componente, ya colocada (ver `salidas`): el eje
        sobre el que gira la pieza que se acopla a él. Sin `nombre`, la única
        que tenga."""
        todas = self.salidas()
        hay = ", ".join(f"«{s['nombre']}»" for s in todas) or "ninguna"
        if nombre is None:
            if len(todas) != 1:
                raise KitError(f"{self._ficha['id']} no tiene una sola salida; tiene: {hay}")
            return todas[0]
        for s in todas:
            if s["nombre"] == nombre:
                return s
        raise KitError(f"{self._ficha['id']} no tiene una salida «{nombre}»; tiene: {hay}")

    def envolvente(self) -> tuple:
        """((xmin, ymin, zmin), (xmax, ymax, zmax)) de los cuerpos del
        componente, ya colocado: para poner paredes y apoyos a su alrededor."""
        from mech_toolkit.componentes import primitivas

        mins, maxs = [], []
        for c in primitivas(self._ficha, self._en, self._giros, "cuerpos"):
            if c["tipo"] in ("caja", "step"):
                mins.append(c["min"])
                maxs.append(c["max"])
            else:
                r = c["diametro"] / 2
                fin = [b + e * c["alto"] for b, e in zip(c["base"], c["eje"])]
                mins.append([min(a, b) - (0 if e else r)
                             for a, b, e in zip(c["base"], fin, c["eje"])])
                maxs.append([max(a, b) + (0 if e else r)
                             for a, b, e in zip(c["base"], fin, c["eje"])])
        return (tuple(min(m[n] for m in mins) for n in range(3)),
                tuple(max(m[n] for m in maxs) for n in range(3)))


class Kit:
    """Las piezas de partida. Cada una devuelve un `Cuerpo`."""

    def __init__(self, perfil: dict | None = None, fichas: dict | None = None,
                 ajenos: dict | None = None) -> None:
        self.perfil = perfil or {}
        self._fichas = fichas or {}
        # En un backlog, lo comprado que monta otra pieza: {id: {cuantos, mensaje}}.
        self._ajenos = ajenos or {}
        self._rasgos: list[dict] = []
        self._avisos: list[str] = []

    def _registrar(self, nombre, tipo, **datos) -> None:
        if not isinstance(nombre, str) or not nombre:
            raise KitError("cada agujero, tuerca, colisa o hueco necesita un nombre")
        if any(r["nombre"] == nombre for r in self._rasgos):
            raise KitError(f"ya hay un rasgo llamado «{nombre}»: los nombres son únicos")
        self._rasgos.append({"nombre": nombre, "tipo": tipo, **datos})

    def rasgos(self) -> list:
        """Los rasgos con nombre registrados hasta ahora."""
        return [dict(r) for r in self._rasgos]

    # --- del perfil -----------------------------------------------------------------

    def agujero_mm(self, nombre) -> float:
        """Un diámetro de la tabla `holes` del perfil: «M3_through», «M3_insert»…"""
        tabla = self.perfil.get("holes", {})
        clave = f"{nombre}_mm"
        if clave not in tabla:
            raise KitError(f"el perfil no tabula {nombre!r}; tiene: "
                           f"{', '.join(sorted(k[:-3] for k in tabla)) or 'nada'}")
        return float(tabla[clave])

    def holgura(self, ajuste) -> float:
        """Holgura en diámetro del perfil: «press», «slide» o «clearance»."""
        tabla = self.perfil.get("fits", {})
        clave = f"{ajuste}_mm"
        if clave not in tabla:
            raise KitError(f"el perfil no define el ajuste {ajuste!r}; tiene: "
                           f"{', '.join(sorted(k[:-3] for k in tabla)) or 'nada'}")
        return float(tabla[clave])

    # --- componentes comprados ------------------------------------------------------

    def componente(self, id, en=(0, 0, 0), girar=(), entra_por="+z",
                   nombre=None) -> Componente:
        """Coloca un componente comprado de la biblioteca (un sensor, una
        placa, un servo, un motor, un perfil, un rodamiento). Su forma sale
        de su ficha: nunca lo dibujes con cajas. `en`: dónde va el origen de
        la ficha; `girar`: cuartos de vuelta, p. ej. [("z", 90)]; `entra_por`:
        desde dónde se mete («+z»: bajando desde arriba; «+y»: desde delante,
        hacia -y). Después, `pieza.quitar(..., componente.hueco())`."""
        from mech_toolkit.componentes import EJES, primitivas

        if id not in self._fichas:
            raise KitError(f"no hay ficha de «{id}» en la biblioteca; hay: "
                           f"{', '.join(sorted(self._fichas)) or 'ninguna'}")
        if entra_por not in EJES:
            raise KitError(f"`entra_por` es uno de {', '.join(EJES)}, no {entra_por!r}")
        # Banco 1109-1949: la plataforma del pan-tilt colocó el SG90 que ya
        # montaba el soporte de giro, y quedaron tres servos en uno de dos.
        if id in self._ajenos:
            puestos = sum(1 for r in self._rasgos
                          if r["tipo"] == "componente" and r.get("ficha") == id)
            if puestos >= self._ajenos[id]["cuantos"]:
                raise KitError(self._ajenos[id]["mensaje"])
        giros = [[str(e), float(g)] for e, g in girar]
        try:
            primitivas(self._fichas[id], en, giros)
        except ValueError as e:
            raise KitError(f"«{id}»: {e}") from None
        self._registrar(nombre or id, "componente", ficha=id, en=[float(c) for c in en],
                        giros=giros, entra_por=entra_por)
        return Componente(self._fichas[id], en, giros, entra_por, self)

    # --- sólidos de partida ----------------------------------------------------------

    def caja(self, x, y, z, en=(0, 0, 0)) -> Cuerpo:
        """Caja de x × y × z con su esquina mínima en `en`."""
        if min(x, y, z) <= 0:
            raise KitError(f"una caja necesita las tres medidas positivas, no {x}, {y}, {z}")
        return Cuerpo(Part.makeBox(float(x), float(y), float(z), _v(en)), self)

    def cilindro(self, diametro, alto, en=(0, 0, 0), eje="z") -> Cuerpo:
        """Cilindro con el centro de su base en `en`, creciendo en `eje`."""
        return Cuerpo(Part.makeCylinder(float(diametro) / 2, float(alto), _v(en), _eje(eje)), self)

    def tubo(self, exterior, interior, alto, en=(0, 0, 0), eje="z") -> Cuerpo:
        """Cilindro hueco: para abrazaderas, casquillos y adaptadores."""
        if interior >= exterior:
            raise KitError(f"el interior ({interior:g}) tiene que ser menor que el exterior "
                           f"({exterior:g})")
        b, d = _v(en), _eje(eje)
        return Cuerpo(Part.makeCylinder(exterior / 2, float(alto), b, d).cut(
            Part.makeCylinder(interior / 2, float(alto) + 2, b - d * 1, d)), self)

    def cono(self, diametro_base, diametro_punta, alto, en=(0, 0, 0), eje="z") -> Cuerpo:
        """Tronco de cono (un diámetro puede ser 0)."""
        return Cuerpo(Part.makeCone(float(diametro_base) / 2, float(diametro_punta) / 2,
                                    float(alto), _v(en), _eje(eje)), self)

    def esfera(self, diametro, en=(0, 0, 0)) -> Cuerpo:
        return Cuerpo(Part.makeSphere(float(diametro) / 2, _v(en)), self)

    def _prisma_hexagonal(self, entrecaras, alto, base, d):
        u, w = _perpendiculares(d)
        r = entrecaras / math.sqrt(3)   # radio a los vértices
        puntos = [base + u * (r * math.cos(math.radians(60 * i)))
                  + w * (r * math.sin(math.radians(60 * i))) for i in range(6)]
        return Part.Face(Part.makePolygon(puntos + [puntos[0]])).extrude(d * alto)

    def hexagono(self, entrecaras, alto, en=(0, 0, 0), eje="z") -> Cuerpo:
        """Prisma hexagonal por su medida entre caras (la de la llave)."""
        return Cuerpo(self._prisma_hexagonal(float(entrecaras), float(alto), _v(en), _eje(eje)),
                      self)

    def extruir(self, puntos, alto, plano="xy", desde=0) -> Cuerpo:
        """Polígono cerrado de `puntos` (u, v) en un plano, extruido `alto`.

        - «xy»: u = x, v = y; crece en +z desde z = `desde`.
        - «xz»: u = x, v = z; crece en +y desde y = `desde`.
        - «yz»: u = y, v = z; crece en +x desde x = `desde`.

        Es la operación de los perfiles: una L, una cartela triangular, una V."""
        if len(puntos) < 3:
            raise KitError("un polígono necesita al menos tres puntos")
        if plano == "xy":
            p3 = [FreeCAD.Vector(u, v, desde) for u, v in puntos]
            d = FreeCAD.Vector(0, 0, alto)
        elif plano == "xz":
            p3 = [FreeCAD.Vector(u, desde, v) for u, v in puntos]
            d = FreeCAD.Vector(0, alto, 0)
        elif plano == "yz":
            p3 = [FreeCAD.Vector(desde, u, v) for u, v in puntos]
            d = FreeCAD.Vector(alto, 0, 0)
        else:
            raise KitError("`plano` es «xy», «xz» o «yz»")
        return Cuerpo(_valido(_cara(p3).extrude(d), "extruir"), self)

    def revolucionar(self, puntos, grados=360, eje="z", en=(0, 0, 0)) -> Cuerpo:
        """Perfil de `puntos` (r, h) —distancia al eje y altura a lo largo de
        él— girado alrededor de `eje` por `en`. Para piezas de revolución:
        casquillos con pestaña, poleas, tapones."""
        d = _eje(eje)
        u, _ = _perpendiculares(d)
        base = _v(en)
        p3 = [base + u * float(r) + d * float(h) for r, h in puntos]
        return Cuerpo(_valido(_cara(p3).revolve(base, d, float(grados)), "revolucionar"),
                      self)

    def seccion(self, puntos, curva=False) -> Seccion:
        """Contorno cerrado por `puntos` (u, v), para `transicion` o `barrer`.
        Con `curva`, una curva lisa que pasa por todos ellos en vez de lados
        rectos: da los puntos por donde quieres que pase y el kit hace la
        curva. Se dibuja alrededor de (0, 0), que es donde va el eje."""
        if len(puntos) < 3:
            raise KitError("una sección necesita al menos tres puntos")
        uv = [(float(a), float(b)) for a, b in puntos]

        def hacer(centro, u, v):
            p3 = _sin_repetidos([centro + u * a + v * b for a, b in uv])
            if len(p3) < 3:
                raise KitError("una sección necesita al menos tres puntos distintos")
            if not curva:
                _cara(p3)   # avisa si los lados se cruzan
                return Part.makePolygon(p3 + [p3[0]])
            # Un tramo de Bézier de cada punto al siguiente, con la tangente
            # de cada punto sacada de sus dos vecinos (Hermite, repartido por
            # cuerdas). La curva periódica de FreeCAD (`interpolate`) por
            # cuatro puntos en cruz daba un óvalo torcido, 0,5 mm más alto
            # que ancho; esta pasa por los puntos y es simétrica si lo son.
            n = len(p3)
            cuerdas = [(p3[(i + 1) % n] - p3[i]).Length for i in range(n)]
            if min(cuerdas) < TOL:
                raise KitError("la curva no pasa por esos puntos: hay dos seguidos repetidos")
            tangentes = []
            for i in range(n):
                antes, despues = cuerdas[i - 1], cuerdas[i]
                llega = (p3[i] - p3[i - 1]) * (1 / antes)
                sale = (p3[(i + 1) % n] - p3[i]) * (1 / despues)
                tangentes.append((llega * despues + sale * antes) * (1 / (antes + despues)))
            tramos = []
            for i in range(n):
                j, largo = (i + 1) % n, cuerdas[i] / 3
                b = Part.BezierCurve()
                b.setPoles([p3[i], p3[i] + tangentes[i] * largo,
                            p3[j] - tangentes[j] * largo, p3[j]])
                tramos.append(b.toShape())
            return Part.Wire(tramos)
        return Seccion(hacer)

    def rectangulo(self, ancho, alto, radio=0) -> Seccion:
        """Sección rectangular centrada, de `ancho` en u y `alto` en v, con las
        esquinas redondeadas a `radio`. La de casi todas las carcasas. `radio`
        es un número para las cuatro, o cuatro —uno por esquina, en el orden
        (-u, -v), (+u, -v), (+u, +v), (-u, +v); 0 la deja viva—: para una
        tapa con las esquinas de delante distintas de las de atrás. Los arcos
        son arcos de verdad: no los dibujes tú con tramos rectos."""
        a, b = float(ancho) / 2, float(alto) / 2
        if isinstance(radio, (int, float)):
            radios = [float(radio)] * 4
        else:
            radios = [float(r) for r in radio]
            if len(radios) != 4:
                raise KitError("`radio` es un número o cuatro, uno por esquina: "
                               "(-u, -v), (+u, -v), (+u, +v), (-u, +v)")
        if max(radios) <= 0:
            return self.seccion([(-a, -b), (a, -b), (a, b), (-a, b)])
        # Dos radios vecinos no pueden comerse entero el lado que comparten.
        for (r0, r1), lado in zip(zip(radios, radios[1:] + radios[:1]), (2 * a, 2 * b) * 2):
            if min(r0, r1) < 0 or r0 + r1 > lado - TOL:
                raise KitError(f"los radios ({r0:g} y {r1:g}) no caben en un lado de {lado:g}: "
                               "tienen que sumar menos que él; para un óvalo usa `kit.elipse`")

        def hacer(centro, u, v):
            def p(x, y):
                return centro + u * x + v * y

            esquinas = [(-a, -b), (a, -b), (a, b), (-a, b)]
            # Hacia dónde queda el centro del arco desde cada esquina, y el
            # ángulo en el que el arco empieza recorriendo el contorno.
            dentro = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
            empieza = [180, 270, 0, 90]
            tramos, puntos = [], []
            for (x, y), (sx, sy), g0, r in zip(esquinas, dentro, empieza, radios):
                if r <= 0:
                    puntos.append(((x, y), None, (x, y)))
                    continue
                cx, cy = x + sx * r, y + sy * r
                g = [math.radians(g0 + k) for k in (0, 45, 90)]
                pts = [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in g]
                puntos.append((pts[0], pts, pts[2]))
            for i, (entra, arco, sale) in enumerate(puntos):
                if arco is not None:
                    tramos.append(Part.Arc(*(p(*q) for q in arco)).toShape())
                siguiente = puntos[(i + 1) % 4][0]
                tramos.append(Part.LineSegment(p(*sale), p(*siguiente)).toShape())
            return Part.Wire(tramos)
        return Seccion(hacer)

    def elipse(self, ancho, alto) -> Seccion:
        """Sección ovalada centrada, de `ancho` en u y `alto` en v. Con los dos
        iguales es un círculo de ese diámetro."""
        a, b = float(ancho) / 2, float(alto) / 2
        if min(a, b) <= 0:
            raise KitError("el ancho y el alto de una elipse son positivos")

        def hacer(centro, u, v):
            if abs(a - b) < TOL:
                curva = Part.Circle(centro, u.cross(v), a)
            elif a > b:
                curva = Part.Ellipse(centro + u * a, centro + v * b, centro)
            else:
                curva = Part.Ellipse(centro + v * b, centro + u * a, centro)
            return Part.Wire([curva.toShape()])
        return Seccion(hacer)

    def transicion(self, tramos, eje="z", en=(0, 0, 0), recta=False) -> Cuerpo:
        """Cuerpo que pasa por varias secciones puestas a lo largo de `eje`.
        `tramos`: lista de (sección, distancia desde `en`), de menor a mayor.
        Con tres o más, la superficie es lisa y pasa por todas; con `recta`
        va en línea recta de cada una a la siguiente. Las secciones se dibujan
        en el plano perpendicular al eje, como en `extruir`: a lo largo de z,
        (u, v) = (x, y); de y, (x, z); de x, (y, z).

        Es la forma de una carcasa, una tapa abombada, un carenado o una
        boquilla: di cómo es el corte en dos o tres alturas y el kit hace la
        superficie. Para dejarla hueca, `.vaciar(grosor)`."""
        if len(tramos) < 2:
            raise KitError("una transición necesita al menos dos secciones")
        if not all(isinstance(t[0], Seccion) for t in tramos):
            raise KitError("cada tramo es (sección, distancia): la sección se hace con "
                           "`kit.seccion`, `kit.rectangulo` o `kit.elipse`")
        donde = [float(h) for _, h in tramos]
        if any(b <= a for a, b in zip(donde, donde[1:])):
            raise KitError("las distancias de los tramos van de menor a mayor, sin repetirse")
        d, base = _eje(eje), _v(en)
        u, v = _plano_de(d)
        alambres = [sec._alambre(base + d * h, u, v) for (sec, _), h in zip(tramos, donde)]
        try:
            forma = Part.makeLoft(alambres, True, bool(recta))
        except Exception:
            raise KitError("no se pudo unir esas secciones: sepáralas más o hazlas más "
                           "parecidas entre sí") from None
        if forma.Volume < 0:
            forma.reverse()
        cuerpo = Cuerpo(_valido(_un_solido(forma), "transicion"), self)
        cuerpo._receta = (list(zip((sec for sec, _ in tramos), donde)), d, base, u, v, recta)
        return cuerpo

    def barrer(self, seccion, camino, curva=False) -> Cuerpo:
        """Lleva una sección a lo largo de `camino`, una lista de puntos
        (x, y, z): un tubo doblado, un pasacables, un asa. Con `curva`, el
        camino es una curva lisa que pasa por los puntos; sin ella, tramos
        rectos. La sección va centrada en el camino y perpendicular a él."""
        if not isinstance(seccion, Seccion):
            raise KitError("lo que se barre es una sección: hazla con `kit.seccion`, "
                           "`kit.rectangulo` o `kit.elipse`")
        puntos = [_v(p) for p in camino]
        if len(puntos) < 2:
            raise KitError("un camino necesita al menos dos puntos")
        if curva and len(puntos) > 2:
            c = Part.BSplineCurve()
            c.interpolate(puntos)
            ruta, sale = Part.Wire([c.toShape()]), c.tangent(c.FirstParameter)[0]
        else:
            ruta, sale = Part.makePolygon(puntos), puntos[1] - puntos[0]
        u, v = _plano_de(sale.normalize())
        cerrado = ("no se pudo barrer por ese camino: dobla más cerrado que el ancho de la "
                   "sección y la superficie se pisa a sí misma. Abre la curva (más distancia "
                   "entre los puntos donde tuerce) o usa una sección más estrecha")
        perfil = seccion._alambre(puntos[0], u, v)
        if curva and len(puntos) > 2:
            # Si el camino se curva con menos radio que el de la sección, la
            # superficie se pisa por dentro de la curva. FreeCAD lo da por
            # válido y hasta mide sección por largo, así que se mira aquí.
            caja = perfil.BoundBox
            medio = max(abs((p - puntos[0]).dot(k)) for k in (u, v) for p in (
                FreeCAD.Vector(caja.XMin, caja.YMin, caja.ZMin),
                FreeCAD.Vector(caja.XMax, caja.YMax, caja.ZMax)))
            pasos = [c.FirstParameter + (c.LastParameter - c.FirstParameter) * k / 200
                     for k in range(201)]
            if max(c.curvature(t) for t in pasos) * medio > 1:
                raise KitError(cerrado)
        try:
            forma = ruta.makePipeShell([perfil], True, True,
                                       0 if curva or len(puntos) == 2 else 1)
        except Exception:
            raise KitError(cerrado) from None
        if forma.Volume < 0:
            forma.reverse()
        return Cuerpo(_valido(_un_solido(forma), "barrer"), self)

    def polea_gt2(self, nombre, dientes, en=(0, 0, 0), eje="z", correa=6.0,
                  pestanas=True) -> Cuerpo:
        """Polea dentada para correa GT2 de 2 mm de paso, maciza, con el
        centro de su base en `en` y creciendo en `eje`. Los dientes los pone
        el kit: nunca los dibujes tú. `dientes`: los de la polea (12 o más);
        `correa`: el ancho de la correa. Con `pestanas` lleva a cada lado un
        cono que guía la correa y se imprime sin soportes con el eje en
        vertical: mide 10 mm de alto para una correa de 6. Acaba antes tu
        pieza (`acabar()`) y súmale después la polea con `+`: acabarla con
        los dientes puestos tarda un minuto y no les hace nada. Taladra al
        final el eje que haga falta."""
        from mech_toolkit import transmisiones as T

        if int(dientes) != dientes or dientes < T.MINIMO_DE_DIENTES:
            raise KitError(f"«{nombre}»: una polea GT2 tiene {T.MINIMO_DE_DIENTES} dientes o "
                           f"más, y enteros; no {dientes!r}")
        dientes = int(dientes)
        base, d = _v(en), _eje(eje)
        u, w = _perpendiculares(d)
        radio = T.diametro_exterior(dientes) / 2
        cara = T.ancho_de_la_cara(float(correa), bool(pestanas))
        pie = T.PESTANA if pestanas else 0.0
        desde = base + d * pie
        forma = Part.makeCylinder(radio, cara, desde, d)
        # Una sola resta con todas las ranuras: de una en una son 80 cortes.
        ranuras = [Part.makeCylinder(
            T.ALTO_DEL_DIENTE, cara + 2,
            desde - d * 1 + (u * math.cos(a) + w * math.sin(a)) * radio, d)
            for a in (2 * math.pi * k / dientes for k in range(dientes))]
        forma = forma.cut(Part.makeCompound(ranuras))
        if pestanas:
            # A 45°: la de abajo se estrecha hacia los dientes y la de arriba
            # se abre desde ellos, así que ninguna cuelga.
            forma = forma.fuse([
                Part.makeCone(radio + T.PESTANA, radio, T.PESTANA, base, d),
                Part.makeCone(radio, radio + T.PESTANA, T.PESTANA, desde + d * cara, d)])
        self._registrar(nombre, "polea_gt2", dientes=dientes, centro=list(base), eje=list(d),
                        ancho_mm=cara, alto_mm=cara + 2 * pie,
                        primitivo_mm=T.diametro_primitivo(dientes),
                        exterior_mm=2 * radio, correa_mm=float(correa))
        return Cuerpo(_valido(_un_solido(forma.removeSplitter()), "polea_gt2"), self)


# --- la API que puede usar el programa -------------------------------------------------

API = frozenset(
    n for cls in (Kit, Cuerpo, Componente) for n, _ in inspect.getmembers(cls)
    if not n.startswith("_")) | {"perfil"}
"""Los únicos atributos que el programa puede tocar. `sandbox` los lee de
aquí: un método nuevo del kit queda disponible sin tocar el validador."""


def referencia() -> str:
    """La API del kit para el prompt del diseñador, sacada de las firmas y los
    docstrings: la documentación no se puede quedar atrás del código."""
    lineas = []
    for titulo, cls, prefijo in (("kit", Kit, "kit."), ("cuerpo", Cuerpo, "cuerpo."),
                                 ("componente", Componente, "componente.")):
        lineas.append(f"### {titulo}\n")
        for n, f in inspect.getmembers(cls, inspect.isfunction):
            if n.startswith("_"):
                continue
            firma = str(inspect.signature(f)).replace("(self, ", "(").replace("(self)", "()")
            doc = inspect.getdoc(f) or ""
            lineas.append(f"- `{prefijo}{n}{firma}`: {doc}\n")
        lineas.append("")
    return "\n".join(lineas)


def ejecutar(codigo: str, kit: Kit) -> Cuerpo:
    """Valida y ejecuta el programa, y devuelve lo que construye.

    La validación se repite aquí aunque el orquestador ya la hiciera: el que
    ejecuta no delega la comprobación en el que pide (como el puente, ADR-014).
    Un fallo sale como `KitError` con la línea del programa."""
    from mech_toolkit.kit.sandbox import NOMBRES, validar

    validar(codigo)
    entorno = dict(NOMBRES)
    try:
        exec(compile(codigo, "programa.py", "exec"), entorno)
        pieza = entorno["construir"](kit)
    except KitError as e:
        raise KitError(f"{_linea()}{e}") from None
    except Exception as e:
        raise KitError(f"{_linea()}{type(e).__name__}: {e}") from None
    if not isinstance(pieza, Cuerpo):
        raise KitError(f"`construir` tiene que devolver un cuerpo, y devolvió "
                       f"{type(pieza).__name__}")
    return pieza


def _linea() -> str:
    marcos = [m for m in traceback.extract_tb(__import__("sys").exc_info()[2])
              if m.filename == "programa.py"]
    return f"programa.py, línea {marcos[-1].lineno}: " if marcos else ""
