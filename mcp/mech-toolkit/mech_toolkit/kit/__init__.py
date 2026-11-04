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


class KitError(ValueError):
    """Un error en el uso del kit, escrito para que el diseñador lo corrija."""


def _v(p) -> "FreeCAD.Vector":
    if len(p) != 3:
        raise KitError(f"un punto son tres coordenadas (x, y, z), no {p!r}")
    return FreeCAD.Vector(float(p[0]), float(p[1]), float(p[2]))


_EJES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1),
         "-x": (-1, 0, 0), "-y": (0, -1, 0), "-z": (0, 0, -1)}


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


class Cuerpo:
    """Un sólido. Se combinan con `+` (unir), `-` (restar) y `&` (intersecar)."""

    def __init__(self, forma, kit: "Kit") -> None:
        self._forma = forma
        self._kit = kit

    def _nuevo(self, forma, que="la operación") -> "Cuerpo":
        return Cuerpo(_valido(_un_solido(forma), que), self._kit)

    def __add__(self, otro: "Cuerpo") -> "Cuerpo":
        return self._nuevo(self._forma.fuse(otro._forma).removeSplitter(), "la unión (+)")

    def __sub__(self, otro: "Cuerpo") -> "Cuerpo":
        return self._nuevo(self._forma.cut(otro._forma).removeSplitter(), "la resta (-)")

    def __and__(self, otro: "Cuerpo") -> "Cuerpo":
        return self._nuevo(self._forma.common(otro._forma).removeSplitter(),
                           "la intersección (&)")

    # --- colocar --------------------------------------------------------------

    def mover(self, dx=0.0, dy=0.0, dz=0.0) -> "Cuerpo":
        """Copia desplazada."""
        f = self._forma.copy()
        f.translate(FreeCAD.Vector(dx, dy, dz))
        return self._nuevo(f)

    def girar(self, grados, eje="z", centro=(0, 0, 0)) -> "Cuerpo":
        """Copia girada `grados` alrededor de `eje` (que pasa por `centro`)."""
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
        b = self._forma.BoundBox
        return (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)

    # --- acabado ----------------------------------------------------------------

    def _aristas(self, aristas, dentro):
        b = self._forma.BoundBox
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

    def _acabar(self, operacion, medida, elegidas, aristas) -> "Cuerpo":
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
        for candidata in (forma, hacer(caben) if caben else None):
            if candidata is not None and candidata.isValid():
                self._kit._avisos.append(
                    f"{operacion} {medida:g} mm: {len(elegidas) - len(caben)} de "
                    f"{len(elegidas)} aristas «{aristas}» no lo admitían y quedaron vivas")
                return Cuerpo(candidata, self._kit)
        self._kit._avisos.append(
            f"{operacion} {medida:g} mm en las aristas «{aristas}»: no se pudo aplicar sin "
            "romper la pieza, y se omite")
        return self

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
        en todas las demás. Donde el radio no cabe, la arista queda viva con
        un aviso. En el banco (2026-11-04) entre el 36 % y el 63 % de las
        aristas quedaban vivas: se redondeaban las verticales y nada más."""
        pieza = self.achaflanar(chaflan_base, aristas="base") if chaflan_base else self
        z0 = pieza._forma.BoundBox.ZMin
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
        return pieza._acabar("redondear", radio, elegidas, "todas menos la base")

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
        return self._nuevo(resultado, f"«{nombre}»")

    # --- rasgos con nombre --------------------------------------------------------

    def taladrar(self, nombre, diametro, en, eje="-z", profundidad=None,
                 lagrima=False, avellanado=None) -> "Cuerpo":
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
                             lagrima=bool(lagrima), avellanado_mm=avellanado)
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
        return self.taladrar(nombre, d, en, eje=eje, profundidad=profundidad,
                             lagrima=lagrima, avellanado=avellanado)

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
        self._kit._registrar(nombre, "tuerca", entrecaras_mm=entrecaras, entrada=list(_v(en)),
                             eje=list(_eje(eje)), profundidad_mm=float(profundidad))
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
        b = herramienta._forma.BoundBox
        self._kit._registrar(nombre, "hueco", desde=[b.XMin, b.YMin, b.ZMin],
                             hasta=[b.XMax, b.YMax, b.ZMax])
        return self._cortar(nombre, herramienta._forma)


class Kit:
    """Las piezas de partida. Cada una devuelve un `Cuerpo`."""

    def __init__(self, perfil: dict | None = None) -> None:
        self.perfil = perfil or {}
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


# --- la API que puede usar el programa -------------------------------------------------

API = frozenset(
    n for cls in (Kit, Cuerpo) for n, _ in inspect.getmembers(cls)
    if not n.startswith("_")) | {"perfil"}
"""Los únicos atributos que el programa puede tocar. `sandbox` los lee de
aquí: un método nuevo del kit queda disponible sin tocar el validador."""


def referencia() -> str:
    """La API del kit para el prompt del diseñador, sacada de las firmas y los
    docstrings: la documentación no se puede quedar atrás del código."""
    lineas = []
    for titulo, cls, prefijo in (("kit", Kit, "kit."), ("cuerpo", Cuerpo, "cuerpo.")):
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
