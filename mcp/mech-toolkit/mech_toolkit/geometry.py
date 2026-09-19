"""Búsqueda de geometría por contrato (F2.13 (puente), ADR-011).

FreeCAD solo extrae hechos: las caras cilíndricas de la pieza. Aquí se
decide cuál corresponde a una interfaz, buscando DONDE EL CONTRATO DICE
QUE DEBE ESTAR. Si no hay nada ahí, no se mide otra cosa: se devuelve
"no encontrado", que para el QA es FAIL.

Python puro, sin numpy: son unas pocas operaciones vectoriales y así el
módulo se prueba en milisegundos sin FreeCAD.
"""

import math

from pydantic import BaseModel

POS_TOL_MM = 0.5
"""Cuánto puede alejarse el eje de un agujero de donde dice el contrato.
Holgado a propósito: la precisión la juzga la aserción, no la búsqueda.
Esto solo decide si "está ahí" o "está en otro sitio"."""

ANG_TOL_DEG = 1.0


# --- vectores ---------------------------------------------------------------

def _resta(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _escala(a, k):
    return [x * k for x in a]


def _norma(a):
    return math.sqrt(_dot(a, a))


def _unitario(a):
    n = _norma(a)
    return [x / n for x in a]


def _distancia_a_recta(punto, punto_recta, direccion):
    d = _unitario(direccion)
    v = _resta(punto, punto_recta)
    return _norma(_resta(v, _escala(d, _dot(v, d))))


def _matvec(m, v):
    return [_dot(fila, v) for fila in m]


def _transpuesta(m):
    return [list(col) for col in zip(*m)]


def _matmul(a, b):
    bt = _transpuesta(b)
    return [[_dot(fila, col) for col in bt] for fila in a]


def _rotacion(rx, ry, rz):
    """R = Rz · Ry · Rx, ángulos en grados."""
    cx, sx = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    cy, sy = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz, sz = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    rx_m = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    ry_m = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    rz_m = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    return _matmul(rz_m, _matmul(ry_m, rx_m))


# --- modelos ----------------------------------------------------------------

class Frame(BaseModel):
    origin: list[float]
    axis: list[float]


class Placement(BaseModel):
    """Dónde está una pieza dentro del ensamble (§ 3.2). La asigna la
    resolución de interfaces, no el Assembly Agent (ADR-011)."""

    origin: list[float] = [0.0, 0.0, 0.0]
    rotation: list[float] = [0.0, 0.0, 0.0]
    scale_z: float = 1.0
    """Estiramiento a lo largo del z local, antes de girar y mover. Solo para
    piezas elásticas (un resorte que se comprime); una pieza rígida es 1."""

    def to_local(self, frame: Frame) -> Frame:
        """Lleva un frame de coordenadas del ensamble a las de la pieza."""
        rt = _transpuesta(_rotacion(*self.rotation))
        return Frame(
            origin=_matvec(rt, _resta(frame.origin, self.origin)),
            axis=_matvec(rt, frame.axis),
        )


class Cylinder(BaseModel):
    """Una cara cilíndrica tal como la extrae FreeCAD."""

    radius: float
    axis: list[float]
    point: list[float]
    """Un punto del eje (el central de la cara)."""
    length: float
    """Extensión de la cara a lo largo del eje."""
    internal: bool = True
    """True = agujero (la normal de la cara apunta hacia el eje); False =
    saliente o pared exterior. Sin esto, un alojamiento redondo confundía
    su pared exterior con el asiento (fallo hallado con el NEMA17 de
    referencia, cuyas esquinas redondeadas son cilindros concéntricos)."""


# --- búsqueda ---------------------------------------------------------------

def _paralelo(a, b, ang_tol_deg: float = ANG_TOL_DEG) -> bool:
    return abs(_dot(_unitario(a), _unitario(b))) >= math.cos(math.radians(ang_tol_deg))


def find_bore(
    caras: list[Cylinder], frame: Frame, pos_tol: float = POS_TOL_MM
) -> Cylinder | None:
    """El agujero centrado en el frame: eje paralelo que pase por su origen.

    Entre varios concéntricos (un avellanado, un escalón) elige el de mayor
    radio, que es el que aloja la pieza comercial.
    """
    candidatos = [
        c for c in caras
        if c.internal
        and _paralelo(c.axis, frame.axis)
        and _distancia_a_recta(frame.origin, c.point, c.axis) <= pos_tol
    ]
    return max(candidatos, key=lambda c: c.radius, default=None)


def _extension_axial(c: Cylinder, frame: Frame) -> tuple[float, float]:
    """Dónde empieza y acaba la cara, medido a lo largo del eje del frame."""
    t = _dot(_resta(c.point, frame.origin), _unitario(frame.axis))
    return t - c.length / 2, t + c.length / 2


def find_boss(
    caras: list[Cylinder], frame: Frame, pos_tol: float = POS_TOL_MM
) -> Cylinder | None:
    """El saliente que nace en el frame y sale en el sentido de su eje.

    Lo que queda detrás del frame (p. ej. las esquinas redondeadas del
    cuerpo de un motor, concéntricas con el saliente) no cuenta.
    """
    candidatos = []
    for c in caras:
        if c.internal or not _paralelo(c.axis, frame.axis):
            continue
        if _distancia_a_recta(frame.origin, c.point, c.axis) > pos_tol:
            continue
        inicio, fin = _extension_axial(c, frame)
        if abs(inicio) <= pos_tol and fin > pos_tol:
            candidatos.append(c)
    return max(candidatos, key=lambda c: c.radius, default=None)


def find_holes_on_circle(
    caras: list[Cylinder], frame: Frame, pcd_mm: float, pos_tol: float = POS_TOL_MM
) -> list[Cylinder]:
    """Los agujeros de un patrón: ejes paralelos a distancia pcd/2 del eje
    del frame. Un agujero partido en varias caras cuenta una sola vez."""
    radio_patron = pcd_mm / 2
    en_su_sitio = [
        c for c in caras
        if c.internal
        and _paralelo(c.axis, frame.axis)
        and abs(_distancia_a_recta(c.point, frame.origin, frame.axis) - radio_patron) <= pos_tol
    ]

    # Agrupar por posición del eje en el plano perpendicular al frame.
    d = _unitario(frame.axis)
    agujeros: list[tuple[list[float], Cylinder]] = []
    for c in en_su_sitio:
        v = _resta(c.point, frame.origin)
        en_plano = _resta(v, _escala(d, _dot(v, d)))
        for i, (pos, existente) in enumerate(agujeros):
            if _norma(_resta(pos, en_plano)) < 0.05:
                if c.radius > existente.radius:
                    agujeros[i] = (pos, c)
                break
        else:
            agujeros.append((en_plano, c))
    return [c for _, c in agujeros]


def axis_distance(cara: Cylinder, frame: Frame) -> float:
    """Distancia del eje de una cara al eje del frame (son paralelos)."""
    return _distancia_a_recta(cara.point, frame.origin, frame.axis)
