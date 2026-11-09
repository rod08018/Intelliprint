"""El ingeniero (F3.18 (ingeniero)): decide cómo se resuelve antes de dibujar.

Lo que salía era inusable porque nadie pensaba la pieza: el Part Designer
recibía la petición y dibujaba cajas. Este agente propone el concepto
—camino de carga, orientación, fijaciones, secciones— y pregunta solo las
cotas críticas que falten. La persona lo aprueba y entonces se modela.

Lo que se puede contar no lo cuenta el modelo: la resistencia de cada
caso de carga la calcula `orchestrator.ingenieria`, y si no aguanta, el
concepto vuelve con el canto que haría falta (dentro del bucle de
`structured`, como cualquier error de esquema).
"""

from pathlib import Path

import yaml

from orchestrator.componentes import cargar, ids, mencionados, resumen
from orchestrator.ingenieria import Material, comprobar
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.concepto import Concepto, ConceptoComprobado
from orchestrator.schemas.spec import Spec

PROMPT_PATH = Path("config/agents/ingeniero.md")

_DEL_PERFIL = ("printer", "material", "layer_height_mm", "bed_mm", "fits", "holes",
               "walls", "overhang_max_deg", "bridge_max_mm", "resistencia")
"""Lo que el ingeniero necesita del perfil activo. Antes nadie que diseñara
lo recibía: las cotas de tornillería salían de memoria."""


def _alojamiento_inventado(c, ficha, ajustes) -> list[str]:
    """Un Ø a menos de 1 mm de un diámetro de la ficha, sin ser él: es el
    alojamiento escrito a mano. Proyecto del 608ZZ (2026-11-06): «Ø21.9 con
    0.1 de interferencia», contra el perfil («press» es +0.10 sobre el
    nominal); habría salido de 21.7 y el rodamiento no entraba."""
    import re

    from orchestrator.componentes import primitivas

    diametros = [d for p in primitivas(ficha) if p["tipo"] == "cilindro"
                 for d in (p["diametro"], p.get("interior")) if d]
    texto = f"{c.como_entra} {c.como_se_sujeta}"
    errores = []
    for n in re.findall(r"(?:[Øø]|di[áa]metro(?: de)?)\s*(\d+(?:[.,]\d+)?)", texto):
        n = float(n.replace(",", "."))
        cerca = [d for d in diametros if 0 < abs(n - d) <= 1.0]
        if cerca:
            tabla = ", ".join(f"{k.removesuffix('_mm')} +{v:g}" for k, v in ajustes.items()
                              if k.endswith("_mm"))
            errores.append(
                f"«Ø{n:g}» para {c.id}: el alojamiento no lo escribes tú. Di el ajuste en "
                f"`ajuste` (press, slide o clearance) y `hueco()` suma al Ø{cerca[0]:g} de la "
                f"ficha la holgura del perfil ({tabla}): los agujeros FDM salen pequeños.")
    return errores


def _metricas(textos) -> set[str]:
    import re
    return {f"M{m.replace(',', '.')}" for t in textos
            for m in re.findall(r"\bM(\d+(?:[.,]\d+)?)\b", t)}


def _lo_que_se_pierde(anterior: Concepto, nuevo: Concepto) -> list[str]:
    """Lo que el concepto nuevo quita del anterior sin decirlo. Se mira lo
    que se puede contar sin leer intenciones: que diga qué cambia, y que no
    desaparezca una métrica de tornillo de las fijaciones sin nombrarla en
    `cambios` (la base del pan-tilt perdió así sus M4 de fijación)."""
    if not nuevo.cambios:
        return ["partes de un concepto anterior: escribe en `cambios` qué cambias respecto "
                "a él y por qué. Si no cambia nada más que lo pedido, dilo igualmente"]
    dichas = _metricas(nuevo.cambios)
    quitadas = sorted(_metricas(anterior.fijaciones) - _metricas(nuevo.fijaciones) - dichas)
    return [f"el concepto anterior llevaba {m} en sus fijaciones "
            f"({'; '.join(f for f in anterior.fijaciones if m in _metricas([f]))}) y este no. "
            f"Si la persona no lo pidió, mantenlo; si hay que quitarlo, dilo en `cambios` "
            "con el porqué" for m in quitadas]


