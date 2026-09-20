"""Articulaciones resueltas por contacto (F3.15 (mecanismos)).

Una pieza con `rest_on` no sigue una fórmula: se mueve desde su posición
de partida hasta **apoyarse** en otra. El valor lo busca la geometría
real, en FreeCAD, para cada posición del ciclo.

Por qué importa: sin esto, que un trinquete monte los dientes y caiga
entre ellos es una fórmula que escribe el agente, y entonces el ensamble
no demuestra nada. Con esto, el trinquete sube porque el diente lo
levanta, y si el perfil de los dientes está mal, no se apoya y se ve.

**Cómo se busca, y por qué así.** La primera versión muestreaba y se
quedaba con el primer valor cuyo hueco bajara del umbral. Eso aceptaba
también un solape de 14 mm³, porque un solape "baja del umbral" de sobra;
el barrido lo rechazaba después y el agente recibía un choque sin causa.
De las 19 rondas del reto del trinquete, 11 murieron ahí.

Ahora: una pasada gruesa localiza el **cambio de signo** del hueco y una
bisección lo afina hasta caer en la banda del contacto (la MISMA que
comprueba el barrido). Cada iteración manda todas las poses de todos los
fotogramas en una sola llamada a FreeCAD, así que el coste es de una
decena de llamadas, no de una por pose.
"""

from pathlib import Path

from orchestrator.assembly import pair_gaps

MUESTRAS_GRUESAS = 16
BISECCIONES = 10
BANDA_POR_DEFECTO = 0.05
"""Hueco máximo que se acepta como contacto, si el par no declara otro."""


class SinApoyo(RuntimeError):
    """La pieza recorrió todo su margen sin apoyarse como se declaró."""


def _muestras(inicio: float, limite: float, sentido: int, n: int) -> list[float]:
    return [inicio + sentido * limite * k / n for k in range(n + 1)]


def _banda(spec, cuerpo) -> float:
    """El hueco máximo que el BARRIDO va a exigir a este par. Solucionador y
    barrido tienen que juzgar con el mismo criterio."""
    objetivo = cuerpo.joint.rest_on.target
    for r in spec.rules:
        if r.kind == "contact" and {r.a, r.b} == {cuerpo.name, objetivo}:
            return r.max_gap_mm
    return max(cuerpo.joint.rest_on.gap_mm, BANDA_POR_DEFECTO)


def _medir(kin, nombre, valores_por_frame, steps, pins, objetivo, freecadcmd) -> dict:
    """Hueco de cada (fotograma, valor) en UNA sola llamada a FreeCAD."""
    poses, etiquetas = {}, {}
    for t, valores in valores_por_frame.items():
        for v in valores:
            clave = len(poses)
            poses[clave] = kin.poses(t, {nombre: v})
            etiquetas[clave] = (t, v)
    medido: dict[float, list[tuple[float, float]]] = {}
    for g in pair_gaps(steps, pins, poses, [(nombre, objetivo)], freecadcmd):
        t, v = etiquetas[g["angle"]]
        medido.setdefault(t, []).append((v, g["gap_mm"]))
    return medido


def solve_contacts(spec, kin, steps: dict[str, Path], pins: dict, freecadcmd: str,
                   frames: list[float]) -> dict[tuple[float, str], float]:
    """Valor de cada articulación `rest_on` en cada posición del ciclo."""
    apoyadas = [b for b in spec.bodies if b.joint and b.joint.rest_on]
    if not apoyadas:
        return {}

    resueltos: dict[tuple[float, str], float] = {}
    for b in apoyadas:
        r = b.joint.rest_on
        banda = _banda(spec, b)
        sentido = 1 if r.toward == "increase" else -1
        inicio = {t: kin.joint_value(b.name, t) for t in frames}

        # 1. Pasada gruesa: dónde deja de haber hueco.
        gruesa = _medir(kin, b.name,
                        {t: _muestras(inicio[t], r.limit, sentido, MUESTRAS_GRUESAS)
                         for t in frames},
                        steps, pins, r.target, freecadcmd)
        horquillas = {}
        for t in frames:
            serie = sorted(gruesa[t], key=lambda x: sentido * x[0])
            if serie[0][1] < 0:
                raise SinApoyo(
                    f"el punto de partida de «{b.name}» ya está dentro de «{r.target}» con "
                    f"{spec.driver.name} = {t:g}: con el valor {serie[0][0]:.2f} se solapan "
                    f"{-serie[0][1]:.1f} mm³. Sepáralo antes de buscar el apoyo, o invierte "
                    "`toward`."
                )
            tocado = next((i for i, (_, d) in enumerate(serie) if d <= banda), None)
            if tocado is None:
                mejor_v, mejor_d = min(serie, key=lambda x: x[1])
                raise SinApoyo(
                    f"«{b.name}» no llega a apoyarse en «{r.target}» con "
                    f"{spec.driver.name} = {t:g}: recorre {r.limit:g} desde "
                    f"{serie[0][0]:.2f} y lo más cerca que pasa es {mejor_d:.2f} mm "
                    f"(con el valor {mejor_v:.2f}). Acerca las piezas esos {mejor_d:.2f} mm, "
                    "alarga el recorrido de búsqueda o corrige la posición de partida."
                )
            # Entre la última separada y la primera que toca está el apoyo.
            horquillas[t] = (serie[max(tocado - 1, 0)][0], serie[tocado][0])

        # 2. Bisección: caer DENTRO de la banda, no pasarse.
        mejores = {t: None for t in frames}
        for t in frames:
            v_toca = horquillas[t][1]
            d_toca = dict(gruesa[t])[v_toca]
            if 0 <= d_toca <= banda:
                mejores[t] = v_toca
        for _ in range(BISECCIONES):
            pendientes = [t for t in frames if mejores[t] is None]
            if not pendientes:
                break
            medios = {t: [(horquillas[t][0] + horquillas[t][1]) / 2] for t in pendientes}
            medido = _medir(kin, b.name, medios, steps, pins, r.target, freecadcmd)
            for t in pendientes:
                v, d = medido[t][0]
                if 0 <= d <= banda:
                    mejores[t] = v
                elif d > banda:                     # todavía separadas
                    horquillas[t] = (v, horquillas[t][1])
                else:                               # se solapan: retroceder
                    horquillas[t] = (horquillas[t][0], v)

        for t in frames:
            if mejores[t] is None:
                # La bisección no cupo en la banda: la geometría cambia muy
                # deprisa ahí (una esquina). Se queda el lado que NO penetra.
                mejores[t] = horquillas[t][0]
            resueltos[(round(t, 6), b.name)] = mejores[t]
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
