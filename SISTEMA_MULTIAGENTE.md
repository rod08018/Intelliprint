# Intelliprint — Sistema multiagente de diseño para impresión 3D

Sistema local de agentes que recibe un requerimiento en lenguaje natural (por ejemplo, *"brazo robótico de 6 ejes, alcance 40 cm, carga 500 g"*) y lo convierte en piezas paramétricas en **FreeCAD**, las ensambla, las valida, las lamina en **PrusaSlicer** y entrega STL/3MF listos para imprimir, con aprobación humana en los puntos críticos.

Restricciones de diseño:

- **Local primero.** Todos los agentes corren con modelos locales (Ollama). **DeepSeek** es el único modelo externo permitido y solo se usa como escalamiento, controlado por reglas explícitas.
- **Todo en Docker.** Orquestador, modelos, servicios de cálculo y almacenamiento corren en contenedores. FreeCAD y PrusaSlicer siguen en el PC (sus MCP ya están probados) y se exponen a los contenedores por red.
- **El LLM no hace geometría.** Los modelos deciden parámetros y llaman herramientas deterministas; la geometría, las tolerancias y los cálculos físicos los hace código.
- **El LLM no emite veredictos.** Un PASS/FAIL siempre sale de una comparación numérica contra un contrato. El LLM interpreta y redacta, y solo puede *añadir* defectos, nunca quitarlos.
- **El humano está en el bucle a distancia.** El sistema puede consultarte y enviarte imágenes por Telegram mientras trabaja, y tú puedes pedir cambios sin estar delante del PC.

---

## 1. Vista general

```
 Requerimiento del usuario
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ORQUESTADOR (LangGraph, máquina de estados + blackboard)           │
│                                                                     │
│  FASE 1 · Definición                                                │
│    1. Requirements Agent   → especificación medible (spec.yaml)     │
│    2. Decomposition Agent  → árbol del producto + interfaces        │
│                              SIMBÓLICAS (topología, sin geometría)  │
│                                                                     │
│  FASE 2 · Ingeniería de sistema                                     │
│    3. Kinematics Agent     → eslabones, GDL, rangos, cargas         │
│    4. Actuation Agent      → motores/servos con margen de torque    │
│    5. Electronics Agent    → MCU, drivers, ruteo de cables          │
│    ·  Resolver interfaces  → simbólicas a resueltas (código)        │
│  ── Gate humano #1: aprobar spec, árbol e interfaces resueltas ──   │
│                                                                     │
│  FASE 3 · Diseño por pieza (en paralelo, una tarea por pieza)       │
│    6. Part Designer Agent  → RECETA de generadores → build.py       │
│    7. Tolerances/DFM Agent → holguras FDM, paredes, orientación     │
│    8. QA Agent             → verificación de contrato + visión      │
│                                                                     │
│  FASE 4 · Integración y prueba                                      │
│    9. Assembly Agent       → ensamble, restricciones, interferencias│
│   10. Test/Sim Agent       → cinemática, torque, colisiones         │
│    8. QA Agent             → revisión del ensamble completo         │
│                                                                     │
│  FASE 5 · Fabricación                                               │
│   11. Slicing/Cost Agent   → PrusaSlicer (MCP): gramos, horas, placas│
│  ── Gate humano #2: aprobar diseño y fabricación ──                 │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
  STL / 3MF / G-code + BOM + reporte + instrucciones de ensamble
          │
          ▼
  Feedback de impresión real (opcional) → vuelve a la fase 3
```

---

## 2. Agentes

Cada agente es un nodo del grafo con: un prompt de sistema corto, un **esquema JSON de salida obligatorio**, una lista blanca de herramientas y un modelo asignado. Ningún agente habla con otro directamente; todos leen y escriben en el **blackboard** (sección 5).

| # | Agente | Responsabilidad | Herramientas | Modelo por defecto |
|---|--------|-----------------|--------------|--------------------|
| 0 | **Orchestrator** | Avanza la máquina de estados, lanza tareas, aplica reintentos y escalamiento. Es código, no un LLM; solo usa el LLM para resumir y redactar mensajes al humano. | blackboard, `HumanPort` | `qwen3.8` |
| 1 | **Requirements** | Convierte el texto libre en `spec.yaml`: dimensiones, cargas, alcance, materiales, impresora, presupuesto, restricciones. Pregunta por `HumanPort` si falta algo crítico. | blackboard, `HumanPort` | `qwen3.8` |
| 2 | **Decomposition** | Divide el producto en árbol jerárquico (producto → sistemas → subensambles → piezas). Define **interfaces simbólicas** (tipo, piezas, hardware, `fit`) **sin geometría** y crea una tarea por pieza con dependencias. | blackboard, hardware library | `qwen3.8` → **DeepSeek** si el árbol supera ~15 piezas o falla validación |
| 3 | **Kinematics** | Longitudes de eslabones, GDL, rangos articulares, espacio de trabajo, cargas por articulación. Aporta los `frame` que resuelven las interfaces. | `sim` MCP (ikpy, numpy) | `qwen3.8` |
| 4 | **Actuation** | Selecciona actuadores de la librería con margen de torque ≥ 1.5×, reductoras, alimentación. Fija el hardware definitivo de las interfaces. | `sim` MCP, hardware library | `qwen3.8` |
| 5 | **Electronics** | MCU (ESP32/Arduino), drivers, fuente, canales de cable, soportes de PCB. Produce requisitos que se vuelven piezas o features. | hardware library | `qwen3.8` |
| — | *Resolución de interfaces* | **Código, no agente.** Toma las interfaces simbólicas y los resultados de la Fase 2 y produce `frame` y `nominal_mm` definitivos. Falla ruidosamente si algo queda sin resolver. | `mech-toolkit` MCP | — |
| 6 | **Part Designer** | Diseña **una** pieza. **No escribe Python**: emite una **receta** (lista validada de llamadas a generadores con sus parámetros). `build.py` lo compone el orquestador desde la receta. Varias instancias en paralelo. | `mech-toolkit` MCP, hardware library | `qwen3.8` → **DeepSeek** solo en la escotilla (ver § 6.3) |
| 7 | **Tolerances / DFM** | Aplica holguras FDM, verifica paredes, voladizos, puentes, orientación de impresión y separación de piezas que no caben en la cama. | `mech-toolkit` MCP, `freecad` MCP | `qwen3.8` |
| 8 | **QA** | Revisor independiente. **No emite el veredicto**: ejecuta mediciones, las compara con las aserciones derivadas del contrato, y añade defectos que las cifras no capturan usando **visión** sobre las vistas renderizadas. Solo puede añadir defectos. | `freecad` MCP (solo lectura), `mech-toolkit` MCP | `gemma3:12b` (residente, con visión) |
| 9 | **Assembly** | Importa las piezas, las posiciona según las interfaces resueltas, añade hardware comercial, detecta interferencias y genera la BOM. | `freecad` MCP (GUI), `mech-toolkit` MCP | `qwen3.8` |
| 10 | **Test / Sim** | Pruebas del ensamble: barrido de rangos articulares con chequeo de colisiones, torque en la peor pose, estabilidad (PyBullet), verificación de alcance. | `sim` MCP (PyBullet, ikpy) | `qwen3.8` |
| 11 | **Slicing / Cost** | Lamina cada STL en PrusaSlicer con el perfil de la impresora, agrupa en placas, reporta gramos, horas, costo y soportes. | `prusaslicer` MCP | `qwen3.8` |

