"""Articulaciones resueltas por contacto (F3.15 (mecanismos)).

Una pieza con `rest_on` no sigue una fórmula: se mueve desde su posición
de partida hasta **apoyarse** en otra. El valor lo busca la geometría
real, en FreeCAD, para cada posición del ciclo.

Por qué importa: sin esto, que un trinquete monte los dientes y caiga
entre ellos es una fórmula que escribe el agente, y entonces el ensamble
no demuestra nada. Con esto, el trinquete sube porque el diente lo
levanta, y si el perfil de los dientes está mal, no se apoya y se ve.

La cinemática sigue en Python: aquí solo se miden distancias. Se hace en
dos pasadas —una malla gruesa para encontrar dónde toca y otra fina
dentro de ese intervalo— para no mandar miles de poses a FreeCAD.
"""

from pathlib import Path

from orchestrator.assembly import pair_gaps

MUESTRAS_GRUESAS = 24
MUESTRAS_FINAS = 12


class SinApoyo(RuntimeError):
    """La pieza recorrió todo su margen sin tocar aquello en lo que se apoya."""


def _muestras(inicio: float, limite: float, sentido: int, n: int) -> list[float]:
    return [inicio + sentido * limite * k / n for k in range(n + 1)]


def solve_contacts(spec, kin, steps: dict[str, Path], pins: dict, freecadcmd: str,
                   frames: list[float]) -> dict[tuple[float, str], float]:
    """Valor de cada articulación `rest_on` en cada posición del ciclo."""
    apoyadas = [b for b in spec.bodies if b.joint and b.joint.rest_on]
    if not apoyadas:
        return {}

    resueltos: dict[tuple[float, str], float] = {}
    for b in apoyadas:
        r = b.joint.rest_on
        sentido = 1 if r.toward == "increase" else -1
        inicio = {t: kin.joint_value(b.name, t) for t in frames}
        candidatos = {t: _muestras(inicio[t], r.limit, sentido, MUESTRAS_GRUESAS) for t in frames}
        for ronda in range(2):
            poses, etiquetas = {}, {}
            for t in frames:
                for v in candidatos[t]:
                    clave = len(poses)
                    poses[clave] = kin.poses(t, {b.name: v})
                    etiquetas[clave] = (t, v)
            huecos = pair_gaps(steps, pins, poses, [(b.name, r.target)], freecadcmd)
            medido: dict[float, list[tuple[float, float]]] = {}
            for g in huecos:
                t, v = etiquetas[g["angle"]]
                medido.setdefault(t, []).append((v, g["gap_mm"]))

            nuevos = {}
            for t in frames:
                serie = sorted(medido[t], key=lambda x: sentido * x[0])
                tocado = next((i for i, (_, d) in enumerate(serie) if d <= r.gap_mm), None)
                if tocado is None:
                    raise SinApoyo(
                        f"«{b.name}» no llega a apoyarse en «{r.target}» con "
                        f"{spec.driver.name} = {t:g}: recorre {r.limit:g} desde "
                        f"{serie[0][0]:.2f} y se queda a {serie[-1][1]:.2f} mm. "
                        "Acerca las piezas, alarga el recorrido de búsqueda o "
                        "corrige la posición de partida."
                    )
                if ronda == 0:
                    anterior = serie[max(tocado - 1, 0)][0]
                    paso = abs(serie[1][0] - serie[0][0])
                    nuevos[t] = _muestras(anterior, paso, sentido, MUESTRAS_FINAS)
                else:
                    resueltos[(round(t, 6), b.name)] = serie[tocado][0]
            candidatos = nuevos
        kin.set_solved(resueltos)
    return resueltos


def block_problems(spec, kin, steps: dict[str, Path], pins: dict, freecadcmd: str) -> list[str]:
    """Cada bloqueo declarado tiene que impedir de verdad el movimiento: al
    forzar `delta` en la articulación, las piezas se atravesarían."""
    problemas = []
    for bl in spec.blocks:
        valor = kin.joint_value(bl.body, bl.at) + bl.delta
        poses = {bl.at: kin.poses(bl.at, {bl.body: valor})}
        hueco = pair_gaps(steps, pins, poses, [(bl.body, bl.against)], freecadcmd)[0]["gap_mm"]
        if hueco >= 0:
            problemas.append(
                f"«{bl.against}» NO bloquea a «{bl.body}» con {spec.driver.name} = {bl.at:g}: "
                f"moviendo {bl.delta:g} su articulación quedan {hueco:.2f} mm de hueco, "
                "así que nada le impide moverse. El bloqueo tiene que salir de la "
                "geometría (un diente, un tope), no de la fórmula."
            )
    return problemas
