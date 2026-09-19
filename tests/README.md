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

- **F2.12** — Con un QA Agent simulado que responde siempre "aprobado", una pieza con una cota fuera de tolerancia **debe seguir dando FAIL**. Si esta prueba pasa a verde por las razones equivocadas, la regla dura de § 7.1 se ha roto.
- **F5.7** — Un mensaje entrante de Telegram con instrucciones embebidas **no debe ejecutar nada**, y ninguna ruta del host debe salir por el canal.

**Regla:** las herramientas deterministas deben tener tests antes de que un agente las use.
