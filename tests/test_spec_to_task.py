"""Spec → PartTask (F1.9 (PartTask)).

Con una sola pieza nadie convertía la spec en el enunciado que recibe el
Part Designer. Con varias lo hará `Decomposition` (F3.2 (decomposition)); esto es su
versión mínima para la Fase 1.
"""

from orchestrator.schemas.spec import Spec
from orchestrator.tasks import spec_to_task

_SPEC = Spec(
    title="soporte de vaso para carruaje",
    description="sujeta un vaso a un tubo de 68 mm de diámetro exterior",
    product_class="static_part",
    printer="ankermake_m5_petg",
    material="PETG",
)


def test_el_enunciado_lleva_la_descripcion_y_las_restricciones():
    """El Part Designer necesita saber en qué material imprime: condiciona
    espesores mínimos y holguras, y no está en la descripción."""
    tarea = spec_to_task(_SPEC)

    assert "tubo de 68 mm" in tarea.brief
    assert "PETG" in tarea.brief


def test_el_nombre_de_la_pieza_es_un_slug_usable_como_archivo():
    """Se usa para `parts/<pieza>/` y para el nombre del .FCStd."""
    tarea = spec_to_task(_SPEC)

    assert tarea.part == "soporte_de_vaso_para_carruaje"
    assert tarea.state == "TODO"


def test_el_enunciado_lleva_la_peticion_literal_del_usuario():
    """Las cotas que dio el usuario tienen que llegar al Part Designer
    aunque el resumen de la spec las haya perdido."""
    spec = _SPEC.model_copy(update={"request": "agujeros de 3.3 mm en cuadro de 31"})

    tarea = spec_to_task(spec)

    assert "agujeros de 3.3 mm en cuadro de 31" in tarea.brief


def test_un_titulo_largo_da_un_nombre_que_cabe_en_las_rutas_de_windows():
    """Fallo real (2026-10-27): «Placa 40x40x5 con taladro central de 25 mm»
    se repite tres veces en la ruta (parts/<pieza>/<pieza>.FCStd, más la
    carpeta del proyecto) y FreeCAD, en Windows, no pasa de 260 caracteres:
    con la misma receta construía a 204 y fallaba a 262. El nombre se corta
    entre palabras, nunca a mitad."""
    from orchestrator.tasks import nombre_corto

    titulo = "Placa 40x40x5 con taladro central de 25 mm"
    pieza = spec_to_task(_SPEC.model_copy(update={"title": titulo})).part
    assert pieza == "placa_40x40x5_con_taladro"

    # La ruta con la que falló: la carpeta temporal de pytest en el PC.
    base = "C:/Users/jdr/AppData/Local/Temp/pytest-of-jdr/pytest-1897/test_de_la_frase_a_la_pieza_pl0"
    ruta = f"{base}/projects/2026-10-27-{nombre_corto(titulo, 40)}/parts/{pieza}/{pieza}.FCStd"
    assert len(ruta) < 260
