# tests

Ver [PLAN_PROYECTO.md](../PLAN_PROYECTO.md) § 6.

| Nivel | Qué prueba |
|---|---|
| Unitario | Esquemas, `apply_fit`, generadores, `validate_macro`, router |
| Herramientas | Chequeos DFM sobre STL con defectos conocidos (`fixtures/stl/`) |
| Integración | Orquestador ↔ MCP de FreeCAD/PrusaSlicer (requiere host con FreeCAD abierto) |
| Agentes | Salida válida y correcta sobre casos fijos, con semilla y temperatura bajas |
| **Adversarial** | Que las garantías sean estructurales y no dependan del buen comportamiento del modelo |
| Extremo a extremo | Proyectos de referencia completos |

## Las dos pruebas adversariales

Son las más importantes del repositorio, porque verifican las dos afirmaciones fuertes de la arquitectura:

- **F2.15** — Con un QA Agent simulado que responde siempre "aprobado", una pieza con una cota fuera de tolerancia **debe seguir dando FAIL**. Si esta prueba pasa a verde por las razones equivocadas, la regla dura de § 7.1 se ha roto.
- **F5.9** — Un mensaje entrante de Telegram con instrucciones embebidas **no debe ejecutar nada**, y ninguna ruta del host debe salir por el canal.

**Regla:** las herramientas deterministas deben tener tests antes de que un agente las use.

## Suite rápida y suite de verificación (F1.17)

```bash
pytest                     # rápida: sin abrir FreeCAD con interfaz ni llamar a modelos
pytest -m "gui or llm"     # verificación en el punto de uso
```

La suite rápida lee archivos y representaciones intermedias. **Eso no basta**: el `.FCStd` que se abría vacío pasaba todos los tests porque estos leían el zip, no lo que ve el usuario. La de verificación mira donde lo experimenta él:

| Marcador | Qué hace | Coste |
|---|---|---|
| `gui` | Abre la pieza en la **interfaz real** de FreeCAD y pregunta qué se ve | Abre una ventana unos segundos |
| `llm` | `intelliprint new` de extremo a extremo con el modelo real, aislado con `INTELLIPRINT_WORKSPACE` | Unos céntimos de DeepSeek |

**Regla:** antes de dar por cerrada una tarea que toque FreeCAD, el laminado o un agente, se ejecuta `pytest -m "gui or llm"`.

`test_start_gcode.py` es una instantánea: **no prueba que el G-code de inicio sea correcto, prueba que no cambia sin que nadie lo mire**. Su cabecera dice si está verificado en la impresora real.
