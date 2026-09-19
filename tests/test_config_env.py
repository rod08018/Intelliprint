"""Carga del archivo .env.

Aquí viven la clave de DeepSeek y el token del bot: un parseo descuidado
(comillas, comentarios, espacios) da una clave que no funciona y un 401
sin explicación.
"""

from orchestrator.config import load_env


def test_lee_claves_ignora_comentarios_y_quita_comillas(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comentario\n"
        "DEEPSEEK_API_KEY=sk-123\n"
        "\n"
        'AGENT_NAME="Crafty"\n'
        "VACIA=\n"
        "  CON_ESPACIOS = valor  \n"
    )

    valores = load_env(env, base={})

    assert valores["DEEPSEEK_API_KEY"] == "sk-123"
    assert valores["AGENT_NAME"] == "Crafty"
    assert valores["VACIA"] == ""
    assert valores["CON_ESPACIOS"] == "valor"
    assert "# comentario" not in valores


def test_el_entorno_real_gana_al_archivo(tmp_path):
    """Una variable exportada en la terminal debe poder sobrescribir la del
    archivo sin editarlo, por ejemplo para cambiar de perfil una vez."""
    env = tmp_path / ".env"
    env.write_text("INTELLIPRINT_PROFILE=dev\n")

    valores = load_env(env, base={"INTELLIPRINT_PROFILE": "prod"})

    assert valores["INTELLIPRINT_PROFILE"] == "prod"


def test_sin_archivo_devuelve_solo_el_entorno(tmp_path):
    assert load_env(tmp_path / "no_existe", base={"A": "1"}) == {"A": "1"}
