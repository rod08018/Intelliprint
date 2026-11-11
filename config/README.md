# config

Configuración. Cambiar cualquier cosa de aquí **no debe requerir tocar código**. Dentro del contenedor esta carpeta está montada en solo lectura. Las secciones (§) que se citan son de [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md).

| Archivo | Contenido |
|---|---|
| `models.yaml` | Perfiles de modelos (`dev` / `prod`), precios y tope de gasto (§ 6) |
| `impresion.yaml` | El perfil activo: con qué impresora y material se diseña y con qué perfil se lamina. Es el único sitio donde se elige |
| `printers/*.yaml` | Perfil por impresora **y material**: holguras, agujeros por métrica, paredes, cama, resistencia (§ 7). Sirve para **diseñar** |
| `slicing/*.ini` | Perfil de **laminado** de PrusaSlicer, F1.12 (laminado). Sirve para **imprimir**. Son dos archivos distintos para dos cosas distintas |
| `slicing/usos.yaml` | Ajustes de laminado por uso de la pieza (general, estructural, estética, prototipo) |
| `slicing/claves_prusaslicer.txt`, `slicing/origen/` | Lo que usa `intelliprint perfil importar`: las claves que PrusaSlicer entiende y el paquete original de eufyMake Studio |
| `categorias.yaml` | Las categorías con las que se ordenan los proyectos en la web |
| `agents/*.md` | Las instrucciones de cada agente: `requirements`, `investigador`, `ingeniero`, `disenador_kit` y `desglosador` |
| `openclaw/*.md` | Instrucciones de Crafty, el agente del canal de Telegram, y cómo levantarlo. En Docker se copian a su contenedor en cada arranque |

## Sobre los perfiles de impresora

Las holguras **no son transferibles** entre impresoras ni entre materiales. Los perfiles de `printers/` traen `calibrated: false` y valores por defecto para boquilla de 0.4 mm, y **no se editan a mano para calibrar**: el usuario imprime las piezas de `intelliprint calibrar`, F2.18 (calibración), y apunta lo que midió en la página «Impresora» de la web, F2.21 (impresora). Eso se guarda en `workspace/impresoras/` y manda sobre lo de aquí.

Un perfil sin calibrar produce diseños dimensionalmente correctos que encajan mal en la práctica. Es la diferencia entre "el modelo está bien" y "la pieza entra".

## Sobre `models.yaml`

Los agentes piden **roles** (`design`, `reason`), nunca modelos concretos. Cambiar de modelo o de máquina es cambiar un perfil, no editar cada agente. Hoy solo funciona el perfil `dev`, con DeepSeek: el cliente de Ollama que necesita `prod` es F0.11 (migrar), sin hacer.

## Sobre los perfiles de laminado

El activo es `slicing/m5_esun_plamas_precision.ini`, importado de la calibración que el usuario hizo en eufyMake Studio. Su cabecera dice de qué paquete salió y qué claves de eufyMake no entiende PrusaSlicer; **no está verificado con una impresión hecha desde PrusaSlicer**.

`slicing/ankermake_m5_petg.ini` deriva del perfil comunitario [AnkerMake CE](https://github.com/Ankermgmt/prusaslicer-ankermake-ce-profiles) (AGPL-3.0, que este archivo hereda). La cabecera dice de qué commit y qué presets salió. **Su G-code de inicio no está verificado en la impresora**: viene de la comunidad, no de AnkerMake Studio ni de una prueba real. Lo que hace es activar la aceleración en curva S de la M5 (`M4899 T3`), templar la boquilla a 150 °C para que no gotee, calentar la cama y la boquilla a la temperatura de la primera capa y hacer home. No hay línea de purga: la cebadura la hacen las dos vueltas de falda (`skirts = 2`).
