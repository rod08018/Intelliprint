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
usuario prueba y apunta qué encajó; lo apuntado pasa por `validar_holguras`
y se guarda en el workspace (F2.21 (impresora)).
"""

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

En la web, en «Impresora», con una foto de la pieza probada; o con la orden:

```
intelliprint calibrar resultados --press 0.1 --slide 0.2 --clearance 0.3 \\
    --m3-through 3.4 --m3-selftap 2.8 --m3-insert 4.1
```

Lo medido se guarda con su fecha en el workspace y manda sobre el perfil
de `config/printers/`, que no se toca: el diseño queda calibrado.
"""


def _en(valor: float, opciones, que: str) -> None:
    if not any(abs(valor - o) < 1e-9 for o in opciones):
        raise CalibracionInvalida(f"{valor} no es ningún agujero de la {que}: {list(opciones)}")


def validar_holguras(*, press_mm: float, slide_mm: float, clearance_mm: float,
                     m3_through_mm: float, m3_selftap_mm: float, m3_insert_mm: float) -> None:
    """Que lo apuntado sea algo que la pieza puede haber dado.

    Antes esto escribía en `config/printers/`, que dentro del contenedor es de
    solo lectura: solo se podía apuntar desde el PC. Lo medido vive ahora en
    el workspace (F2.21 (impresora)) y se apunta desde la web o la orden."""
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


# --- La barra de flexión (F2.21 (impresora)) ------------------------------------------
#
# La resistencia del perfil es una estimación sin ensayar (F3.19 (resistencia)).
# La barra la mide: se sujeta el bloque al borde de la mesa, se cuelga peso del
# agujero y se apunta con cuánto rompió. Dos barras porque una pieza FDM no
# aguanta igual a lo largo del filamento (tumbada) que entre capas (de pie).

BARRA = {"ancho_mm": 10.0, "grueso_mm": 4.0, "brazo_mm": 50.0, "agujero_mm": 5.0,
         "punta_mm": 6.0, "metida_mm": 2.0, "bloque_mm": (20.0, 10.0, 12.0)}
G = 9.80665


def mpa_de_barra(carga_kg: float) -> float:
    """Tensión en el borde del bloque al romper: voladizo, σ = M·c/I = 6·F·L / (b·h²).

    Es la de una sección sin entallas; en una pieza real con esquinas vivas
    rompe antes, y para eso está el factor de seguridad del perfil."""
    b, h, brazo = BARRA["ancho_mm"], BARRA["grueso_mm"], BARRA["brazo_mm"]
    return 6 * carga_kg * G * brazo / (b * h ** 2)


def recetas_barra() -> list[Recipe]:
    b, h, brazo = BARRA["ancho_mm"], BARRA["grueso_mm"], BARRA["brazo_mm"]
    metida, punta = BARRA["metida_mm"], BARRA["punta_mm"]
    largo_bloque, ancho_bloque, alto_bloque = BARRA["bloque_mm"]
    largo = metida + brazo + punta
    # Tumbada: el bloque de x = −20 a 0 y la barra de x = −2 a 56, de 4 de alto.
    # El esfuerzo va a lo largo del filamento.
    xy = Recipe.model_validate({"part": "calibracion_barra_xy", "steps": [
        _paso("generate_box", length_mm=largo_bloque, width_mm=ancho_bloque, height_mm=alto_bloque,
              x_mm=-largo_bloque / 2, y_mm=0, z_mm=0),
        _paso("generate_box", length_mm=largo, width_mm=b, height_mm=h,
              x_mm=-metida + largo / 2, y_mm=0, z_mm=0),
        _paso("generate_hole", diameter_mm=BARRA["agujero_mm"], x_mm=brazo, y_mm=0),
    ]})
    # De pie: el bloque de z = 0 a 20 y la barra encima. La flexión intenta
    # separar las capas, que es por donde rompe una pieza impresa.
    z = Recipe.model_validate({"part": "calibracion_barra_z", "steps": [
        _paso("generate_box", length_mm=alto_bloque, width_mm=ancho_bloque, height_mm=largo_bloque,
              x_mm=0, y_mm=0, z_mm=0),
        _paso("generate_box", length_mm=h, width_mm=b, height_mm=largo,
              x_mm=0, y_mm=0, z_mm=largo_bloque - metida),
        _paso("generate_hole_axis", diameter_mm=BARRA["agujero_mm"], x_mm=0, y_mm=0,
              z_mm=largo_bloque + brazo, axis="x"),
    ]})
    return [xy, z]