> **OpenClaw / Telegram no es un agente.** Es un *adaptador* del `HumanPort` (§ 8.5), fuera del grafo. No lee ni escribe el blackboard: solo transporta preguntas, imágenes y respuestas.

### 2.1 Por qué estos agentes adicionales

- **Decomposition Agent**: sin él, el modelo intenta diseñar "el brazo" de golpe y falla. Con él, cada Part Designer recibe una tarea pequeña y cerrada ("base giratoria, Ø120 mm, aloja un 608zz y un NEMA17, 4×M3 hacia la pieza `hombro`"). Es el agente que más valor aporta.
- **QA Agent** separado del diseñador: el mismo modelo que diseñó una pieza tiende a aprobarla. La defensa principal **no** es usar otro modelo — es que el veredicto sea aritmético (§ 7.1). Usar `gemma3:12b` es una segunda red, barata porque cabe residente junto al modelo de diseño.
- **Assembly + Test/Sim**: permiten el ciclo que pediste: piezas individuales → ensamble → prueba → corrección de las piezas que fallan.

---

## 3. Contratos entre piezas (interfaces)

La clave para que piezas diseñadas por separado encajen es que las interfaces se definan **antes** de diseñar, y que todas las piezas las referencien por ID.

Una interfaz tiene **dos estados**. Esto no es un detalle de implementación: es la corrección de un error de orden. `Decomposition` corre antes que `Kinematics` y `Actuation`, así que **no puede conocer la geometría**: no sabe cuánto mide un eslabón que aún no se ha calculado, ni qué motor se va a elegir. Pedirle números en la Fase 1 es pedirle que invente.

### 3.1 Interfaz simbólica (salida de `Decomposition`, Fase 1)

Declara **topología**: qué se une con qué, con qué clase de hardware y con qué tipo de ajuste. Sin una sola cota.

```yaml
# projects/<id>/interfaces.yaml   (state: symbolic)
- id: IF-003
  state: symbolic
  type: bearing_seat          # bearing_seat | shaft | bolt_pattern | press_fit | slide_fit | snap_fit | cable_pass
  between: [base_giratoria, hombro]
  hardware_class: bearing     # clase, no pieza concreta
  fit: press                  # press | clearance | slide
  role: eje_de_giro_j1        # para qué sirve; lo usa la Fase 2 para resolverla
```

### 3.2 Interfaz resuelta (salida de la Fase 2, por código)

`Kinematics` aporta los `frame`, `Actuation` fija el hardware concreto, y el resolvedor rellena las cotas desde la hardware library. **Ningún LLM escribe estos números.**

```yaml
- id: IF-003
  state: resolved
  type: bearing_seat
  between: [base_giratoria, hombro]
  hardware: bearing_608zz     # ya es una pieza concreta de library/
  fit: press
  nominal_mm: {bore: 8, od: 22, width: 7}
  frame: {origin: [0, 0, 45], axis: [0, 0, 1]}   # de Kinematics, no inventado
  resolved_by: kinematics+actuation
```

El validador rechaza que una interfaz `symbolic` llegue a la Fase 3. El Tolerances Agent traduce `fit` a holguras reales (§ 7) y el Assembly Agent usa `frame` para posicionar piezas.

### 3.3 Las interfaces generan el QA

Una interfaz resuelta contiene todo lo necesario para escribir sus propias pruebas. `mech-toolkit` deriva de ella las **aserciones medibles**, sin intervención de ningún modelo:

```yaml
# derivado automáticamente de IF-003 (press fit → +0.10 mm, § 7)
- assert: hole_diameter
  at: IF-003.frame
  expected_mm: 22.10
  tol_mm: 0.05
- assert: hole_depth
  at: IF-003.frame
  expected_mm: 7.0
  tol_mm: 0.20
```

Esto es lo que convierte al QA de opinión en verificación (§ 7.1), y es la razón por la que vale la pena que las interfaces sean un contrato formal y no prosa.

---

## 4. Máquina de estados y ciclo de corrección

```
DRAFT → SPEC_READY → DECOMPOSED → SYSTEM_DESIGNED → INTERFACES_RESOLVED
      → [gate 1] → PARTS_IN_PROGRESS ──(todas PASS)──► ASSEMBLED → TESTED
      → SLICED → [gate 2] → RELEASED
                 ▲                                │         │
                 └────── defectos por pieza ◄─────┴─────────┘
```

El **gate 1 va después de resolver las interfaces**, no después de la descomposición: apruebas árbol y geometría juntos, ya coherentes, en lugar de aprobar cotas que la Fase 2 va a cambiar de todas formas.

