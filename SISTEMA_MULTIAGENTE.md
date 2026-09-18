# Intelliprint — Sistema multiagente de diseño para impresión 3D

Sistema local de agentes que recibe un requerimiento en lenguaje natural (por ejemplo, *"brazo robótico de 6 ejes, alcance 40 cm, carga 500 g"*) y lo convierte en piezas paramétricas en **FreeCAD**, las ensambla, las valida, las lamina en **PrusaSlicer** y entrega STL/3MF listos para imprimir, con aprobación humana en los puntos críticos.

Restricciones de diseño:

- **Local primero.** Todos los agentes corren con modelos locales (Ollama). **DeepSeek** es el único modelo externo permitido y solo se usa como escalamiento, controlado por reglas explícitas.
- **Todo en Docker.** Orquestador, modelos, servicios de cálculo y almacenamiento corren en contenedores. FreeCAD y PrusaSlicer siguen en el PC (sus MCP ya están probados) y se exponen a los contenedores por red.
- **El LLM no hace geometría.** Los modelos pequeños deciden parámetros y llaman herramientas deterministas; la geometría, las tolerancias y los cálculos físicos los hace código.

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
│    2. Decomposition Agent  → árbol del producto: sistemas →         │
│                              subensambles → piezas + interfaces     │
│  ── Gate humano #1: aprobar spec y árbol ──                         │
│                                                                     │
│  FASE 2 · Ingeniería de sistema                                     │
│    3. Kinematics Agent     → eslabones, GDL, rangos, cargas         │
│    4. Actuation Agent      → motores/servos con margen de torque    │
│    5. Electronics Agent    → MCU, drivers, ruteo de cables          │
│                                                                     │
│  FASE 3 · Diseño por pieza (en paralelo, una tarea por pieza)       │
│    6. Part Designer Agent  → pieza paramétrica en FreeCAD (MCP)     │
│    7. Tolerances/DFM Agent → holguras FDM, paredes, orientación     │
│    8. QA Agent             → revisión independiente de cada pieza   │
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
| 0 | **Orchestrator** | Avanza la máquina de estados, lanza tareas, aplica reintentos y escalamiento. Es código, no un LLM; solo usa el LLM para resumir y redactar mensajes al humano. | blackboard | `qwen3:8b` |
| 1 | **Requirements** | Convierte el texto libre en `spec.yaml`: dimensiones, cargas, alcance, materiales, impresora, presupuesto, restricciones. Hace preguntas si falta algo crítico. | blackboard | `qwen3:8b` |
| 2 | **Decomposition** | Divide el producto en árbol jerárquico (producto → sistemas → subensambles → piezas). Define **interfaces** entre piezas (ejes, tornillos, rodamientos, encajes) y crea una tarea por pieza con dependencias. | blackboard, hardware library | `qwen3:8b` → **DeepSeek** si el árbol supera ~15 piezas o falla validación |
| 3 | **Kinematics** | Longitudes de eslabones, GDL, rangos articulares, espacio de trabajo, cargas por articulación. | `kinematics` MCP (ikpy, numpy) | `qwen3:8b` |
| 4 | **Actuation** | Selecciona actuadores de la librería con margen de torque ≥ 1.5×, reductoras, alimentación. | `kinematics` MCP, hardware library | `qwen3:8b` |
| 5 | **Electronics** | MCU (ESP32/Arduino), drivers, fuente, canales de cable, soportes de PCB. Produce requisitos que se vuelven piezas o features. | hardware library | `qwen3:8b` |
| 6 | **Part Designer** | Genera **una** pieza paramétrica en FreeCAD a partir de su tarea e interfaces. Escribe/ejecuta macros Python vía MCP. Puede haber varias instancias en paralelo. | `freecad` MCP, `mech-toolkit` MCP | `qwen2.5-coder:14b` (o `qwen3:8b` con poca VRAM) → **DeepSeek** tras 2 fallos |
| 7 | **Tolerances / DFM** | Aplica holguras FDM, verifica paredes, voladizos, puentes, orientación de impresión y separación de piezas que no caben en la cama. | `mech-toolkit` MCP, `freecad` MCP | `qwen3:8b` |
| 8 | **QA** | Revisor independiente. No diseña: compara la pieza/ensamble contra la spec, las interfaces y las reglas FDM usando **mediciones reales** del modelo. Emite `PASS` / `FAIL` con defectos concretos. | `freecad` MCP (solo lectura), `mech-toolkit` MCP | Modelo **distinto** al del diseñador (p. ej. `gemma3:12b` o `mistral-small`) para evitar sesgo propio |
| 9 | **Assembly** | Importa las piezas, las posiciona según las interfaces, añade hardware comercial, detecta interferencias y genera la BOM. | `freecad` MCP, `mech-toolkit` MCP | `qwen3:8b` |
| 10 | **Test / Sim** | Pruebas del ensamble: barrido de rangos articulares con chequeo de colisiones, torque en la peor pose, estabilidad (PyBullet), verificación de alcance. | `sim` MCP (PyBullet, ikpy) | `qwen3:8b` |
| 11 | **Slicing / Cost** | Lamina cada STL en PrusaSlicer con el perfil de la impresora, agrupa en placas, reporta gramos, horas, costo y soportes. | `prusaslicer` MCP | `qwen3:8b` |

