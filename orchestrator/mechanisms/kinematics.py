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
        self._apoyos: dict[tuple[float, str], float] = {}
        """Valores resueltos por contacto (F3.15 (mecanismos)): los calcula
        `solve_contacts` con la geometría real, no una fórmula."""

    def set_solved(self, valores: dict[tuple[float, str], float]) -> None:
        self._apoyos = dict(valores)

    def joint_value(self, nombre: str, t: float, forzado: dict | None = None) -> float:
        b = self._por_nombre[nombre]
        if forzado and nombre in forzado:
            return forzado[nombre]
        if b.joint.rest_on is not None:
            clave = (round(t, 6), nombre)
            if clave in self._apoyos:
                return self._apoyos[clave]
            # Sin resolver todavía: la posición de partida, separada del apoyo.
            return evaluate(b.joint.rest_on.start, self._vars_base(t))
        return evaluate(b.joint.value, self._vars_base(t))

    def frames(self) -> list[float]:
        d = self.spec.driver
        n = int(round((d.end - d.start) / d.step))
        valores = [d.start + i * d.step for i in range(n + 1)]
        if valores[-1] < d.end - 1e-9:
            valores.append(d.end)
        return [round(v, 6) for v in valores]

    def _vars_base(self, t: float) -> dict[str, float]:
        return {**self.spec.params, self.spec.driver.name: t}

    def _vars(self, t: float) -> dict[str, float]:
        """Los parámetros, el ciclo y el valor de cada articulación como
        `q_<pieza>`. Solo las fórmulas de estiramiento los ven: un resorte se
        comprime lo que se mueve quien lo aplasta, y eso no se puede escribir
        en función del ciclo cuando lo decide un contacto. Las fórmulas de las
        articulaciones NO los ven, para que no puedan depender unas de otras."""
        valores = self._vars_base(t)
        base = dict(valores)
        for b in self.spec.bodies:
            if b.joint is None:
                continue
            if b.joint.rest_on is not None:
                clave = (round(t, 6), b.name)
                valores[f"q_{b.name}"] = self._apoyos.get(
                    clave, evaluate(b.joint.rest_on.start, base))
            else:
                valores[f"q_{b.name}"] = evaluate(b.joint.value, base)
        return valores

    def _mundo(self, nombre: str, t: float, cache: dict, forzado: dict | None = None):
        if nombre in cache:
            return cache[nombre]
        b = self._por_nombre[nombre]
        if b.parent is None:
            rp, pp = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0.0, 0.0, 0.0]
        else:
            rp, pp = self._mundo(b.parent, t, cache, forzado)
        p = [a + c for a, c in zip(pp, _aplicar(rp, b.origin))]
        r = _matmul(rp, _rotacion(*b.rotation))
        if b.joint is not None:
            v = self.joint_value(nombre, t, forzado)
            if b.joint.type == "revolute":
                r = _matmul(r, _rodrigues(b.joint.axis, v))
            else:
                n = math.sqrt(sum(a * a for a in b.joint.axis))
                p = [a + c for a, c in zip(p, _aplicar(r, [v * a / n for a in b.joint.axis]))]
        cache[nombre] = (r, p)
        return r, p

    def poses(self, t: float, forzado: dict[str, float] | None = None) -> dict[str, Placement]:
        """`forzado` fija a mano el valor de alguna articulación (para probar
        si una pieza podría retroceder: `blocks`)."""
        cache: dict = {}
        salida = {}
        for b in self.spec.bodies:
            r, p = self._mundo(b.name, t, cache, forzado)
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

    def _depende_de_apoyo(self, nombre: str) -> bool:
        """¿El movimiento de esta pieza (o el de su padre) lo decide un
        contacto todavía sin resolver?"""
        while nombre:
            b = self._por_nombre[nombre]
            if b.joint and b.joint.rest_on and not any(
                    n == nombre for _, n in self._apoyos):
                return True
            nombre = b.parent
        return False

    def checks_pendientes(self) -> list:
        """Requisitos que no se pueden juzgar hasta resolver los apoyos."""
        return [c for c in self.spec.checks if self._depende_de_apoyo(c.body)]

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
        pendientes = {id(c) for c in self.checks_pendientes()}
        for c in self.spec.checks:
            if id(c) in pendientes:
                # Su movimiento lo decide la geometría, no una fórmula: se
                # juzga después de resolver el apoyo (fallo real: la leva).
                continue
            medido = self.measure(c, frames)
            if abs(medido - c.expected) > c.tolerance:
                fallos.append(
                    f"{c.description}: {c.body} tiene {c.measure} en {c.axis} de {medido:.2f} "
                    f"y se pide {c.expected:g} ± {c.tolerance:g}"
                )
        if fallos:
            raise ValueError("requisitos no cumplidos: " + "; ".join(fallos))
