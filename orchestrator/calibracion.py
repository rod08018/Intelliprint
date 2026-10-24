"""Pieza de calibración de holguras (F2.18 (calibración)).

Las holguras de config/printers/ son valores por defecto de boquilla 0.4,
no medidas. `M3_through_mm: 3.3` es casi un ajuste justo (la ISO normal es
3.4) y nadie lo ha comprobado imprimiendo: cambiarlo a ojo sería sustituir
un valor sin validar por otro igual de sin validar. Esta pieza lo mide.

Tres piezas, impresas con el perfil activo:

- un peine de agujeros de 5.0 a 5.5 mm (holguras de 0.0 a 0.5 en diámetro);
- un eje de 5.0 mm para probarlo en cada agujero;
- una placa M3: rosca directa y pasante (2.6 a 3.6) e inserto (3.8 a 4.4).

No hay generador de texto, así que no llevan números grabados: los agujeros
van de menor a mayor empezando junto a la muesca de una esquina. El
usuario prueba, apunta qué encajó y lo mete con `aplicar_resultados`, que
es el ÚNICO camino por el que cambian las holguras del perfil.
"""

import re
from pathlib import Path

from orchestrator.schemas.recipe import Recipe

EJE_MM = 5.0
HOLGURAS_MM = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
M3_ROSCA_Y_PASANTE_MM = (2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6)
M3_INSERTO_MM = (3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4)

PASO_MM = 10.0
MARGEN_MM = 9.0
MUESCA_MM = 4.0


class CalibracionInvalida(ValueError):
    """Unos resultados que la pieza no puede haber dado."""


def _paso(generador: str, **params) -> dict:
    return {"generator": generador, "params": params}


def _placa_con_filas(nombre: str, filas: list[tuple[float, tuple[float, ...]]],
                     paso: float, ancho: float, espesor: float) -> Recipe:
    """Una placa con filas de agujeros, de menor a mayor desde la muesca de
    la esquina (x mínima, y mínima)."""
    mas_larga = max(len(diametros) for _, diametros in filas)
    largo = 2 * MARGEN_MM + paso * (mas_larga - 1)
    x0 = -largo / 2 + MARGEN_MM
    pasos = [_paso("generate_box", length_mm=largo, width_mm=ancho, height_mm=espesor,
                   x_mm=0, y_mm=0, z_mm=0)]
    for y, diametros in filas:
        pasos += [_paso("generate_hole", diameter_mm=d, x_mm=round(x0 + i * paso, 3), y_mm=y)
                  for i, d in enumerate(diametros)]
    # Atraviesa la placa entera, y el test del volumen lo cuenta así.
    pasos.append(_paso("generate_cut_box", length_mm=MUESCA_MM, width_mm=MUESCA_MM,
                       height_mm=espesor + 2, x_mm=-largo / 2 + MUESCA_MM / 2,
                       y_mm=-ancho / 2 + MUESCA_MM / 2, z_mm=-1))
    return Recipe.model_validate({"part": nombre, "steps": pasos})


def recetas() -> list[Recipe]:
    agujeros = _placa_con_filas(
        "calibracion_agujeros", [(0.0, tuple(round(EJE_MM + h, 2) for h in HOLGURAS_MM))],
        paso=PASO_MM, ancho=16.0, espesor=5.0)
    eje = Recipe.model_validate({"part": "calibracion_eje", "steps": [
        _paso("generate_box", length_mm=16, width_mm=16, height_mm=3, x_mm=0, y_mm=0, z_mm=0),
        _paso("generate_cylinder", diameter_mm=EJE_MM, length_mm=12, x_mm=0, y_mm=0, z_mm=3,
              axis="z"),
    ]})
    # 6 mm de espesor: un inserto M3 corriente mide de 4 a 5.7 de largo.
    m3 = _placa_con_filas("calibracion_m3", [(6.0, M3_ROSCA_Y_PASANTE_MM), (-5.0, M3_INSERTO_MM)],
                          paso=8.0, ancho=26.0, espesor=6.0)
    return [agujeros, eje, m3]


