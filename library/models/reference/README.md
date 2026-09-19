# Modelos de referencia independientes

Modelos de hardware comercial **dibujados por otras personas** a partir del objeto real. Sirven para comprobar las piezas que diseña Intelliprint **sin circularidad**: si el sistema dibujara también la referencia con sus propios números, que encajaran no probaría nada.

Los `.step` son los originales, sin modificar: su huella SHA-256, autor, licencia y ruta de origen están en **`manifest.yaml`**, y `tests/test_library_reference.py` falla si un solo byte cambia o si aparece un STEP sin procedencia declarada. Los `.FCStd` se generan a partir de ellos con `mech_toolkit.library_models.import_reference`, porque *Insert Component* de FreeCAD no acepta STEP.

## `nema17_40mm_obijuan`

| | |
|---|---|
| Autor | **obijuan** (Juan González Gómez), 2014-11-30, commit *"NEMA 17 Stepper motor 40mm"* |
| Fuente | [FreeCAD/FreeCAD-library](https://github.com/FreeCAD/FreeCAD-library), `Electronics Parts/Motors/Stepper/NEMA/Old/NEMA-17_Stepper_Motor_40mm.step` |
| Licencia | [CC-BY 3.0](http://creativecommons.org/licenses/by/3.0/) |
| SHA-256 del STEP | `7a192833722ef5216bf7916c97870b6d4677db237143e3275305d5e846cc0521` |
| Descargado | 2026-09-19 |

**Medido en el propio modelo** con el extractor de `mech_toolkit` (no tomado de nuestras cotas):

| Cota | Valor | ¿Normalizada por NEMA 17? |
|---|---|---|
| Cuerpo | 42.3 × 42.3 × 40.1 | Sí (la cara) |
| Saliente de centrado | Ø22.00 × **1.6** | Ø sí; la altura varía por fabricante |
| Eje | Ø5.00 × **20** | Ø sí; el largo varía por fabricante |
| Roscas de la brida | 4 × M3 (taladro Ø2.46, 4.5 de fondo) en cuadro de 31 | Sí |

**El `.FCStd` está en posición de montaje**: desplazado `dz = -40.1` para que su cara frontal quede en z=0, como la de los soportes que genera Intelliprint. Ese 40.1 se midió en el modelo (donde acaban las roscas M3 y empieza el saliente), no se tomó de nuestras cotas. El `.step` conserva el origen original del autor.

## Resto de referencias

Todas de [FreeCAD/FreeCAD-library](https://github.com/FreeCAD/FreeCAD-library), CC-BY 3.0. Detalle en `manifest.yaml`.

| Archivo | Autor | Medido con el extractor |
|---|---|---|
| `bearing_608zz.step` | Normand C (2013) | Agujero Ø8 interior, exterior Ø22, ancho 7. Coincide con lo que usa `derive_assertions` para un asiento de 608 |
| `screw_m3x10_iso4762.step` | Peta-T (2015) | Caña Ø3.0, cabeza Ø5.5 |
| `iso273_m3_close.step` | Tony Hursh (2020) | Agujero pasante M3 ajuste **justo**: Ø3.26 (media de tolerancia) |
| `iso273_m3_normal.step` | Tony Hursh (2020) | Ajuste **normal**: Ø3.49 |
| `iso273_m3_loose.step` | Tony Hursh (2020) | Ajuste **holgado**: Ø3.75 |

**Lo que dicen de nuestro perfil:** el `M3_through_mm: 3.3` de `config/printers/ankermake_m5_petg.yaml` es prácticamente un agujero *justo* de la ISO 273. Y el perfil es incoherente consigo mismo: 3.3 implica una holgura de 0.3 en diámetro, mientras que `fits.clearance_mm: 0.35` pide más. La norma queda del lado del valor mayor. Pendiente de decisión del usuario y, en última instancia, de la pieza de calibración (F2.18).
