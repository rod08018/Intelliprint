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

from orchestrator.ingenieria import Material, comprobar
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.concepto import Concepto, ConceptoComprobado
from orchestrator.schemas.spec import Spec

PROMPT_PATH = Path("config/agents/ingeniero.md")

_DEL_PERFIL = ("printer", "material", "layer_height_mm", "bed_mm", "fits", "holes",
               "walls", "overhang_max_deg", "bridge_max_mm", "resistencia")
"""Lo que el ingeniero necesita del perfil activo. Antes nadie que diseñara
lo recibía: las cotas de tornillería salían de memoria."""


class IngenieroAgent:
    def __init__(self, client: LlmClient, activo, prompt_path: Path = PROMPT_PATH,
                 reserva: LlmClient | None = None) -> None:
        self._client = client
        self._reserva = reserva
        self._material = Material.del_perfil(activo.datos)
        perfil = {k: activo.datos[k] for k in _DEL_PERFIL if k in activo.datos}
        self._instrucciones = (
            prompt_path.read_text(encoding="utf-8")
            + "\n\n## Perfil activo (impresora y material)\n\n```yaml\n"
            + yaml.safe_dump(perfil, allow_unicode=True, sort_keys=False) + "```\n")

    def concebir(self, spec: Spec) -> ConceptoComprobado:
        requisitos = "".join(
            f"- {r.id} ({r.tipo}, {r.origen}): {r.texto}"
            + (f" → {r.valor:g} {r.unidad}" if r.valor is not None else "") + "\n"
            for r in spec.requisitos) or "(ninguno estructurado)\n"
        prompt = (f"{self._instrucciones}\n## Encargo: {spec.title}\n\n{spec.description}\n\n"
                  f"Petición literal:\n> {spec.request}\n\n## Requisitos\n\n{requisitos}")

        def validar(concepto: Concepto) -> None:
            errores = []
            pide_carga = [r.id for r in spec.requisitos if r.tipo == "carga"]
            if (pide_carga or spec.payload_g) and not concepto.casos_de_carga:
                errores.append(
                    f"se pide aguantar una carga ({', '.join(pide_carga) or 'payload_g'}) y no "
                    "hay ningún caso de carga: di qué sección trabaja y con cuánto.")
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
