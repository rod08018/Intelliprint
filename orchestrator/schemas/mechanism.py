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


class RestOn(BaseModel):
    """La pieza NO sigue una fórmula: se mueve hasta APOYARSE en otra.

    El sistema busca en la geometría real, en cada posición del ciclo, el
    primer valor (partiendo de `start` y avanzando hacia `toward`) en el que
    las dos piezas se tocan. Así un trinquete monta los dientes porque la
    geometría lo obliga, no porque alguien escriba la fórmula."""
    target: str
    start: str
    """Fórmula del valor de partida: la pieza separada de aquello en lo que
    se apoya (p. ej. el trinquete levantado)."""
    toward: Literal["increase", "decrease"]
    limit: float
    """Cuánto puede moverse como máximo desde `start` buscando el apoyo."""
    gap_mm: float = 0.02


class Joint(BaseModel):
    type: Literal["revolute", "prismatic"]
    axis: list[float]
    """Eje de la articulación en el marco de la pieza (tras `rotation`),
    pasando por su origen."""
    value: str | None = None
    """Fórmula del ángulo (grados) o del desplazamiento (mm), en función del
    parámetro del mecanismo y de `params`."""
    rest_on: RestOn | None = None
    """Alternativa a `value`: el valor lo decide el contacto con otra pieza."""

    @model_validator(mode="after")
    def _formula_o_contacto(self) -> "Joint":
        if (self.value is None) == (self.rest_on is None):
            raise ValueError(
                "una articulación lleva `value` (fórmula) o `rest_on` (apoyo en "
                "otra pieza), pero no las dos ni ninguna"
            )
        return self


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


class BlockDef(BaseModel):
    """Bloqueo: en la posición `at` del ciclo, `body` NO puede moverse
    `delta` en su articulación porque `against` se lo impide.

    Es lo que hace que un trinquete sea un trinquete: el sistema comprueba
    que al intentar retroceder las piezas se atravesarían."""
    body: str
    against: str
    at: float
    delta: float


class StopDef(BaseModel):
    """Tope: `a` y `b` se tocan cuando el parámetro vale `at` y, pasado ese
    valor (hacia `beyond`: "above" = mayor, "below" = menor), se
    atravesarían. Así se verifica que el tope de verdad para el movimiento."""
    a: str
    b: str
    at: float
    beyond: Literal["above", "below"]


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
    stops: list[StopDef] = []
    blocks: list[BlockDef] = []

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
                                 ("joint.rest_on.start",
                                  b.joint.rest_on.start if b.joint and b.joint.rest_on else None),
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
        apoyadas = {b.name for b in self.bodies if b.joint and b.joint.rest_on}
        for b in self.bodies:
            if b.parent in apoyadas:
                errores.append(
                    f"{b.name}: cuelga de {b.parent!r}, que se apoya por contacto; "
                    "una pieza apoyada no puede llevar otras encima"
                )
            if b.joint and b.joint.rest_on and b.joint.rest_on.target not in conocidos:
                errores.append(f"{b.name}: se apoya en {b.joint.rest_on.target!r}, que no existe")
            if b.joint and b.joint.rest_on and b.joint.rest_on.limit <= 0:
                errores.append(f"{b.name}: el recorrido de búsqueda del apoyo tiene que ser > 0")
        for bl in self.blocks:
            for n in (bl.body, bl.against):
                if n not in conocidos:
                    errores.append(f"bloqueo {bl.body}/{bl.against}: {n!r} no existe")
            if bl.delta == 0:
                errores.append(f"bloqueo {bl.body}/{bl.against}: delta no puede ser 0")
            cuerpo = next((x for x in self.bodies if x.name == bl.body), None)
            if cuerpo is not None and cuerpo.joint is None:
                errores.append(f"bloqueo {bl.body}/{bl.against}: {bl.body!r} no tiene articulación")
        for t in self.stops:
            for n in (t.a, t.b):
                if n not in conocidos:
                    errores.append(f"tope {t.a}/{t.b}: {n!r} no existe")
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
