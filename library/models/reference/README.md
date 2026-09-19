# Modelos de referencia independientes

Modelos de hardware comercial **dibujados por otras personas** a partir del objeto real. Sirven para comprobar las piezas que diseña Intelliprint **sin circularidad**: si el sistema dibujara también la referencia con sus propios números, que encajaran no probaría nada.

Los `.step` son los originales, sin modificar. Los `.FCStd` se generan a partir de ellos con `mech_toolkit.library_models.import_reference`, porque *Insert Component* de FreeCAD no acepta STEP.

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
