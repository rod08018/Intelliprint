# Intelliprint

Sistema multiagente local para diseñar piezas y mecanismos imprimibles en 3D usando FreeCAD y PrusaSlicer vía MCP.

En el canal humano el sistema se llama **Crafty**: es la cara visible del orquestador, que por dentro coordina once agentes.

```bash
.venv/bin/python scripts/demo.py "un soporte para NEMA17, placa de 60x60x6 con taladro central de 22"
```

Esa demo recorre lo que ya funciona: admisión con confirmación, diseño por receta y construcción real en FreeCAD. Todavía no lamina, no pasa QA y no habla por Telegram — ver el plan.

- [Arquitectura del sistema multiagente](SISTEMA_MULTIAGENTE.md) — qué es el sistema y cómo funciona
- [Plan del proyecto](PLAN_PROYECTO.md) — fases, tareas y criterios de aceptación
- [Registro de decisiones](DECISIONES.md) — por qué el sistema es así y qué se descartó