### 2.1 Por qué estos agentes adicionales

- **Decomposition Agent**: sin él, un modelo de 8B intenta diseñar "el brazo" de golpe y falla. Con él, cada Part Designer recibe una tarea pequeña y cerrada ("base giratoria, Ø120 mm, aloja un 608zz y un NEMA17, 4×M3 hacia la pieza `hombro`"). Es el agente que más valor aporta.
- **QA Agent** separado del diseñador: el mismo modelo que diseñó una pieza tiende a aprobarla. QA usa otro modelo y, sobre todo, **mide** (volúmenes, distancias, diámetros de agujeros) en vez de opinar.
- **Assembly + Test/Sim**: permiten el ciclo que pediste: piezas individuales → ensamble → prueba → corrección de las piezas que fallan.

---

## 3. Contratos entre piezas (interfaces)

La clave para que piezas diseñadas por separado encajen es que el Decomposition Agent defina las interfaces **antes** de diseñar, y que todas las piezas las referencien por ID.

```yaml
# projects/<id>/interfaces.yaml
- id: IF-003
  type: bearing_seat          # bearing_seat | shaft | bolt_pattern | press_fit | slide_fit | snap_fit | cable_pass
  between: [base_giratoria, hombro]
  hardware: bearing_608zz     # referencia a la hardware library
  fit: press                  # press | clearance | slide
  nominal_mm: {bore: 8, od: 22, width: 7}
  frame: {origin: [0, 0, 45], axis: [0, 0, 1]}   # en coordenadas del ensamble
- id: IF-004
  type: bolt_pattern
  between: [hombro, eslabon_1]
  hardware: screw_M3x12
  count: 4
  pcd_mm: 30
  fit: clearance
```

El Tolerances Agent traduce `fit` a holguras reales (sección 7) y el Assembly Agent usa `frame` para posicionar piezas.

---

## 4. Máquina de estados y ciclo de corrección

```
DRAFT → SPEC_READY → [gate 1] → DECOMPOSED → SYSTEM_DESIGNED
      → PARTS_IN_PROGRESS ──(todas PASS)──► ASSEMBLED → TESTED → SLICED → [gate 2] → RELEASED
                 ▲                                │         │
                 └────── defectos por pieza ◄─────┴─────────┘
```

Reglas del orquestador:

1. Cada pieza sigue `TODO → DESIGNING → DFM → QA → PASS | FAIL`.
2. Un `FAIL` de QA devuelve la pieza al Part Designer con la lista de defectos. Máximo **3 iteraciones** por pieza.
3. Si Assembly o Test encuentran un problema, el orquestador identifica las piezas o interfaces responsables y **solo reabre esas**, no todo el diseño.
4. Si una interfaz cambia, se reabren todas las piezas que la referencian.
5. Si se agotan los reintentos: primero escala a DeepSeek (sección 6); si aun así falla, se detiene y pregunta al humano.
6. Las piezas sin dependencias entre sí se diseñan en paralelo (limitado por VRAM, ver sección 9).

---

## 5. Blackboard y artefactos

Estado compartido en disco + SQLite, versionado con git para poder volver atrás.

