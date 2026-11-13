# Intelliprint: cómo es el sistema hoy

Intelliprint recibe una petición en lenguaje natural —«un soporte para un rodamiento 608ZZ», «un pan-tilt con dos servos SG90»— y la convierte en piezas imprimibles en 3D. Las decide con modelos de lenguaje, las construye en FreeCAD y **mide lo construido** antes de darlo por bueno: una pieza se mide contra sus requisitos, y un conjunto de piezas se mueve por todo su recorrido buscando choques.

Este documento describe lo que hay en el código a 2026-11-11, después de la limpieza de F9.13 (limpieza). Hasta esa fecha describía la arquitectura que se planeó en septiembre de 2026, de la que casi nada llegó a existir o sobrevivió. **La numeración de las secciones se conserva** porque `PLAN_PROYECTO.md`, `DECISIONES.md` y el código las citan; donde el contenido original ya no existe, la sección dice qué pasó y qué decisión (ADR) lo explica. Lo que se planeó y no está se resume en § 13. El código retirado sigue en git, en la etiqueta `antes-de-fase-9`.

---

## 1. Vista general

Cinco ideas ordenan el sistema:

- **El modelo propone; el código comprueba y mide.** Ningún agente devuelve texto libre: todos devuelven un esquema que el código valida. Lo que se puede calcular —resistencia, holguras, choques, par de un servo, lista de compras— lo calcula el código.
- **La persona aprueba antes de que se gaste en dibujar.** El concepto de cada pieza, el plan de un conjunto y cada pieza terminada esperan su visto bueno.
- **El estado está en la carpeta del proyecto.** No hay base de datos ni proceso que recuerde por dónde iba. Cada orden da un paso, deja archivos y termina; lanzarla otra vez sobre la misma carpeta sigue donde se quedó.
- **Todo corre en contenedores salvo PrusaSlicer** (ADR-014, § 8).
- **«Local primero» sigue siendo el objetivo y hoy no se cumple.** Los modelos son de DeepSeek, en la nube (ADR-007b). Pasar a modelos locales es F0.11 (migrar), sin hacer (§ 6.1.1).

Hay dos flujos. Al segundo el usuario lo llama **backlog**; en el código y en la línea de órdenes se llama `obra`.

```
 intelliprint pieza "…"                   intelliprint obra "…"   (un backlog)
 ──────────────────────                   ─────────────────────────────────────
 investigador  busca medidas, con cita    desglosador  plan mecánico: piezas y uniones
 requisitos    redacta spec.yaml          plan.py      lo valida contra fichas y perfil
 ingeniero     propone el concepto        ✋ visto bueno al plan
 ✋ visto bueno al concepto                por cada pieza, en orden de dependencias:
 diseñador     escribe construir(kit)        el flujo de pieza entero (a la izquierda)
 FreeCAD       construye                     ✋ «está bien, la siguiente»: se ficha
 medidas       si algo no cumple, vuelve  por cada conjunto:
               al diseñador (5 veces)        se mueve entero y se buscan choques
                                             estudio: par, vuelco, alcance, carga
 → STEP, STL, FCStd e informe             → piezas, ensamble, animación y compras
```

Las órdenes de `intelliprint` (`orchestrator/cli.py`):

| Orden | Qué hace |
|---|---|
| `pieza` | Una pieza suelta: propone el concepto y para; con el visto bueno, la modela |
| `obra` | Un backlog: lo desglosa y diseña una pieza cada vez |
| `banco` | Pide los catorce encargos de `tests/banco/encargos/`, mide lo que sale y da la nota. Cuesta dinero |
| `calibrar` | Construye las piezas de prueba de holguras y las barras de flexión, o apunta lo medido |
| `animar`, `estudio` | Rehacen la animación o el estudio de movimientos de un backlog ya verificado, sin modelo |
| `proyectos` | Lista los proyectos y, con `--archivar`, mueve lo no aprobado a `workspace/archivo/` |
| `perfil importar` | Convierte una calibración de eufyMake Studio en un perfil de PrusaSlicer |

---

## 2. Agentes

Un agente es aquí una llamada a un modelo con unas instrucciones (`config/agents/*.md`) y un esquema de salida obligatorio. Son **cinco**:

| Agente | Qué decide | Qué le comprueba el código | Rol |
|---|---|---|---|
| **Investigador** (`orchestrator/investigar.py`) | Qué componentes nombra la petición sin dar sus medidas, y qué dato sale de cada página encontrada | Que la cita literal está en la página y el número está en la cita | `design` |
| **Requisitos** (`agents/requirements.py`) | La especificación: título, material y una lista de requisitos con identificador | Que lo atribuido al usuario es cita literal de la petición y que ninguna cota en mm se queda sin requisito | `design` |
| **Ingeniero** (`agents/ingeniero.py`) | El concepto: cómo se resuelve, cómo se imprime, cómo se fija, casos de carga y hasta tres preguntas | La resistencia de cada caso de carga (`orchestrator/ingenieria.py`), y que no escriba a mano el alojamiento de un componente con ficha | `reason` |
| **Diseñador** (`agents/disenador_kit.py`) | El programa `construir(kit)` que dibuja la pieza | La lista blanca del programa (§ 6.3) y, ya construida, las medidas de § 3.3 | `reason` |
| **Desglosador** (`agents/desglosador.py`) | El plan mecánico de un backlog: piezas, conjuntos y uniones | `orchestrator/plan.py`, contra fichas y perfil (§ 3.1) | `reason` |

Todos pasan por `orchestrator/llm/structured.py`: si la salida no valida, el error exacto vuelve al modelo, hasta tres intentos. Los de rol `reason` usan el modelo con pensamiento; si se corta dos veces por longitud, contesta el modelo sin pensamiento.

Lo que **no** es un agente de Intelliprint:

