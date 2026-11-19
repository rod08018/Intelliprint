"""Abre en el FreeCAD del PC el invento montado (F13.14 (ensamble)).

La lanza el puente del host (`abrir_en_freecad`) con el documento en
INTELLIPRINT_FCSTD. Ese documento lo escribe el contenedor con freecadcmd,
que no tiene ventana y no guarda colores: cada malla lleva el suyo en la
propiedad `Color`, y aquí se pinta.
"""

import os

import FreeCAD
import FreeCADGui

from PySide import QtCore


def _pintar():
    doc = FreeCAD.openDocument(os.environ["INTELLIPRINT_FCSTD"])
    for o in doc.Objects:
        # Los escritos sin ventana pueden venir ocultos (2026-11-19).
        if o.ViewObject is not None:
            o.ViewObject.Visibility = True
        if hasattr(o, "Color") and o.ViewObject is not None:
            try:
                o.ViewObject.ShapeColor = o.Color
            except Exception:   # FreeCAD 1.x: el color de una malla es su apariencia
                m = FreeCAD.Material()
                m.DiffuseColor = o.Color
                o.ViewObject.ShapeAppearance = (m,)
    # La vista 3D del documento, no «la activa»: al arrancar, delante puede
    # estar la pestaña de inicio.
    gui = FreeCADGui.getDocument(doc.Name)
    for vista in gui.mdiViewsOfType("Gui::View3DInventor"):
        vista.viewIsometric()
        vista.fitAll()
    # Pintar lo marcaba como cambiado, y al cerrar FreeCAD preguntaba si
    # guardar algo que él no había tocado (2026-11-19).
    gui.Modified = False


# Lanzada al arrancar, la ventana todavía no tiene vista: se espera a que la
# tenga.
QtCore.QTimer.singleShot(1500, _pintar)