```
workspace/projects/<proyecto>/
├── spec.yaml                # salida de Requirements
├── tree.yaml                # árbol de producto (Decomposition)
├── interfaces.yaml          # contratos entre piezas
├── system/                  # kinematics.json, actuation.json, electronics.json
├── parts/<pieza>/
│   ├── task.yaml            # tarea, dependencias, interfaces, estado
│   ├── params.json          # parámetros de diseño
│   ├── build.py             # macro FreeCAD reproducible
│   ├── <pieza>.FCStd
│   ├── <pieza>.step / .stl
│   └── qa_report.json
├── assembly/                # assembly.FCStd, interference.json, bom.csv
├── tests/                   # sim_report.json, reach.png, torque.json
├── fabrication/             # *.3mf, *.gcode, slicing_report.json
├── log/                     # trazas de cada llamada a LLM y herramienta
└── state.sqlite             # estados de tareas, iteraciones, costos
```

`build.py` es importante: la pieza se regenera siempre desde parámetros, así un cambio de tolerancia o de interfaz no requiere que el LLM rediseñe desde cero.

---

## 6. Modelos y política de escalamiento

### 6.1 Modelos locales (Ollama)

| Rol | Modelo sugerido | Nota |
|-----|-----------------|------|
| General / razonamiento | `qwen3:8b` | Buen uso de herramientas y JSON |
| Código FreeCAD | `qwen2.5-coder:14b` o `qwen3-coder` | Mejor para macros Python |
| QA (revisor distinto) | `gemma3:12b` o `mistral-small` | Diversidad de modelo |
| Embeddings (librería / docs FreeCAD) | `nomic-embed-text` | Para RAG sobre la API de FreeCAD y la hardware library |

Todo se configura en `config/models.yaml`; cambiar de modelo no requiere tocar código.

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

agents:
  requirements:   {model: local/qwen3:8b}
  decomposition:  {model: local/qwen3:8b, escalate_to: deepseek, escalate_after_failures: 1}
  part_designer:  {model: local/qwen2.5-coder:14b, escalate_to: deepseek, escalate_after_failures: 2}
  qa:             {model: local/gemma3:12b}
  default:        {model: local/qwen3:8b, escalate_to: deepseek, escalate_after_failures: 2}

escalation:
  max_usd_per_project: 2.0
  max_context_tokens_local: 16000
```

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

---

## 8. Despliegue en Docker

### 8.1 Topología

```
┌─────────────────────── PC Windows (host) ───────────────────────┐
│  FreeCAD + addon RPC        PrusaSlicer                          │
│  MCP freecad  ─┐            MCP prusaslicer ─┐   (ya probados)   │
│                └─ mcp-proxy :8101           └─ mcp-proxy :8102   │
│                      ▲                              ▲            │
│  C:\...\Intelliprint\workspace  ◄── bind mount ──┐  │            │
└──────────────────────┼──────────────────────────┼──┼────────────┘
                       │ host.docker.internal     │  │
┌──────────────────────┼──── Docker Desktop (WSL2) ┼──┼────────────┐
│  orchestrator (LangGraph + API + UI)  ───────────┴──┘            │
│  ollama (GPU)                                                    │
│  mech-toolkit MCP   (tolerancias, paredes, librería de hardware) │
│  kinematics/sim MCP (ikpy, PyBullet, trimesh)                    │
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

No se monta `C:\` completo ni el socket de Docker: un modelo de 8B ejecutando macros Python con acceso irrestricto puede borrar archivos por error. Si necesitas más carpetas, añádelas una por una en `docker-compose.yml`. Las macros de FreeCAD se ejecutan dentro de FreeCAD, que sí tiene acceso al PC; por eso el orquestador valida las macros (lista negra de `os.remove`, `shutil.rmtree`, `subprocess`, rutas fuera de `workspace`) antes de enviarlas.

### 8.4 `docker-compose.yml` (base)

```yaml
services:
  ollama:
    image: ollama/ollama:latest
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

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant:/qdrant/storage

volumes:
  ollama:
  qdrant:
```

> Si prefieres que Ollama use la GPU nativa de Windows, puedes correr Ollama en el host y cambiar `OLLAMA_URL` a `http://host.docker.internal:11434`.

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
| `validate_macro(code)` | Análisis estático de la macro antes de enviarla a FreeCAD. |

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
`measure(part, feature)`, `interference_check(assembly)`, `export_stl_batch(parts)`, `section_view(part, plane)` (imagen para QA).