def cuadro_barra() -> str:
    """Cómo romperla y qué apuntar: va con las barras, en calibracion.md."""
    return f"""# Barras de flexión (F2.21 (impresora))

Imprime las dos barras con el perfil activo, laminadas como las piezas que
aguantan carga, y **sin** escalar nada:

- `calibracion_barra_xy`, tumbada: mide la resistencia a lo largo del filamento;
- `calibracion_barra_z`, de pie: mide la resistencia entre capas.

Para cada una:

1. Sujeta el bloque al borde de la mesa con un sargento, con la barra en
   horizontal y la cara de {BARRA['grueso_mm']:g} mm hacia arriba.
2. Cuelga del agujero un cubo, a {BARRA['brazo_mm']:g} mm del borde del bloque.
3. Ve echando agua (o peso) poco a poco hasta que la barra rompa.
4. Pesa el cubo con lo que tenía dentro y apúntalo en kg en la web, en
   «Impresora», con una foto de la rotura.

Si rompe lejos del borde del bloque, la impresión tenía un defecto: repítela.
"""


# --- las transmisiones (F10.8 (calibrar)) -----------------------------------------------------

HOLGURAS_DE_TRANSMISION_MM = (0.10, 0.15, 0.20, 0.25)


def piezas_de_transmision() -> dict[str, str]:
    """{nombre: programa del kit} de lo que se imprime para medir con qué
    holgura giran las transmisiones: la carcasa y la excéntrica de la
    cicloidal 10:1 de verdad, su disco con cada holgura —lo que se apunte
    vale tal cual para la reductora— y una polea GT2 de 40 dientes con un
    paso de 5 mm, para ver si la correa asienta."""
    from orchestrator.cicloidal import generar
    base = generar(10)
    piezas = {"carcasa": base.piezas["carcasa"], "excentrica": base.piezas["excentrica"]}
    for h in HOLGURAS_DE_TRANSMISION_MM:
        piezas[f"disco_{round(h * 100):03d}"] = generar(10, holgura=h).piezas["disco"]
    piezas["polea_40"] = (
        'def construir(kit):\n'
        '    return kit.polea_gt2("polea", 40).taladrar("eje", 5.2, en=(0, 0, 10))\n')
    return piezas


def cuadro_de_transmision() -> str:
    filas = "\n".join(f"| disco_{round(h * 100):03d} | {h:.2f} mm |"
                       for h in HOLGURAS_DE_TRANSMISION_MM)
    return f"""# Piezas de prueba de las transmisiones (F10.8 (calibrar))

Imprime todo con el perfil de siempre. La carcasa, de pie como sale; los discos y la
excéntrica, tumbados.

## La cicloidal

1. Mete la excéntrica en un eje de 5 mm (el de un NEMA 17 o una varilla) por el centro de
   la carcasa.
2. Pon un disco sobre la leva, dentro de los pernos, y gira el eje con la mano.
3. Prueba los cuatro. El bueno es el que **gira entero sin atascarse y sin bailar**: el de
   menos holgura que no se agarra en ningún punto de la vuelta.

| Disco | Holgura |
|---|---|
{filas}

Apunta su holgura en la página «Impresora» → «Holgura de las transmisiones». Desde entonces
la reductora se hace con ella.

## La polea

Pasa una correa GT2 de 6 mm por la polea de 40 dientes. Tiene que asentar en las ranuras
sin montarse en las crestas y sin holgura de lado. Si no asienta, apúntalo como «prueba
tuya» con una foto: la ranura de la polea es una aproximación y habrá que corregirla.
"""