- **Crafty** es el agente de OpenClaw que conversa por Telegram, con su propio modelo. Usa Intelliprint por un servidor MCP (§ 8.5, § 9.1) y no diseña nada.
- **El juez JEV** (`orchestrator/juez.py`) es un servicio externo y opcional. Lee el concepto y contesta una sola pregunta: si algún componente queda suelto. Su respuesta es un aviso para la persona; no frena ni rehace nada, y sin `JEV_API_KEY` no se llama.
- **El laminado** (`orchestrator/slicing.py`) es una llamada a PrusaSlicer, sin modelo. El «agente 11» de la tabla original no existe.

La tabla original tenía once agentes. Por qué faltan los demás está en § 13.

---

## 3. Cómo se unen las piezas

El plan original describía interfaces con dos estados, simbólica y resuelta (ADR-001), y un QA que derivaba de ellas lo que había que medir (ADR-011). Ese código se retiró en F9.13 (limpieza) porque ningún flujo lo llamaba. Lo que hay hoy sale de ADR-016, ADR-018 y ADR-020.

### 3.1 El plan mecánico: uniones `fija` y `gira`

El desglosador propone en una sola llamada los nodos del backlog (piezas y conjuntos) y sus uniones (`orchestrator/schemas/obra.py`). Hay dos tipos:

- **`fija`**: dos piezas atornilladas, o una pieza atornillada a algo de fuera. Dice en qué pieza apoya la cabeza, en cuál agarra, la métrica, cuántos tornillos y el agarre: tuerca cautiva, inserto o rosca en el plástico.
- **`gira`**: una pieza que gira sobre la salida de un componente comprado que monta otra pieza (el eje de un servo, el aro de un rodamiento). Dice cuánto recorre y cuánto **radio libre** necesita alrededor del eje, y, si la petición lo dice, hacia dónde mira ese eje con el invento puesto como se usa (`eje`: horizontal o vertical): a la pieza que monta el componente se le mide. Si no la mueve ese componente sino un motor que está al lado, lo dice en `movido_por`: qué motor (va en la misma pieza que el rodamiento), si por correa o por reductora, y con qué relación (F10.2 (transmisión), ADR-021). La transmisión es un dato del giro, no una pieza: el invento sigue siendo un árbol.

El plan no lleva coordenadas. `orchestrator/plan.py` lo comprueba sin modelo: que la salida exista en la ficha del componente, que el recorrido pedido quepa en el de la ficha, que cada actuador mueva una sola pieza (sea en su eje o por una transmisión), que el motor de una transmisión dé par según su ficha, que todo giro esté dentro de un nodo conjunto y que ninguna pieza quede sin unir. Un plan que no se puede construir vuelve al desglosador con el error. Una métrica que el perfil de la impresora no tiene tabulada es un aviso que la persona ve antes de aprobar.

Límite conocido: solo se describen **árboles de giros** sobre la salida de algo comprado. No hay correderas, engranajes ni cadenas cerradas; una pinza de dos dedos con un solo servo no sale (ADR-020). Hoy tres fichas tienen salidas: el SG90, el 608ZZ y el NEMA 17. De una correa sale lo demás sin que lo decida un modelo (`orchestrator/transmision.py`, F10.3 (correa)): la polea del motor es una comprada de 20 dientes, la pieza que gira lleva una de 20 × relación hecha por `kit.polea_gt2`, y los dos ejes van a la distancia de una correa cerrada, sin tensor; las tres cosas se miden en el bucle de cada pieza. El rendimiento (0,9 la correa, 0,7 la reductora) es un supuesto, la ranura del diente es una aproximación, y ningún invento con correa ha pasado por el banco. De una reductora solo existe el dato.

### 3.2 Dónde queda cada pieza

Nadie asigna posiciones de antemano; la resolución de interfaces que lo hacía no existe. Una pieza terminada se convierte en una **ficha** (`obra.fichar`, ADR-018): su forma construida, sus agujeros con nombre y las salidas de lo comprado que monta. La pieza siguiente se diseña contra esa ficha y la coloca en su propio programa con `kit.componente`, igual que colocaría un rodamiento comprado. La posición de cada pieza en el conjunto sale de encadenar esas colocaciones (`conjunto.poses`).

Límites: el hueco que una pieza impresa deja en otra es su caja envolvente, y a la ficha solo pasan los agujeros de eje alineado con x, y o z.

### 3.3 Qué se mide y con qué

Tras cada construcción, `orchestrator/medida.py` reúne lo que la pieza no cumple y se lo devuelve al diseñador con cifras:

- los agujeros que piden los requisitos —diámetro, número y distancias entre centros—, comparados con los rasgos con nombre que el kit registró al taladrar;
- que cada componente comprado **cabe** y **entra** en su sitio, con la forma de su ficha, y que el programa colocó todos los que el concepto nombra;
- las sondas de `mech_toolkit/sondas.py`, que corren en FreeCAD sobre el STEP construido: pared mínima, aristas vivas, acceso de la llave a cada tornillo, aberturas por las que tiene que pasar un cuerpo, y el cilindro libre que el plan reserva a cada giro;
- en un backlog, la pieza que gira se mueve contra lo ya construido en cuanto se construye, F9.5 (parcial);
- en un backlog, los tornillos que el plan prevé y la pieza no lleva, F9.6 (previsto): los de sus uniones (`plan.compras_previstas`) y los que sujetan lo comprado que monta, uno por cada fijación de su ficha. Se cuentan en los agujeros construidos (`tornilleria.tornillos`) por la métrica, las piezas que unen y cómo acaban; uno que rosca en el plástico no cuenta si su agujero es tan ancho como él. De una unión entre dos piezas responde la que se diseñó después; la que se diseña antes, de su mitad.

`derive_assertions` y las aserciones por tipo de interfaz no existen. De ADR-011 queda la regla de fondo: el programa del diseñador declara **dónde** va cada cosa, y la forma se mide en lo construido o se toma de la ficha, que el programa no puede cambiar.

---

## 4. Los dos flujos y sus paradas

