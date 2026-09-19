"""Router de modelos. Ver SISTEMA_MULTIAGENTE.md § 6.

Los agentes piden **roles** (`design`, `qa`), nunca modelos concretos. El
perfil activo decide el modelo. Por eso migrar de DeepSeek a Ollama es
cambiar una variable de entorno y no tocar once agentes (ADR-007b).
"""

from pathlib import Path
from typing import Literal, Mapping

import yaml
from pydantic import BaseModel


class ClaveAusente(RuntimeError):
    """Falta una credencial que el perfil activo necesita."""


class PerfilDesconocido(KeyError):
    """`INTELLIPRINT_PROFILE` no coincide con ningún perfil de models.yaml."""


class ModelRef(BaseModel):
    provider: Literal["local", "deepseek"]
    model: str


class Router:
    def __init__(self, config: dict, env: Mapping[str, str]) -> None:
        self._config = config
        self._env = env

        nombre = env.get(
            config.get("active_profile_env", "INTELLIPRINT_PROFILE"),
            config.get("active_profile_default", "dev"),
        )
        perfiles = config.get("profiles", {})
        if nombre not in perfiles:
            raise PerfilDesconocido(
                f"perfil {nombre!r} desconocido. Definidos: {sorted(perfiles)}"
            )
        self.profile_name = nombre
        self._profile = perfiles[nombre]

        clave_env = (
            config.get("providers", {}).get("deepseek", {}).get("api_key_env")
            or "DEEPSEEK_API_KEY"
        )
        self._tiene_clave = bool(env.get(clave_env))

        # Si algún rol del perfil apunta a DeepSeek, la clave es obligatoria:
        # es el proveedor principal, no un extra. Falla aquí y no con un 401
        # a mitad del primer proyecto.
        if self._usa_deepseek_como_proveedor() and not self._tiene_clave:
            raise ClaveAusente(
                f"el perfil {nombre!r} usa DeepSeek como proveedor principal, "
                f"pero {clave_env} está vacía. Ponla en el archivo .env "
                "(plantilla en .env.example)."
            )

    def _usa_deepseek_como_proveedor(self) -> bool:
        return any(
            isinstance(destino, str) and destino.startswith("deepseek/")
            for destino in self._profile.values()
        )

    @property
    def escalation_available(self) -> bool:
        """En `prod`, DeepSeek es escalamiento opcional (§ 6.2): sin clave el
        sistema trabaja solo con modelos locales en vez de romperse."""
        return self._tiene_clave

    @classmethod
    def from_config_file(
        cls, path: str | Path, env: Mapping[str, str]
    ) -> "Router":
        config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(config, env)

    def for_role(self, role: str) -> ModelRef:
        destino = self._profile.get(role)
        if not destino:
            raise KeyError(
                f"el perfil {self.profile_name!r} no define el rol {role!r}"
            )
        provider, _, model = destino.partition("/")
        return ModelRef(provider=provider, model=model)
