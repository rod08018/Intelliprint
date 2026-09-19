# config

Configuración. Cambiar cualquier cosa de aquí **no debe requerir tocar código**.

| Archivo | Contenido |
|---|---|
| `models.yaml` | Perfiles de modelos (`prod` / `dev`), asignación por agente y política de escalamiento (§ 6) |
| `printers/*.yaml` | Perfil por impresora **y material**: holguras, agujeros, paredes, cama (§ 7). Sirve para **diseñar** |
| `slicing/*.ini` | Perfil de **laminado** de PrusaSlicer (F1.12). Sirve para **imprimir**. Son dos archivos distintos para dos cosas distintas |
| `agents/*.md` | Prompt de sistema de cada agente |

## Sobre los perfiles de impresora

Las holguras **no son transferibles** entre impresoras ni entre materiales. Cada perfil nace con `calibrated: false` y valores por defecto para boquilla de 0.4 mm; se corrige imprimiendo la pieza de calibración (F2.18) e introduciendo las medidas reales.

Un perfil sin calibrar produce diseños dimensionalmente correctos que encajan mal en la práctica. Es la diferencia entre "el modelo está bien" y "la pieza entra".

## Sobre `models.yaml`

Los agentes referencian **roles** (`$design`, `$qa`), nunca modelos concretos. Cambiar de modelo o de máquina es cambiar un perfil, no editar once entradas.

## Sobre `slicing/ankermake_m5_petg.ini`

Derivado del perfil comunitario [AnkerMake CE](https://github.com/Ankermgmt/prusaslicer-ankermake-ce-profiles) (AGPL-3.0, que este archivo hereda). La cabecera dice de qué commit y qué presets salió.

**Su G-code de inicio no está verificado en la impresora.** Viene de la comunidad, no de AnkerMake Studio ni de una prueba real. Lo que hace es: activar la aceleración en curva S de la M5 (`M4899 T3`), templar la boquilla a 150 °C para que no gotee, calentar la cama a 80 °C, subir la boquilla a 240 °C, y hacer home. No hay línea de purga: la cebadura la hacen las dos vueltas de falda (`skirts = 2`).
