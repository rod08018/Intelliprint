"""El plan mecánico se comprueba antes de dibujar nada (F9.2 (uniones)).

El desglose dice qué piezas hay y cómo se unen: qué gira sobre qué y con
cuánto sitio, qué va atornillado y con qué. Aquí se comprueba, sin modelo,
contra lo que no puede inventar: las fichas de lo comprado y el perfil de
la impresora.

Hay dos clases de reparo. Un **error** es un plan que no se puede construir
(girar sobre una salida que el servo no tiene) y vuelve al desglosador. Un
**aviso** es algo que la persona tiene que saber antes de aprobar (una
métrica que su impresora aún no tiene medida) y no tira el plan: al
desglosador solo le quedan tres intentos, y gastarlos en lo que se arregla
apuntando una medida lo dejaría sin plan.
"""

from pathlib import Path
from typing import Sequence

from orchestrator.componentes import Ficha, Salida, cargar
from orchestrator.schemas.obra import EXTERIOR, Fija, Gira, Obra

_AGARRE = {"tuerca": "nut_af", "inserto": "insert", "rosca": "selftap"}
"""Del agarre de una unión a la clave del perfil con la que se taladra."""


def salida_de(u: Gira, ficha: Ficha) -> Salida:
    """La salida de la ficha sobre la que gira la unión, o ValueError
    diciendo cuáles hay."""
    hay = ", ".join(f"«{s.nombre}»" for s in ficha.salidas)
    if not ficha.salidas:
        raise ValueError(f"unión «{u.id}»: «{ficha.id}» no mueve nada: su ficha no tiene "
                         "ninguna salida")
    if not u.salida:
        if len(ficha.salidas) > 1:
            raise ValueError(f"unión «{u.id}»: «{ficha.id}» tiene varias salidas ({hay}); "
                             "di cuál en `salida`")
        return ficha.salidas[0]
    for s in ficha.salidas:
        if s.nombre == u.salida:
            return s
    raise ValueError(f"unión «{u.id}»: «{ficha.id}» no tiene la salida «{u.salida}»; "
                     f"tiene: {hay}")


def claves_del_perfil(u: Fija) -> list[str]:
    """Las claves de `holes` que hacen falta para taladrar la unión: el
    pasante de la cabeza y, entre dos piezas, lo que pide su agarre."""
    claves = [f"{u.metrica}_through_mm"]
    if u.agarra != EXTERIOR and u.agarre:
        claves.append(f"{u.metrica}_{_AGARRE[u.agarre]}_mm")
    return claves


def validar_plan(obra: Obra, agujeros: dict,
                 extra: Sequence[Path] = ()) -> tuple[list[str], list[str]]:
    """(errores, avisos) del plan. `agujeros` es `holes` del perfil activo;
    `extra`, más carpetas de fichas."""
    errores: list[str] = []
    avisos: list[str] = []
    en_cada_salida: dict[tuple, list[str]] = {}
    for u in obra.uniones:
        if isinstance(u, Fija):
            faltan = [c for c in claves_del_perfil(u) if c not in agujeros]
            if faltan:
                avisos.append(
                    f"unión «{u.id}»: el perfil de la impresora no tiene "
                    f"{', '.join(faltan)}. Hasta que lo midas y lo apuntes en la página "
                    "«Impresora» no se puede taladrar: elige otra métrica o mídelo. Tiene: "
                    f"{', '.join(sorted(agujeros))}")
            continue
        try:
            salida = salida_de(u, cargar(u.componente, extra))
        except ValueError as e:
            errores.append(str(e))
            continue
        lo, hi = salida.recorrido
        if u.recorrido_grados > hi - lo + 1e-6:
            errores.append(
                f"unión «{u.id}»: pide {u.recorrido_grados:g}° y «{u.componente}» da "
                f"{hi - lo:g}° (de {lo:g}° a {hi:g}°, según su ficha)")
        # Lo que abraza un rodamiento no tiene un cilindro libre delante de
        # una cara: su salida ocupa un tramo (`largo`) y la pieza va en él.
        if u.radio_libre_mm is None and not salida.largo:
            errores.append(
                f"unión «{u.id}»: falta `radio_libre_mm`: cuánto sitio necesita «{u.gira}» "
                f"alrededor del eje de «{u.componente}» para girar sin tocar nada. Es lo que "
                "mide la pieza que gira desde su eje hasta su punta más lejana")
        en_cada_salida.setdefault((u.sobre, u.componente, salida.nombre), []).append(u.id)
    for (sobre, componente, _), ids in en_cada_salida.items():
        hay = obra.nodo(sobre).compra.count(componente)
        if len(ids) > hay:
            errores.append(
                f"«{sobre}» lleva {hay} {componente} y sobre él giran {len(ids)} uniones "
                f"({', '.join(ids)}): cada actuador mueve una sola pieza. Pon otro en "
                f"`compra` de «{sobre}» o quita una")
    conjuntos = [n for n in obra.nodos if n.tipo == "conjunto"]
    for u in obra.uniones:
        if isinstance(u, Gira) and not any({u.gira, u.sobre} <= set(c.depende_de)
                                           for c in conjuntos):
            errores.append(
                f"unión «{u.id}»: «{u.gira}» gira sobre «{u.sobre}» y ningún nodo de tipo "
                "«conjunto» lleva a las dos en `depende_de`: un giro solo se verifica "
                "moviéndolo, y eso lo hace el conjunto")
    if obra.uniones:
        piezas = [n for n in obra.nodos if n.tipo == "pieza"]
        for n in piezas:
            if len(piezas) > 1 and not obra.uniones_de(n.id):
                errores.append(f"«{n.id}» no se une a nada: no gira sobre ninguna pieza ni "
                               "va atornillada a ninguna. Di cómo se sujeta")
    return errores, avisos