Reglas del orquestador:

1. Cada pieza sigue `TODO → DESIGNING → DFM → QA → PASS | FAIL`, más un estado transversal `BLOCKED_ON_HUMAN`.
2. Un `FAIL` de QA devuelve la pieza al Part Designer con la lista de defectos. Máximo **3 iteraciones** por pieza.
3. Si Assembly o Test encuentran un problema, el orquestador identifica las piezas o interfaces responsables y **solo reabre esas**, no todo el diseño.
4. Si una interfaz cambia, se reabren todas las piezas que la referencian.
5. Si se agotan los reintentos: primero escala a DeepSeek (§ 6); si aun así falla, se detiene y pregunta al humano.
6. Las piezas sin dependencias entre sí se diseñan en paralelo. El límite es **CPU**, no VRAM: cada pieza se construye en su propio proceso `freecadcmd` (§ 9.3).
7. **Una consulta al humano no detiene el proyecto.** La pieza que pregunta pasa a `BLOCKED_ON_HUMAN` y el planificador sigue con las demás. El estado se persiste: un proyecto puede dormir días esperando respuesta y sobrevivir a un reinicio. Los **gates sí bloquean** — son barreras de proyecto por definición.
8. **Una petición de cambio del humano es un defecto con autor humano.** Entra por la misma maquinaria de reapertura de las reglas 3 y 4, con los mismos límites de iteración. No hay un camino paralelo para cambios pedidos por Telegram.

---

## 5. Blackboard y artefactos

Estado compartido en disco + SQLite, versionado con git para poder volver atrás.

```
workspace/projects/<proyecto>/
├── spec.yaml                # salida de Requirements
├── tree.yaml                # árbol de producto (Decomposition)
├── interfaces.yaml          # contratos entre piezas (symbolic → resolved)
├── assertions.yaml          # aserciones de QA derivadas de las interfaces (§ 3.3)
├── system/                  # kinematics.json, actuation.json, electronics.json
├── parts/<pieza>/
│   ├── task.yaml            # tarea, dependencias, interfaces, estado
│   ├── recipe.json          # SALIDA DEL LLM: llamadas a generadores + parámetros
│   ├── params.json          # parámetros de diseño
│   ├── build.py             # GENERADO desde recipe.json por el orquestador
│   ├── <pieza>.FCStd
│   ├── <pieza>.step / .stl
│   ├── views/               # renders para el QA con visión (§ 7.1)
│   └── qa_report.json
├── assembly/                # assembly.FCStd, interference.json, bom.csv
├── tests/                   # sim_report.json, reach.png, torque.json
├── fabrication/             # *.3mf, *.gcode, slicing_report.json
├── human/                   # preguntas, respuestas y peticiones de cambio (§ 8.5)
├── log/                     # trazas de cada llamada a LLM y herramienta
└── state.sqlite             # estados de tareas, iteraciones, costos
```

Dos artefactos merecen atención:

- **`recipe.json` es la salida real del Part Designer.** El LLM produce esto, no Python. Es un documento validable contra esquema, así que un error del modelo se detecta *antes* de ejecutar nada.
- **`build.py` lo genera el orquestador** a partir de la receta. Sigue siendo el corazón de la reproducibilidad: la pieza se regenera siempre desde parámetros, así que un cambio de tolerancia o de interfaz no requiere que el LLM rediseñe desde cero.

---

## 6. Modelos y política de escalamiento

### 6.1 Modelos locales (Ollama)

**Hardware de referencia:** RTX 5090 (32 GB VRAM) + 92 GB de RAM de sistema.

| Rol | Modelo | VRAM | Nota |
|-----|--------|------|------|
| Diseño (todos los roles salvo QA) | `qwen3.8` (27B) | 16.5 GB | `tools`, `thinking` y `vision`. Sustituye a `qwen3:8b` |
| QA (revisor distinto) | `gemma3:12b` | ~8 GB | **Residente en paralelo**. También tiene visión |
| Embeddings (librería / docs FreeCAD) | `nomic-embed-text` | ~0.3 GB | RAG sobre la API de FreeCAD y la hardware library |
| | **Total** | **~25 GB** | Deja margen para contexto largo en 32 GB |

Ya **no hace falta un modelo especializado en código**: con recetas en vez de Python (§ 6.3), lo que se le pide al modelo es rellenar un esquema, no programar. Eso elimina `qwen2.5-coder:14b` del stack y simplifica `models.yaml`.

Dos modelos residentes requiere `OLLAMA_MAX_LOADED_MODELS=2`.

**Requisito de plataforma:** la 5090 es Blackwell (`sm_120`) y necesita **CUDA 12.8+** y una versión reciente de Ollama. Las versiones antiguas no fallan de forma visible: **caen a CPU en silencio**. Hay que verificarlo explícitamente (tarea F0.3), porque si no lo haces vas a creer que el modelo es lento cuando en realidad no está usando la GPU.

**Perfiles.** `config/models.yaml` define dos: `prod` (la tabla de arriba, en el PC con la 5090) y `dev` (un modelo pequeño para desarrollar en un portátil sin GPU). Cambiar de perfil no requiere tocar código — solo así el sistema es desarrollable fuera de la máquina de destino.

### 6.2 Escalamiento a DeepSeek

DeepSeek se usa **solo** cuando se cumple alguna condición:

- El mismo paso falló validación de esquema o QA **2 veces** con el modelo local.
- La descomposición supera un umbral de complejidad (p. ej. > 15 piezas o > 25 interfaces).
- El contexto necesario excede lo que el modelo local maneja bien (~16k tokens efectivos).
- El humano lo pide explícitamente para un paso.

Salvaguardas:

- Presupuesto máximo de tokens/costo por proyecto (`DEEPSEEK_MAX_USD_PER_PROJECT`), registrado en `state.sqlite`.
- Solo se envía texto (spec, interfaces, errores, código de macros). **Nunca** archivos del PC ni rutas personales.
- Cada escalamiento queda registrado en `log/` con el motivo.