El plan original era una máquina de estados sobre LangGraph (`INTAKE → … → RELEASED`) con dos barreras humanas. Se retiró en F9.13 (limpieza) (ADR-008, enmienda). Hoy no hay grafo: `orchestrator/pieza.py` y `orchestrator/obra.py` miran qué archivos hay en la carpeta y dan el paso que toca.

**Una pieza** pasa por: concepto por aprobar → concepto aprobado → diseñada, o con fallos.

**Un backlog** pasa por: plan por aprobar, y después cada nodo en orden de dependencias. Un nodo pieza recorre los estados de una pieza y queda «lista» cuando la persona la da por buena; está «bloqueado» mientras no lo estén los nodos de los que depende, y «por revalidar» si se corrigió algo de lo que tiene debajo y falta comprobarla contra ello. Un nodo conjunto pasa de «por verificar» a «verificado» o «con choques».

Las reglas del plan original, con su número —el código y las ADR las citan así— y lo que vale hoy:

1. **Estados de una pieza.** Los de arriba. La lista `TODO … PASS | FAIL` de `orchestrator/schemas/part_task.py` es del plan original y ningún flujo la recorre.
2. **Reintentos.** Hasta cinco construcciones por pieza; cada fallo vuelve al diseñador con su motivo. Cada llamada a un modelo admite tres intentos.
3. **Un choque va a la pieza que lo causa** (F7.7 (culpable)): la que incumple el radio libre que el plan le reservó o, en un backlog sin plan, la que se diseñó después. El sistema escribe la corrección con cifras y la persona la manda; no se corrige solo.
4. **Corregir una pieza no rehace lo que se diseñó contra ella: lo revalida** (F9.9 (revalidar), `orchestrator/revalidar.py`). Lo ya construido encima queda «por revalidar» y, cuando la pieza corregida vuelve a estar lista, se comprueba sin modelo contra su ficha nueva: que los agujeros con nombre, lo montado y las salidas que tenía sigan igual, que siga cabiendo, entrando y tocando donde la otra la colocó, y que no aparezca un defecto del plan que no tuviera. Si vale no se toca; si no, se corrige partiendo de ella. Lo que no llegó a construirse y la verificación del conjunto sí se archivan. Nada se borra.
5. **Si se agotan los intentos no se escala a otro modelo.** Se entrega la construcción que menos falla (F6.8 (mejor)), `blocked.md` dice qué no cumple, y decide la persona.
6. **No hay diseño en paralelo.** Las piezas se diseñan de una en una. Cada construcción es un proceso `freecadcmd` propio.
7. **Esperar a la persona no cuesta nada.** El proceso termina en cada parada, así que un proyecto puede esperar días y sobrevive a un reinicio. Como va una pieza cada vez, una parada sí detiene el backlog entero.
8. **Un cambio pedido por la persona entra por el mismo camino.** En una pieza suelta crea una versión nueva del proyecto; en un backlog corrige el programa de la pieza ya construida, o la rehace desde cero si se pide. **Añadirle una función a un backlog** (F9.10 (ampliar), `orchestrator/ampliar.py`) es otra parada: el desglosador propone el plan con lo nuevo, el código comprueba que no quita ni cambia nada de lo aprobado, y la propuesta espera en `ampliacion.json` sin tocar `obra.json`. Al aprobarla se archivan el plan anterior y la verificación del conjunto, y de las piezas hechas solo se corrige la que la función toca; lo demás sigue listo.
9. **Un trabajo a la vez** (`orchestrator/jobs.py`). No hay cola: una segunda petición se rechaza diciendo cuál está en marcha.

### 4.1 Antes de dibujar: investigación, requisitos y concepto

No hay conversación de admisión dentro de Intelliprint. Lo que impide modelar sin que la persona haya visto qué se va a hacer es el visto bueno al concepto (ADR-015, F3.20 (concepto)):

1. El código mira qué componentes con ficha nombra la petición (§ 10); esos no se buscan. Lo demás que venga sin medidas lo busca el investigador en internet, y cada dato trae su URL y una cita literal comprobada.
2. El agente de requisitos redacta `spec.yaml`. Cada requisito lleva su origen: `usuario` (cita literal), `catalogo` (buscado) o `estimado`.
3. El ingeniero propone el concepto y el código calcula si aguanta. Queda en `concepto.md` y el flujo para.
4. La persona aprueba desde la web o por Crafty. Si en vez de aprobar contesta a las preguntas, el ingeniero propone otro concepto.

A Intelliprint solo le llega el texto de la petición: no recibe fotos ni archivos. Crafty sí ve las fotos y pasa a texto lo que haga falta.

### 4.2 Clases de producto

`Spec` conserva el campo `product_class` (`static_part`, `mechanism`, `robot`) y el esquema sigue exigiendo los datos de cada clase, pero ningún flujo decide nada con él: las fases condicionales de ADR-010 se fueron con el grafo. Lo que separa los casos es la orden que se lanza: `pieza` para una pieza, `obra` para varias.

---

## 5. Lo que queda en disco

### 5.1 El registro de proyectos

No hay `registry.sqlite` ni `state.sqlite`. `orchestrator/registry.py` clasifica cada carpeta por lo que tiene dentro —aprobado, con reparos, por aprobar, en marcha, fallido, incompleto, antiguo— y escribe un índice legible, `INDEX.md` (ADR-009, enmienda). Un proyecto en marcha se reconoce por su `job.json` y por un archivo `latido` que el proceso toca mientras trabaja.

```
workspace/
├── projects/     los proyectos; el nombre es fecha, hora y un resumen de la petición
├── archivo/      lo que `proyectos --archivar` movió: archivar no es borrar
├── banco/        una carpeta por corrida del banco, con su informe
└── impresoras/   lo que el usuario midió en su impresora (§ 7)
```

En la web, las ejecuciones de una misma petición se agrupan como versiones de un proyecto (`orchestrator/web/versiones.py`).

### 5.2 Archivos de un proyecto

Una pieza suelta:

```
<proyecto>/
├── request.md, job.json, run.log    la petición, quién la lanzó y lo que fue imprimiendo
├── investigacion.json               lo buscado en internet, con sus citas
├── spec.yaml, pieza.json            los requisitos y el título
├── concepto.json, concepto.md       lo que se aprueba; `concepto_aprobado` es la marca
├── juez.json                        el aviso de JEV, si lo hubo
├── parts/<pieza>/
│   ├── programa.py, recipe.json     lo que escribió el diseñador
│   ├── build.py                     el guion que ejecuta FreeCAD; lo compone el código
│   ├── <pieza>.FCStd / .step / .stl
│   └── rasgos.json, envolvente.json agujeros y componentes con nombre: de aquí salen medidas y compras
├── intentos/                        cada intento rechazado, con su motivo
├── rounds.json, pieza_report.json   el resultado
├── blocked.md                       si no salió, qué falla
└── design_cost.md, design_cost.json el gasto desglosado
```

Un backlog añade `obra.json` y `obra.md` (el plan), la marca `obra_aprobada`, `fichas/` (una ficha por pieza dada por buena) y `nodos/<id>/`. El nodo de una pieza es una carpeta de pieza completa más `uniones.json` (lo que el plan decidió de ella) y `lista.json`. Una ampliación a medias deja `ampliacion_pedida.json` o `ampliacion.json` y `ampliacion.md`; las aprobadas quedan en `ampliaciones.json`, con la huella de cada pieza justo antes. El nodo de un conjunto guarda `verificacion.json`, `assembly.FCStd`, `ensamble.json`, `animation.gif`, `estudio.json` y `estudio.md`.

No hay un repositorio git por proyecto: el commit por etapa lo hacía el grafo y se fue con él (F1.15).

---

## 6. Modelos

### 6.1 Perfiles y roles

Los agentes piden un **rol**, y `config/models.yaml` dice qué modelo lo atiende según el perfil activo (`INTELLIPRINT_PROFILE`):

| Rol | Perfil `dev` (el activo) | Perfil `prod` (sin cablear) |
|---|---|---|
| `design` | `deepseek-chat` | `qwen3.8` en Ollama |
| `reason` | `deepseek-reasoner` | `qwen3.8` con pensamiento |
| `qa` | `deepseek-chat` | `gemma3:12b` |
| `embed` | ninguno | `nomic-embed-text` |

Hoy solo se piden `design` y `reason`; `qa` y `embed` están definidos y nadie los usa. `deepseek-chat` y `deepseek-reasoner` son dos nombres del mismo modelo de DeepSeek, sin y con pensamiento; el detalle y los precios están en `config/models.yaml`.

La máquina de destino tiene una RTX 5090 de 32 GB. Los dos modelos locales de `prod` caben a la vez (unos 25 GB) si Ollama arranca con `OLLAMA_MAX_LOADED_MODELS=2` (ADR-007); con 1, cada cambio de modelo paga una recarga.

### 6.1.1 El perfil `dev` es deuda declarada

Usar DeepSeek como proveedor principal incumple «local primero» a propósito (ADR-007b). Para saldarlo falta lo que pide F0.11 (migrar): escribir el cliente de Ollama —hoy `orchestrator/cli.py` termina con un error claro si el perfil no es de DeepSeek— y volver a pasar la suite y el banco con modelos locales. Lo que funciona con DeepSeek no está probado en local: DeepSeek sigue esquemas mejor que `qwen3.8`, así que sus resultados sirven para descartar problemas, no para dar algo por bueno. Mientras tanto, todas las peticiones, especificaciones y programas salen hacia la API de DeepSeek.

### 6.2 Gasto y tope

El plan preveía DeepSeek solo como escalamiento, para cuando el modelo local fallara. Con el perfil `dev` no hay a quién escalar. El router conserva la previsión para `prod`, donde la clave de DeepSeek sería opcional.

Lo que sí funciona es el control de gasto (`orchestrator/llm/cost.py`). Cada proyecto apunta sus llamadas en `design_cost.md`, y antes de cada paso se comprueba que no ha pasado de `escalation.max_usd_per_project`, que el usuario fijó en 3 USD el 2026-11-11 (antes, 5; F5.12 (tope)). Un backlog entero —un robot— tiene el suyo aparte, `escalation.max_usd_per_backlog`, de 50 USD; cada una de sus piezas sigue teniendo además el de una pieza. Como se mira al empezar el paso, un proyecto puede pasarse en lo que cueste ese paso.

### 6.3 El programa del diseñador y su lista blanca

La «escotilla de Python libre» que describía esta sección —macros libres vigiladas por `validate_macro`— no está en el código, y las recetas de generadores dejaron de ser el camino normal. Desde la enmienda de ADR-002 (F5.18 (kit)), el diseñador escribe una función `construir(kit)` en Python usando solo las operaciones del kit (`mech_toolkit/kit/`): cajas, cilindros, perfiles extruidos y de revolución, uniones y restas, redondeos y chaflanes, taladros, tornillos y tuercas con la tabla del perfil, y la colocación de componentes con ficha.

`mech_toolkit/kit/sandbox.py` valida el programa contra una lista blanca antes de ejecutarlo: sin `import`, sin `open`, sin clases, sin `try`, y sin atributos que no sean de la API del kit. Lo que no pasa vuelve al modelo con la línea y el motivo.

Las recetas (`orchestrator/schemas/recipe.py`, `orchestrator/recipes/compose.py`, `mech_toolkit/generators.py`) siguen en el código para una cosa: construir las piezas de calibración.

---

## 7. Perfil de impresora y reglas de impresión

Las holguras, los diámetros de agujero por métrica, las paredes mínimas, el voladizo y el puente máximos, la cama y la resistencia estimada del material están en `config/printers/<impresora>.yaml`. `config/impresion.yaml` elige el perfil activo —hoy la AnkerMake M5 con PLA+— y el perfil de laminado de PrusaSlicer que le corresponde. Esos valores llegan al ingeniero y al diseñador dentro de sus instrucciones, y el kit los aplica al taladrar: el diseñador escribe `tornillo("M3")`, no un diámetro. El perfil trae M3 entero y M4 y M5 pasantes; los demás agujeros de tornillo (un M2 de rosca, la tuerca de un M4) los apunta la persona en la página «Impresora», se guardan con sus otras medidas en `workspace/impresoras/` y se suman a la tabla, F9.8 (métricas). Lo que no esté, el kit no lo taladra y el plan lo avisa.

