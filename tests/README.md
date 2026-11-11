# tests

Ver [PLAN_PROYECTO.md](../PLAN_PROYECTO.md) § 6.

| Qué hay | Qué prueba |
|---|---|
| `test_*.py` sin FreeCAD | Esquemas, router de modelos, salida estructurada, plan mecánico, requisitos, fichas, registro, trabajos, web y servidor MCP, con modelos de guion en vez de llamadas reales |
| `test_*.py` con `freecadcmd` | El kit, las sondas, la construcción de piezas, el ensamble y el barrido de choques sobre geometría de verdad. Se saltan si no hay `freecadcmd` |
| `test_plan_references.py` | Que cada ID de tarea citado en el código y en los documentos exista en el plan y apunte a la tarea correcta |
| `banco/encargos/` | Los doce encargos del banco (diez piezas y dos backlogs), cada uno con lo esperado escrito a mano. No los corre la suite: los corre `intelliprint banco`, que cuesta dinero |
| `kit_regresiones/`, `acabado_regresiones/`, `sondas_regresiones/` | Programas y piezas que fallaron de verdad, guardados para que no vuelvan a fallar |
| `snapshots/` | Instantáneas del G-code de inicio |

**Reglas:** el test primero, y visto fallar. El valor esperado sale de un oráculo independiente —una referencia descargada, un cálculo a mano, la petición literal—, nunca de la salida del propio sistema.

No hay prueba de inyección por el canal de Telegram: la pide F5.9 (seguridad) y no está escrita.

## Suite rápida y suite de verificación (F1.17)

La suite rápida se corre **en el contenedor**; nativa en Windows caen tests que no son del código, sino del sistema operativo.

```bash
docker compose run --rm suite     # rápida: sin interfaz de FreeCAD ni modelos reales
```

La suite rápida lee archivos y representaciones intermedias. **Eso no basta**: el `.FCStd` que se abría vacío pasaba todos los tests porque estos leían el zip, no lo que ve el usuario. La de verificación mira donde lo experimenta él, y solo puede correr en el host:

| Marcador | Qué hace | Coste |
|---|---|---|
| `gui` | Abre la pieza en la **interfaz real** de FreeCAD y pregunta qué se ve | Abre una ventana unos segundos |
| `llm` | Llama a servicios de verdad: `intelliprint pieza` de extremo a extremo (aislado con `INTELLIPRINT_WORKSPACE`), el plan del pan-tilt con DeepSeek y el juez JEV | Unos céntimos de DeepSeek |

```powershell
$env:FREECADCMD = "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
$env:FREECAD_GUI = "C:\Program Files\FreeCAD 1.1\bin\freecad.exe"
$env:PRUSASLICER = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
$env:PYTHONUTF8 = "1"
.venv\Scripts\python.exe -m pytest -m "gui or llm" -q
```

Sin `FREECAD_GUI` los tests `gui` se saltan en silencio y el código de salida es 0 sin haberlos corrido. Los que laminan de verdad se saltan si no encuentran PrusaSlicer, así que dentro del contenedor no corren.

**Regla:** antes de dar por cerrada una tarea que toque FreeCAD, el laminado o un agente, se ejecuta `pytest -m "gui or llm"`.

`test_start_gcode.py` es una instantánea: **no prueba que el G-code de inicio sea correcto, prueba que no cambia sin que nadie lo mire**. Su cabecera dice si está verificado en la impresora real.