class IngenieroAgent:
    def __init__(self, client: LlmClient, activo, prompt_path: Path = PROMPT_PATH,
                 reserva: LlmClient | None = None) -> None:
        self._client = client
        self._reserva = reserva
        self._material = Material.del_perfil(activo.datos)
        perfil = {k: activo.datos[k] for k in _DEL_PERFIL if k in activo.datos}
        self._ajustes = activo.datos.get("fits") or {}
        self._instrucciones = (
            prompt_path.read_text(encoding="utf-8")
            + "\n\n## Perfil activo (impresora y material)\n\n```yaml\n"
            + yaml.safe_dump(perfil, allow_unicode=True, sort_keys=False) + "```\n")

    def concebir(self, spec: Spec, anterior: ConceptoComprobado | None = None,
                 cambios: str = "") -> ConceptoComprobado:
        """`anterior`: el último concepto que vio la persona (al rehacer o al
        contestar sus preguntas). Se parte de él: la base del pan-tilt
        (2026-11-09) salió de cero en cada vuelta y lo que nadie pidió —con
        qué tornillos se fija— cambió cuatro veces, hasta desaparecer."""
        requisitos = "".join(
            f"- {r.id} ({r.tipo}, {r.origen}): {r.texto}"
            + (f" → {r.valor:g} {r.unidad}" if r.valor is not None else "") + "\n"
            for r in spec.requisitos) or "(ninguno estructurado)\n"
        prompt = (f"{self._instrucciones}\n## Encargo: {spec.title}\n\n{spec.description}\n\n"
                  f"Petición literal:\n> {spec.request}\n\n## Requisitos\n\n{requisitos}")
        # F6.11 (biblioteca): lo que la petición nombra y tiene ficha va con su
        # forma entera. El soporte del HC-SR04 se pensó con cifras de una
        # tienda y sin saber que el sensor lleva integrados detrás.
        nombrados = mencionados(f"{spec.request}\n{spec.title}")
        prompt += (f"\n## Componentes con ficha en la biblioteca\n\nHay ficha de: "
                   f"{', '.join(ids())}. Sus medidas son estas; no las supongas.\n")
        if nombrados:
            prompt += ("\nLa petición nombra estos; cada uno va en `componentes`, con "
                       "cómo entra y cómo se sujeta:\n\n"
                       + "\n\n".join(resumen(cargar(i)) for i in nombrados) + "\n")
        if anterior is not None:
            prompt += (
                "\n## Concepto anterior: el que vio la persona\n\n"
                f"{anterior.texto()}\n\n"
                "Parte de él. Lo que la persona no pide cambiar se queda como está: las "
                "fijaciones, cómo entra y cómo se sujeta cada componente, la orientación. "
                "Cambia solo lo que piden los cambios y las respuestas, no añadas nada que "
                "nadie haya pedido, y escribe en `cambios` cada cosa que cambias respecto a "
                "este concepto y por qué.\n")
        if cambios.strip():
            prompt += f"\n## Cambios que pide la persona\n\n{cambios.strip()}\n"

        def validar(concepto: Concepto) -> None:
            errores = []
            if anterior is not None:
                errores += _lo_que_se_pierde(anterior.concepto, concepto)
            pide_carga = [r.id for r in spec.requisitos if r.tipo == "carga"]
            if (pide_carga or spec.payload_g) and not concepto.casos_de_carga:
                errores.append(
                    f"se pide aguantar una carga ({', '.join(pide_carga) or 'payload_g'}) y no "
                    "hay ningún caso de carga: di qué sección trabaja y con cuánto.")
            puestos = {c.id for c in concepto.componentes}
            for c in concepto.componentes:
                if c.id not in ids():
                    errores.append(f"«{c.id}» no tiene ficha en la biblioteca; hay: "
                                   f"{', '.join(ids())}. Usa uno de esos ids.")
            for c in concepto.componentes:
                if c.id in ids():
                    errores += _alojamiento_inventado(c, cargar(c.id), self._ajustes)
            for i in nombrados:
                if i not in puestos:
                    errores.append(f"la petición nombra «{i}» y no está en `componentes`: "
                                   "di cómo entra y cómo se sujeta.")
            for caso in concepto.casos_de_carga:
                c = comprobar(caso, self._material)
                if not c.cumple:
                    errores.append(c.texto() + " Cambia la sección, el brazo o la orientación.")
            if errores:
                raise ValueError("el concepto no se sostiene:\n- " + "\n- ".join(errores))

        concepto = structured(self._client, prompt, Concepto, extra_validation=validar,
                              cliente_de_reserva=self._reserva)
        return ConceptoComprobado(
            concepto=concepto,
            comprobaciones=[comprobar(c, self._material) for c in concepto.casos_de_carga])
