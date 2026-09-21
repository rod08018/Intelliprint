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

EXTENSIONES = 3
"""Cuántas veces puede el solucionador alargar por su cuenta una búsqueda
que se acabó con la pieza todavía acercándose: hasta 4 veces el recorrido
declarado. Más allá, la pieza no se acerca: se está yendo a otra parte."""


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


def _sigue_acercandose(serie) -> bool:
    """El hueco más pequeño está en el ÚLTIMO punto del recorrido y todavía
    bajaba: la búsqueda se acabó antes que el acercamiento."""
    huecos = [d for _, d in serie]
    return len(huecos) >= 2 and huecos[-1] == min(huecos) and huecos[-1] < huecos[-2]


def _motivo_sin_apoyo(spec, b, t, serie, recorrido) -> str:
    r = b.joint.rest_on
    mejor_i, (mejor_v, mejor_d) = min(enumerate(serie), key=lambda x: x[1][1])
    base = (f"«{b.name}» no llega a apoyarse en «{r.target}» con {spec.driver.name} = {t:g}: "
            f"recorre {recorrido:g} desde {serie[0][0]:.2f} y lo más cerca que pasa es "
            f"{mejor_d:.2f} mm (con el valor {mejor_v:.2f}).")
    if mejor_i == 0:
        # Lo más cerca es el punto de partida: se aleja desde el principio.
        return base + (" Desde el punto de partida solo se ALEJA: probablemente busca en "
                       "el sentido equivocado; prueba `toward` al revés.")
    if mejor_i == len(serie) - 1:
        return base + (" Seguía acercándose al acabar, incluso después de alargar la "
                       "búsqueda: revisa la posición de partida.")
    # Pasa cerca a mitad de camino y luego se aleja: le falta pieza.
    return base + (f" Pasa cerca y se aleja sin tocar: a la pieza le faltan esos "
                   f"{mejor_d:.2f} mm. Acerca las piezas o alarga la que tiene que tocar.")


def solve_contacts(spec, kin, steps: dict[str, Path], pins: dict, freecadcmd: str,
                   frames: list[float], notas: list[str] | None = None
                   ) -> dict[tuple[float, str], float]:
    """Valor de cada articulación `rest_on` en cada posición del ciclo.

    `notas` recoge lo que el solucionador decidió por su cuenta (alargar una
    búsqueda), para que quede dicho: el diseño no cambió, la búsqueda sí."""
    notas = notas if notas is not None else []
    apoyadas = [b for b in spec.bodies if b.joint and b.joint.rest_on]
    if not apoyadas:
        return {}

    resueltos: dict[tuple[float, str], float] = {}
    for b in apoyadas:
        r = b.joint.rest_on
        if r.carry:
            resueltos.update(_resolver_con_memoria(
                spec, kin, b, steps, pins, freecadcmd, frames, resueltos))
            kin.set_solved(resueltos)
            continue
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
            # Fallo real (trinquete del 2026-09-21, rondas 13-15): lo más
            # cerca caía siempre en el FINAL del recorrido, a 0.15, 0.06 y
            # 0.18 mm. La pieza seguía acercándose y el modelo pasó tres rondas
            # alargando la búsqueda 5° cada vez. Alargarla no es diseño: es un
            # parámetro de este solucionador, así que lo hace él.
            extra = 0
            while tocado is None and extra < EXTENSIONES and _sigue_acercandose(serie):
                extra += 1
                mas = _medir(kin, b.name,
                             {t: _muestras(serie[-1][0], r.limit, sentido, MUESTRAS_GRUESAS)[1:]},
                             steps, pins, r.target, freecadcmd)[t]
                serie = sorted(serie + mas, key=lambda x: sentido * x[0])
                tocado = next((i for i, (_, d) in enumerate(serie) if d <= banda), None)
            # La bisección lee los huecos de aquí: tiene que ver también las
            # muestras de la búsqueda alargada.
            gruesa[t] = serie
            if tocado is None:
                raise SinApoyo(_motivo_sin_apoyo(spec, b, t, serie, r.limit * (extra + 1)))
            if extra:
                notas.append(
                    f"el código alargó la búsqueda de apoyo de «{b.name}» sobre «{r.target}» "
                    f"con {spec.driver.name} = {t:g}: de {r.limit:g} a {r.limit * (extra + 1):g}, "
                    "porque al acabarse seguía acercándose")
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


def _resolver_con_memoria(spec, kin, b, steps, pins, freecadcmd, frames, previos) -> dict:
    """Una pieza EMPUJADA: parte de donde quedó y solo se mueve lo que la
    obliguen. Así una rueda de trinquete avanza cuando la uña entra y se
    queda donde llegó cuando sale, sin que nadie escriba su fórmula.

    Se resuelve fotograma a fotograma —cada uno depende del anterior— en dos
    llamadas a FreeCAD: una malla y un afinado dentro del tramo.
    """
    r = b.joint.rest_on
    banda = _banda(spec, b)
    sentido = 1 if r.toward == "increase" else -1
    valor = kin.joint_value(b.name, frames[0])
    resueltos = dict(previos)

    for t in frames:
        for ronda, muestras in ((0, MUESTRAS_GRUESAS), (1, MUESTRAS_GRUESAS)):
            paso = r.limit if ronda == 0 else r.limit / MUESTRAS_GRUESAS
            candidatos = _muestras(valor, paso, sentido, muestras)
            serie = sorted(_medir(kin, b.name, {t: candidatos}, steps, pins,
                                  r.target, freecadcmd)[t],
                           key=lambda x: sentido * x[0])
            if serie[0][1] >= 0:
                break          # nadie la empuja: se queda donde estaba
            tocado = next((i for i, (_, d) in enumerate(serie) if d >= 0), None)
            if tocado is None:
                mejor_v, mejor_d = max(serie, key=lambda x: x[1])
                raise SinApoyo(
                    f"«{b.name}» está siendo atravesada por «{r.target}» con "
                    f"{spec.driver.name} = {t:g} y no puede apartarse: recorre "
                    f"{r.limit:g} y lo mejor que consigue es solaparse {-mejor_d:.1f} mm³ "
                    f"(con el valor {mejor_v:.2f}). Separa las piezas o revisa el perfil "
                    "que las empuja."
                )
            valor = serie[tocado][0]
            if serie[tocado][1] <= banda:
                break          # ya está apoyada justo, sin necesidad de afinar
        resueltos[(round(t, 6), b.name)] = valor
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
