# Intelliprint — Registro de decisiones de arquitectura

Cada entrada explica **por qué** el sistema es como es. [SISTEMA_MULTIAGENTE.md](SISTEMA_MULTIAGENTE.md) describe el *qué*; esto describe el *por qué* y qué se descartó.

Fecha de la sesión: **2026-09-18**.

---

## ADR-001 · Las interfaces tienen dos estados: simbólica y resuelta

**Estado:** aceptada · **Afecta a:** § 3, § 4 de la arquitectura; F3.1–F3.4

**Problema.** El diseño original ponía `Decomposition` en la Fase 1 y `Kinematics`/`Actuation` en la Fase 2, pero pedía a `Decomposition` que emitiera interfaces con geometría concreta (`frame: {origin: [0, 0, 45]}`). Eso es imposible de hacer bien: el `45` depende de longitudes de eslabón que aún no se han calculado, y el patrón de tornillos depende de un motor que aún no se ha elegido. El modelo no tenía más opción que inventar. Peor: el **gate humano #1** hacía aprobar precisamente esos números inventados, que la Fase 2 iba a cambiar después.

**Decisión.** Una interfaz nace **simbólica** (tipo, piezas, clase de hardware, `fit`, rol — sin una sola cota) y la Fase 2 la **resuelve** a números por código. El gate #1 se mueve detrás de la resolución.

**Alternativas descartadas.**
- *Reordenar el grafo* (cinemática antes que descomposición): circular. La cinemática necesita saber qué eslabones existen, y eso sale de la descomposición. Además no aplica a productos sin cadena cinemática, como la garra o el soporte NEMA17.
- *Dejarlo y confiar en la reapertura selectiva*: pagas iteraciones de LLM para corregir números que nunca debieron inventarse, y apruebas en el gate algo que sabes que va a cambiar.

**Consecuencias.** El esquema `Interface` gana un estado y el validador impide que una interfaz `symbolic` llegue a la Fase 3. Aparece una dependencia invertida respecto al plan original: `F3.3 resolve_interfaces` depende de `F4.2` y `F4.4` para productos con cinemática.

---

## ADR-002 · El Part Designer emite recetas, no Python

**Estado:** aceptada · **Afecta a:** § 2, § 5, § 6.3, § 8.3; F1.4, F1.6, F1.7

**Problema.** El documento original estaba a medio camino entre dos arquitecturas incompatibles: F1.6 decía que el agente genera `build.py`, y § 9.2 decía que `mech-toolkit` tiene generadores. La tabla de riesgos calificaba "macros generadas por un modelo pequeño" como probabilidad **alta** e impacto **alto** — el mayor riesgo del proyecto.

**Decisión.** El Part Designer emite una **receta**: una lista validada contra esquema de llamadas a generadores con sus parámetros. `build.py` lo compone el orquestador. Existe una **escotilla** para piezas atípicas donde sí se permite Python libre, con DeepSeek y `validate_macro`.

**Por qué.** Un error del modelo pasa de ser un traceback tras ejecutar FreeCAD a un campo rechazado por el esquema antes de lanzar nada. Y rellenar un JSON de seis campos es una tarea mucho más fácil que escribir Python de la API de FreeCAD, que es justo donde los modelos se caen.

**Consecuencias.**
- Desaparece la necesidad de un modelo especializado en código (`qwen2.5-coder:14b` sale del stack).
- **El porcentaje de piezas que usan la escotilla se convierte en métrica de producto**, no en tasa de fallo: cada pieza atípica nombra el generador que falta escribir. El sistema se vuelve más determinista con el uso.
- El riesgo principal se desplaza de "el modelo escribe mal" a "me faltan generadores", que es un problema de trabajo acotado en vez de uno de fiabilidad estadística.

---

## ADR-003 · El veredicto del QA es aritmético; el LLM solo puede añadir defectos

**Estado:** aceptada · **Afecta a:** § 3.3, § 7.1; F2.10–F2.13

**Problema.** El riesgo "QA aprueba todo" estaba mitigado únicamente con "usa otro modelo". Es una defensa débil: un `gemma3:12b` tampoco sabe qué debería medir en una pieza que no diseñó, y sigue siendo un LLM emitiendo un juicio.

**Decisión.** Tres capas —aserciones derivadas del contrato, chequeos DFM, y un pase libre con visión— y una regla dura:

```
PASS  ⟺  capa1.todas_ok  ∧  capa2.todas_ok  ∧  capa3.defectos == []
```

El LLM escribe en una **lista de defectos**, nunca en el veredicto. No existe ninguna ruta por la que pueda convertir un `FAIL` determinista en `PASS`.

**Por qué funciona.** El peor comportamiento posible de un modelo complaciente pasa a ser *ser inútil* (no aportar defectos) en vez de *aprobar una pieza rota*. Un fallo silencioso se convierte en un fallo barato.

**Habilitado por ADR-001.** Solo es posible porque una interfaz resuelta contiene lo necesario para generar sus propias pruebas: de `IF-003 = bearing_seat, 608zz, press` se deriva mecánicamente "agujero Ø22.10 ±0.05 en el frame de IF-003". Las interfaces dejan de ser documentación y pasan a ser la especificación ejecutable del QA.

**Consecuencia lateral.** Usar un modelo distinto para QA deja de ser un requisito de correctitud y pasa a ser una segunda red opcional. Eso libera presión de VRAM y desacopla el diseño de la elección de modelos.

---

## ADR-004 · Construcción headless, inspección con GUI

**Estado:** aceptada · **Afecta a:** § 9.3, regla 6 de § 4; F0.10, F3.5

