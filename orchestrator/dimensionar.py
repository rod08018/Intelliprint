"""Que el motor alcance antes de dibujar (F10.4 (dimensionar), ADR-021).

El estudio de movimientos dice si cada motor aguanta, pero con las piezas
ya construidas: el brazo del banco 1112-0318 costó 1,22 USD antes de saber
que su hombro iba al 16 % de su par. Aquí se hace la misma cuenta con lo
que dice el plan —la carga, lo que mide el brazo desde cada eje y lo
comprado que cuelga— y con el peso de lo impreso estimado, antes de gastar
en ninguna pieza. El estudio la repite después con las masas de verdad.

No es F7.11 (dimensionado), que es de drones y elige componentes: aquí no
se elige nada, se comprueba lo que el plan eligió.
"""

from pathlib import Path
from typing import Sequence

from orchestrator.componentes import cargar
from orchestrator.estudio import G, MARGEN_SERVO, RENDIMIENTO
from orchestrator.schemas.obra import Gira, Obra

GRAMOS_POR_MM = 0.2
"""Lo que pesa lo impreso por cada milímetro de brazo. Es una estimación
del lado pesado, de lo único medido: los dos tramos del brazo del banco
1112-0318 (brazo superior y antebrazo) pesan 21,8 g en 120 mm, 0,18 g/mm.
Un brazo para NEMA 17 pesará más por milímetro, y esto no lo sabe."""


def _disponible(u: Gira, extra: Sequence[Path]) -> float | None:
    """El par que se le puede pedir al giro, en N·m: la parte del par del
    motor que el estudio da por buena, llevada al eje por su transmisión.
    None si lo que lo mueve no da par (un rodamiento suelto)."""
    try:
        ficha = cargar(u.movido_por.motor if u.movido_por else u.componente, extra)
    except KeyError:
        return None
    # La tensión más baja de su hoja, del lado seguro: como el estudio
    # cuando el invento no dice con cuál va.
    par = ficha.par_motor_Nm(min(ficha.par_kgf_cm) if ficha.par_kgf_cm else None)
    if par is None:
        return None
    if u.movido_por:
        par *= u.movido_por.relacion * RENDIMIENTO[u.movido_por.tipo]
    return MARGEN_SERVO * par


def pares(obra: Obra, extra: Sequence[Path] = ()) -> list[dict]:
    """Lo que la gravedad le pide a cada giro que levanta, con el brazo
    estirado en horizontal y la carga en la punta, y lo que da su motor:
    [{"union", "pide_Nm", "da_Nm", "brazo_mm", "cuelga_g"}], en el orden
    del plan. Solo los giros con `brazo_mm`, y solo si el plan trae la
    carga; uno de eje vertical no carga peso y no sale."""
    giros = [u for u in obra.uniones if isinstance(u, Gira)]
    if obra.carga_g is None:
        return []
    de = {u.gira: u for u in giros}          # el giro que mueve a cada pieza

    def mas_alla(u: Gira) -> list[Gira]:
        """Los giros que cuelgan de `u`, él incluido."""
        suyos = [u]
        for otro in giros:
            if otro.sobre == u.gira:
                suyos += mas_alla(otro)
        return suyos

    salida = []
    for u in giros:
        if u.brazo_mm is None or u.eje == "vertical":
            continue
        momento, cuelga = obra.carga_g * u.brazo_mm, 0.0       # en g·mm
        for k in mas_alla(u):
            largo_k = k.brazo_mm if k.brazo_mm is not None else 0.0
            hijos = [h.brazo_mm or 0.0 for h in giros if h.sobre == k.gira]
            tramo = max(largo_k - max(hijos, default=0.0), 0.0)
            desde = max(u.brazo_mm - largo_k, 0.0)             # de `u` al eje de `k`
            momento += GRAMOS_POR_MM * tramo * (desde + tramo / 2)
            cuelga += GRAMOS_POR_MM * tramo
            # Lo comprado que lleva la pieza que mueve `k`: va en el eje del
            # giro siguiente, que es para lo que lo lleva; si no hay
            # siguiente, en la punta, que es lo peor.
            for id_ in obra.nodo(k.gira).compra:
                try:
                    masa = cargar(id_, extra).masa_g
                except KeyError:
                    masa = None
                if not masa:
                    continue
                donde = desde + tramo if hijos else u.brazo_mm
                momento += masa * donde
                cuelga += masa
        salida.append({"union": u.id, "pide_Nm": momento * 1e-6 * G,
                       "da_Nm": _disponible(u, extra) if de.get(u.gira) is u else None,
                       "brazo_mm": u.brazo_mm, "cuelga_g": cuelga})
    return salida


def errores(obra: Obra, extra: Sequence[Path] = ()) -> list[str]:
    """Los giros a los que el plan les pide más de lo que da su motor."""
    fallos = []
    for p in pares(obra, extra):
        if p["da_Nm"] is None or p["pide_Nm"] <= p["da_Nm"] + 1e-9:
            continue
        fallos.append(
            f"unión «{p['union']}»: el motor no alcanza. Con el brazo estirado en horizontal "
            f"la gravedad le pide {p['pide_Nm']:.3f} N·m ({obra.carga_g:g} g de carga a "
            f"{p['brazo_mm']:g} mm, más unos {p['cuelga_g']:.0f} g de lo que cuelga) y lo que "
            f"lo mueve da {p['da_Nm']:.3f} N·m en el eje (el {MARGEN_SERVO:.0%} de su par). "
            "Pon un motor con más par, muévelo por una transmisión con más relación "
            "(`movido_por`), o acorta el brazo")
    return fallos
