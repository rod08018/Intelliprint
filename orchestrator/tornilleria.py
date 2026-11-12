"""La tornillería de un invento (F7.8 (inventario)): cada tornillo que lleva,
de qué largo, dónde apoya su cabeza y en qué agarra.

«El ensamble debe mostrar todo lo que el BOM requiere, y en el BOM deben ir
todas las cosas que no imprimo» (el usuario, 2026-11-10). Hasta entonces la
lista de materiales decía «M3, M4»: ni cuántos, ni de qué largo, ni las
tuercas, y el ensamble no enseñaba ninguno.

Nada de esto lo dice un modelo. Sale de lo que cada pieza construida dejó en
`rasgos.json` —los agujeros con métrica (`kit.tornillo`), las tuercas
cautivas— y de las fichas de lo comprado, que dicen qué tornillo va en cada
fijación. Los agujeros que caen en la misma recta, en piezas distintas, son
UN tornillo: el que une la tapa con la base pasa por un agujero de cada una.
El largo se mide: de donde apoya la cabeza a donde acaba lo que atraviesa.
"""

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# ISO 4762 / ISO 4017: los largos que se venden.
LARGOS_MM = (3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 30, 35, 40, 45, 50, 55, 60,
             65, 70, 80, 90, 100)
# ISO 4032: entrecaras y alto de la tuerca, para dibujarla.
TUERCA_ISO_4032_MM = {"M2": (4.0, 1.6), "M2.5": (5.0, 2.0), "M3": (5.5, 2.4), "M4": (7.0, 3.2),
                      "M5": (8.0, 4.7), "M6": (10.0, 5.2), "M8": (13.0, 6.8)}
COAXIAL_MM = 0.6
"""Dos agujeros son del mismo tornillo si sus ejes están a menos de esto: la
holgura de un pasante M3 (3.3 para un tornillo de 3) es 0.3 de radio."""


@dataclass
class _Tramo:
    """Un trozo de la recta de un tornillo: un agujero, una tuerca o la
    fijación de un componente. En el marco de la raíz del invento."""
    pieza: str
    tipo: str                     # "agujero" | "tuerca" | "fijacion"
    nombre: str
    en: list
    eje: list
    largo: float
    diametro: float = 0.0
    metrica: str = ""
    pasante: bool = False
    avellanado: float | None = None
    incluido_con: str = ""
    tuerca_aparte: str = ""
    a_lo_largo: list | None = None
    uso: str = ""
    """De un agujero hecho con `kit.tornillo`: «pasante», «rosca» o «inserto»."""
    ficha: str = ""
    """De una fijación: el id de la ficha de lo comprado."""


@dataclass
class Tornillo:
    metrica: str
    largo_mm: float
    """Medido: de donde apoya la cabeza a donde acaba."""
    largo: int | None
    """El de catálogo. None si depende de dónde se fije la pieza."""
    termina: str
    """«tuerca», «rosca» (en el plástico), «inserto» (térmico, en el
    plástico), «componente» (en lo comprado) o «superficie» (atraviesa y no
    llega a nada: va a donde se fije)."""
    pieza: str
    """Donde apoya la cabeza: se mueve con ella."""
    cabeza: list
    eje: list
    """De la cabeza a la punta. `cabeza` y `eje`, en el marco de `pieza`."""
    avellanado: float | None = None
    viene_con: str = ""
    compra_aparte: str = ""
    tuercas: list = field(default_factory=list)
    agujeros: list = field(default_factory=list)
    # Para comparar con lo que previó el plan (F9.6 (previsto)).
    piezas: list = field(default_factory=list)
    """Las piezas por las que pasa, sin repetir."""
    componente: str = ""
    """La ficha de lo comprado que sujeta, si pasa por una fijación suya."""
    lo_monta: str = ""
    """La pieza que monta ese componente."""
    agarra_en: str = ""
    agarra_mm: float | None = None
    """El agujero donde acaba la punta y su diámetro: si es el plástico lo
    que tiene que roscar, ha de ser más estrecho que el tornillo."""

    def rosca_en_el_plastico(self) -> bool:
        """Lo que lo sujeta es el plástico del último agujero: ni tuerca, ni
        inserto, ni la rosca de lo comprado. El que sujeta un servo por la
        oreja lo es aunque su agujero guía atraviese la pieza."""
        return self.termina == "rosca" or (self.termina == "superficie"
                                           and bool(self.componente))

    def no_rosca(self) -> bool:
        """Su agujero es tan ancho como él o más. El soporte del pan-tilt
        1111-1342 taladró Ø2.2 para un tornillo de 2: pasa sin tocar."""
        return (self.rosca_en_el_plastico() and self.agarra_mm is not None
                and self.agarra_mm >= _diametro(self.metrica) - 1e-6)

    def nombre(self) -> str:
        cabeza = " avellanado" if self.avellanado else ""
        if self.viene_con:
            return f"Tornillo {self.metrica} de {self.largo_mm:g} mm"
        if self.largo is None:
            return (f"Tornillo{cabeza} {self.metrica} · {self.largo_mm:g} mm de pieza "
                    "+ lo que entre donde se fije")
        return f"Tornillo{cabeza} {self.metrica} × {self.largo}"

    def para_el_visor(self) -> dict:
        d = _diametro(self.metrica)
        return {"nombre": self.nombre(), "pieza": self.pieza, "cabeza": self.cabeza,
                "eje": self.eje, "d": d, "largo": self.largo or self.largo_mm,
                "avellanado": self.avellanado,
                "cabeza_d": self.avellanado or _cabeza_iso_4762(self.metrica),
                "tuercas": self.tuercas}


