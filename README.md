# Intelliprint

Sistema que diseña piezas imprimibles en 3D —sueltas, o las de un robot o conjunto— con modelos de lenguaje, las construye en FreeCAD y **mide que funcionan** antes de que nadie imprima nada.

Cinco agentes deciden (qué medidas faltan, los requisitos, el concepto, el dibujo de cada pieza y el plan de un conjunto) y el código comprueba y mide lo que sale. Hoy los modelos son de DeepSeek, en la nube; pasar a modelos locales es deuda declarada, F0.11 (migrar).

Se usa desde la **web** o desde Telegram, donde atiende **Crafty**: un agente de OpenClaw que conversa y lanza los encargos, y que no diseña.

Todo corre en contenedores menos PrusaSlicer, que se queda en tu PC porque es
donde miras **qué vas a imprimir** antes de mandarlo a la máquina (ADR-014).

```bash
docker compose up -d web            # la interfaz:  http://localhost:8080
docker compose up -d crafty         # Crafty en Telegram
docker compose run --rm suite       # la suite, donde dice la verdad
docker compose run --rm orchestrator pieza peticion.md --archivo   # una pieza
docker compose run --rm orchestrator obra peticion.md --archivo    # varias: un backlog
```

Y en el PC, para que el contenedor pueda usar tu PrusaSlicer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1
```

Antes de nada: `cp .env.example .env` y rellenarlo. El canal de Telegram va
abierto; `TELEGRAM_ALLOWED_USERS` es opcional (F5.10 (lista)).

- [Cómo es el sistema hoy](SISTEMA_MULTIAGENTE.md) — los flujos, los agentes, qué se mide y dónde corre
- [Plan del proyecto](PLAN_PROYECTO.md) — fases, tareas, criterios de aceptación y deuda técnica
- [Registro de decisiones](DECISIONES.md) — por qué el sistema es así y qué se descartó