**Problema.** La Fase 3 exige diseñar piezas en paralelo, pero el MCP de FreeCAD habla por RPC con **una** instancia en un puerto fijo. Con una GPU rápida, el cuello de botella deja de ser el modelo y pasa a ser FreeCAD.

**Decisión.** Cada pieza se construye en su propio proceso `freecadcmd` efímero. Una única instancia con GUI queda para renderizar vistas y ensamblar.

**Alternativas descartadas.**
- *Pool de instancias GUI en puertos distintos*: obliga a parchear el addon y consume varios GB y una ventana por pieza.
- *Serializar el acceso a una sola FreeCAD*: serializa justo la parte lenta.

**Por qué encaja.** Si `build.py` regenera siempre la pieza desde parámetros, un proceso limpio por pieza es lo natural: sin documento global, sin estado compartido. Un cuelgue de FreeCAD mata una pieza, no el proyecto.

**Tensión conocida.** `freecadcmd` no renderiza. Por eso la inspección se separa: la instancia GUI carga los `.FCStd` ya construidos solo para capturar las imágenes que consume la capa de visión del QA (ADR-003).

*Verificado en macOS el 2026-09-18: `freecadcmd` construye y exporta STL sin GUI.*

---

## ADR-005 · `validate_macro` es una red de seguridad, no un límite de seguridad

**Estado:** aceptada · **Afecta a:** § 8.3; F2.8

**Problema.** El documento presentaba `validate_macro` (lista negra sobre AST) como la razón por la que es seguro no restringir más el acceso al PC. Una lista negra de AST se esquiva sin dificultad con `getattr`, `__import__`, `__builtins__` o `__class__.__bases__`.

**Decisión.** No se endurece la lista negra: se **declara explícitamente su alcance real** en la documentación. Su amenaza es un modelo confundido que borra algo por error, no un atacante.

**Por qué es aceptable.** ADR-002 elimina casi toda la superficie: en el camino normal no hay Python arbitrario que validar. `validate_macro` solo actúa en la escotilla.

**Si algún día hace falta una garantía real**, la respuesta no es una lista negra mejor, sino ejecutar `freecadcmd` en un contenedor desechable sin red y con solo la carpeta de la pieza montada. Anotado en mejoras futuras.

---

## ADR-006 · Telegram es un adaptador de un `HumanPort`, no un agente

**Estado:** aceptada · **Afecta a:** § 8.5, reglas 7 y 8 de § 4; F0.9, F5.4–F5.7

**Problema.** Se pidió "un agente OpenClaw con Telegram" para que el sistema pueda consultar cosas del diseño y recibir peticiones de cambio.

**Decisión.** OpenClaw **no entra en el grafo**. Se define un `HumanPort` con `ask(pregunta, adjuntos)` y `notify(evento)`, y CLI, web y Telegram son tres **adaptadores** del mismo puerto.

**Por qué no es un agente.** Los agentes son trabajadores: leen el blackboard y producen artefactos. OpenClaw mueve mensajes. Además un nodo del grafo se planifica, y los mensajes llegan de forma asíncrona, incluso cuando no hay ningún nodo ejecutándose. Y ya existían dos gates y una UI planeada que son la misma operación —preguntar y esperar—: meter Telegram como agente habría triplicado esa lógica.

**Beneficio colateral.** Unifica el gate por consola (F0.9) y el gate por navegador (F5.4), que en el plan original eran dos implementaciones separadas de lo mismo.

**Asincronía.** Una consulta pone la pieza en `BLOCKED_ON_HUMAN` y el planificador sigue con las demás; los gates sí bloquean el proyecto. Sin esto, una duda sobre una pieza congelaría las otras seis — y el caso de uso es precisamente que no estés delante del PC.

**Peticiones de cambio.** Un cambio pedido por ti es **un defecto con autor humano** y entra por la maquinaria de reapertura existente (reglas 3 y 4), con sus límites de iteración. No hay camino paralelo.

**Seguridad.** Este canal es entrada no confiable a un sistema que puede ejecutar código (ADR-002). Lista blanca obligatoria; el texto entrante es dato y nunca instrucción de sistema; una petición de cambio nunca abre la escotilla de Python sin gate; el filtro de salida de DeepSeek se aplica también aquí.

---

## ADR-007 · Dos modelos residentes, configurados por perfil

**Estado:** aceptada · **Afecta a:** § 6.1; F0.3

**Contexto.** Hardware confirmado: RTX 5090 (32 GB VRAM) y 92 GB de RAM. El documento original estaba calibrado para `qwen3:8b`.

**Decisión.** `qwen3.8` (27B, con `tools`, `thinking` y `vision`, 16.5 GB) para todos los roles de diseño, y `gemma3:12b` (~8 GB, también con visión) residente para QA. Total ~25 GB de 32 GB. `config/models.yaml` define perfiles `prod` y `dev` para poder desarrollar en un portátil sin GPU.

**Por qué importa la visión.** Habilita la capa 3 del QA (ADR-003). Sin ella, `section_view` producía imágenes que nadie podía mirar.

**Riesgo específico del hardware.** La 5090 es Blackwell (`sm_120`) y requiere CUDA 12.8+. Una versión antigua de Ollama **no falla: cae a CPU en silencio**. F0.3 debe verificar explícitamente el uso de GPU, o se perderán horas creyendo que el modelo es lento.

**Nota.** Estas elecciones son configuración, no arquitectura. Ninguna de las decisiones ADR-001 a ADR-006 depende de qué modelo se use — que es la señal de que las fronteras están en el sitio correcto.
