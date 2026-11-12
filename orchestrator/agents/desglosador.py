"""El desglosador (F7.2 (desglose)): parte un proyecto en piezas que se
diseñan una a una.

Los mecanismos grandes se pedían de una sola vez: la Ginebra (2026-09-20)
murió porque el razonador se cortó tres veces escribiendo todo el
mecanismo. Este agente no diseña nada: decide qué piezas hay y cómo se
apoyan unas en otras, y es una llamada pequeña.
"""

import re
from pathlib import Path

from orchestrator.componentes import cargar, ids, mencionados, resumen
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra

PROMPT_PATH = Path("config/agents/desglosador.md")

_AGARRES = (("through", "pasante"), ("nut_af", "tuerca"), ("insert", "inserto"),
            ("selftap", "rosca"))


def tabulado(agujeros: dict) -> list[str]:
    """«M3: pasante, tuerca, inserto, rosca»: de cada métrica del perfil, lo
    que se puede taladrar con ella. Sin el pasante no hay dónde apoyar la
    cabeza, y la métrica no sale."""
    metricas = sorted({k.split("_")[0] for k in agujeros if re.match(r"^M\d", k)},
                      key=lambda m: float(m[1:]))
    lineas = []
    for m in metricas:
        hay = [nombre for clave, nombre in _AGARRES if f"{m}_{clave}_mm" in agujeros]
        if "pasante" in hay:
            lineas.append(f"{m}: {', '.join(hay)}")
    return lineas


def es_componente(nombre: str) -> str | None:
    """El id del componente comprado que ES este nodo, o None.

    El primer pan-tilt de verdad (2026-11-09) traía «Servo SG90 de giro»
    como nodo: se habría «diseñado» un servo. Un nodo es el componente si su
    nombre EMPIEZA por palabras de la ficha y entre ellas va su id o un
    alias: «Rodamiento 608ZZ», «SG90 de inclinación». «Soporte del SG90»
    empieza por «soporte», que no es del SG90, y es una pieza."""
    palabras = re.findall(r"[\wáéíóúñü-]+", nombre.casefold())
    for i in ids():
        ficha = cargar(i)
        suyas = set(re.findall(r"[\wáéíóúñü-]+", ficha.nombre.casefold()))
        suyas |= {a.casefold() for a in [i, *ficha.alias]}
        delante = []
        for p in palabras:
            if p not in suyas:
                break
            delante.append(p)
        plano = re.sub(r"[\s\-_]+", "", "".join(delante))
        if any(re.sub(r"[\s\-_]+", "", a.casefold()) in plano for a in [i, *ficha.alias]):
            return i
    return None