def _diametro(metrica: str) -> float:
    try:
        return float(metrica.lstrip("Mm"))
    except ValueError:
        return 3.0


def _cabeza_iso_4762(metrica: str) -> float:
    from orchestrator.medida import CABEZA_ISO_4762_MM
    return CABEZA_ISO_4762_MM.get(metrica) or round(_diametro(metrica) * 1.8, 1)


# --- vectores ------------------------------------------------------------------------------

def _resta(a, b):
    return [x - y for x, y in zip(a, b)]


def _punto(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cruz(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norma(a):
    return math.sqrt(_punto(a, a))


def _unit(a):
    n = _norma(a) or 1.0
    return [x / n for x in a]


def _aplicar(t, p):
    from orchestrator.conjunto import _mv
    r, d = t
    return [x + y for x, y in zip(_mv(r, p), d)]


def _girar(t, v):
    from orchestrator.conjunto import _mv
    return _mv(t[0], v)


# --- cuánto atraviesa un agujero -------------------------------------------------------------

@lru_cache(maxsize=32)
def _triangulos(ruta: str, _cuando: float):
    """Los triángulos de un STL, binario o de texto, como un array (n, 3, 3)."""
    import numpy as np
    datos = Path(ruta).read_bytes()
    if len(datos) >= 84:
        n = int.from_bytes(datos[80:84], "little")
        if 84 + 50 * n == len(datos):
            filas = np.frombuffer(datos[84:], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                                              ("a", "<u2")]), count=n)
            return filas["v"].astype(float)
    vs = [list(map(float, linea.split()[1:4])) for linea in datos.decode("utf-8", "replace").splitlines()
          if linea.strip().startswith("vertex")]
    return np.array(vs, dtype=float).reshape(-1, 3, 3)


