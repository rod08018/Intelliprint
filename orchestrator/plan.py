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

from dataclasses import dataclass, field
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
    avisos += _roscas_sin_medir(obra, agujeros, extra)
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


def _roscas_sin_medir(obra: Obra, agujeros: dict, extra: Sequence[Path]) -> list[str]:
    """Un aviso por cada tornillo de lo comprado que rosca en la pieza y
    cuyo agujero el perfil no tiene (F9.8 (métricas)). El soporte del
    pan-tilt 1111-1342 taladró Ø2.2 para los tornillos de 2 de su SG90: no
    tenía de dónde sacar el diámetro."""
    faltan: dict[tuple[str, str], list[str]] = {}
    for n in obra.nodos:
        for id_ in dict.fromkeys(n.compra):
            try:
                ficha = cargar(id_, extra)
            except KeyError:
                continue
            for m in dict.fromkeys(f.tornillo for f in ficha.fijacion
                                   if f.tornillo and f.rosca_en_la_pieza):
                if f"{m}_selftap_mm" not in agujeros:
                    faltan.setdefault((ficha.nombre, m), []).append(f"«{n.nombre}»")
    return [f"el {que} de {' y '.join(piezas)} se sujeta con tornillos {m} que roscan en la "
            f"pieza, y el perfil de la impresora no tiene {m}_selftap_mm. Hasta que lo midas y "
            "lo apuntes en la página «Impresora» («Apuntar otro tornillo»), el diámetro de "
            "esos agujeros lo elige el diseñador sin ninguna medida detrás"
            for (que, m), piezas in faltan.items()]


# --- la tornillería: lo previsto contra lo construido (F9.6 (previsto)) -----------------------

@dataclass(frozen=True)
class Prevista:
    """Unos tornillos iguales que el invento tiene que llevar."""
    union: str
    """El id de la unión del plan; vacío si son los de algo comprado."""
    piezas: tuple[str, ...]
    """(cabeza, agarra); una sola si van al exterior o sujetan algo comprado."""
    metrica: str
    cantidad: int
    termina: str
    """Como `Tornillo.termina`: «tuerca», «inserto», «rosca» o «superficie»
    (al exterior). Vacío en los de lo comprado: depende de la ficha."""
    componente: str = ""
    incluido: bool = False
    """Vienen en la bolsa del componente."""


def compras_previstas(obra: Obra, extra: Sequence[Path] = ()) -> list[Prevista]:
    """Los tornillos que el invento lleva según el plan, antes de dibujar
    nada. Los de las uniones los dice el plan. Los de lo comprado no los
    dice ningún modelo: salen de la ficha, una fijación un tornillo. En el
    pan-tilt 1111-1342 el plan no hablaba de los de los SG90, y la base
    salió con su servo suelto en el alojamiento.

    Una fijación que puede ir en cualquier punto (`a_lo_largo`, la ranura
    de un perfil) no se prevé: cuántos lleva lo decide el diseño."""
    previstas = [Prevista(u.id, u.nodos(), u.metrica, u.cantidad,
                          "superficie" if u.agarra == EXTERIOR else u.agarre)
                 for u in obra.uniones if isinstance(u, Fija)]
    for n in obra.nodos:
        for id_ in dict.fromkeys(n.compra):
            try:
                ficha = cargar(id_, extra)
            except KeyError:
                continue   # sin ficha no se sabe con qué se sujeta
            por_metrica: dict[str, list] = {}
            for f in ficha.fijacion:
                if f.tornillo and f.a_lo_largo is None:
                    por_metrica.setdefault(f.tornillo, []).append(f)
            previstas += [Prevista("", (n.id,), m, len(fs) * n.compra.count(id_), "", id_,
                                   all(f.incluido for f in fs))
                          for m, fs in por_metrica.items()]
    return previstas


def _n(cuantos: int, uno: str, varios: str | None = None) -> str:
    return f"{cuantos} {uno if cuantos == 1 else varios or uno + 's'}"


_CON = {"tuerca": ("tuerca", "tuercas"), "inserto": ("inserto térmico", "insertos térmicos")}
_AGARRE_EN_PALABRAS = {"tuerca": "con tuerca cautiva", "inserto": "con inserto térmico",
                       "rosca": "roscados en el plástico"}


