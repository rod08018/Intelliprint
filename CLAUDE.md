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

El sistema vive en contenedores (ADR-014). La suite se corre **ahí**: nativa en
Windows caen 9 tests que no son del código, sino de que `/bin/sh` y los procesos
zombi no existen igual.

```bash
docker compose run --rm suite                       # la suite rápida
docker compose run --rm orchestrator mecanismo peticion.md --archivo
docker compose run --rm orchestrator animar <carpeta-del-proyecto>
docker compose up -d web                            # http://localhost:8080
docker compose up -d crafty                         # Telegram
```

En el PC, para que el contenedor pueda laminar en tu PrusaSlicer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1
```

Los tests `gui` abren ventanas de FreeCAD y **solo pueden correr en el host**,
igual que los que laminan de verdad; los `llm` cuestan dinero. Hay que pasarlos
antes de cerrar una tarea que toque FreeCAD, el laminado o un agente:

```powershell
$env:FREECADCMD = "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
$env:PRUSASLICER = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
$env:PYTHONUTF8 = "1"
.venv\Scripts\python.exe -m pytest -m "gui or llm" -q
```

**En Windows hace falta `PYTHONUTF8=1`.** Sin él, Python lee los archivos como
cp1252 y cualquier acento del repo revienta: son 10 tests de diferencia.

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

**2026-09-20: el sistema se mudó a la PC de la RTX 5090 y entró en contenedores.**

- **FreeCAD dentro, PrusaSlicer fuera** (ADR-014). FreeCAD es una herramienta
  interna —construye y calla—; PrusaSlicer es donde la persona mira qué va a
  imprimir, así que sigue siendo el suyo y el contenedor se lo pide por un
  puente MCP en el host (`scripts/host_bridge.py`).
- **La interfaz web** (F5.5 (web), parcial): lista de proyectos, descarga en zip
  y un botón que abre PrusaSlicer con las piezas y el perfil cargados.
- **El canal ya no nace abierto**: ADR-012 saldada con F5.10 (lista).
  `TELEGRAM_ALLOWED_USERS` cierra el bot propio y a Crafty con la misma lista.
- **Crafty vive en su contenedor**, con la configuración generada desde el `.env`
  y ningún secreto en `openclaw.json`.

Antes de eso, lo último había sido endurecer el diseño de mecanismos para que el
ensamble **demuestre** que funciona en vez de declararlo: apoyos por contacto
(`rest_on`), bloqueos comprobados forzando la articulación, y la regla de que no
se puede declarar que algo frena a una pieza cuyo movimiento impones con una
fórmula. **Esa regla sigue sin ejercitarse en una ejecución real.**

### Lo que quedó pendiente

0. **Comprobar los modelos de DeepSeek antes que nada.** La documentación de
   DeepSeek ya solo lista `deepseek-flash` y `deepseek-v4-pro`, y
   `config/models.yaml` usa `deepseek-chat` y `deepseek-reasoner`. Si están
   retirados, el perfil `dev` entero está muerto y no hay agente que funcione.
   Se resuelve con una llamada en cuanto haya clave.
1. **Relanzar el trinquete** (`tests/e2e/retos/2_trinquete.md`) y comprobar que la
   rueda avanza por contacto. Es lo último del diagnóstico sin probar de verdad.
2. **Relanzar el mecanismo de Ginebra**: murió porque el razonador agotó
   `max_tokens` tres veces. La reserva existe (tras dos cortes contesta el modelo
   sin pensamiento), pero **nadie la ha visto entrar en una ejecución real**.
3. **Decidir el tope de gasto.** Los 2 USD de `max_usd_per_project` los puse yo
   por defecto en el primer commit; el usuario preguntó quién decidió ese valor y
   no se eligió otro.
4. **Los demás retos** (leva, gato de tijera, prensa) no se han relanzado con el
   conjunto completo de mejoras.
5. **F0.11 (migrar) es la deuda mayor que queda.** La 5090 está aquí y Ollama
   corre con ella, pero falta el cliente de Ollama y revalidar la suite con
   modelos locales.
6. **Los botones de gate** de la interfaz web, que es lo que cierra F5.5 (web).

Cada proyecto deja su coste desglosado en `design_cost.md`, y si se detiene sin
resolver, un parte en `blocked.md` con la imagen de la pose donde falla.
