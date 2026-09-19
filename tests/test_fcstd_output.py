"""El .FCStd tiene que abrirse en FreeCAD mostrando la pieza (bug real).

freecadcmd no escribe GuiDocument.xml, así que la visibilidad sale de la
propiedad Visibility de cada objeto. Se guardaban los 9 visibles, incluidas
las brocas de 1000 mm: al abrir, FreeCAD encuadraba las brocas y la placa
de 60x60x6 quedaba invisible. "Se guarda vacío", dijo el usuario.
"""

import re
import zipfile

import pytest

from tests.test_generators import _freecadcmd
from tests.test_measure_extract import _nema17


def _objetos(fcstd) -> dict[str, dict]:
    xml = zipfile.ZipFile(fcstd).read("Document.xml").decode()
    objetos = {}
    for nombre in re.findall(r'<Object name="([^"]+)"', xml):
        bloque = xml.split(f'<Object name="{nombre}"')[-1]
        vis = re.search(r'name="Visibility".*?value="(\w+)"', bloque, re.S)
        etiqueta = re.search(r'name="Label".*?value="([^"]*)"', bloque, re.S)
        objetos[nombre] = {
            "visible": vis is not None and vis.group(1) == "true",
            "label": etiqueta.group(1) if etiqueta else None,
        }
    return objetos


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_solo_la_pieza_final_queda_visible(tmp_path):
    _nema17(tmp_path)

    visibles = [n for n, o in _objetos(tmp_path / "pieza.FCStd").items() if o["visible"]]

    assert len(visibles) == 1


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_la_pieza_final_se_llama_como_la_pieza(tmp_path):
    """Para ensamblarla hay que encontrarla en el árbol: `con_patron` no
    dice nada, `pieza` sí."""
    _nema17(tmp_path)

    objetos = _objetos(tmp_path / "pieza.FCStd")
    visible = next(o for o in objetos.values() if o["visible"])

    assert visible["label"] == "pieza"


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_la_historia_parametrica_se_conserva_oculta(tmp_path):
    """Ocultar no es borrar: la placa y las brocas siguen ahí para poder
    editar la pieza en FreeCAD."""
    _nema17(tmp_path)

    assert len(_objetos(tmp_path / "pieza.FCStd")) == 9


def _visibilidad_gui(fcstd) -> dict[str, bool]:
    xml = zipfile.ZipFile(fcstd).read("GuiDocument.xml").decode()
    return {
        nombre: valor == "true"
        for nombre, valor in re.findall(
            r'<ViewProvider name="([^"]+)".*?name="Visibility".*?<Bool value="(\w+)"',
            xml, re.S,
        )
    }


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_fcstd_lleva_la_visibilidad_que_lee_la_interfaz(tmp_path):
    """El bug real. Sin GuiDocument.xml, FreeCAD abre un documento guardado
    por freecadcmd con TODO oculto: el usuario lo veía vacío. La propiedad
    Visibility del documento no basta, se comprobó abriéndolo en la
    interfaz: la ignora. Hay que escribir GuiDocument.xml."""
    _nema17(tmp_path)

    gui = _visibilidad_gui(tmp_path / "pieza.FCStd")

    assert len(gui) == 9
    assert sum(gui.values()) == 1
    visible = next(n for n, v in gui.items() if v)
    assert _objetos(tmp_path / "pieza.FCStd")[visible]["label"] == "pieza"
