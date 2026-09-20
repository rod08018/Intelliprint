# Intelliprint

Sistema multiagente que diseña piezas y mecanismos imprimibles en 3D, los monta
en FreeCAD y **verifica que funcionan** antes de que nadie imprima nada.

## Cómo se trabaja aquí

- **Todo en español**: la conversación, los comentarios, los docstrings, los
  nombres de los tests y los mensajes de commit.
- **El test primero, y visto fallar.** Un test que nunca se vio en rojo no
  prueba nada. El valor esperado viene de un oráculo independiente —una
  referencia descargada, un cálculo a mano, la petición literal—, nunca de la
  salida del propio sistema.
- **Los comentarios explican el porqué, no el qué.** Cuando un arreglo viene de
  un fallo real, el comentario dice cuál fue: eso es lo que impide que alguien
  lo «simplifique» de vuelta.
- **Commit y push a `main` directamente**, sin preguntar, cuando la suite esté
  en verde. Mensaje en español explicando el porqué, y al final:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Verificar antes de afirmar.** `pytest … | tail` esconde el código de salida;
  hay que mirarlo. Ya se commiteó una vez con dos tests rojos por eso.

## Reglas que no se rompen

- **Nunca borrar `workspace/`.** Es el trabajo del usuario. Para pruebas, usar
  `INTELLIPRINT_WORKSPACE` apuntando a una carpeta temporal.
- **Nunca imprimir ni commitear `.env`.** Lleva la clave de DeepSeek y el token
  del bot. Antes de cada commit, comprobar que no está en el índice.
- **Archivar no es borrar.** Un intento fallido es la única prueba de por qué
  algo no funcionó.
- **No tocar `M3_through_mm: 3.3`** sin la impresora delante: cambiarlo a ciegas
  es sustituir un valor sin validar por otro igual de sin validar (deuda F2.18).

## Órdenes

```bash
.venv/bin/python -m pytest -q                      # suite rápida (la que corre siempre)
.venv/bin/python -m pytest -m "gui or llm" -q      # abre FreeCAD de verdad / gasta modelo
.venv/bin/python -m orchestrator.cli mecanismo <peticion.md> --archivo
.venv/bin/python -m orchestrator.cli animar <carpeta-del-proyecto>
```

Los tests `gui` abren ventanas de FreeCAD y los `llm` cuestan dinero: fuera de
la suite rápida, pero hay que pasarlos antes de cerrar una tarea que toque
FreeCAD, el laminado o un agente.

## Dónde está escrito qué

| Archivo | Qué contiene |
|---|---|
| `PLAN_PROYECTO.md` | Las tareas con su ID (`F3.15`), el criterio de aceptación y **la tabla de deuda técnica declarada** |
| `DECISIONES.md` | Las ADR: por qué el sistema es como es, con sus enmiendas cuando la realidad las corrigió |
| `SISTEMA_MULTIAGENTE.md` | La arquitectura y los once agentes |
| `config/agents/*.md` | El prompt de sistema de cada agente |
| `config/openclaw/` | Crafty, el agente del canal humano (Telegram) |

Al citar un ID en el código va con su palabra clave —`F3.15 (mecanismos)`— y un
test lo comprueba: si la cita no cuadra con el plan, la suite se pone roja.

## Por dónde iba esto

Lo último fue endurecer el diseño de mecanismos para que el ensamble **demuestre**
que funciona en vez de declararlo:

- Las piezas empujadas se mueven por contacto (`rest_on`), y con `carry` recuerdan
  dónde quedaron. El valor lo busca la geometría real en FreeCAD.
- Los bloqueos (`blocks`) se comprueban forzando la articulación: si no se
  atravesarían, el bloqueo es mentira.
- **No se puede declarar que algo impide moverse a una pieza cuyo movimiento
  impones tú con una fórmula.** Esta regla es nueva y **todavía no se ha
  ejercitado en una ejecución real**: el trinquete hay que relanzarlo para que
  el agente se vea obligado a mover la rueda por contacto.

### Lo que quedó pendiente

1. **Relanzar el trinquete** (`tests/e2e/retos/2_trinquete.md`) y comprobar que la
   rueda avanza por contacto. Es lo último del diagnóstico sin probar de verdad.
2. **Relanzar el mecanismo de Ginebra**: murió porque deepseek-reasoner agotó
   `max_tokens` tres veces. Ahora existe la reserva (tras dos cortes contesta el
   modelo sin pensamiento), pero **nadie la ha visto entrar en una ejecución real**.
3. **Decidir el tope de gasto.** Los 2 USD de `max_usd_per_project` los puse yo
   por defecto en el primer commit; el usuario preguntó quién decidió ese valor y
   no se eligió otro.
4. **Los demás retos** (leva, gato de tijera, prensa) no se han relanzado con el
   conjunto completo de mejoras.

Cada proyecto deja su coste desglosado en `design_cost.md`, y si se detiene sin
resolver, un parte en `blocked.md` con la imagen de la pose donde falla.