La única variable requerida es `DEEPSEEK_API_KEY`, que ya existe en Windows; Docker Compose la pasa sin escribirla en ningún archivo (ver sección 8). `DEEPSEEK_BASE_URL` y `DEEPSEEK_MODEL` son **opcionales**: si no están definidas se usan los valores por defecto `https://api.deepseek.com` y `deepseek-chat`. Solo hace falta crearlas si quieres cambiar el endpoint o el modelo (p. ej. `deepseek-reasoner`). Si `DEEPSEEK_API_KEY` no está definida, el escalamiento se desactiva y el sistema trabaja solo con modelos locales.

```yaml
# config/models.yaml
providers:
  local:
    base_url: http://ollama:11434
  deepseek:
    api_key_env: DEEPSEEK_API_KEY        # requerida (ya definida en Windows)
    base_url_env: DEEPSEEK_BASE_URL      # opcional
    base_url_default: https://api.deepseek.com
    model_env: DEEPSEEK_MODEL            # opcional
    model_default: deepseek-chat         # o deepseek-reasoner

profiles:
  prod:                                  # PC con RTX 5090
    design: local/qwen3.8
    qa:     local/gemma3:12b
  dev:                                   # portátil sin GPU
    design: local/qwen3:4b
    qa:     local/qwen3:4b

active_profile_env: INTELLIPRINT_PROFILE  # prod | dev

agents:
  requirements:   {model: $design}
  decomposition:  {model: $design, escalate_to: deepseek, escalate_after_failures: 1}
  part_designer:  {model: $design, escalate_to: deepseek, escalate_after_failures: 2}
  qa:             {model: $qa}
  default:        {model: $design, escalate_to: deepseek, escalate_after_failures: 2}

escalation:
  max_usd_per_project: 2.0
  max_context_tokens_local: 16000
```

### 6.3 La escotilla de Python libre

El Part Designer **no escribe Python** en el camino normal: emite una receta de generadores (§ 2, § 5). Pero ningún catálogo de generadores cubre toda la geometría posible, así que existe una salida de emergencia.

Cuando ningún generador cubre lo que la pieza necesita, se marca como **atípica** y solo entonces se permite generar una macro Python libre. Condiciones obligatorias:

- Se ejecuta con **DeepSeek**, no con el modelo local.
- `validate_macro` está activo (§ 8.3).
- Queda registrado en `log/` con el motivo.
- **Una petición de cambio del humano nunca abre la escotilla por sí sola** (§ 8.5). Requiere gate.

El porcentaje de piezas que usan la escotilla es una **métrica de producto, no un fallo**: cada pieza atípica es una petición de funcionalidad para `mech-toolkit`. Si el 30 % de tus piezas necesitan Python libre, te faltan generadores; escribirlos hace el sistema más determinista con el uso, en vez de depender de que los modelos mejoren.

---

## 7. Reglas FDM (Tolerances / DFM y QA)

Valores por defecto para boquilla de 0.4 mm; son configurables por impresora/material en `config/printers/*.yaml` y se deben **calibrar con una pieza de prueba de holguras** en tu impresora.

| Regla | Valor por defecto |
|-------|-------------------|
| Encaje a presión (press-fit) | +0.10 mm en diámetro |
| Encaje deslizante (slide-fit) | +0.20 mm |
| Encaje con holgura / movimiento (clearance) | +0.30 a +0.40 mm |
| Agujero pasante M3 | 3.2–3.4 mm |
| Agujero para rosca en plástico M3 (auto-roscante) | 2.8 mm |
| Inserto térmico M3 | según fabricante (típico 4.0–4.2 mm) |
| Tuerca M3 hexagonal (cavidad) | 5.7 mm entre caras + 0.2 |
| Pared mínima | 2 × ancho de línea (0.8 mm), recomendado ≥ 1.2 mm |
| Pared estructural | ≥ 4 perímetros (≈ 1.8 mm) |
| Voladizo sin soporte | ≤ 45° |
| Puente sin soporte | ≤ 10 mm |
| Agujeros horizontales | Forma de gota o techo plano para evitar soportes |
| Orientación | Las cargas principales en el plano XY, nunca tirando entre capas |
| Tamaño máximo | Volumen de la cama de `config/printers/<impresora>.yaml`; si no cabe, dividir con uniones atornilladas o cola de milano |

### 7.1 Arquitectura del QA: tres capas y una regla dura

El riesgo clásico de un revisor LLM es que apruebe todo. La mitigación **no** es elegir bien el modelo — es quitarle la capacidad de aprobar.

| Capa | Qué comprueba | Quién decide |
|------|---------------|--------------|
| 1. **Aserciones de contrato** | Cada interfaz resuelta genera sus cotas esperadas (§ 3.3): diámetros, profundidades, patrones, posiciones | Código (comparación numérica) |
| 2. **Chequeos DFM** | `check_wall_thickness`, `check_overhangs`, `check_fits_bed` sobre el STL | Código (trimesh) |
| 3. **Pase libre con visión** | El modelo *mira* los renders de `views/` y busca lo que las cifras no capturan | LLM |

**La regla dura: el LLM solo puede añadir defectos, nunca quitarlos.**

El veredicto se calcula así, y el modelo no participa en el cálculo:

```
PASS  ⟺  capa1.todas_ok  ∧  capa2.todas_ok  ∧  capa3.defectos == []
```

El LLM escribe en una **lista de defectos**, no en el veredicto. No existe ninguna ruta por la que pueda convertir un `FAIL` determinista en `PASS`. El peor comportamiento posible de un modelo complaciente es ser *inútil* (no aportar defectos), que es un fallo mucho más barato que aprobar una pieza rota.

**Qué aporta la visión, y qué no.** Detecta catástrofes que las cotas no ven: un `pocket` aplicado en la cara equivocada (todas las medidas correctas, en el sitio opuesto), una pieza que salió como dos sólidos separados, una booleana que se comió media pieza. Son los modos de fallo típicos de geometría generada por un LLM.

