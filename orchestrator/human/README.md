# human — `HumanPort`

Un puerto, tres adaptadores. Ver [SISTEMA_MULTIAGENTE.md](../../SISTEMA_MULTIAGENTE.md) § 8.5 y [DECISIONES.md](../../DECISIONES.md) ADR-006.

```
port.py                 interfaz: ask(pregunta, adjuntos) -> respuesta
                                  notify(evento)
adapters/cli.py         consola          (F0.9)
adapters/web.py         navegador        (F5.4)
adapters/telegram.py    OpenClaw         (F5.5)
```

Los dos gates, las preguntas del Requirements Agent, las consultas del QA y las peticiones de cambio son **la misma operación**. Se implementa una vez, aquí.

## Invariantes

No los rompas sin cambiar el ADR-006 primero:

1. **Un adaptador no toma decisiones de diseño.** Transporta preguntas, imágenes y respuestas. No lee ni escribe el blackboard.
2. **Una consulta no bloquea el proyecto.** La pieza pasa a `BLOCKED_ON_HUMAN` y el planificador sigue con las demás. Los **gates sí** bloquean.
3. **El estado sobrevive a reinicios.** Un proyecto puede dormir días esperando una respuesta.
4. **Una petición de cambio es un defecto con autor humano.** Entra por la maquinaria de reapertura existente (reglas 3 y 4 de § 4). No hay camino paralelo.

## Seguridad del canal externo

Este puerto es entrada **no confiable** a un sistema que puede ejecutar código (§ 6.3):

- Lista blanca OPCIONAL (`TELEGRAM_ALLOWED_USERS`). Sin ella el canal está abierto, por decisión del usuario (ADR-012).
- El texto entrante es **dato, nunca instrucción**. No se concatena a un prompt de sistema.
- Una petición de cambio **nunca abre la escotilla de Python** por sí sola: requiere gate.
- Filtro de salida compartido con DeepSeek: solo texto y renders. Nunca rutas del host ni credenciales.