def cuadro() -> str:
    """Qué es cada agujero y cómo probarlo: va con la pieza, en calibracion.md."""
    def fila(diametros, nota):
        return "\n".join(f"| {i} | {d:.2f} | {nota(d)} |" for i, d in enumerate(diametros, 1))

    peine = [EJE_MM + h for h in HOLGURAS_MM]
    return f"""# Calibración de holguras (F2.18 (calibración))

Imprime las tres piezas con el perfil activo y **sin** escalar nada en el
laminador. Los agujeros van de menor a mayor **empezando junto a la muesca**
de la esquina: el 1 es el más cercano a ella.

## Peine (`calibracion_agujeros`) con el eje de 5.00 mm (`calibracion_eje`)

Prueba el eje en cada agujero y apunta la HOLGURA (diámetro del agujero menos 5.00):

- **a presión** (`--press`): el primero en el que el eje entra empujando fuerte y se queda;
- **deslizante** (`--slide`): el primero en el que entra y gira con poco juego;
- **con holgura** (`--clearance`): el primero en el que gira libre, como un pivote.

| Posición | Agujero (mm) | Holgura |
|---|---|---|
{fila(peine, lambda d: f"{d - EJE_MM:.2f}")}

## Placa M3 (`calibracion_m3`), con un tornillo M3 y un inserto M3

Fila de arriba (lado opuesto a la muesca), con el tornillo:

- **rosca directa** (`--m3-selftap`): el más pequeño en el que el tornillo rosca firme sin partir la pieza;
- **pasante** (`--m3-through`): el más pequeño por el que el tornillo pasa sin tocar.

| Posición | Agujero (mm) | |
|---|---|---|
{fila(M3_ROSCA_Y_PASANTE_MM, lambda d: "")}

Fila de abajo (junto a la muesca), con el inserto y el soldador:

- **inserto** (`--m3-insert`): el que sujeta el inserto recto, sin grietas ni que gire.

| Posición | Agujero (mm) | |
|---|---|---|
{fila(M3_INSERTO_MM, lambda d: "")}

## Apuntar los resultados

En el PC (config/ está en solo lectura dentro del contenedor):

```
intelliprint calibrar resultados --press 0.1 --slide 0.2 --clearance 0.3 \\
    --m3-through 3.4 --m3-selftap 2.8 --m3-insert 4.1
```

Es el único camino por el que cambian las holguras del perfil activo; el
perfil queda marcado como calibrado, con la fecha.
"""


def _en(valor: float, opciones, que: str) -> None:
    if not any(abs(valor - o) < 1e-9 for o in opciones):
        raise CalibracionInvalida(f"{valor} no es ningún agujero de la {que}: {list(opciones)}")


def aplicar_resultados(ruta: Path, *, press_mm: float, slide_mm: float, clearance_mm: float,
                       m3_through_mm: float, m3_selftap_mm: float, m3_insert_mm: float,
                       fecha: str) -> None:
    """Escribe lo medido en el YAML de la impresora y lo marca calibrado.

    Se toca solo el número de cada línea: comentarios y demás valores se
    quedan. Si algo no cuadra con la pieza, no se escribe NADA."""
    for v in (press_mm, slide_mm, clearance_mm):
        _en(v, HOLGURAS_MM, "pieza: el peine solo tiene holguras de")
    _en(m3_through_mm, M3_ROSCA_Y_PASANTE_MM, "placa M3")
    _en(m3_selftap_mm, M3_ROSCA_Y_PASANTE_MM, "placa M3")
    _en(m3_insert_mm, M3_INSERTO_MM, "placa M3")
    if not press_mm < slide_mm < clearance_mm:
        raise CalibracionInvalida(
            f"tiene que ser press < slide < clearance, y es {press_mm}, {slide_mm}, {clearance_mm}")
    if not m3_selftap_mm < m3_through_mm:
        raise CalibracionInvalida(
            f"el agujero de rosca directa ({m3_selftap_mm}) tiene que ser menor que el "
            f"pasante ({m3_through_mm})")

    texto = Path(ruta).read_text(encoding="utf-8")
    nuevos = {"press_mm": press_mm, "slide_mm": slide_mm, "clearance_mm": clearance_mm,
              "M3_through_mm": m3_through_mm, "M3_selftap_mm": m3_selftap_mm,
              "M3_insert_mm": m3_insert_mm}
    for clave, valor in nuevos.items():
        texto, n = re.subn(rf"^(\s*{clave}:\s*)[\d.]+", rf"\g<1>{valor:.2f}", texto, flags=re.M)
        if n != 1:
            raise CalibracionInvalida(f"{ruta} no tiene exactamente una línea «{clave}:»")
    texto, n = re.subn(r"^calibrated:.*$",
                       f"calibrated: true             # medido con F2.18 (calibración), {fecha}",
                       texto, flags=re.M)
    if n != 1:
        raise CalibracionInvalida(f"{ruta} no tiene exactamente una línea «calibrated:»")
    Path(ruta).write_text(texto, encoding="utf-8")