def compras_en_palabras(obra: Obra, extra: Sequence[Path] = ()) -> list[str]:
    """Lo que `compras_previstas` dice, como lo lee la persona antes de
    aprobar el plan. Sin largos: se miden en las piezas construidas."""
    def nombre(i):
        return f"«{obra.nodo(i).nombre}»"

    lineas = []
    for p in compras_previstas(obra, extra):
        tornillos = f"{_n(p.cantidad, 'tornillo')} {p.metrica}"
        if p.componente:
            que = cargar(p.componente, extra).nombre
            lineas.append(f"{tornillos}, que vienen con el {que} de {nombre(p.piezas[0])}"
                          if p.incluido else
                          f"{tornillos} para sujetar el {que} de {nombre(p.piezas[0])}")
        elif p.termina == "superficie":
            lineas.append(f"{tornillos} para fijar {nombre(p.piezas[0])} a algo de fuera; el "
                          "largo depende de dónde")
        elif p.termina in _CON:
            lineas.append(f"{tornillos} y {_n(p.cantidad, *_CON[p.termina])} {p.metrica}, entre "
                          f"{nombre(p.piezas[0])} y {nombre(p.piezas[1])}")
        else:
            lineas.append(f"{tornillos} roscados en el plástico, entre {nombre(p.piezas[0])} y "
                          f"{nombre(p.piezas[1])}")
    return lineas


@dataclass
class Falta:
    """Tornillos previstos que las piezas construidas no llevan."""
    uniones: tuple[str, ...]
    piezas: tuple[str, ...]
    metrica: str
    termina: str
    previstos: int
    hechos: int
    componente: str = ""
    incluido: bool = False
    mitad: str = ""
    """«agarra»: la otra pieza de la unión aún no está construida, y a esta
    se le pide donde agarran sus tornillos."""
    de: tuple[str, ...] = ()
    """Las piezas de esas uniones que faltan por construir."""
    de_otra_manera: dict = field(default_factory=dict)
    """Los que hay entre esas piezas y no acaban como aprobó la persona."""
    no_roscan: list = field(default_factory=list)
    """Los agujeros tan anchos como su tornillo, o más."""
    ancho_mm: float = 0.0
    al_reves: int = 0
    """Los que acaban «sin agarrar» porque la pieza que agarra se puso del
    lado de la cabeza: la cabeza cae en ella y la punta en el pasante."""

    def texto(self, obra: Obra, extra: Sequence[Path] = ()) -> str:
        """Para quien diseña la pieza: qué falta y cómo se hace."""
        def nombre(i):
            return f"«{obra.nodo(i).nombre}»"

        k = self.previstos - self.hechos
        falta = f"falta{'n' if k != 1 else ''} {k}"
        tornillos = f"{_n(self.previstos, 'tornillo')} {self.metrica}"
        hay = (f"hay {self.hechos}" if self.hechos
               else "ninguno agarra" if self.no_roscan else "no hay ninguno")
        flojos = ""
        if self.no_roscan:
            d = float(self.metrica.lstrip("Mm"))
            flojos = (f" {', '.join(f'«{a}»' for a in self.no_roscan)} "
                      f"{'mide' if len(self.no_roscan) == 1 else 'miden'} Ø{self.ancho_mm:g} y "
                      f"el tornillo {self.metrica} mide {d:g}: no rosca, pasa sin tocar. Tiene "
                      "que ser más estrecho que el tornillo.")
        if self.componente:
            que = cargar(self.componente, extra).nombre
            return (f"tornillos del {que}: se sujeta con {tornillos}"
                    + (", que vienen con él" if self.incluido else "")
                    + f", uno por cada fijación de su ficha, y {hay}: {falta}."
                    + (flojos or
                       " `componente.agujeros()` da el punto y el eje de cada fijación: "
                       "taladra en línea con cada una el agujero donde entra su tornillo; si "
                       "rosca en esta pieza, más estrecho que él y con `profundidad`."))
        cual = f"unión {', '.join(self.uniones)}"
        if self.mitad == "agarra":
            otras = " y ".join(nombre(i) for i in dict.fromkeys(self.de))
            return (f"{cual}: en esta pieza agarran {tornillos} de {otras}, "
                    f"{_AGARRE_EN_PALABRAS[self.termina]}, y {hay}: {falta}. {otras} se "
                    "diseñará después y contra esta: lo que no lleve ahora no podrá ponérselo")
        if len(self.piezas) == 1:
            return (f"{cual}: el plan pide en esta pieza {tornillos} que la atraviesan, cada uno "
                    f"con su agujero pasante (`tornillo(..., \"{self.metrica}\")`), y {hay} "
                    f"libre{'s' if self.hechos != 1 else ''}: {falta}")
        como = {"tuerca": "en una tuerca", "inserto": "en un inserto",
                "rosca": "en rosca en el plástico", "componente": "en algo comprado",
                "superficie": "sin agarrar en nada"}
        otros = "".join(f" Hay {n} que acaba{'n' if n != 1 else ''} {como.get(t, t)}: no es lo "
                        "aprobado." for t, n in self.de_otra_manera.items())
        if self.al_reves:
            # Con «acaban sin agarrar en nada» el soporte de la pinza del
            # banco 1112-1359 gastó cinco intentos: los agujeros estaban en
            # línea y bien hechos; lo que estaba mal era el lado.
            otros += (f" {'Está' if self.al_reves == 1 else 'Están'} al revés: "
                      f"{nombre(self.piezas[1])} quedó del lado de {nombre(self.piezas[0])} "
                      "por donde entra la cabeza (donde `punto()` da el agujero), y así la "
                      "cabeza cae en el fondo de su agujero y la punta en el pasante. Pásala "
                      f"al otro lado de {nombre(self.piezas[0])}, donde sale el tornillo "
                      "(en el sentido del `eje` del agujero), con el agujero mirando a él.")
        return (f"{cual}: el plan pide {tornillos} entre {nombre(self.piezas[0])} y "
                f"{nombre(self.piezas[1])}, {_AGARRE_EN_PALABRAS[self.termina]}, y {hay}: "
                f"{falta}.{otros}{flojos} Cada uno pasa por un agujero de cada pieza, en la "
                "misma recta: `punto()` da los de la pieza ya hecha por su nombre")


