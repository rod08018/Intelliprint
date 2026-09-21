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


# --- Comentarios al final de la línea -------------------------------------
#
# Fallo real al mudar el sistema a Windows: la plantilla trae
#
#     # TELEGRAM_BOT_TOKEN=                # SECRETO: quien lo tenga controla el bot
#
# y al quitarle el `#` y pegar el token delante del comentario, load_env
# entregaba «123:ABC                # SECRETO: quien lo…» —103 caracteres en
# vez de 46—, y Telegram habría contestado 401 sin decir por qué.
#
# Docker Compose SÍ quita ese comentario al leer el MISMO archivo. Dos
# lectores del mismo .env que no están de acuerdo: el sistema funcionaba en
# el contenedor y fallaba al correrlo nativo, o al revés. Aquí se sigue la
# regla de Compose: en un valor SIN comillas, un `#` precedido de espacio
# abre un comentario.


def test_un_comentario_tras_el_valor_no_forma_parte_de_el(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=123456:ABCdef                # SECRETO: quien lo tenga controla el bot\n"
        "TELEGRAM_ALLOWED_USERS=111,222            # OBLIGATORIA\n",
        encoding="utf-8")
    valores = load_env(env, base={})
    assert valores["TELEGRAM_BOT_TOKEN"] == "123456:ABCdef"
    assert valores["TELEGRAM_ALLOWED_USERS"] == "111,222"


def test_una_almohadilla_pegada_es_parte_del_valor(tmp_path):
    """Sin espacio delante no es un comentario: una contraseña puede llevar #."""
    env = tmp_path / ".env"
    env.write_text("CLAVE=abc#123\n", encoding="utf-8")
    assert load_env(env, base={})["CLAVE"] == "abc#123"


def test_entre_comillas_la_almohadilla_es_literal(tmp_path):
    env = tmp_path / ".env"
    env.write_text('FRASE="hola # mundo"   # y esto sí es comentario\n', encoding="utf-8")
    assert load_env(env, base={})["FRASE"] == "hola # mundo"


def test_un_valor_vacio_con_comentario_sigue_vacio(tmp_path):
    """Es la forma de la plantilla antes de rellenarla: vacío, no el
    texto del comentario."""
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_ALLOWED_USERS=            # OBLIGATORIA\n", encoding="utf-8")
    assert load_env(env, base={})["TELEGRAM_ALLOWED_USERS"] == ""


def test_una_ruta_de_windows_no_se_toca(tmp_path):
    env = tmp_path / ".env"
    env.write_text(r"FREECADCMD=C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" + "\n",
                   encoding="utf-8")
    assert load_env(env, base={})["FREECADCMD"] == r"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