**Los valores de `config/printers/` son valores por defecto, sin calibrar.** `M3_through_mm: 3.3` es deuda declarada y no se cambia sin medir. El usuario calibra imprimiendo las piezas de `intelliprint calibrar`, F2.18 (calibración), y apunta lo medido en la página «Impresora» de la web, F2.21 (impresora). Eso se guarda en `workspace/impresoras/` y manda sobre `config/printers/`, que no se toca.

El diseño **no lamina** (ADR-014, enmienda): los gramos y el tiempo salen cuando la persona abre la pieza en PrusaSlicer desde la web.

### 7.1 Quién decide que una pieza vale

El QA de tres capas —aserciones derivadas de interfaces, chequeos sobre el STL y un revisor con visión— se retiró en F9.13 (limpieza): solo se había escrito una parte y ningún flujo vivo la llamaba (ADR-003 y ADR-011, enmiendas). El principio se mantiene por otros medios: **ningún modelo aprueba nada**.

- Una pieza queda «resuelta» solo si las medidas de § 3.3 no encuentran defectos. Son comparaciones numéricas.
- Un conjunto queda «verificado» si al moverlo por todo el recorrido de sus articulaciones, en pasos de 10°, no hay choques (`orchestrator/conjunto.py`). La holgura que se exige al moverse es la mitad de la holgura deslizante del perfil. El recorrido de cada giro es el que pide el plan, la mitad a cada lado de como se dibujó la pieza, sin pasar de lo que da el actuador; y dos piezas sin ningún giro por medio —atornilladas una a otra— pueden tocarse, pero no atravesarse (los dos, desde el banco 1112-1359).
- Lo que se atornilla después necesita sitio (F9.10 (ampliar), `medida.sin_sitio_para_lo_nuevo`): en una unión `fija` con una pieza que aún no existe, la que taladra primero no puede poner los tornillos dando a lo que tiene debajo. Se mide con cajas, en 20 mm de fondo y dos diámetros alrededor: es un criterio, no una medida, y pide poco. En el banco 1112-1359 dio por buena la cara de abajo de la plataforma (12 mm) para una pieza de 85 × 73 mm cuyo dedo necesitaba 40 mm libres: no miraba qué necesita la pieza que viene. Ahora, si esa pieza monta un actuador sobre el que girará otra, se busca saliendo de los agujeros (cada 10 mm, hasta dos veces el radio libre del giro) un punto donde quepa ese eje, contando que bajo la base está aquello en lo que se apoya; si no lo hay, el defecto dice por qué caras de la pieza sí (`medida._sitio_para_un_giro`). Y a la pieza que agarra se le dice de qué lado de los agujeros va (donde sale el tornillo, no donde entra la cabeza); si se pone al revés, el recuento de tornillos lo dice así.
- La nota global la da el **banco** (`orchestrator/banco.py`, F6.1 (evaluación)): catorce encargos con lo esperado escrito a mano desde la petición y medido en la pieza construida. A un backlog se le puede pedir además hasta dónde llega y cuánto levanta (`alcance` y `carga`, F10.1 (serie)): salen del estudio de movimientos, con el material medido en FreeCAD. El alcance se mide del hombro —el primer giro que levanta— a la punta, en perpendicular a su eje, para que un desvío a lo largo de ese eje no cuente como brazo; si no se sabe el par de lo que mueve un giro, o el material no se midió, queda sin medir. Lo que el banco aún no sabe medir cuenta como no aprobado.
- «Lista» lo decide la persona. «Impresa y probada» es otra marca, que solo puede poner ella.

Límites: nadie mira la pieza con visión, y pasar todas las medidas no significa que la pieza sea lo que la persona imaginaba. El barrido no ve un choque que ocurra entre dos puntos de la rejilla de 10°. No mide los pares cuyas cajas están más separadas que la holgura, que no pueden rozarse; prueba todas las combinaciones, así que con cuatro giros o más no acaba.

---

## 8. Dónde corre

### 8.1 Topología

```
┌───────────────────── PC con Windows (host) ──────────────────────┐
│  PrusaSlicer  ◄──  scripts/host_bridge.py  (MCP, puerto 8102)     │
│  FreeCAD de escritorio: solo para abrir los .FCStd que salen      │
│  workspace/   config/   library/      (carpetas montadas)         │
└──────────────────────────────▲───────────────────────────────────┘
                               │ host.docker.internal
┌──────────────────────────────┴───── Docker ──────────────────────┐
│  orchestrator      ejecuta una orden y termina                    │
│  suite             pytest, con el código montado en vivo          │
│  web               FastAPI, http://localhost:8080                 │
│  intelliprint-mcp  las herramientas para Crafty, en la red interna│
│  crafty-config     genera la configuración de Crafty y termina    │
│  crafty            OpenClaw  ──►  Telegram                        │
│  (ollama)          opcional, perfil `ollama`; nadie lo usa aún    │
└──────────────────────────────────────────────────────────────────┘
```

Todos menos `crafty` y `ollama` usan la misma imagen (`docker/orchestrator.Dockerfile`): Python y FreeCAD 1.1.3, la misma versión que el escritorio. No hay Qdrant, ni un servicio aparte para `mech-toolkit`, ni simulación física.

### 8.2 El puente al PrusaSlicer del host

El `mcp-proxy` para FreeCAD y PrusaSlicer que describía esta sección nunca se construyó (ADR-014). FreeCAD va dentro del contenedor y se lanza como subproceso. PrusaSlicer se queda en el PC porque es donde la persona mira qué va a imprimir, y el contenedor se lo pide a `scripts/host_bridge.py`, que arranca `scripts/start-host-mcps.ps1`. El puente ofrece dos herramientas: `laminar` y `abrir_en_prusaslicer`.

