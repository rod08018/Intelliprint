# config

Configuración. Cambiar cualquier cosa de aquí **no debe requerir tocar código**.

| Archivo | Contenido |
|---|---|
| `models.yaml` | Perfiles de modelos (`prod` / `dev`), asignación por agente y política de escalamiento (§ 6) |
| `printers/*.yaml` | Perfil por impresora **y material**: holguras, agujeros, paredes, cama (§ 7) |
| `agents/*.md` | Prompt de sistema de cada agente |

## Sobre los perfiles de impresora

Las holguras **no son transferibles** entre impresoras ni entre materiales. Cada perfil nace con `calibrated: false` y valores por defecto para boquilla de 0.4 mm; se corrige imprimiendo la pieza de calibración (F2.18) e introduciendo las medidas reales.

Un perfil sin calibrar produce diseños dimensionalmente correctos que encajan mal en la práctica. Es la diferencia entre "el modelo está bien" y "la pieza entra".

## Sobre `models.yaml`

Los agentes referencian **roles** (`$design`, `$qa`), nunca modelos concretos. Cambiar de modelo o de máquina es cambiar un perfil, no editar once entradas.
