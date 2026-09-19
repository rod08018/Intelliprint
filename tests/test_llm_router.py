"""Router de modelos: perfil activo, roles y escalamiento.

Ver SISTEMA_MULTIAGENTE.md § 6 y DECISIONES.md ADR-007 / ADR-007b.
"""

import pytest

from orchestrator.llm.router import ClaveAusente, Router


def _router(profile: str, env: dict | None = None) -> Router:
    base = {"INTELLIPRINT_PROFILE": profile}
    base.update(env or {})
    return Router.from_config_file("config/models.yaml", env=base)


def test_el_perfil_dev_resuelve_el_rol_de_diseno_a_deepseek():
    """Los agentes piden roles, no modelos. El perfil decide el modelo."""
    ref = _router("dev", {"DEEPSEEK_API_KEY": "sk-loquesea"}).for_role("design")

    assert ref.provider == "deepseek"
    assert ref.model == "deepseek-chat"


def test_el_perfil_prod_resuelve_el_mismo_rol_a_ollama():
    """Migrar es cambiar una variable de entorno (ADR-007b)."""
    ref = _router("prod").for_role("design")

    assert ref.provider == "local"
    assert ref.model == "qwen3.8"


def test_sin_clave_el_perfil_dev_falla_al_arrancar_y_dice_donde_ponerla():
    """Un 401 a mitad del primer proyecto es un mal sitio para enterarse.

    Con `dev` la clave no es opcional: es el proveedor principal. Mejor
    romper al construir el router y nombrar el archivo que hay que tocar.
    """
    with pytest.raises(ClaveAusente, match=r"\.env"):
        _router("dev")


def test_sin_clave_el_perfil_prod_arranca_y_solo_desactiva_el_escalamiento():
    """En `prod` DeepSeek es un extra, no una dependencia (§ 6.2).

    "Si DEEPSEEK_API_KEY no está definida, el escalamiento se desactiva y
    el sistema trabaja solo con modelos locales."
    """
    router = _router("prod")

    assert router.escalation_available is False
    assert router.for_role("design").provider == "local"


def test_con_clave_el_escalamiento_esta_disponible_en_prod():
    assert _router("prod", {"DEEPSEEK_API_KEY": "sk-x"}).escalation_available is True
