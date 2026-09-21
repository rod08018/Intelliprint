"""Verificar una ronda, puntuarla y afinar sus números sin el modelo
(F3.15 (mecanismos)).

Fallo real que lo motiva, el cuarto trinquete del 2026-09-21: en las rondas
11-16 la rueda ya avanzaba 37-39° empujada de verdad por la uña (se pedían
45). En la 17 el diseñador lo tiró todo, empeoró y agotó el dinero.

Faltaban dos cosas, y las dos son de código:

- **Saber cuál es la mejor ronda**, para volver a ella cuando una empeora
  (`puntuacion`).
- **Afinar los números** —la amplitud de la palanca, el punto de partida de
  una búsqueda— midiendo, en vez de que el modelo los pruebe a ciegas a
  0.08 USD por intento (`afinar`). Los `params` solo entran en fórmulas, así
  que cambiarlos no obliga a redibujar ninguna pieza: basta volver a barrer.

«El LLM no hace geometría» (§ 1): el modelo elige la estructura del
mecanismo; los números que se pueden medir los ajusta el código.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.assembly import build_assembly, sweep_collisions
from orchestrator.mechanisms.checks import joint_axis_problems, stop_problems
from orchestrator.mechanisms.contact import SinApoyo, block_problems, solve_contacts
from orchestrator.mechanisms.resumen import requisitos_medidos
from orchestrator.mechanisms.run import POSE_GUARDADA, MechanismReport
from orchestrator.mechanisms.spec_layout import SpecLayout


@dataclass
class Verificacion:
    """Hasta dónde llegó una ronda y qué falló."""

    PIEZAS = 0    # alguna pieza no se pudo dibujar
    EJES = 1      # alguna pieza no tiene agujero en su eje de giro
    APOYOS = 2    # se cayó buscando apoyos o midiendo requisitos
    BARRIDO = 3   # llegó a barrer el recorrido completo

    etapa: int
    fallos: list[str] = field(default_factory=list)
    desvio: float = 0.0
    """Cuánto se alejan los requisitos de lo pedido, en tolerancias: 0 si
    todos caen dentro."""
    layout: SpecLayout | None = None
    choques: list | None = None
    ajustes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.etapa == self.BARRIDO and not self.fallos


# Las cifras que dicen CUÁNTO falla algo, y solo esas. En un motivo hay más
# números —«recorre 90», «con el valor 118.12», «t = 15»— que son del ciclo o
# de la búsqueda, no del fallo.
_MAGNITUDES = [
    re.compile(r"solapa(?:rse|n)\s+([\d.]+)\s*mm³"),
    re.compile(r"([\d.]+)\s*mm³ en común"),
    re.compile(r"más cerca que pasa es\s+([\d.]+)\s*mm"),
    re.compile(r"se separan\s+([\d.]+)\s*mm"),
    re.compile(r"quedan\s+([\d.]+)\s*mm de hueco"),
]


def magnitud_del_fallo(lineas: list[str]) -> float:
    """Cuánto fallan, sumado: mm³ de solape y mm de hueco que sobran.

    Fallo real (Ginebra del 2026-09-21): «el pasador atraviesa la rueda» con
    29.9, 1.2, 29.9, 29.9 y 1.1 mm³. Las de 1 mm³ estaban casi resueltas y
    para el sistema eran «el mismo fallo» que las de 30: la memoria no supo
    anclarse en la buena y el detector de atasco paró el proyecto."""
    total = 0.0
    for linea in lineas:
        for patron in _MAGNITUDES:
            total += sum(float(m) for m in patron.findall(linea))
    return total


def puntuacion(v: Verificacion) -> tuple:
    """Menor es mejor. Primero HASTA DÓNDE llegó, luego cuántos fallos tuvo,
    luego CUÁNTO fallan, y al final cuánto se desvía de lo pedido.

    El orden importa: una ronda que se cae al buscar apoyos da UN fallo, y
    una que llega al barrido y encuentra dos choques da dos. Contando solo
    fallos, ganaría la que avanzó menos. Y entre dos rondas con el mismo
    fallo, la de 1 mm³ de solape está mucho más cerca que la de 30."""
    return (-v.etapa, len(v.fallos), round(magnitud_del_fallo(v.fallos), 4),
            round(v.desvio, 6))


def _desvio(spec, layout) -> float:
    total = 0.0
    for r in requisitos_medidos(spec, layout):
        if r["medido"] is None:
            total += 10.0     # sin medir: lejos, pero no infinito
        else:
            total += max(0.0, abs(r["desviacion"]) - r["tolerancia"]) / max(r["tolerancia"], 1e-6)
    return total


def _resumen_de_choques(choques, angulos, min_gap_mm) -> list[str]:
    informe = MechanismReport(parts={}, assembly="", animation=None, angles=angulos,
                              min_gap_mm=min_gap_mm, collisions=choques)
    return informe.collision_summary()


def verificar(spec, steps: dict[str, Path], freecadcmd: str, min_gap_mm: float, *,
              comprobar_ejes: bool = True) -> Verificacion:
    """Todo lo que se comprueba de una ronda con las piezas ya dibujadas:
    ejes, apoyos, requisitos, barrido, topes, bloqueos y pasadores. No
    escribe nada en la carpeta del proyecto: el afinado la llama muchas veces,
    a la vez, con la misma geometría."""
    layout = SpecLayout(spec)
    ajustes: list[str] = []

    if comprobar_ejes:
        fallos = [f"- {x}" for x in joint_axis_problems(spec, steps, freecadcmd)]
        if fallos:
            return Verificacion(Verificacion.EJES, fallos, 10.0, layout, None, ajustes)

    try:
        if any(b.joint and b.joint.rest_on for b in spec.bodies):
            # Las piezas que se apoyan encuentran su sitio en la geometría real
            # ANTES de barrer: su movimiento no lo decide una fórmula.
            solve_contacts(spec, layout.kin, steps, layout.pins(), freecadcmd, layout.frames(),
                           notas=ajustes)
        # Con los apoyos resueltos, los requisitos que dependían de ellos ya
        # se pueden medir. Sin apoyos es barato y confirma lo del agente.
        layout.kin.validate()
    except (SinApoyo, ValueError) as e:
        return Verificacion(Verificacion.APOYOS, [f"- {e}"], _desvio_seguro(spec, layout),
                            layout, None, ajustes)

    angulos = layout.frames()
    poses = {a: layout.poses(a) for a in angulos}
    choques = sweep_collisions(steps, layout.pins(), poses, min_gap_mm, freecadcmd,
                               layout.pair_rules())
    fallos = [f"- {linea}" for linea in (
        _resumen_de_choques(choques, angulos, min_gap_mm)
        + stop_problems(spec, layout, steps, freecadcmd)
        + block_problems(spec, layout.kin, steps, layout.pins(), freecadcmd))]
    ejes = {x.name for x in spec.pins}
    atravesados = sorted({(c.a if c.b in ejes else c.b, c.b if c.b in ejes else c.a)
                          for c in choques if c.gap_mm < 0 and ({c.a, c.b} & ejes)})
    for pieza, eje in atravesados:
        fallos.append(f"- «{eje}» atraviesa material de «{pieza}»: falta el agujero, "
                      "no está en el eje del pasador, o el pasador es demasiado largo "
                      "y se mete en otra pieza")
    return Verificacion(Verificacion.BARRIDO, fallos, _desvio_seguro(spec, layout),
                        layout, choques, ajustes)


def _desvio_seguro(spec, layout) -> float:
    try:
        return _desvio(spec, layout)
    except Exception:
        return 10.0 * max(len(spec.checks), 1)


def montar(v: Verificacion, steps: dict[str, Path], carpeta: Path, freecadcmd: str,
           min_gap_mm: float) -> MechanismReport:
    """El ensamble de una ronda que llegó al barrido, sin volver a barrer."""
    layout = v.layout
    ensamble = Path(carpeta) / "assembly.FCStd"
    guardada = getattr(layout, "saved_frame", POSE_GUARDADA)
    build_assembly(steps, layout.pins(), layout.poses(guardada), ensamble, freecadcmd)
    return MechanismReport(
        parts={n: str(p) for n, p in steps.items()}, assembly=str(ensamble), animation=None,
        angles=layout.frames(), min_gap_mm=min_gap_mm, collisions=v.choques or [],
        notes=layout.notes(),
    )


# --- Afinado ------------------------------------------------------------------

FACTORES = (0.8, 1.25)
"""Primera pasada: cada parámetro un 20 % abajo y un 25 % arriba (simétrico
en escala logarítmica). Luego se insiste en la dirección que mejoró."""


def _variante(spec, nombre: str, valor: float):
    copia = spec.model_copy(deep=True)
    copia.params[nombre] = valor
    return copia


def afinar(spec, base: Verificacion, evaluar, *, max_pruebas: int = 10, hilos: int = 4):
    """Prueba variaciones de los `params` y se queda con la que mejor
    puntúa, si mejora a `base`. Devuelve (spec, verificación, notas) o None.

    `evaluar(spec) -> Verificacion` es la verificación sin dibujar (en el
    flujo, `verificar` con la geometría ya construida). No modifica `spec`.
    """
    candidatos = [(n, v, v * f) for n, v in spec.params.items() if v for f in FACTORES]
    candidatos = candidatos[:max_pruebas]
    if not candidatos:
        return None

    def probar(c):
        nombre, _, nuevo = c
        variante = _variante(spec, nombre, nuevo)
        return c, variante, evaluar(variante)

    with ThreadPoolExecutor(max_workers=hilos) as pool:
        resultados = list(pool.map(probar, candidatos))
    usadas = len(resultados)

    (nombre, original, nuevo), mejor_spec, mejor = min(resultados, key=lambda r: puntuacion(r[2]))
    if puntuacion(mejor) >= puntuacion(base):
        return None

    # Insistir en la dirección que mejoró, mientras siga mejorando.
    factor = nuevo / original
    while mejor.fallos and usadas < max_pruebas:
        siguiente = mejor_spec.params[nombre] * factor
        variante = _variante(mejor_spec, nombre, siguiente)
        prueba = evaluar(variante)
        usadas += 1
        if puntuacion(prueba) >= puntuacion(mejor):
            break
        mejor_spec, mejor = variante, prueba

    final = mejor_spec.params[nombre]
    nota = (f"el código afinó «{nombre}» de {original:g} a {final:.4g} midiendo {usadas} "
            f"variantes: {len(base.fallos)} → {len(mejor.fallos)} fallos")
    return mejor_spec, mejor, [nota]