El mismo archivo tiene un nombre dentro del contenedor y otro en el host; `orchestrator/hostpaths.py` traduce las rutas con `HOST_WORKSPACE`. Sin el puente arrancado no hay laminado ni botón de PrusaSlicer.

### 8.3 Qué puede tocar el sistema en el PC

- El contenedor monta `workspace/` en lectura y escritura, y `config/` y `library/` en solo lectura. No se monta el disco entero ni el socket de Docker.
- El puente del host solo acepta archivos de dentro de `workspace/`, y el perfil de laminado se le pide por nombre y lo resuelve él en `config/slicing/`. Lo comprueba aunque el contenedor ya lo haya comprobado.
- El único código escrito por un modelo que se ejecuta es `construir(kit)`, y solo si pasa la lista blanca de § 6.3, que se valida al recibir el programa y otra vez dentro de FreeCAD.

`validate_macro`, que esta sección describía como red de seguridad de la escotilla (ADR-005), no está en el código. Límite conocido: FreeCAD no corre aislado en un contenedor desechable y sin red; lo que separa el programa del modelo de `workspace/` es la lista blanca, no un aislamiento del proceso.

### 8.4 `docker-compose.yml`

El archivo real está en la raíz del repositorio y lleva comentado el porqué de cada servicio. El ejemplo que había aquí era del diseño original.

```bash
docker compose run --rm suite                                    # la suite rápida
docker compose run --rm orchestrator pieza peticion.md --archivo
docker compose run --rm orchestrator obra peticion.md --archivo
docker compose up -d web                                         # http://localhost:8080
docker compose up -d crafty                                      # Telegram
```

Tres cosas que conviene saber antes de tocarlo: `web` publica el puerto solo en `127.0.0.1` salvo que se defina `WEB_BIND`, porque la página no tiene contraseña; `intelliprint-mcp` no publica ningún puerto; y recrear el contenedor que está diseñando mata ese trabajo, que después se retoma con «continuar».

### 8.5 Los canales: la web y Crafty

El `HumanPort` con sus tres adaptadores se retiró en F9.13 (limpieza) (ADR-006, enmienda). De aquella decisión queda el fondo: **el canal no es un agente y no diseña**. Hay dos canales, y los dos lanzan los mismos trabajos con `orchestrator/jobs.py`:

- **La web** (`orchestrator/web/`, FastAPI, con el HTML generado en Python). Permite pedir una pieza o un backlog, cancelar el diseño en marcha (solo si lo lanzó la propia web: el de Crafty corre en otro contenedor y se cancela desde Crafty), aprobar o contestar el concepto y el plan, dar por buena cada pieza o pedir rehacerla, ver el conjunto en 3D moviendo sus articulaciones, leer el estudio de movimientos y la lista de materiales, bajar el proyecto en zip, abrirlo en PrusaSlicer, ver las corridas del banco y apuntar las medidas de la impresora.
- **Crafty** (`config/openclaw/`), un agente de OpenClaw en su propio contenedor que conversa por Telegram con su propio modelo y llama a las quince herramientas de `orchestrator/mcp_server.py`. Su configuración la genera `orchestrator/crafty.py` desde el `.env`, sin secretos en el archivo.

Las reglas de seguridad del canal, con su número original (ADR-012 las cita) y su estado:

1. **Lista blanca.** Opcional, por decisión del usuario (ADR-012, F5.10 (lista)): sin `TELEGRAM_ALLOWED_USERS` el canal va abierto, y quien encuentre el bot puede lanzar proyectos y gastar saldo. En grupos Crafty no atiende.
2. **El texto que entra es dato.** Las herramientas del MCP reciben una petición de diseño y devuelven datos; ninguna ejecuta código. La web escapa todo texto escrito por un modelo antes de pintarlo.
3. **Un cambio pedido por el canal no abre un camino de código libre**, porque ese camino no existe (§ 6.3).
4. **Filtro de salida.** No hay un filtro escrito. Lo que acota la salida es el montaje: Crafty no ve `workspace/`, solo el buzón al que el MCP copia los archivos de un proyecto (`jobs.entregar`).
5. **Lista blanca de adjuntos.** Intelliprint no recibe adjuntos (§ 4.1); la lista se fue con ellos.
6. **El contenido de una imagen es dato.** Las fotos solo las ve Crafty; a Intelliprint le llega el texto que Crafty escriba.
7. **Los adjuntos no se ejecutan.** No llegan: el volumen donde OpenClaw guarda las fotos no se monta en Intelliprint.

La prueba de inyección que pide F5.9 (seguridad) no está escrita.

---

## 9. Servidores MCP y herramientas deterministas

### 9.1 Los dos servidores MCP que hay

| Servidor | Dónde corre | Quién lo llama | Qué ofrece |
|---|---|---|---|
| `orchestrator/mcp_server.py` (`intelliprint-mcp`) | Contenedor, red interna, puerto 8200 | Crafty | Pedir una pieza o un backlog, aprobar, dar por lista, rehacer, modificar, continuar, cancelar, consultar estado y archivos, listar, ordenar y buscar medidas |
| `scripts/host_bridge.py` | El PC, puerto 8102 | El contenedor, con `orchestrator/mcp/client.py` | `laminar` y `abrir_en_prusaslicer` |

No hay servidor MCP de FreeCAD ni de simulación.

### 9.2 `mech-toolkit`: un paquete, no un servicio

`mcp/mech-toolkit/mech_toolkit/` se instala junto al orquestador y se importa como cualquier paquete de Python. Convertirlo en un servicio MCP era F2.1 (servicio), que no se hizo. Contiene:

