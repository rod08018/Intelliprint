# Intelliprint

Sistema multiagente local para diseñar piezas y mecanismos imprimibles en 3D usando FreeCAD y PrusaSlicer vía MCP.

En el canal humano el sistema se llama **Crafty**: es la cara visible del orquestador, que por dentro coordina once agentes.

Todo corre en contenedores menos PrusaSlicer, que se queda en tu PC porque es
donde miras **qué vas a imprimir** antes de mandarlo a la máquina (ADR-014).

```bash
docker compose up -d web            # la interfaz:  http://localhost:8080
docker compose up -d crafty         # Crafty en Telegram
docker compose run --rm suite       # la suite, donde dice la verdad
docker compose run --rm orchestrator mecanismo peticion.md --archivo
```

Y en el PC, para que el contenedor pueda usar tu PrusaSlicer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1
```

Antes de nada: `cp .env.example .env` y rellenarlo. Sin `TELEGRAM_ALLOWED_USERS`
el canal no arranca, a propósito (F5.10 (lista)).

- [Arquitectura del sistema multiagente](SISTEMA_MULTIAGENTE.md) — qué es el sistema y cómo funciona
- [Plan del proyecto](PLAN_PROYECTO.md) — fases, tareas y criterios de aceptación
- [Registro de decisiones](DECISIONES.md) — por qué el sistema es así y qué se descartó