Lo que **no** hace: medir. Un modelo de visión no distingue una pared de 0.9 mm de una de 1.2 mm en un render, y si le preguntas una cota se la inventa con total confianza. Por eso vive en la capa 3 y nunca en las capas 1 y 2. Sirve para gritar "esto está mal", jamás para decir "esto está bien".

---

## 8. Despliegue en Docker

### 8.1 Topología

```
┌─────────────────────── PC Windows (host) ───────────────────────┐
│  FreeCAD GUI + addon RPC     PrusaSlicer      freecadcmd ×N      │
│  (inspección, ensamble)                       (construcción)     │
│  MCP freecad  ─┐            MCP prusaslicer ─┐   (ya probados)   │
│                └─ mcp-proxy :8101           └─ mcp-proxy :8102   │
│                      ▲                              ▲            │
│  C:\...\Intelliprint\workspace  ◄── bind mount ──┐  │            │
└──────────────────────┼──────────────────────────┼──┼────────────┘
                       │ host.docker.internal     │  │
┌──────────────────────┼──── Docker Desktop (WSL2) ┼──┼────────────┐
│  orchestrator (LangGraph + API + UI + HumanPort) ─┴──┘            │
│  ollama (RTX 5090, 32 GB: qwen3.8 + gemma3:12b)                  │
│  openclaw (adaptador Telegram del HumanPort)  ──►  Telegram      │
│  mech-toolkit MCP   (generadores, aserciones, tolerancias, DFM)  │
│  sim MCP            (ikpy, PyBullet, trimesh)                    │
│  qdrant (RAG de docs FreeCAD + hardware)  ·  postgres/sqlite     │
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 Cómo conectar los MCP que ya tienes

FreeCAD y PrusaSlicer se quedan en el PC porque ya funcionan ahí. Los MCP que corren por **stdio** no se pueden invocar desde un contenedor, así que se exponen por HTTP con un puente en el host:

```bash
# En el PC (fuera de Docker); ajusta el comando al que ya usas para lanzar cada MCP
mcp-proxy --port 8101 --host 0.0.0.0 -- <comando del MCP de FreeCAD>
mcp-proxy --port 8102 --host 0.0.0.0 -- <comando del MCP de PrusaSlicer>
```

Alternativa: si tu MCP de FreeCAD habla con FreeCAD por RPC (p. ej. XML-RPC en el puerto 9875), puedes correr el propio MCP dentro de un contenedor y apuntarlo a `host.docker.internal:9875`. En ambos casos el orquestador ve URLs HTTP.

**Rutas de archivos**: el orquestador escribe en `/workspace` (contenedor) y FreeCAD/PrusaSlicer leen `C:\Users\jdr\Desktop\hobbies\Intelliprint\workspace` (host). El orquestador traduce rutas con `HOST_WORKSPACE` antes de llamar a un MCP del host.

### 8.3 Acceso al PC

El sistema tiene acceso a tu PC a través de:

1. Los MCP del host (FreeCAD, PrusaSlicer): control total de esas aplicaciones.
2. Bind mounts explícitos: `workspace/` (lectura/escritura) y, si quieres, carpetas de solo lectura (librería de STEP, perfiles de PrusaSlicer).

No se monta `C:\` completo ni el socket de Docker: un modelo ejecutando macros Python con acceso irrestricto puede borrar archivos por error. Si necesitas más carpetas, añádelas una por una en `docker-compose.yml`.

**La defensa principal es que casi nunca hay Python.** En el camino normal el Part Designer emite una receta validada contra esquema (§ 6.3) y `build.py` lo compone el orquestador a partir de plantillas propias. No hay código arbitrario que validar porque no hay código arbitrario. Esto no es una capa de seguridad añadida: es la ausencia de la superficie de ataque.

**Sobre `validate_macro`, con honestidad.** Solo entra en juego en la escotilla. Es un análisis estático (AST) que bloquea `os`, `shutil`, `subprocess`, `open` fuera de `workspace/` y similares.

> ⚠️ **`validate_macro` es una red de seguridad, no un límite de seguridad.** Una lista negra sobre AST se esquiva sin dificultad con `getattr`, `__import__`, `__builtins__` o `__class__.__bases__`. Funciona bien contra su amenaza real — un modelo confundido que escribe algo destructivo por error — y no resistiría a nada adversarial. No confíes en ella como si fuera un *sandbox*.

Si en algún momento necesitas una garantía real (por ejemplo, si la escotilla creciera o si el canal de Telegram se abriera a más gente), la respuesta no es endurecer la lista negra: es ejecutar `freecadcmd` en un contenedor desechable sin red y con solo la carpeta de la pieza montada. Queda anotado en mejoras futuras.

### 8.4 `docker-compose.yml` (base)

```yaml
services:
  ollama:
    image: ollama/ollama:latest          # versión con soporte Blackwell / CUDA 12.8+
    environment:
      - OLLAMA_MAX_LOADED_MODELS=2       # modelo de diseño + modelo de QA residentes
    volumes:
      - ollama:/root/.ollama
    ports: ["11434:11434"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  orchestrator:
    build: ./orchestrator
    depends_on: [ollama, mech-toolkit, sim, qdrant]
    ports: ["8080:8080"]            # API + UI de aprobación
    environment:
      # Sin valor = Docker Compose toma la variable del entorno de Windows
      - DEEPSEEK_API_KEY
      # Opcionales: si no existen en Windows se usan estos valores por defecto
      - DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-https://api.deepseek.com}
      - DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-deepseek-chat}
      - OLLAMA_URL=http://ollama:11434
      - INTELLIPRINT_PROFILE=prod       # perfil de models.yaml (prod | dev)
      - HUMAN_CHANNELS=cli,web,telegram # adaptadores activos del HumanPort (§ 8.5)
      - FREECAD_MCP_URL=http://host.docker.internal:8101/sse
      - PRUSASLICER_MCP_URL=http://host.docker.internal:8102/sse
      - MECH_TOOLKIT_MCP_URL=http://mech-toolkit:8000/mcp
      - SIM_MCP_URL=http://sim:8000/mcp
      - WORKSPACE=/workspace
      - HOST_WORKSPACE=C:\Users\jdr\Desktop\hobbies\Intelliprint\workspace
    volumes:
      - ./workspace:/workspace
      - ./config:/app/config:ro
      - ./library:/app/library:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"

  mech-toolkit:
    build: ./mcp/mech-toolkit
    volumes:
      - ./workspace:/workspace
      - ./library:/app/library:ro
      - ./config:/app/config:ro

  sim:
    build: ./mcp/sim
    volumes:
      - ./workspace:/workspace

  openclaw:                             # adaptador de Telegram del HumanPort (§ 8.5)
    image: openclaw/openclaw:latest
    depends_on: [orchestrator]
    environment:
      - TELEGRAM_BOT_TOKEN              # del entorno; nunca en el repo
      - TELEGRAM_ALLOWED_USERS          # lista blanca de chat IDs. OBLIGATORIA
      - ORCHESTRATOR_URL=http://orchestrator:8080
    volumes:
      - openclaw:/data

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant:/qdrant/storage

