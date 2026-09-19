"""Post-proceso del .FCStd que guarda freecadcmd.

Un documento guardado sin interfaz no lleva GuiDocument.xml, y FreeCAD lo
abre con TODOS los objetos ocultos: el usuario ve un documento vacío. La
propiedad Visibility del propio documento no basta — se comprobó abriendo
el archivo en la interfaz real: la ignora.

Como `setupWithoutGUI()` no crea proveedores de vista en esta versión de
FreeCAD, se escribe GuiDocument.xml a mano. Basta la visibilidad: FreeCAD
rellena el resto de propiedades visuales con sus valores por defecto.
Verificado en la interfaz de FreeCAD 1.1.3 el 2026-09-19.
"""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path


def _gui_document(objetos: list[str], visibles: set[str]) -> str:
    proveedores = "".join(
        f'        <ViewProvider name="{nombre}" expanded="0">\n'
        '            <Properties Count="1" TransientCount="0">\n'
        '                <Property name="Visibility" type="App::PropertyBool" status="1">\n'
        f'                    <Bool value="{"true" if nombre in visibles else "false"}"/>\n'
        "                </Property>\n"
        "            </Properties>\n"
        "        </ViewProvider>\n"
        for nombre in objetos
    )
    return (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        '<Document SchemaVersion="1" HasExpansion="1">\n'
        "    <Expand />\n"
        f'    <ViewProviderData Count="{len(objetos)}">\n'
        f"{proveedores}"
        "    </ViewProviderData>\n"
        "</Document>\n"
    )


def mostrar_solo(fcstd: Path, objeto: str) -> None:
    """Deja visible en la interfaz solo `objeto` (nombre interno, no Label).

    La construcción (brocas, cortes intermedios) queda oculta pero no se
    borra: la historia paramétrica sigue editable en FreeCAD.
    """
    mostrar(fcstd, {objeto})


def mostrar(fcstd: Path, visibles: set[str]) -> None:
    """Deja visibles en la interfaz exactamente los objetos `visibles`."""
    fcstd = Path(fcstd)
    with zipfile.ZipFile(fcstd) as origen:
        documento = origen.read("Document.xml").decode("utf-8")
        objetos = re.findall(r'<Object name="([^"]+)"', documento)
        faltan = sorted(set(visibles) - set(objetos))
        if faltan:
            raise ValueError(f"{faltan} no están en {fcstd.name}: {objetos}")

        # Reescribir el zip entero: añadir con modo "a" duplicaría la
        # entrada si el archivo ya tuviera un GuiDocument.xml.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".FCStd") as tmp:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as destino:
                for entrada in origen.infolist():
                    if entrada.filename != "GuiDocument.xml":
                        destino.writestr(entrada, origen.read(entrada.filename))
                destino.writestr("GuiDocument.xml", _gui_document(objetos, set(visibles)))
    # El temporal nace con permisos 0600: sin esto el .FCStd quedaba legible
    # solo por su dueño.
    shutil.copymode(fcstd, tmp.name)
    shutil.move(tmp.name, fcstd)