def sin_hacer(obra: Obra, tornillos: Sequence, construidas,
              extra: Sequence[Path] = ()) -> list[Falta]:
    """Lo que `compras_previstas` pide y los `tornillos` medidos en las
    piezas `construidas` no dan (`tornilleria.tornillos`). Se compara por
    firma: la métrica, las piezas que une y cómo acaba.

    Una unión con una sola de sus dos piezas construida se le pide a esa por
    su mitad: los pasantes si lleva la cabeza, y si no, donde agarra. Es
    cuando se puede arreglar; con la otra hecha, esta ya está dada por
    buena. Los que comparten firma (los de la mesa y la mitad de los de la
    tapa son, en la base, pasantes iguales) se cuentan juntos."""
    construidas = set(construidas)
    faltas: list[Falta] = []
    pedidos: dict[tuple, list] = {}
    for p in compras_previstas(obra, extra):
        hechas = tuple(i for i in p.piezas if i in construidas)
        if not hechas:
            continue
        if p.componente:
            suyos = [t for t in tornillos if t.componente == p.componente
                     and t.lo_monta == p.piezas[0] and t.metrica == p.metrica]
            flojos = [t for t in suyos if t.no_rosca()]
            if len(suyos) - len(flojos) < p.cantidad:
                faltas.append(Falta((), p.piezas, p.metrica, "", p.cantidad,
                                    len(suyos) - len(flojos), p.componente, p.incluido,
                                    no_roscan=[t.agarra_en for t in flojos],
                                    ancho_mm=max((t.agarra_mm for t in flojos), default=0.0)))
            continue
        if len(hechas) == len(p.piezas):
            clave = (p.piezas, p.metrica, p.termina, "")
        elif hechas[0] == p.piezas[0]:
            clave = (hechas, p.metrica, "superficie", "")
        else:
            clave = (hechas, p.metrica, p.termina, "agarra")
        pedidos.setdefault(clave, []).append(p)
    for (piezas, metrica, termina, mitad), ps in pedidos.items():
        if len(piezas) == 1:
            # Solo los que no salen de la pieza: el que ya une dos es de otra unión.
            hay = [t for t in tornillos if not t.componente and t.metrica == metrica
                   and t.piezas == list(piezas)]
        else:
            hay = [t for t in tornillos if t.metrica == metrica and set(piezas) <= set(t.piezas)]
        flojos = [t for t in hay if t.termina == termina and t.no_rosca()]
        hechos = sum(t.termina == termina for t in hay) - len(flojos)
        previstos = sum(p.cantidad for p in ps)
        if hechos >= previstos:
            continue
        otra: dict[str, int] = {}
        if len(piezas) == 2:
            for t in hay:
                if t.termina != termina:
                    otra[t.termina] = otra.get(t.termina, 0) + 1
        faltas.append(Falta(
            tuple(p.union for p in ps), piezas, metrica, termina, previstos, hechos, mitad=mitad,
            de=tuple(i for p in ps for i in p.piezas if i not in construidas),
            de_otra_manera=otra, no_roscan=[t.agarra_en for t in flojos],
            ancho_mm=max((t.agarra_mm for t in flojos), default=0.0),
            al_reves=(sum(t.termina == "superficie" and t.pieza == piezas[1] for t in hay)
                      if len(piezas) == 2 and termina != "superficie" else 0)))
    return faltas
