# Intelliprint

Sistema multiagente que diseña piezas imprimibles en 3D —sueltas, o las de un
robot, una a una—, las monta en FreeCAD y **verifica que funcionan** antes de
que nadie imprima nada.

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
  Lo cambia el usuario midiendo: lo apunta en la página «Impresora» de la web
  (F2.21 (impresora)), se guarda en `workspace/impresoras/` y manda sobre
  `config/printers/`, que no se toca. La impresora la configura él.

## Órdenes

El sistema vive en contenedores (ADR-014). La suite se corre **ahí**: nativa en
Windows caen 9 tests que no son del código, sino de que `/bin/sh` y los procesos
zombi no existen igual.

```bash
docker compose run --rm suite                       # la suite rápida
docker compose run --rm orchestrator pieza peticion.md --archivo
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
$env:FREECAD_GUI = "C:\Program Files\FreeCAD 1.1\bin\freecad.exe"
$env:PRUSASLICER = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
$env:PYTHONUTF8 = "1"
.venv\Scripts\python.exe -m pytest -m "gui or llm" -q
```

**Sin `FREECAD_GUI` los dos tests `gui` se saltan en silencio** (buscan el
FreeCAD de Mac por defecto): el código de salida sale 0 sin haberlos corrido.

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

**2026-11-10: Fase 9, robots con plan mecánico (ADR-020).** El usuario quiere
diseñar robots: que el desglose decida antes de dibujar qué gira sobre qué y con
cuánto sitio, qué va atornillado y con qué, y poder añadir funciones a un
invento. El plan aprobado está en `PLAN_PROYECTO.md`, Fase 9, con su orden.

- **El pan-tilt pasa sus cinco comprobaciones** (2026-11-11, corrida
  `1111-1342`, a la primera, 45 min y 0,53 USD). El de `1110-0313` chocaba
  porque el soporte dejaba 12.7 mm entre el eje de inclinación y el servo de
  abajo; ahora el plan reserva el sitio de cada giro y cada pieza lo mide en su
  propio bucle (F9.1 a F9.5). **Es una sola corrida**, y su plataforma es un
  disco coaxial con el eje, que el banco no sabe ver que no sirve para
  inclinar una cámara: está escrito en la Fase 9 del plan.
- **Los backlogs están desaparcados**, con la regla de siempre: no relanzar
  corridas enteras para probar un arreglo (`banco --reanudar`).
- **El flujo `mecanismo` ya no existe** (F9.13 (limpieza), 2026-11-11): lo
  decidió él para cuando el pan-tilt subiera. Con él se fueron `new`/`resume`
  (LangGraph), el bot propio y el QA de interfaces, que no llamaba nadie.
  Todo está en git, en la etiqueta `antes-de-fase-9`. Los mecanismos ya hechos
  se siguen viendo en la web. **Lo que se perdió:** engranajes y cadenas
  cerradas; un backlog solo sabe piezas que giran sobre un servo o un
  rodamiento, en árbol.
- **El tope de 5 USD ahora sí para.** Solo lo comprobaba el flujo de
  mecanismos; una pieza o un backlog nunca se detenían. Cada paso lo mira
  antes de empezar (`cli._apuntar_gasto`).
- **El banco se corre con el código de hoy desde el servicio `suite`**, que lo
  monta en vivo; `orchestrator` y `web` llevan el de su imagen hasta
  reconstruirla (`docker compose build`):
  `docker compose run --rm --entrypoint python3 suite -m orchestrator.cli banco --solo pan_tilt_sg90`
  (en Git Bash, con `MSYS_NO_PATHCONV=1` si se pasa una ruta `/workspace/...`).
  El puente de PrusaSlicer tiene que estar arriba o «sin soportes» sale sin medir.
- **Decidido por él:** el agarre de cada tornillo lo propone el plan en cada
  unión; un componente sin ficha entra como borrador que él aprueba viendo la
  huella; `AGENTS.md` se borra.

**2026-09-20: el sistema se mudó a la PC de la RTX 5090 y entró en contenedores.**

- **FreeCAD dentro, PrusaSlicer fuera** (ADR-014). FreeCAD es una herramienta
  interna —construye y calla—; PrusaSlicer es donde la persona mira qué va a
  imprimir, así que sigue siendo el suyo y el contenedor se lo pide por un
  puente MCP en el host (`scripts/host_bridge.py`).
- **La interfaz web** (F5.5 (web), parcial): lista de proyectos, descarga en zip
  y un botón que abre PrusaSlicer con las piezas y el perfil cargados.
- **El canal de Telegram va ABIERTO, por decisión del usuario** (ADR-012). La
  lista blanca de F5.10 (lista) existe pero es opcional: se había hecho
  obligatoria sin que él lo aprobara, y la quitó.
- **Crafty vive en su contenedor**, con la configuración generada desde el `.env`
  y ningún secreto en `openclaw.json`.

### Lo que quedó pendiente

0. ✅ **Los modelos de DeepSeek funcionan** (comprobado llamándolos el
   2026-10-23). `deepseek-chat` y `deepseek-reasoner` son alias que DeepSeek
   sirve con `deepseek-flash` (sin y con pensamiento), y ya se cobran como
   Flash: está explicado en `config/models.yaml`, junto a los precios.
1. ~~El trinquete, la Ginebra y los demás retos de mecanismos.~~ El flujo
   que los hacía se quitó el 2026-11-11 (arriba). El trinquete salió
   (2026-09-21, 1.17 USD) y sigue en `workspace/`.
3. ~~Decidir el tope de gasto.~~ **Decidido por el usuario: 5 USD por proyecto**
   (2026-09-21). Los 2 USD anteriores los había puesto el asistente por defecto.
5. **F0.11 (migrar) es la deuda mayor que queda.** La 5090 está aquí, Ollama
   corre con ella y los dos modelos del perfil `prod` están descargados
   (`qwen3.8` y `gemma3:12b`, comprobado al 100% en GPU). Falta el cliente de
   Ollama y revalidar la suite con modelos locales.

   **Y algo que hay que decidir antes:** el contenedor `ollama` de esta máquina
   no es del compose de Intelliprint —es uno anterior, de otro proyecto— y trae
   `OLLAMA_MAX_LOADED_MODELS=1`. Con ese valor los dos modelos NO conviven:
   cargar el del QA descarga el de diseño, y cada turno que alterne paga una
   recarga de 17 GB. § 6.1 pide dos residentes. Caben (17 + 8.9 GB en 32), pero
   subirlo a 2 obliga a recrear ese contenedor, que es de otro proyecto. Las dos
   salidas: cambiarlo allí, o levantar el servicio `ollama` del compose
   (`docker compose --profile ollama up -d ollama`), que ya lo trae en 2 a costa
   de una segunda copia de los modelos.
6. **Los botones de gate** de la interfaz web, que es lo que cierra F5.5 (web).
7. **Kits para montar** (Fase 8, ADR-019): el usuario diseña kits de
   robótica infantil, **los imprime en sus impresoras** y el cliente los
   monta; la programación va después. La impresora la configura y calibra
   él. Se empieza por F8.1 (cliente): las preguntas abiertas de la ADR las
   decide el usuario, no el asistente. Requiere antes el pan-tilt de
   F7.3 (arbol) hecho con DeepSeek.

Cada proyecto deja su coste desglosado en `design_cost.md`, y si se detiene sin
resolver, un parte en `blocked.md` con la imagen de la pose donde falla.