volumes:
  ollama:
  qdrant:
  openclaw:
```

> Si prefieres que Ollama use la GPU nativa de Windows, puedes correr Ollama en el host y cambiar `OLLAMA_URL` a `http://host.docker.internal:11434`.

### 8.5 `HumanPort`: un puerto, tres adaptadores

Los dos gates, las preguntas del Requirements Agent, las consultas del QA y las peticiones de cambio son **la misma operación**: preguntar algo a un humano y esperar. Se implementan una sola vez.

```
                  ┌──────────────────────────────┐
  Orquestador ───►│  HumanPort                   │
                  │   ask(pregunta, adjuntos)    │
                  │   notify(evento)             │
                  └──────────────┬───────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         adaptador CLI     adaptador Web      adaptador Telegram
           (F0.9)            (F5.4)          (F5.5, fuera del grafo)
```

Esto es lo que unifica el gate por consola y el gate por navegador, que en el plan original eran dos implementaciones separadas de lo mismo, y permite añadir Telegram sin tocar la lógica de gates.

**OpenClaw** es una pasarela auto-alojada que conecta apps de mensajería con agentes. Aquí se usa **solo como transporte**: no lee ni escribe el blackboard, no toma decisiones de diseño y no aparece en la tabla de agentes. Recibe del orquestador una pregunta y sus adjuntos, la entrega en Telegram, y devuelve la respuesta.

**Qué habilita en la práctica.** Como el QA ya renderiza vistas para su capa de visión (§ 7.1), esas mismas imágenes se pueden enviar por Telegram. El sistema no te manda una lista de cotas: te manda **la pieza** y te pregunta si es lo que querías. Y tú puedes pedir cambios desde el móvil sin estar delante del PC — que es justamente el caso de uso, porque si estuvieras delante usarías la UI.

**Comportamiento asíncrono.** Una consulta pone la pieza en `BLOCKED_ON_HUMAN` y el planificador sigue con las demás (regla 7, § 4). Un proyecto puede dormir días esperando una respuesta. Los gates, en cambio, sí bloquean el proyecto entero.

#### Reglas de seguridad del canal

Este canal es **entrada no confiable a un sistema que puede ejecutar código** (§ 6.3). No es paranoia: es la consecuencia directa de tener una escotilla de Python.

1. **Lista blanca estricta.** Solo los chat IDs de `TELEGRAM_ALLOWED_USERS`. Sin lista blanca, el canal no arranca.
2. **El texto entrante es dato, nunca instrucción.** Un mensaje jamás se concatena a un prompt de sistema. Se procesa como contenido a clasificar, no como orden a obedecer.
3. **Una petición de cambio nunca abre la escotilla de Python por sí sola.** Requiere gate explícito.
4. **Filtro de salida.** Igual que con DeepSeek, por Telegram solo sale texto y renders: nunca rutas del host, credenciales ni archivos del PC. Es el mismo filtro, aplicado a un segundo destino.

Conviene tener presente que las imágenes y el texto que salen por Telegram pasan por servidores de Telegram. Para diseños propios es irrelevante; si algún día trabajas algo confidencial, es una salida de datos más que considerar.

---

## 9. Servidores MCP

### 9.1 Existentes (en el host)

- **FreeCAD MCP**: crear/editar objetos, ejecutar macros Python, capturas de vista, exportar.
- **PrusaSlicer MCP**: laminar, aplicar perfiles, obtener estadísticas (filamento, tiempo), exportar 3MF/G-code.

### 9.2 Nuevos (en Docker)

**`mech-toolkit`**: herramientas deterministas que evitan que el LLM calcule geometría.

| Herramienta | Qué hace |
|-------------|----------|
| `list_hardware(category)` | Lista piezas comerciales disponibles (tornillos, tuercas, insertos, rodamientos, motores, servos, MCU). |
| `get_hardware(part_id)` | Dimensiones, masa, torque, envolvente y modelo STEP. |
| `place_commercial_part(part_id, frame)` | Genera la macro FreeCAD para insertar la pieza comercial. |
| `generate_bearing_housing(bearing_id, fit)` | Macro de cavidad para rodamiento con holgura aplicada. |
| `generate_bolt_pattern(screw_id, count, pcd_mm, fit)` | Patrón de agujeros con holgura, avellanado/cavidad de tuerca. |
| `generate_servo_mount(servo_id)` | Alojamiento y orejetas para servo (SG90, MG996R...). |
| `apply_fit(nominal_mm, fit)` | Devuelve la dimensión corregida según `config/printers`. |
| `check_wall_thickness(stl, min_mm)` | Espesor mínimo por ray casting (trimesh). |
| `check_overhangs(stl, orientation)` | Área con voladizo > 45°. |
| `suggest_print_orientation(stl, load_axes)` | Orientación que maximiza resistencia y minimiza soportes. |
| `check_fits_bed(stl, printer)` | Verifica que la pieza cabe en la cama. |
| `validate_macro(code)` | Análisis estático de la macro. **Solo se usa en la escotilla** (§ 6.3, § 8.3). |
| `list_generators()` | Catálogo de generadores disponibles. Es lo que el Part Designer consulta para componer su receta. |
| `compose_build_script(recipe)` | Convierte una `recipe.json` validada en el `build.py` de la pieza. Sin LLM. |
| `resolve_interfaces(symbolic, system)` | Convierte interfaces simbólicas en resueltas usando la salida de la Fase 2 (§ 3.2). |
| `derive_assertions(interface)` | Genera las aserciones medibles de una interfaz resuelta (§ 3.3). Es la base del QA. |

