"""El desglosador (F7.2 (desglose)): parte un proyecto en piezas que se
diseñan una a una.

Los mecanismos grandes se pedían de una sola vez: la Ginebra (2026-09-20)
murió porque el razonador se cortó tres veces escribiendo todo el
mecanismo. Este agente no diseña nada: decide qué piezas hay y cómo se
apoyan unas en otras, y es una llamada pequeña.
"""

from pathlib import Path

from orchestrator.componentes import cargar, ids, mencionados, resumen
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.obra import Obra

PROMPT_PATH = Path("config/agents/desglosador.md")


class DesglosadorAgent:
    def __init__(self, client: LlmClient, prompt_path: Path = PROMPT_PATH,
                 reserva: LlmClient | None = None) -> None:
        self._client = client
        self._reserva = reserva
        self._instrucciones = prompt_path.read_text(encoding="utf-8")

    def desglosar(self, peticion: str) -> Obra:
        disponibles = ids()
        prompt = (f"{self._instrucciones}\n\n## Componentes con ficha\n\n"
                  f"{', '.join(disponibles)}\n")
        nombrados = mencionados(peticion)
        if nombrados:
            prompt += ("\nLa petición nombra estos:\n\n"
                       + "\n\n".join(resumen(cargar(i)) for i in nombrados) + "\n")
        prompt += f"\n## Petición\n\n> {peticion.strip()}\n"

        def validar(obra: Obra) -> None:
            errores = [f"«{c}» (en «{n.id}») no tiene ficha; los ids que hay son: "
                       f"{', '.join(disponibles)}"
                       for n in obra.nodos for c in n.compra if c not in disponibles]
            errores += [f"«{n.id}» es un conjunto y no depende de ninguna pieza: un "
                        "conjunto agrupa las piezas que se mueven"
                        for n in obra.nodos if n.tipo == "conjunto" and not n.depende_de]
            if errores:
                raise ValueError("el desglose no vale:\n- " + "\n- ".join(errores))

        return structured(self._client, prompt, Obra, extra_validation=validar,
                          cliente_de_reserva=self._reserva)
