"""`MechanismSpec` → disposición para `build_mechanism` (F3.15 (mecanismos))."""

from mech_toolkit.geometry import Placement
from orchestrator.mechanisms.kinematics import Kinematics
from orchestrator.schemas.mechanism import MechanismSpec


class SpecLayout:
    view = (30, -55)

    def __init__(self, spec: MechanismSpec) -> None:
        self.spec = spec
        self.kin = Kinematics(spec)
        self.title = spec.title
        self.colors = {p.name: p.color for p in spec.parts if p.color}
        f = self.frames()
        self.saved_frame = f[len(f) // 3]

    def briefs(self) -> dict[str, str]:
        return {p.name: p.brief for p in self.spec.parts}

    def pins(self) -> dict[str, tuple[float, float]]:
        return {p.name: (p.diameter_mm, p.length_mm) for p in self.spec.pins}

    def poses(self, t: float) -> dict[str, Placement]:
        return self.kin.poses(t)

    def frames(self) -> list[float]:
        return self.kin.frames()

    def animation_frames(self) -> list[float]:
        ida = self.frames()
        return ida + ida[-2:0:-1] if self.spec.driver.ping_pong else ida

    def pair_rules(self):
        reglas = {(r.a, r.b): (0.0, r.max_gap_mm if r.kind == "contact" else None)
                  for r in self.spec.rules}
        # En un tope las piezas se tocan al final del recorrido: tocarse sí,
        # atravesarse no (que bloquee de verdad lo comprueba stop_problems).
        for t in self.spec.stops:
            reglas.setdefault((t.a, t.b), (0.0, None))
        # Una pieza apoyada TOCA aquello en lo que se apoya: si no se declara,
        # el barrido le exigiría la holgura de una pieza suelta y siempre
        # fallaría (fallo real: 11 rondas del trinquete).
        from orchestrator.mechanisms.contact import BANDA_POR_DEFECTO

        for b in self.spec.bodies:
            if b.joint and b.joint.rest_on:
                reglas.setdefault(
                    (b.name, b.joint.rest_on.target),
                    (0.0, max(b.joint.rest_on.gap_mm, BANDA_POR_DEFECTO)))
        return reglas

    def label(self, t: float) -> str:
        d = self.spec.driver
        return f"{d.label or d.name} = {t:g}{'°' if d.unit == 'deg' else ' mm'}"

    def check_bounds(self, nombre: str, resultado, tol: float = 0.1) -> str | None:
        """La pieza dibujada tiene que ocupar la caja que declaró el
        Mechanism Designer: es donde la colocan las poses."""
        p = next(x for x in self.spec.parts if x.name == nombre)
        if resultado.bbox_min is None:
            return None
        fuera = [i for i in range(3)
                 if abs(resultado.bbox_min[i] - p.bbox_min[i]) > tol
                 or abs(resultado.bbox_max[i] - p.bbox_max[i]) > tol]
        if not fuera:
            return None
        rango = lambda a, b, i: f"{'xyz'[i]} de {a[i]:.4g} a {b[i]:.4g} mm"  # noqa: E731
        return (
            f"la pieza ocupa {', '.join(rango(resultado.bbox_min, resultado.bbox_max, i) for i in fuera)}; "
            f"el mecanismo la necesita en {', '.join(rango(p.bbox_min, p.bbox_max, i) for i in fuera)}. "
            "Revisa el origen, la posición y las medidas de cada cuerpo según el enunciado."
        )

    def notes(self) -> list[str]:
        frames = self.frames()
        return [
            *(f"decisión: {a}" for a in self.spec.assumptions),
            *(f"requisito «{c.description}»: {self.kin.measure(c, frames):.2f} "
              f"(se pide {c.expected:g} ± {c.tolerance:g})" for c in self.spec.checks),
        ]