| Módulo | Qué hace |
|---|---|
| `kit/` | Las operaciones con las que el diseñador escribe la pieza, y la lista blanca que valida su programa |
| `sondas.py` | Las medidas sobre el STEP construido, que corren dentro de FreeCAD |
| `componentes.py` | Coloca la forma de una ficha en la pieza y construye sus sólidos |
| `profile.py` | El perfil de impresora y sus holguras |
| `transmisiones.py` | Las cuentas de una correa GT2: los diámetros de una polea, el largo de la correa y la distancia entre ejes que pide |
| `measure.py`, `geometry.py` | Extraen las caras cilíndricas de una pieza y buscan agujeros y salientes por su posición; los usa el banco para juzgar. `geometry.py` da además la colocación de una pieza en el ensamble |
| `generators.py` | El catálogo de ocho generadores de las recetas; hoy construye las piezas de calibración |
| `library_models.py` | Importa los modelos de referencia de `library/models/reference/` |

### 9.3 Cómo se usa FreeCAD

Solo sin interfaz. Cada construcción, cada tanda de sondas y cada barrido de choques es un proceso `freecadcmd` que arranca, hace su trabajo y termina, con un tiempo máximo. Las imágenes y las animaciones se dibujan con matplotlib a partir de las mallas, sin FreeCAD. La interfaz gráfica es la del escritorio de la persona, que abre los `.FCStd` que quedan en `workspace/` (ADR-004, con la enmienda de ADR-014); `orchestrator/fcstd.py` los retoca para que se abran con las piezas visibles.

---

## 10. Fichas de componentes

Ningún modelo debe sacar de memoria las medidas de un servo. Un componente comprado es **geometría con ficha y fuente** (ADR-016): `library/components/*.yaml`, leídas por `orchestrator/componentes.py`. Hay ocho: `608zz`, `hc-sr04`, `mg996r`, `nema17`, `perfil-2020`, `polea-gt2-20`, `raspberry-pi-4` y `sg90`.

Una ficha dice qué es sólido (`cuerpos`), qué hay que dejar libre y por qué (`despejar`: un cable, el haz de un sensor), dónde se atornilla y con qué (`fijacion`), qué mueve (`salidas`: el eje de un servo con su recorrido y su `acople`, el cuerno al que se atornilla lo que gira, F9.7 (acople)) y, en los servos, su par y su masa; en el paso a paso, su par de retención. Cada fijación dice qué tornillo lleva, si viene con el componente y si rosca en la pieza impresa o en el propio componente. Las fuentes van citadas en la propia ficha.

Qué componentes nombra una petición lo decide el código, por los alias de la ficha. Lo que tiene ficha no se busca en internet ni se convierte en requisitos sueltos. De las fichas salen también la lista de materiales y la tornillería (`orchestrator/materiales.py`, `orchestrator/tornilleria.py`), contadas en lo construido, y el estudio de movimientos (`orchestrator/estudio.py`): si aguanta cada servo, si vuelca, hasta dónde llega, cuánto tarda y cuánta carga admite. Si un giro lleva transmisión, el par del motor llega al eje multiplicado por la relación y por el rendimiento supuesto, y la velocidad dividida por la relación.

Límites conocidos:

- **Ninguna ficha está medida con calibre**: las ocho llevan `verificado: false`.
- Las formas son cajas y cilindros alineados con los ejes, y un componente solo se gira de 90 en 90°.
- Un componente sin ficha sigue adelante con las cifras sueltas que encuentre el investigador. El borrador de ficha que la persona aprueba es F9.11 (borrador), pendiente.
- El estudio de movimientos estima la masa de lo impreso sin laminar.

`library/models/reference/` es otra cosa: modelos STEP descargados de terceros, con autor, licencia y huella, que los tests usan como referencia independiente.

---

## 11. Un ejemplo real: el pan-tilt del banco

Es la corrida `1111-1342` del banco, la que se cita en `PLAN_PROYECTO.md` (Fase 9). El visto bueno de cada paso lo dio el propio banco; en uso normal lo da la persona.

1. **Petición**: un pan-tilt con dos servos SG90.
2. **Plan mecánico**: tres piezas (`base`, `soporte-inclinacion`, `plataforma-camara`) y un conjunto (`pan-tilt`). Una unión `fija` —la base, con dos M3, a lo que haya fuera— y dos `gira` de 180° sobre el eje de un SG90: el plan reserva 50 mm de radio libre al giro y 35 mm a la inclinación.
3. **Cada pieza, por orden**: investigación, requisitos, concepto, programa y medidas. El soporte salió al tercer intento y la plataforma al segundo; los intentos rechazados lo fueron dentro de su propio bucle, sin intervención.
4. **Conjunto**: se movió entero en la rejilla de 10° sin un solo choque. Queda el ensamble, la animación y el estudio de movimientos.
5. **Coste**: 45 minutos y 0,53 USD en 20 llamadas. Nota del encargo: cinco comprobaciones de cinco.

Lo que esta corrida no dice: es una sola, y el banco tiene ruido de una corrida a otra; la plataforma que salió es un disco coaxial con el eje de inclinación, que pasa las cinco comprobaciones pero no serviría para cabecear una cámara; y la tornillería ni se planificó ni se midió. Desde F9.6 (previsto) el encargo pide los cuatro tornillos de sus dos servos, y esta corrida, rejuzgada, tenía cero que agarraran. Reanudada una vez, agarran los cuatro, pero al rehacerse la plataforma dejó de caber la cámara: 6 de 7 (1,46 USD). Reanudada otra vez, la plataforma se rehízo con una cara plana de 29 × 27 y pasa 7 de 7 (1,64 USD en total, con cinco reanudaciones).

---

## 12. Estructura del repositorio

