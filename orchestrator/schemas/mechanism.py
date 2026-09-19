"""Especificación de un mecanismo (F3.15 (mecanismos)).

La produce el Mechanism Designer a partir de la petición del usuario. Es
una descripción, no un cálculo: el agente declara piezas, un árbol
cinemático con fórmulas y qué pares se tocan; la cinemática la evalúa el
código (ADR-010, enmienda) y el movimiento lo verifica el barrido.
"""

from typing import Literal

from pydantic import BaseModel, model_validator

from orchestrator.mechanisms.expr import ExprError, check_expr

MAX_FRAMES = 73


class Joint(BaseModel):
    type: Literal["revolute", "prismatic"]
    axis: list[float]
    """Eje de la articulación en el marco de la pieza (tras `rotation`),
    pasando por su origen."""
    value: str
    """Fórmula del ángulo (grados) o del desplazamiento (mm), en función del
    parámetro del mecanismo y de `params`."""


class Body(BaseModel):
    name: str
    parent: str | None = None
    """Pieza de la que cuelga; None = fija al mundo."""
    origin: list[float] = [0.0, 0.0, 0.0]
    """Origen de la pieza en el marco del padre (o del mundo)."""
    rotation: list[float] = [0.0, 0.0, 0.0]
    """Giro fijo [rx, ry, rz] en grados (R = Rz·Ry·Rx), antes de la articulación."""
    joint: Joint | None = None
    stretch: str | None = None
    """Solo resortes: fórmula del factor de escala a lo largo de su z local."""


class PartDef(Body):
    brief: str
    """Enunciado para el Part Designer: todas las cotas, en el marco LOCAL."""
    bbox_min: list[float]
    bbox_max: list[float]
    """Caja envolvente esperada en el marco local. Con ella se comprueba
    que la pieza dibujada es la que el mecanismo necesita."""
    color: str | None = None


class PinDef(Body):
    """Pasador o eje comprado: cilindro a lo largo de su z local, de 0 a largo."""
    diameter_mm: float
    length_mm: float


class PairRuleDef(BaseModel):
    a: str
    b: str
    kind: Literal["contact", "fixed"]
    """contact: tienen que tocarse en todo el recorrido (hueco ≤ max_gap_mm).
    fixed: van unidas (ajuste, chaveta): pueden tocarse, no atravesarse."""
    max_gap_mm: float = 0.05


class CheckDef(BaseModel):
    """Requisito medible del usuario, verificado con la cinemática."""
    body: str
    measure: Literal["travel", "rotation"]
    axis: Literal["x", "y", "z"]
    expected: float
    tolerance: float
    description: str


class Driver(BaseModel):
    name: str = "t"
    unit: Literal["deg", "mm"] = "deg"
    start: float
    end: float
    step: float
    ping_pong: bool = False
    """La animación va y vuelve (bisagra, prensa) en vez de dar vueltas."""
    label: str = ""
    """Texto de cada fotograma, p. ej. "manivela" → "manivela = 90°"."""


class MechanismSpec(BaseModel):
    title: str
    summary: str
    assumptions: list[str] = []
    """Decisiones que tomó el agente donde el usuario dijo "tú decides"."""
    params: dict[str, float] = {}
    driver: Driver
    parts: list[PartDef]
    pins: list[PinDef] = []
    rules: list[PairRuleDef] = []
    checks: list[CheckDef] = []

    @property
    def bodies(self) -> list[Body]:
        return [*self.parts, *self.pins]

    @model_validator(mode="after")
    def _coherente(self) -> "MechanismSpec":
        errores = []
        nombres = [b.name for b in self.bodies]
        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidos:
            errores.append(f"nombres repetidos: {repetidos}")
        if len(self.parts) < 2:
            errores.append("un mecanismo necesita al menos dos piezas")
        conocidos = set(nombres)
        for b in self.bodies:
            if b.parent is not None and b.parent not in conocidos:
                errores.append(f"{b.name}: el padre {b.parent!r} no existe")
        for b in self.bodies:  # ciclos
            visto, p = {b.name}, b.parent
            while p is not None and p in conocidos:
                if p in visto:
                    errores.append(f"{b.name}: el árbol cinemático tiene un ciclo")
                    break
                visto.add(p)
                p = next(x.parent for x in self.bodies if x.name == p)
        variables = set(self.params) | {self.driver.name}
        for b in self.bodies:
            for campo, texto in (("joint.value", b.joint.value if b.joint else None),
                                 ("stretch", b.stretch)):
                if texto is None:
                    continue
                try:
                    check_expr(texto, variables)
                except ExprError as e:
                    errores.append(f"{b.name}.{campo}: {e}")
            if b.joint is not None and sum(x * x for x in b.joint.axis) < 1e-9:
                errores.append(f"{b.name}: el eje de la articulación es nulo")
        for p in self.parts:
            if any(lo >= hi for lo, hi in zip(p.bbox_min, p.bbox_max)) or len(p.bbox_min) != 3:
                errores.append(f"{p.name}: bbox_min tiene que ser menor que bbox_max en x, y, z")
        for r in self.rules:
            for n in (r.a, r.b):
                if n not in conocidos:
                    errores.append(f"regla {r.a}/{r.b}: {n!r} no existe")
        for c in self.checks:
            if c.body not in conocidos:
                errores.append(f"comprobación {c.description!r}: {c.body!r} no existe")
        d = self.driver
        if d.step <= 0 or d.end <= d.start:
            errores.append("driver: hace falta start < end y step > 0")
        elif (d.end - d.start) / d.step + 1 > MAX_FRAMES:
            errores.append(f"driver: más de {MAX_FRAMES} posiciones; usa un paso mayor")
        if errores:
            raise ValueError("; ".join(errores))
        return self