---

## 10. Librería de hardware

Un modelo de 8B no debe inventar las dimensiones de un NEMA17. Todo el hardware comercial vive en `library/` y se indexa también en Qdrant para búsqueda semántica.

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
2. **Decomposition** → 7 piezas: `base_servo`, `engranaje_motriz`, `engranaje_conducido`, `dedo_izq`, `dedo_der`, `eslabon_paralelo ×2`, `almohadilla ×2` (TPU opcional); 9 interfaces (ejes M3, patrón de servo, pasadores).
3. **Gate 1:** apruebas el árbol en la UI.
4. **Kinematics/Actuation** → geometría de dedos paralelos; fuerza de agarre requerida vs. torque del MG996R (margen 2.1× ✓).
5. **Part Designer ×3 en paralelo** → macros FreeCAD por pieza.
6. **Tolerances** → pasadores M3 a 3.3 mm, eje de engranaje con clearance +0.35 mm, orientación de dedos en plano.
7. **QA** → `dedo_der` FALLA: pared de 0.9 mm junto al pasador → vuelve al diseñador → PASA en la iteración 2.
8. **Assembly + Test** → interferencia entre engranajes a 0° de apertura → reabre `engranaje_conducido` (−0.3 mm de adendo) → barrido sin colisiones.
9. **Slicing** → 2 placas, 71 g PETG, 3 h 40 min, sin soportes salvo `base_servo`.
10. **Gate 2:** revisas en FreeCAD y PrusaSlicer, apruebas → STL/3MF/G-code, BOM (1 MG996R, 6 tornillos M3×12, 6 tuercas M3) e instrucciones de ensamble.
11. **Feedback** (opcional): tras imprimir reportas "el pasador entra muy flojo" → el sistema ajusta el perfil de holguras de tu impresora para próximos diseños.

---

## 12. Estructura del repositorio

```
Intelliprint/
├── SISTEMA_MULTIAGENTE.md
├── docker-compose.yml
├── config/
│   ├── models.yaml
│   ├── printers/prusa_mk4_petg.yaml
│   └── agents/*.md              # prompts de sistema por agente
├── orchestrator/
│   ├── Dockerfile
│   ├── graph.py                 # LangGraph: estados, transiciones, gates
│   ├── agents/                  # un módulo por agente (prompt + esquema + tools)
│   ├── schemas/                 # Pydantic: spec, tree, interface, task, qa_report
│   ├── llm/router.py            # local vs. DeepSeek, presupuestos
│   ├── mcp/client.py            # clientes MCP (HTTP/SSE)
│   └── ui/                      # web de aprobación y seguimiento
├── mcp/
│   ├── mech-toolkit/
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
| **2** | `mech-toolkit` + librería de hardware + QA con mediciones | QA detecta agujeros y paredes fuera de norma en piezas de prueba |
| **3** | Decomposition + diseño paralelo + Assembly + chequeo de interferencias | Garra de 5–8 piezas ensamblada sin interferencias |
| **4** | Kinematics/Actuation/Sim + ciclo de reapertura selectiva | Brazo de 3 GDL con torque validado y barrido sin colisiones |
| **5** | Escalamiento a DeepSeek con presupuesto + UI de gates + feedback de impresión | Brazo de 6 GDL con < 20 % de pasos escalados |

---

## 14. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Modelos de 8B generan macros FreeCAD inválidas | Plantillas de macros + funciones de alto nivel en `mech-toolkit`; RAG sobre la API de FreeCAD; reintento con el error exacto; escalamiento a DeepSeek |
| Piezas diseñadas por separado no encajan | Interfaces definidas antes de diseñar, holguras centralizadas, chequeo de interferencias en el ensamble |
| QA aprueba todo | Otro modelo + checks numéricos obligatorios; el LLM de QA solo interpreta mediciones |
| VRAM insuficiente para varios modelos | `OLLAMA_MAX_LOADED_MODELS`, cola de tareas con paralelismo configurable, modelos cuantizados Q4_K_M |
| Macros con efectos sobre el PC | `validate_macro` + rutas restringidas a `workspace/` |
| Costos de DeepSeek | Reglas de escalamiento explícitas y tope por proyecto |
| Holguras distintas en cada impresora | Perfil por impresora/material calibrado con pieza de prueba y ajustado con feedback |