**`sim`**: pruebas físicas.

| Herramienta | Qué hace |
|-------------|----------|
| `solve_ik(chain, target)` / `workspace_reach(chain)` | Cinemática con ikpy. |
| `joint_torques(chain, payload_kg, poses)` | Torque estático por articulación en las poses críticas. |
| `export_urdf(assembly)` | Genera URDF desde el ensamble para simular. |
| `sweep_collisions(urdf, joint_ranges)` | Barre rangos y reporta colisiones entre eslabones. |
| `stability_test(urdf)` | Vuelco con carga máxima (PyBullet). |
| `mass_properties(stl, material, infill)` | Masa y centro de masa estimados. |

**Herramientas adicionales vía FreeCAD MCP** (implementadas como macros que el orquestador envía):
`measure(part, feature)`, `interference_check(assembly)`, `export_stl_batch(parts)`, `section_view(part, plane)` y `get_view(part)` (imágenes para la capa de visión del QA, § 7.1).

### 9.3 Ejecución: headless para construir, GUI para inspeccionar

FreeCAD se usa de **dos formas distintas**, y confundirlas cuesta paralelismo.

| | Construcción de piezas | Inspección y ensamble |
|---|---|---|
| **Binario** | `freecadcmd` (sin GUI) | FreeCAD con GUI + addon RPC |
| **Instancias** | N procesos efímeros, uno por pieza | Una sola, persistente |
| **Paralelismo** | Sí, limitado por CPU | No, serial |
| **Para qué** | Ejecutar `build.py`, exportar STL/STEP | Renderizar vistas, ensamblar, medir |

Construir cada pieza en su propio proceso `freecadcmd` encaja con `build.py`: si la pieza se regenera siempre desde parámetros, un proceso limpio por pieza es lo natural. No hay documento global ni estado compartido, y **un cuelgue de FreeCAD mata una pieza, no el proyecto**.

La contrapartida es que sin GUI no se pueden renderizar vistas. Por eso la inspección se separa: una única instancia con GUI carga los `.FCStd` ya construidos solo para capturar imágenes y hacer el ensamble. Es serial, pero abrir y renderizar es barato comparado con construir.

> El MCP de FreeCAD soporta ambos modos: `execute_code` contra la instancia GUI por RPC, y `execute_code_headless` con el flag `--freecadcmd`.

---

## 10. Librería de hardware

Ningún modelo debe inventar las dimensiones de un NEMA17, por grande que sea. Todo el hardware comercial vive en `library/` y se indexa también en Qdrant para búsqueda semántica. Es además la fuente de la que el resolvedor de interfaces (§ 3.2) saca las cotas reales.

```yaml
# library/motors/nema17_42x40.yaml
id: nema17_42x40
category: stepper
body_mm: {w: 42.3, h: 42.3, l: 40}
shaft_mm: {d: 5, l: 24, flat: true}
mount: {bolt: M3, pcd_square_mm: 31, pilot_d_mm: 22}
holding_torque_nm: 0.40
mass_g: 280
step: library/step/nema17_42x40.step
```

Contenido inicial: tornillería métrica M2–M5, tuercas, insertos térmicos, rodamientos 608zz/623zz/625zz, NEMA17/NEMA14, SG90/MG90S/MG996R/DS3218, ESP32 DevKit, Arduino Nano, drivers A4988/TMC2209, varillas y ejes.

---

## 11. Ejemplo de ejecución

**Entrada:** *"Diseña una garra robótica para levantar una lata de refresco, accionada por un servo MG996R, impresora Prusa MK4, PETG."*

1. **Requirements** → `spec.yaml`: objeto Ø66 mm, 350 g, apertura ≥ 80 mm, MG996R, PETG, cama 250×210×220.
2. **Decomposition** → 7 piezas: `base_servo`, `engranaje_motriz`, `engranaje_conducido`, `dedo_izq`, `dedo_der`, `eslabon_paralelo ×2`, `almohadilla ×2` (TPU opcional); 9 interfaces **simbólicas**: *"IF-002: `bolt_pattern` entre `base_servo` y el servo, clase `servo_horn`, `fit: clearance`"* — sin una sola cota.
3. **Kinematics/Actuation** → geometría de dedos paralelos; fuerza de agarre requerida vs. torque del MG996R (margen 2.1× ✓). Confirma el MG996R como actuador.
4. **Resolución de interfaces** (código) → IF-002 pasa a `resolved`: patrón real del MG996R desde `library/`, `frame` en el origen calculado por Kinematics, M3 a 3.3 mm por `fit: clearance`. **Ningún LLM escribió esos números.**
5. **Gate 1:** apruebas árbol **e interfaces ya resueltas**. Lo que ves es lo que se va a construir.
6. **Part Designer ×3 en paralelo** → cada uno emite su `recipe.json` (`generate_servo_mount(MG996R)`, `generate_bolt_pattern(M3, 4, pcd=19)`…). El orquestador compone `build.py` y lo ejecuta en tres procesos `freecadcmd` independientes.
7. **Tolerances** → pasadores M3 a 3.3 mm, eje de engranaje con clearance +0.35 mm, orientación de dedos en plano.
8. **QA** → capa 1 y 2 en verde para `dedo_der`, pero la **capa de visión** ve en el render que el alojamiento del pasador quedó abierto por un lado. Añade el defecto → vuelve al diseñador → PASA en la iteración 2.
9. **Consulta por Telegram** → el sistema no sabe si la almohadilla debe ser TPU o PETG. Te manda el render y la pregunta al móvil; `almohadilla` pasa a `BLOCKED_ON_HUMAN` mientras **las otras seis piezas siguen diseñándose**. Respondes "TPU" desde el bus y el proyecto continúa.
10. **Assembly + Test** → interferencia entre engranajes a 0° de apertura → reabre `engranaje_conducido` (−0.3 mm de adendo) → barrido sin colisiones.
11. **Slicing** → 2 placas, 71 g PETG, 3 h 40 min, sin soportes salvo `base_servo`.
12. **Gate 2:** revisas en FreeCAD y PrusaSlicer, apruebas → STL/3MF/G-code, BOM (1 MG996R, 6 tornillos M3×12, 6 tuercas M3) e instrucciones de ensamble.
13. **Feedback** (opcional): tras imprimir escribes por Telegram "el pasador entra muy flojo" → entra como petición de cambio, se traduce a defecto sobre la interfaz del pasador, y el sistema ajusta el perfil de holguras de tu impresora para próximos diseños.