def _cortes(tris, origen, d):
    """Dónde corta el rayo `origen + t·d` a la malla (Möller–Trumbore)."""
    import numpy as np
    o, d = np.array(origen, float), np.array(d, float)
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    p = np.cross(d, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - v0
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    v = (q * d).sum(1) * inv
    t = (e2 * q).sum(1) * inv
    dentro = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
    return sorted(set(round(x, 6) for x in t[dentro]))


ATRAS_MM = 3.0


def _grosor_en_malla(tris, entrada, eje, diametro) -> float | None:
    """Cuánta pieza atraviesa un agujero sin fondo. Su propio eje está
    vacío —el agujero se cortó—, así que se mide la pared de alrededor, con
    rayos paralelos a medio milímetro del agujero. Gana el que llega más
    lejos: un avellanado se come la pared de arriba en unos y no en otros."""
    eje = _unit(eje)
    a = _unit(_cruz(eje, [1, 0, 0] if abs(eje[0]) < 0.9 else [0, 1, 0]))
    b = _cruz(eje, a)
    r = diametro / 2 + 0.6
    mejor = None
    for k in range(8):
        ang = k * math.pi / 4
        lado = [r * (math.cos(ang) * x + math.sin(ang) * y) for x, y in zip(a, b)]
        origen = [p + l - ATRAS_MM * e for p, l, e in zip(entrada, lado, eje)]
        cortes = _cortes(tris, origen, eje)
        tramos, k2 = [], 0
        while k2 + 1 < len(cortes):
            ini, fin = cortes[k2], cortes[k2 + 1]
            if tramos and ini - tramos[-1][1] < 0.05:   # dos caras que se tocan
                tramos[-1][1] = fin
            else:
                tramos.append([ini, fin])
            k2 += 2
        for ini, fin in tramos:
            if ini <= ATRAS_MM + 3 and fin > ATRAS_MM + 0.3:
                mejor = max(mejor or 0.0, fin - ATRAS_MM)
                break
    return mejor


def _grosor_en_caja(envolvente, entrada, eje) -> float:
    """Sin malla, hasta la cara de la caja de la pieza por donde sale."""
    a, b = envolvente
    ts = [((hi if e > 0 else lo) - p) / e for p, e, lo, hi in zip(entrada, eje, a, b)
          if abs(e) > 1e-9]
    return max(0.0, min(ts)) if ts else 0.0


def _atraviesa(r: dict, stl: Path | None, envolvente) -> float:
    if r.get("profundidad_mm"):
        return float(r["profundidad_mm"])
    if stl is not None and stl.is_file():
        g = _grosor_en_malla(_triangulos(str(stl), stl.stat().st_mtime), r["entrada"],
                             r["eje"], float(r.get("diametro_mm") or 3))
        if g is not None:
            return round(float(g), 2)
    return round(float(_grosor_en_caja(envolvente, r["entrada"], _unit(r["eje"]))), 2)


# --- las piezas del invento ------------------------------------------------------------------

@dataclass
class _Pieza:
    id: str
    rasgos: list
    componentes: list            # rasgos de componente que son suyos
    stl: Path | None
    envolvente: tuple
    mundo: tuple                 # (R, t) a la raíz, en reposo


def _leer(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None


def _piezas(carpeta: Path, conjunto: str | None) -> tuple[list[_Pieza], list[Path]]:
    from orchestrator import obra as O
    from orchestrator.conjunto import I3, poses

    if O.es_obra(carpeta):
        from orchestrator.conjunto import leer_piezas
        piezas = leer_piezas(carpeta, conjunto, solo_construidas=True)
        mundo = poses(piezas, {}, {})
        salida = []
        for i, p in piezas.items():
            parte = p.step.parent
            stl = next(iter(sorted(parte.glob("*.stl"))), None)
            salida.append(_Pieza(i, _leer(parte / "rasgos.json") or [], p.propios, stl,
                                 p.envolvente, mundo[i]))
        return salida, [O.carpeta_de_fichas(carpeta)]
    salida = []
    for parte in sorted((carpeta / "parts").glob("*")):
        rasgos = _leer(parte / "rasgos.json") or []
        env = _leer(parte / "envolvente.json") or {"min": [0, 0, 0], "max": [0, 0, 0]}
        salida.append(_Pieza(parte.name, rasgos,
                             [r for r in rasgos if r.get("tipo") == "componente" and r.get("ficha")
                              and not r["ficha"].startswith("obra-")],
                             next(iter(sorted(parte.glob("*.stl"))), None),
                             (env["min"], env["max"]), (I3, [0.0, 0.0, 0.0])))
    return salida, []


def _tramos(p: _Pieza, fichas: list[Path]) -> list[_Tramo]:
    from orchestrator.componentes import cargar
    from mech_toolkit.componentes import colocar, orientar

    tramos = []
    for r in p.rasgos:
        if r.get("tipo") not in ("agujero", "tuerca") or not r.get("entrada") or not r.get("eje"):
            continue   # un rasgo de antes de que se guardara dónde está
        en, eje = _aplicar(p.mundo, r["entrada"]), _unit(_girar(p.mundo, r["eje"]))
        if r["tipo"] == "tuerca":
            tramos.append(_Tramo(p.id, "tuerca", r["nombre"], en, eje,
                                 float(r.get("profundidad_mm") or 0),
                                 metrica=r.get("metrica") or ""))
            continue
        tramos.append(_Tramo(p.id, "agujero", r["nombre"], en, eje,
                             _atraviesa(r, p.stl, p.envolvente),
                             diametro=float(r.get("diametro_mm") or 0),
                             metrica=r.get("tornillo") or "",
                             pasante=not r.get("profundidad_mm"),
                             avellanado=r.get("avellanado_mm"), uso=r.get("uso") or ""))
    for c in p.componentes:
        try:
            ficha = cargar(c["ficha"], fichas)
        except Exception:   # una ficha que ya no está: sin ella no se sabe qué tornillo va
            continue
        giros = [tuple(g) for g in c.get("giros") or []]
        for f in ficha.fijacion:
            if not f.tornillo:
                continue
            local, eje_l = colocar(f.en, c["en"], giros), orientar(f.eje, giros)
            tramos.append(_Tramo(
                p.id, "fijacion", f"{ficha.id}: {f.nombre}", _aplicar(p.mundo, local),
                _unit(_girar(p.mundo, eje_l)), f.dentro_mm, diametro=f.diametro,
                metrica=f.tornillo, incluido_con=ficha.nombre if f.incluido else "",
                tuerca_aparte=f.tuerca,
                a_lo_largo=(_unit(_girar(p.mundo, orientar(f.a_lo_largo, giros)))
                            if f.a_lo_largo else None), ficha=ficha.id))
    return tramos


def _en_la_recta(a: _Tramo, b: _Tramo, libre=None) -> bool:
    if _norma(_cruz(a.eje, b.eje)) > 0.05:
        return False
    w = _resta(b.en, a.en)
    for d in [a.eje] + ([libre] if libre else []):
        k = _punto(w, d)
        w = [x - k * y for x, y in zip(w, d)]
    return _norma(w) < COAXIAL_MM


def _agrupar(tramos: list[_Tramo]) -> list[list[_Tramo]]:
    """Los tramos de cada recta. Una fijación que puede ir en cualquier punto
    de la ranura no une rectas: se añade a cada una que la cruce, o los dos
    M5 de un soporte sobre el perfil acabarían siendo un tornillo."""
    fijos = [t for t in tramos if t.a_lo_largo is None]
    padre = list(range(len(fijos)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(len(fijos)):
        for j in range(i + 1, len(fijos)):
            if _en_la_recta(fijos[i], fijos[j]):
                padre[raiz(j)] = raiz(i)
    grupos: dict[int, list] = {}
    for i, t in enumerate(fijos):
        grupos.setdefault(raiz(i), []).append(t)
    salida = list(grupos.values())
    for t in tramos:
        if t.a_lo_largo is not None:
            for g in salida:
                if any(_en_la_recta(x, t, t.a_lo_largo) for x in g if x.tipo == "agujero"):
                    g.append(t)
    return salida


def _de_catalogo(largo: float, llegar: bool) -> int:
    """Con tuerca, el de encima: tiene que llegar. En una rosca, el de
    debajo: no puede pasar del fondo."""
    if llegar:
        return next((n for n in LARGOS_MM if n >= largo - 0.05), LARGOS_MM[-1])
    return next((n for n in reversed(LARGOS_MM) if n <= largo + 0.05), LARGOS_MM[0])


def _tornillo(g: list[_Tramo], piezas: dict[str, _Pieza]) -> Tornillo | None:
    from orchestrator.conjunto import _inversa
    agujeros = [t for t in g if t.tipo == "agujero"]
    metrica = next((t.metrica for t in g if t.tipo == "agujero" and t.metrica), "") or \
        next((t.metrica for t in g if t.metrica), "")
    if not agujeros or not metrica:
        return None
    # La cabeza entra por el pasante más ancho; si no hay, la dirección la
    # marca la ficha (la oreja del servo se atornilla desde arriba).
    pasantes = sorted((t for t in agujeros if t.pasante), key=lambda t: -t.diametro)
    fij = [t for t in g if t.tipo == "fijacion"]
    d = (pasantes[0] if pasantes else (fij[0] if fij else agujeros[0])).eje

    def tramo(t):
        a, b = _punto(t.en, d), _punto([p + t.largo * e for p, e in zip(t.en, t.eje)], d)
        return min(a, b), max(a, b)

    lo = min(tramo(t)[0] for t in g)
    hi = max(tramo(t)[1] for t in g)
    cabeza = min(g, key=lambda t: (tramo(t)[0], t.tipo != "fijacion"))
    punta = max(g, key=lambda t: (tramo(t)[1], t.tipo == "tuerca", t.tipo == "fijacion"))
    tuercas = [t for t in g if t.tipo == "tuerca"]
    if tuercas:
        termina = "tuerca"
    elif punta.tipo == "fijacion" and punta is not cabeza:
        termina = "componente"
    elif punta.tipo == "agujero" and punta.uso in ("rosca", "inserto"):
        # Lo dice el rasgo: un inserto y una rosca son dos agujeros ciegos
        # que solo se distinguen por el diámetro.
        termina = punta.uso
    elif punta.tipo == "agujero" and punta.pasante:
        termina = "superficie"
    else:
        termina = "rosca"
    largo_mm = round(hi - lo, 2)
    largo = None if termina == "superficie" else _de_catalogo(largo_mm, termina == "tuerca")

    base = cabeza.pieza
    k = lo - _punto(cabeza.en, d)
    punto = [p + k * x for p, x in zip(cabeza.en, d)]

    def local(pieza, p, e):
        t = _inversa(piezas[pieza].mundo)
        return [round(x, 4) for x in _aplicar(t, p)], [round(x, 6) for x in _girar(t, e)]

    cab, eje = local(base, punto, d)
    dibujo = []
    for t in tuercas:
        en, e = local(t.pieza, t.en, t.eje)
        s, alto = TUERCA_ISO_4032_MM.get(metrica, (_diametro(metrica) * 1.8, _diametro(metrica) * 0.8))
        dibujo.append({"pieza": t.pieza, "en": en, "eje": e, "alto": t.largo or alto,
                       "entrecaras": s})
    aparte = next((t.tuerca_aparte for t in g if t.tipo == "fijacion" and t.tuerca_aparte), "")
    if aparte:
        # La tuerca en T no tiene medidas en la ficha: se dibuja la ISO de
        # su métrica, donde acaba el tornillo, para que se vea que lleva una.
        s, alto = TUERCA_ISO_4032_MM.get(metrica, (_diametro(metrica) * 1.8, _diametro(metrica) * 0.8))
        fin = [p + (hi - lo - alto) * x for p, x in zip(punto, d)]
        en, e = local(base, fin, d)
        dibujo.append({"pieza": base, "en": en, "eje": e, "alto": alto, "entrecaras": s})
    return Tornillo(
        metrica=metrica, largo_mm=largo_mm, largo=largo, termina=termina, pieza=base,
        cabeza=cab, eje=eje,
        avellanado=cabeza.avellanado if cabeza.tipo == "agujero" else None,
        viene_con=next((t.incluido_con for t in g if t.incluido_con), ""),
        compra_aparte=aparte, tuercas=dibujo,
        agujeros=[f"{t.pieza}: {t.nombre}" for t in g],
        piezas=sorted({t.pieza for t in g}),
        componente=fij[0].ficha if fij else "", lo_monta=fij[0].pieza if fij else "",
        agarra_en=punta.nombre if punta.tipo == "agujero" else "",
        agarra_mm=punta.diametro if punta.tipo == "agujero" else None)


def tornillos(carpeta: Path, conjunto: str | None = None, sin=()) -> list[Tornillo]:
    """Cada tornillo del invento (de un conjunto, si se dice), con las
    articulaciones en reposo. `sin`: piezas que se dejan fuera de la cuenta,
    como si no estuvieran construidas."""
    carpeta = Path(carpeta)
    piezas, fichas = _piezas(carpeta, conjunto)
    piezas = [p for p in piezas if p.id not in set(sin)]
    por_id = {p.id: p for p in piezas}
    tramos = [t for p in piezas for t in _tramos(p, fichas)]
    salida = [t for g in _agrupar(tramos) if (t := _tornillo(g, por_id))]
    return sorted(salida, key=lambda t: (t.pieza, t.cabeza))