```
Intelliprint/
├── SISTEMA_MULTIAGENTE.md       este documento
├── PLAN_PROYECTO.md             las tareas con su ID y la deuda técnica declarada
├── DECISIONES.md                las ADR, con sus enmiendas
├── docker-compose.yml, docker/  los contenedores (§ 8)
├── config/
│   ├── models.yaml, impresion.yaml, categorias.yaml
│   ├── agents/                  las instrucciones de los cinco agentes
│   ├── printers/, slicing/      perfil de diseño y perfil de laminado
│   └── openclaw/                Crafty
├── orchestrator/
│   ├── cli.py                   las órdenes (§ 1)
│   ├── pieza.py, obra.py        los dos flujos (§ 4)
│   ├── ampliar.py, revalidar.py añadir una función y comprobar lo que había (§ 4)
│   ├── agents/, investigar.py   los agentes (§ 2)
│   ├── plan.py, medida.py, conjunto.py, estudio.py   lo que no decide un modelo
│   ├── componentes.py, tornilleria.py, materiales.py fichas y compras (§ 10)
│   ├── build.py, assembly.py, animation.py           FreeCAD y dibujo
│   ├── banco.py                 el banco de pruebas (§ 7.1)
│   ├── llm/, schemas/, recipes/ modelos, esquemas y recetas
│   ├── jobs.py, registry.py     trabajos y registro (§ 5)
│   ├── mcp_server.py, mcp/      el MCP para Crafty y el cliente del puente (§ 9.1)
│   └── web/                     la interfaz web (§ 8.5)
├── mcp/mech-toolkit/            el paquete `mech_toolkit` (§ 9.2)
├── library/                     fichas de componentes y modelos de referencia (§ 10)
├── scripts/                     el puente del host y dos medidores
├── tests/                       la suite y los encargos del banco
└── workspace/                   el trabajo del usuario; no se versiona ni se borra
```

---

## 13. Lo que se planeó y no está

| Qué | Qué pasó | Dónde se explica |
|---|---|---|
| Once agentes: Decomposition, Kinematics, Actuation, Electronics, Tolerances/DFM, QA, Assembly, Test/Sim y Slicing como agentes | No llegaron a escribirse como agentes. Lo que hacían lo hace código (holguras, ensamble, choques, laminado) o no se hace (elegir actuadores, electrónica) | ADR-015, ADR-018, ADR-020 |
| Flujo `mecanismo`: Mechanism Designer, Design Reviewer y `mcp/sim` | Se hizo y se quitó: pedía el mecanismo entero en una llamada y los grandes no salían | ADR-013 (enmienda), ADR-018 |
| Part Designer de recetas | Se hizo y se quitó: el catálogo solo sabía cajas y cilindros. Lo sustituye el kit | ADR-002 (enmiendas) |
| Interfaces simbólicas y resueltas, `derive_assertions`, QA de tres capas con visión | Se hizo en parte y se quitó: ningún flujo vivo lo llamaba | ADR-001, ADR-003, ADR-011 (enmiendas) |
| Grafo de LangGraph, `intelliprint new` y `resume`, `state.sqlite`, commit de git por etapa | Se hizo y se quitó: la web, Crafty y el banco ya pedían con `pieza` | ADR-008 (enmienda), F1.14, F1.15 |
| `HumanPort`, bot propio de Telegram, adjuntos | Se hizo y se quitó: lo sustituyó Crafty, y los adjuntos solo los leía el flujo de mecanismos | ADR-006 (enmienda), F5.6 (telegram) |
| `registry.sqlite` | No se hizo: un índice aparte se desincroniza; la carpeta manda | ADR-009 (enmienda) |
| Modelos locales con Ollama y DeepSeek solo como escalamiento | Pendiente: falta el cliente de Ollama | ADR-007b, F0.11 (migrar) |
| Qdrant y búsqueda semántica | No se hizo: solo servía a la escotilla | F2.19 |
| Escotilla de Python libre y `validate_macro` | No se hizo: el kit con lista blanca cubre lo que el catálogo no sabía | ADR-002 (enmienda), F2.9 (escotilla) |
| MCP de FreeCAD con `mcp-proxy`; `mech-toolkit` como servicio | No se hizo: FreeCAD está en el mismo contenedor que quien lo llama | ADR-014, F2.1 (servicio) |
| Cinemática inversa, PyBullet, URDF, ROS y Gazebo | No están en el código. El usuario lleva ROS y la simulación aparte; aquí queda el estudio de movimientos | ADR-017 (enmienda) |
| Diseño de piezas en paralelo y varios proyectos a la vez | No se hizo: un trabajo cada vez | § 4, reglas 6 y 9 |
| Laminar dentro del diseño | Se hizo y se quitó por decisión del usuario: al diseñar no se sabe en qué impresora se imprimirá | ADR-014 (enmienda) |
| Carpeta `ui/` y adaptador web del `HumanPort` | La web es `orchestrator/web/` y llama a los trabajos directamente | § 8.5 |
| Hoja de ruta y tabla de riesgos de este documento | Viven en `PLAN_PROYECTO.md`, que es el que se mantiene | `PLAN_PROYECTO.md` |

Lo que está planeado y todavía por hacer no va en esta tabla: está en `PLAN_PROYECTO.md`. De la Fase 9 faltan F9.11 y F9.12 (el borrador de ficha y las pantallas); ampliar un invento, F9.10, está hecho y en el banco no pasa: 7 de 9, 8 de 9 con una reanudación y 0 de 9 con la segunda (el pan-tilt con pinza: el plan se amplía bien, pero la plataforma no acierta a poner los tornillos de la pinza donde hay sitio, y el soporte de la pinza, rehecho, no llegó a construirse). La Fase 10 (brazos con transmisión, ADR-021) está aprobada y empezada: de ella existe lo que mide el banco en F10.1 (serie), con un brazo de tres ejes con servos que pasa sus ocho comprobaciones, y F10.2 (transmisión): el plan dice qué motor mueve un giro y con qué relación, y el estudio hace la cuenta. Y F10.3 (correa): el kit dibuja la polea GT2 y cada pieza mide su parte de la correa. No hay reductoras. El primer invento con transmisión, el encargo 14, se quedó en 6 de 10 en el banco: el plan salió bien, pero el soporte se dibujó tumbado (el eje, vertical) y con el eje del motor sin asomar. Desde entonces las dos cosas se le miden, y el rodamiento en el que gira una pieza no cuenta para los choques.
