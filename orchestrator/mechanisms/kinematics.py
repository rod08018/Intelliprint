"""Cinemática de un `MechanismSpec`: de fórmulas a poses (F3.15 (mecanismos)).

Pose de una pieza = pose del padre · traslación(origin) · giro(rotation) ·
articulación(valor). Todo en código determinista: el LLM declara, el
código calcula (ADR-010, enmienda).
"""

import math

from mech_toolkit.geometry import Placement, _matmul, _rotacion
from orchestrator.mechanisms.expr import ExprError, evaluate
from orchestrator.schemas.mechanism import MechanismSpec


def _rodrigues(eje, grados):
    n = math.sqrt(sum(a * a for a in eje))
    x, y, z = (a / n for a in eje)
    c, s = math.cos(math.radians(grados)), math.sin(math.radians(grados))
    k = 1 - c
    return [[c + x * x * k, x * y * k - z * s, x * z * k + y * s],
            [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
            [z * x * k - y * s, z * y * k + x * s, c + z * z * k]]


def _aplicar(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def euler_zyx(r) -> list[float]:
    """[rx, ry, rz] en grados con R = Rz·Ry·Rx (convención de Placement)."""
    sy = -r[2][0]
    sy = max(-1.0, min(1.0, sy))
    ry = math.degrees(math.asin(sy))
    if abs(sy) < 1 - 1e-9:
        rx = math.degrees(math.atan2(r[2][1], r[2][2]))
        rz = math.degrees(math.atan2(r[1][0], r[0][0]))
    else:  # bloqueo de cardán: rx y rz se mezclan; se fija rx = 0
        rx = 0.0
        rz = math.degrees(math.atan2(-r[0][1], r[1][1]))
    return [rx, ry, rz]


class Kinematics:
    def __init__(self, spec: MechanismSpec) -> None:
        self.spec = spec
        self._por_nombre = {b.name: b for b in spec.bodies}

    def frames(self) -> list[float]:
        d = self.spec.driver
        n = int(round((d.end - d.start) / d.step))
        valores = [d.start + i * d.step for i in range(n + 1)]
        if valores[-1] < d.end - 1e-9:
            valores.append(d.end)
        return [round(v, 6) for v in valores]

    def _vars(self, t: float) -> dict[str, float]:
        return {**self.spec.params, self.spec.driver.name: t}

    def _mundo(self, nombre: str, t: float, cache: dict):
        if nombre in cache:
            return cache[nombre]
        b = self._por_nombre[nombre]
        if b.parent is None:
            rp, pp = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0.0, 0.0, 0.0]
        else:
            rp, pp = self._mundo(b.parent, t, cache)
        p = [a + c for a, c in zip(pp, _aplicar(rp, b.origin))]
        r = _matmul(rp, _rotacion(*b.rotation))
        if b.joint is not None:
            v = evaluate(b.joint.value, self._vars(t))
            if b.joint.type == "revolute":
                r = _matmul(r, _rodrigues(b.joint.axis, v))
            else:
                n = math.sqrt(sum(a * a for a in b.joint.axis))
                p = [a + c for a, c in zip(p, _aplicar(r, [v * a / n for a in b.joint.axis]))]
        cache[nombre] = (r, p)
        return r, p

    def poses(self, t: float) -> dict[str, Placement]:
        cache: dict = {}
        salida = {}
        for b in self.spec.bodies:
            r, p = self._mundo(b.name, t, cache)
            escala = evaluate(b.stretch, self._vars(t)) if b.stretch else 1.0
            salida[b.name] = Placement(origin=p, rotation=euler_zyx(r), scale_z=escala)
        return salida

    def matrices(self, t: float) -> dict[str, tuple]:
        cache: dict = {}
        return {b.name: self._mundo(b.name, t, cache) for b in self.spec.bodies}

    # --- requisitos -----------------------------------------------------------

    def measure(self, check, frames: list[float]) -> float:
        eje = "xyz".index(check.axis)
        if check.measure == "travel":
            valores = [self.matrices(t)[check.body][1][eje] for t in frames]
            return max(valores) - min(valores)
        # rotation: ángulo barrido alrededor del eje del mundo
        u = [0.0, 0.0, 0.0]
        u[(eje + 1) % 3] = 1.0
        angulos = []
        for t in frames:
            v = _aplicar(self.matrices(t)[check.body][0], u)
            a, b = v[(eje + 1) % 3], v[(eje + 2) % 3]
            angulos.append(math.degrees(math.atan2(b, a)))
        seguido = [angulos[0]]
        for a in angulos[1:]:
            d = (a - seguido[-1] + 180) % 360 - 180
            seguido.append(seguido[-1] + d)
        return max(seguido) - min(seguido)

    def validate(self) -> None:
        """Lo que se puede comprobar sin geometría: que todas las fórmulas se
        evalúan en todo el recorrido y que se cumplen los requisitos
        medibles. Lanza ValueError con el motivo para el agente."""
        frames = self.frames()
        for t in frames:
            try:
                self.poses(t)
            except ExprError as e:
                raise ValueError(f"con {self.spec.driver.name} = {t:g}: {e}") from None
        fallos = []
        for c in self.spec.checks:
            medido = self.measure(c, frames)
            if abs(medido - c.expected) > c.tolerance:
                fallos.append(
                    f"{c.description}: {c.body} tiene {c.measure} en {c.axis} de {medido:.2f} "
                    f"y se pide {c.expected:g} ± {c.tolerance:g}"
                )
        if fallos:
            raise ValueError("requisitos no cumplidos: " + "; ".join(fallos))