---

## 12. Estructura del repositorio

```
Intelliprint/
├── SISTEMA_MULTIAGENTE.md
├── PLAN_PROYECTO.md
├── DECISIONES.md                # registro de decisiones de arquitectura (ADR)
├── docker-compose.yml
├── config/
│   ├── models.yaml              # perfiles prod / dev (§ 6.1)
│   ├── printers/prusa_mk4_petg.yaml
│   └── agents/*.md              # prompts de sistema por agente
├── orchestrator/
│   ├── Dockerfile
│   ├── graph.py                 # LangGraph: estados, transiciones, gates
│   ├── agents/                  # un módulo por agente (prompt + esquema + tools)
│   ├── schemas/                 # Pydantic: spec, tree, interface, recipe, qa_report
│   ├── recipes/                 # receta → build.py (plantillas + compositor)
│   ├── human/                   # HumanPort (§ 8.5)
│   │   ├── port.py              #   interfaz ask() / notify()
│   │   └── adapters/            #   cli.py, web.py, telegram.py
│   ├── llm/router.py            # local vs. DeepSeek, presupuestos
│   ├── mcp/client.py            # clientes MCP (HTTP/SSE)
│   └── ui/                      # web de aprobación y seguimiento
├── mcp/
│   ├── mech-toolkit/
│   │   ├── generators/          # un módulo por generador de geometría
│   │   └── assertions/          # derivación de aserciones por tipo de interfaz
│   └── sim/
├── library/                     # hardware comercial (yaml + step)
├── scripts/
│   └── start-host-mcps.ps1      # lanza mcp-proxy para FreeCAD y PrusaSlicer
└── workspace/                   # proyectos (bind mount)
```

---

## 13. Hoja de ruta

| Fase | Objetivo | Criterio de éxito |
|------|----------|-------------------|
| **0** | Docker + Ollama + puentes MCP del host | El orquestador lista herramientas de FreeCAD y PrusaSlicer desde el contenedor |
| **1** | Pipeline lineal de una pieza: Requirements → Part Designer → Tolerances → Slicing | Un soporte de NEMA17 imprimible generado de extremo a extremo |
| **2** | `mech-toolkit` + librería de hardware + QA de tres capas | QA detecta agujeros y paredes fuera de norma en piezas de prueba sin que el LLM pueda aprobarlas |
| **3** | Decomposition + interfaces simbólicas/resueltas + diseño paralelo + Assembly | Garra de 5–8 piezas ensamblada sin interferencias |
| **4** | Kinematics/Actuation/Sim + ciclo de reapertura selectiva | Brazo de 3 GDL con torque validado y barrido sin colisiones |
| **5** | `HumanPort` + adaptadores (CLI, web, Telegram) + escalamiento a DeepSeek con presupuesto | Ambos gates y una petición de cambio resueltos desde el móvil |
| **6** | Endurecimiento y evaluación | Brazo de 6 GDL con < 20 % de pasos escalados |

---

## 14. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| El modelo genera geometría inválida | **No genera código**: emite una receta validada contra esquema (§ 6.3). Un error es un parámetro rechazado antes de ejecutar nada, no un traceback |
| Faltan generadores para una pieza | Escotilla con DeepSeek + métrica del % de piezas atípicas, que dirige qué generador escribir a continuación |
| Piezas diseñadas por separado no encajan | Interfaces como contrato formal, resueltas por código antes de diseñar (§ 3), holguras centralizadas, chequeo de interferencias en el ensamble |
| QA aprueba todo | **Estructuralmente imposible**: el veredicto es aritmético y el LLM solo puede añadir defectos (§ 7.1). Modelo distinto como segunda red |
| Interfaces con cotas inventadas | Estado `symbolic` → `resolved`; el validador impide que una interfaz sin resolver llegue a la Fase 3 |
| VRAM insuficiente para varios modelos | 25 GB de 32 GB con los dos modelos residentes; `OLLAMA_MAX_LOADED_MODELS=2` |
| Ollama cae a CPU en silencio (Blackwell) | Verificación explícita de uso de GPU en F0.3; requisito de CUDA 12.8+ documentado (§ 6.1) |
| Macros con efectos sobre el PC | Superficie casi eliminada (no hay Python en el camino normal); `validate_macro` como red en la escotilla, **declarado explícitamente como no-sandbox** (§ 8.3) |
| Inyección por el canal de Telegram | Lista blanca obligatoria; texto entrante tratado como dato; la escotilla de Python nunca se abre sin gate (§ 8.5) |
| Una consulta al humano congela el proyecto | `BLOCKED_ON_HUMAN` por pieza; el planificador sigue con las demás (regla 7, § 4) |
| Costos de DeepSeek | Reglas de escalamiento explícitas y tope por proyecto |
| Holguras distintas en cada impresora | Perfil por impresora/material calibrado con pieza de prueba y ajustado con feedback |