class DesglosadorAgent:
    def __init__(self, client: LlmClient, prompt_path: Path = PROMPT_PATH,
                 reserva: LlmClient | None = None) -> None:
        self._client = client
        self._reserva = reserva
        self._instrucciones = prompt_path.read_text(encoding="utf-8")

    def desglosar(self, peticion: str, agujeros: dict | None = None,
                  anterior: str | None = None, ampliar: Obra | None = None) -> Obra:
        """El plan mecánico (F9.3 (planificador)): las piezas y cómo se unen.

        `agujeros` es `holes` del perfil activo: lo que la impresora sabe
        taladrar. `anterior` es el plan que la persona vio y contestó (sus
        respuestas ya van al final de la petición): se parte de él.

        `ampliar` (F9.10 (ampliar)): el plan aprobado de un invento que ya
        tiene piezas diseñadas, al que se le añade una función. Lo que
        devuelve es ese plan entero más lo nuevo; quitar o cambiar algo de
        lo que había es un error que vuelve al modelo."""
        disponibles = ids()
        prompt = (f"{self._instrucciones}\n\n## Componentes con ficha\n\n"
                  f"{', '.join(disponibles)}\n")
        nombrados = mencionados(peticion)
        if nombrados:
            prompt += ("\nLa petición nombra estos:\n\n"
                       + "\n\n".join(resumen(cargar(i)) for i in nombrados) + "\n")
        if agujeros:
            prompt += ("\n## Lo que tabula la impresora\n\nPara una unión `fija` solo puedes "
                       "usar estas métricas, y de cada una solo estos agarres:\n\n"
                       + "\n".join(f"- {linea}" for linea in tabulado(agujeros)) + "\n")
        prompt += f"\n## Petición\n\n> {peticion.strip()}\n"
        if ampliar is not None:
            # Las reglas, con los ids de lo que ya hay: cuando `anterior` es
            # una propuesta contestada, el JSON solo no dice qué es de antes.
            prompt += (
                "\n## Esto es una ampliación\n\nEl invento ya está aprobado y tiene piezas "
                "diseñadas. La persona pide añadirle una función: está al final de la "
                "petición. Devuelve el plan ENTERO, con todo lo que ya hay y lo nuevo:\n\n"
                f"- Ya existen estos nodos: {', '.join(n.id for n in ampliar.nodos)}; y estas "
                f"uniones: {', '.join(u.id for u in ampliar.uniones) or 'ninguna'}. No quites "
                "ni cambies ninguno, ni su id: las piezas se hicieron con ellos.\n"
                "- Una pieza que ya existe no puede pasar a depender de una nueva: lo nuevo se "
                "diseña contra lo que hay (va en `depende_de` de lo nuevo), nunca al revés.\n"
                "- A una pieza que ya existe solo puedes añadirle algo en `compra` o meterla en "
                "una unión nueva, y eso obliga a corregirla: toca las menos posibles.\n"
                "- El conjunto lleva también las piezas nuevas en `depende_de`.\n\n"
                "Parte de este plan:\n\n"
                f"```json\n{(anterior or ampliar.model_dump_json(indent=2)).strip()}\n```\n")
        elif anterior:
            # Sin esto, contestar al desglose lo tiraba y se desglosaba de
            # cero: corregir una unión podía rebarajar todas las piezas.
            prompt += ("\n## Tu plan anterior\n\nLa persona vio este plan y contestó; sus "
                       "respuestas están al final de la petición. Cambia solo lo que piden: "
                       "los nodos, los ids y las uniones que no toquen se quedan igual.\n\n"
                       f"```json\n{anterior.strip()}\n```\n")

        def validar(obra: Obra) -> None:
            errores = [f"«{c}» (en «{n.id}») no tiene ficha; los ids que hay son: "
                       f"{', '.join(disponibles)}"
                       for n in obra.nodos for c in n.compra if c not in disponibles]
            errores += [f"«{n.id}» es un conjunto y no depende de ninguna pieza: un "
                        "conjunto agrupa las piezas que se mueven"
                        for n in obra.nodos if n.tipo == "conjunto" and not n.depende_de]
            # Sin la f, al modelo le llegaba «{c}» tal cual en vez del id.
            errores += [f"«{n.nombre}» es el componente comprado «{c}», no una pieza: no se "
                        f"diseña ni se imprime. Quita ese nodo y pon «{c}» en `compra` de la "
                        "pieza que lo aloja"
                        for n in obra.nodos if n.tipo == "pieza"
                        for c in [es_componente(n.nombre)] if c]
            piezas = [n for n in obra.nodos if n.tipo == "pieza"]
            if len(piezas) > 1 and not obra.uniones:
                errores.append("faltan las `uniones`: con varias piezas hay que decir cómo "
                               "se une cada una a las demás (`gira` o `fija`)")
            if ampliar is not None:
                from orchestrator.ampliar import diferencia
                errores += diferencia(ampliar, obra).errores
            # Con un componente sin ficha no hay salidas que mirar.
            if not errores:
                errores += validar_plan(obra, agujeros or {})[0]
            if errores:
                raise ValueError("el desglose no vale:\n- " + "\n- ".join(errores))

        return structured(self._client, prompt, Obra, extra_validation=validar,
                          cliente_de_reserva=self._reserva)
