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
| `SISTEMA_MULTIAGENTE.md` | Cómo es el sistema hoy: los dos flujos, los cinco agentes y lo que mide el código |
| `config/agents/*.md` | El prompt de sistema de cada agente |
| `config/openclaw/` | Crafty, el agente del canal humano (Telegram) |

Al citar un ID en el código va con su palabra clave —`F3.15 (mecanismos)`— y un
test lo comprueba: si la cita no cuadra con el plan, la suite se pone roja.

## Por dónde iba esto

**2026-11-13: Fases 11 a 13 aprobadas por él (ADR-022)**, con «me parece
tu propuesta comienza a trabajar asap»: carcasas con superficies, brazo de
clase Arctos y avión, en ese orden. Están en `PLAN_PROYECTO.md`. Las
filas de la 12 y la 13 se concretan con él al empezarlas; antes del avión
decide si el laminado entra en el diseño, si Gazebo queda fuera y qué
avión. La Fase 10 se cierra con el brazo mediano en 11 de 12 y sin
imprimir; lo que dejó abierto está abajo.

- **Hechas: F11.1 (curvas) y F11.2 (cáscara)** (2026-11-13). El kit
  dibuja secciones (`seccion`, `rectangulo`, `elipse`), las une
  (`transicion`), las lleva por un camino (`barrer`) y deja un cuerpo
  en una pared (`vaciar`). A mano, sin modelo, sale una carcasa curva
  hueca con orejas, tornillos y acabado. Su STL pesaba 216 MB: ahora
  toda pieza se malla a 0,01 mm y en binario. **Sin resolver:** tras
  unir un barrido curvo FreeCAD mide mal el volumen (el informe lo
  contrasta con la malla; lo de dentro del kit que compara volúmenes
  no está revisado). Ningún modelo las ha usado todavía: eso es
  F11.5 (diseñador).
- **Orden cambiado por él el 2026-11-13** («Sí, carcasa primero»):
  F11.5 y F11.4, la medición (F11.6) y, al final, F11.3 (tramos).
- **Hecha: F11.5 (diseñador).** Los prompts del diseñador y del
  ingeniero cuentan las formas curvas, con un ejemplo que un test
  construye. DeepSeek, pedida una tapa abombada, la dibujó con
  `transicion` y `vaciar` a la primera (una petición, una corrida).
- **Hecha a medias: F11.4 (cubre).** Un nodo del plan dice `cubre` y
  a la carcasa se le mide que envuelve lo comprado, que no lo toca,
  que no le tapa el cable y que le deja 1 mm (**el milímetro lo puso
  el asistente**). Probado con un NEMA 17 de pie. **No se hizo para
  el antebrazo del brazo mediano**: ahí el motor ya va dentro de la
  pieza y lo que se ve son la polea y la correa, que no tienen
  cuerpo en el sistema. No mide que esté cerrada ni que no roce con
  lo que gira.
- **Decidido por él el 2026-11-13 («Sí, con 2 USD»): F11.6 se mide
  con el encargo 16**, un NEMA 17 en una escuadra con su carcasa
  atornillada; tope de 2 USD, una corrida y hasta dos reanudaciones.
  El banco tiene la exigencia nueva `cubre`. Hecho a mano, sin
  modelo, pasa 5 de 5 (a la segunda: la carcasa se imprime boca
  abajo, con bridas en vez de orejas). La carcasa del antebrazo
  queda para cuando la polea y la correa tengan cuerpo.
- **El encargo 16, medido, se queda en 3 de 5** (corrida `1114-0023`,
  0,49 USD de los 2). Plan y soporte, a la primera; la carcasa gastó
  sus cinco intentos. No cumple el encaje (un saliente de la escuadra
  no la deja bajar recta: es real, mirado en FreeCAD) ni «sin
  soportes». Tres intentos se fueron en el sistema, y el juez se
  cayó al final. Arreglado: un punto repetido ya no es un error, el
  juez encuentra las fichas, el resumen del plan dice qué cubre la
  carcasa y al reanudar se le dice a la pieza lo que dijo
  PrusaSlicer. Sin arreglar: vaciar una forma que se estrecha hasta
  casi cerrarse, y una construcción de más de 180 s.
- **Reanudado una vez, el encargo 16 sigue en 3 de 5** (0,40 USD
  más: 0,89 de los 2; queda una reanudación). El acabado no se podía
  cumplir: el modelo dibujó los arcos con tramos rectos, porque
  quería un radio distinto delante y detrás y `rectangulo` solo
  admitía uno, y una superficie de facetas no se redondea. Y el
  aviso del encaje no decía dónde chocaba. Arreglado: un radio por
  esquina, decírselo al diseñador, y el choque con su sitio.
- **Reanudado por segunda y última vez, pasa 4 de 5** (1,19 USD de
  los 2; no queda más acordado). Ya encaja; falla «sin soportes».
  La carcasa no pasó su bucle por el chaflán de la base (10 de 12
  aristas, sin arreglar). Las construcciones de más de 180 s son el
  acabado sobre programas facetados, no un cambio de hoy.
- **Decidido por él el 2026-11-13, molesto: PrusaSlicer queda fuera
  de todo.** «El slicer no tiene nada que ver con el diseño» y «que
  el banco le ponga nota, pero que no tenga nada que ver con Prusa
  de momento». No volver a proponer laminar. «Sin soportes» se mide
  en la forma de la pieza (`orchestrator/voladizos.py`): seis
  posturas, voladizos de más de 45° y vuelos de más de medio puente
  (5 mm, **regla del asistente**). Con ella se corrige la pieza en
  su bucle y con ella pone el banco la nota; el banco ya no llama a
  PrusaSlicer. Rejuzgado todo: diez piezas 52 de 52, pan-tilt 7 de
  7, brazo de servos 8 de 8, encargo 14 9 de 10, 14b 8 de 9 (baja
  una), brazo mediano 11 de 12 y encargo 16 4 de 5.
- **Reanudado una tercera vez con su «sí», el encargo 16 seguía en
  4 de 5** (1,45 USD de los 2). El fallo era de la medida: la
  carcasa apoya en su brida, que por la holgura con el soporte quedó
  0,18 mm sobre un borde, y se contaba entera como «en el aire».
  Corregido: lo que queda a menos de una capa (0,2 mm) de la cama
  está en la cama. **Rejuzgado sin modelo, pasa 5 de 5.** La medida
  se corrigió después de ver el resultado; **aprobada por él** ese
  día («Si supongo que esta bien»).
- **Pedido por él el 2026-11-13: «mejorar las medidas del inicio
  para que no falle».** Entendido así (interpretación del asistente):
  lo que hoy se le dice a una pieza cuando ya ha fallado, dárselo
  antes de dibujar y con cifras. Hecho, sin correr: a la carcasa se
  le da la caja de lo que cubre y el hueco mínimo; el diseñador y el
  ingeniero saben cómo se mide «sin soportes»; y el acabado trata
  como base lo que queda a menos de una capa del fondo (el último
  programa de la carcasa baja del 56–71 % de aristas vivas al 6 %).
  **Falta medirlo:** una corrida nueva del encargo 16, por acordar.
- **Dicho por él la noche del 2026-11-13 al 14, antes de irse:** la
  corrida nueva del encargo 16, «Si con 2 dolares»; «cuando termines
  todo pasa a la siguiente fase automaticamente no me esperes»; y
  «sube a 15 dolares maximo puedes modificar medidas en caso extremo
  documentalo y me lo dices mañana». Entendido así (interpretación
  del asistente): 15 USD en total de banco desde ese mensaje, y una
  medida solo se cambia si no hay otra salida, apuntada aquí con su
  antes y su después. **Al volver él, el gasto se acuerda otra vez.**
- **La corrida nueva del encargo 16 se paró a mano** (`1114-0535`,
  0,57 USD de los 15): iba a fallar por el sistema. Tres medidas del
  bucle de la pieza **cambiadas sin él, con su permiso de esa noche;
  hay que contárselo**: (1) la tuerca cautiva que el plan pide en una
  pieza para el tornillo de otra ya no cuenta como «brida que no
  aprieta» (al soporte se le pedía y se le reprochaba a la vez, cinco
  intentos); (2) si un requisito nombra un tornillo y trae un
  diámetro que su texto no dice (Ø3.2 para un M3), vale el agujero
  del perfil; (3) un requisito que cita lo que escribe el sistema ya
  no cuenta aunque lo cite entero (la frase nueva del hueco mínimo se
  volvió una «ventana de 44.3 × 44.3» que nadie pidió: fallo del
  cambio del 13). Ninguna cambia lo que juzga el banco. Además el
  aviso de holgura de la carcasa dice con qué cuerpo y dónde.
- **Con esos arreglos, la corrida nueva da 2 de 5** (`1114-0631`,
  0,75 USD; 1,32 de los 15). El soporte salió, con sus tuercas. La
  carcasa, con el motor de eje horizontal esta vez, perdió cuatro de
  cinco intentos al construir: `acabar()` no construía una pieza sin
  arista hacia abajo, y la limpieza de caras de FreeCAD tumbaba una
  resta válida. Arreglados los dos en el kit.
- **Reanudada dos veces, la `1114-0631` pasa 4 de 5** (primero 3 de
  5; `banco_reanudado-2.md`; 1,47 USD la corrida, 2,03 de los 15).
  Solo falla el encaje: 8,3 mm³ de la carcasa se cruzan al meter la
  escuadra. Por el camino, dos intentos se perdieron con FreeCAD
  caído al redondear. Arreglado: si se cae redondeando, se repite
  sin redondear y la pieza se mide igual; y unir las caras de una
  booleana ya no tumba ninguna operación del kit. La carcasa sigue
  sin pasar su bucle (del 12 al 15 % de aristas vivas).
- **Con cuatro reanudaciones, la `1114-0631` pasa 5 de 5**
  (`banco_reanudado-4.md`; 2,02 USD la corrida, 2,59 de los 15). El
  encaje fallaba porque la carcasa se dibujaba dentro de la escuadra
  y le quedaba material en las ranuras de las tuercas, y el aviso
  le decía que el `hueco()` abría el camino, que con una pieza del
  invento no es verdad. **No es a la primera**, y la carcasa no pasa
  su bucle: del 21 al 24 % de aristas vivas, y FreeCAD se cae o
  tarda más de 180 s al redondearla (sin arreglar).
- **Hecha: F11.3 (tramos)** (2026-11-14). `pieza.partir(eje, en,
  lengueta)` corta una pieza que no cabe en la cama; cada tramo va a
  su STL en `tramos/` con una unión a media madera, y se le mide que
  quepa, que se imprima sin soportes y que un tornillo cierre cada
  corte. A mano, un carenado curvo de 400 mm sale en dos tramos sin
  defectos. **Criterio del asistente:** 0,8 mm de labio y de
  lengüeta como poco. Ningún modelo la ha usado y el banco no tiene
  encargo que la pida. Con ella la Fase 11 no tiene más filas.
- **Empezada la Fase 12 sin él, por lo que no depende de su
  respuesta:** la ficha `nema23` (F12.1 (fichas)), con las cotas de
  la hoja del fabricante. Qué NEMA 23 tiene o va a comprar no lo ha
  dicho: es un supuesto. **Las filas de la Fase 12 siguen por
  concretar con él**, y también el tope de gasto de su brazo.
- **Dicho por él el 2026-11-14: «quiero que levante 2 kg el brazo, tú
  propón rodamientos y motores».** Propuesto, **por aprobar** (la
  tabla está en `PLAN_PROYECTO.md`, Fase 12): tramos de 260 + 240 +
  100 mm; base con NEMA 23 de 56 mm y correa 5:1; la muñeca, tres
  NEMA 17 con las cicloidales de hoy (28, 28 y 10 a 1). Rodamientos:
  2 × 6810-2RS en la base, 6806-2RS en hombro, codo, J4 y J6, y
  608ZZ en el cabeceo. Las masas de lo impreso son estimaciones del
  asistente. Hechas las fichas `6806-2rs` y `6810-2rs`. **La tabla
  no tiene su visto bueno salvo las reductoras**, y falta el tope
  de gasto del brazo. Un giro del plan va sobre un solo componente:
  nada dice todavía que una articulación lleva dos rodamientos.
- **Decidido por él el 2026-11-14: «Ambas compradas y en los bom
  agrega el link de compra de la reductora».** Las reductoras del
  hombro y del codo se compran y F12.2 (reductora) no se hace. Hechas
  sus fichas: `nema23-pg47-76` (hombro: pide 25,1 N·m de 32,2) y
  `nema23-pg47-56` (codo: 10,1 de 21,3), un NEMA 23 con planetaria
  de 46,656:1 ya montada; la pieza gira en su eje, sin `movido_por`.
  Una ficha puede decir dónde se compra (`compra_url`) y la lista
  de materiales lo enseña. Su hoja da hasta 1,5° de juego (15,7 mm
  en la punta por el hombro y 8,9 por el codo), y al proponérselas
  se le había dicho «casi 9 mm». **Dicho y aceptado por él ese día:
  «dale usa esa reductora con el juego».** Las hojas son las de una
  tienda (Oyostepper); la del fabricante no se dejó leer.
- **El avión, dicho por él esa noche:** un VTOL, con una autonomía
  muy buena en horas, hasta 250 km de alcance, hasta 8 libras
  (3,63 kg) de carga, y que lleve hasta dos cámaras y un lidar sin
  perder aerodinámica. La referencia que mandó, «similar a este pero
  mejorado»: el TerraHawk FPV de Nomadium, un VTOL de ala integrada
  con cuatro rotores bajo el ala y hélice de empuje (1,4 m, ~2 kg,
  6S2P, largueros de carbono; su página no da autonomía ni carga).
  Y lo concretó: **envergadura de 2 m o más, 8 libras de carga
  máxima y la autonomía del TerraHawk** (según la captura que mandó,
  sin verificar: más de 3 h y 180–216 km a 72 km/h; el comercial de
  2 m pesa 4 kg y carga 1 kg). **Y bajó la carga esa misma noche:**
  «que sea igual, yo siento que podemos usar lo mismo»: la del
  TerraHawk, no 8 libras (entendido como la del comercial de 2 m,
  hasta 1 kg; sin confirmar). Queda por decidir
  si el laminado entra en el diseño y si Gazebo queda fuera.

**2026-11-11 (noche): Fase 10, brazos con transmisión (ADR-021).** Decidido
por él: **el brazo antes que el avión**; empezar por uno pequeño con servos;
la meta de la fase es un brazo mediano solo con NEMA 17 (350–400 mm,
300–500 g, 4–5 ejes); la primera reductora impresa, la cicloidal. El de
clase Arctos es otra fase. El avión irá con **OpenVSP y AeroSandbox**, sin
AVL ni PX4, y no tiene fase. El plan y su orden están en `PLAN_PROYECTO.md`,
Fase 10.

- **Hecho: F10.1 (serie).** Dos exigencias nuevas de backlog, `alcance` y
  `carga`, que salen del estudio de movimientos, y el encargo 13: un brazo
  de 3 ejes con SG90 que llega a 120 mm y levanta 30 g.
- **El encargo 13 pasa 8 de 8** (corrida `1112-0318`, 1,22 USD: la corrida
  y una reanudación de pago; quedó otra sin usar). Antes hubo que arreglar
  dos cosas del sistema: FreeCAD se caía al crecer el hueco de una pieza
  vecina y el diseñador gastaba sus intentos a ciegas (ahora la
  construcción se repite por otro camino), y mover tres giros con piezas
  de verdad pasaba de 600 s (ahora no se miden los pares que no pueden
  tocarse). El alcance (233 mm del eje de la base) salía de un desvío
  lateral, no de un brazo largo. **Decidido por él el 2026-11-12: el
  alcance se mide del hombro a la punta.** Rejuzgada sin modelo sigue en
  8 de 8, con 120,0 mm de los 120 pedidos: sin margen. **Lo que no dice:**
  es un brazo raro (el tramo cuelga a un lado, y sin atornillar vuelca), y
  los M3 de la base no se comprueban.
- **«Banco» en la web enseña una corrida mientras corre**, con «En marcha»
  y recargándose sola; lo pidió él para ver cómo iba el brazo.
- **Hecho: F9.10 (ampliar)** (2026-11-12, `orchestrator/ampliar.py`). A un
  backlog se le añade una función sin pedirlo entero otra vez: la
  propuesta espera en `ampliacion.json` sin tocar el plan, y al aprobarla
  solo se corrige la pieza que la función toca. Desde la web («Añadir una
  función»), Crafty (`ampliar_proyecto`) y `obra --ampliar`.
- **La ampliación, medida, se queda en 7 de 9** (corrida `1112-1359`,
  «pan-tilt con pinza» partiendo de la `1111-1342`; 0,84 USD de los 2
  acordados, y las dos reanudaciones sin usar). El mecanismo funcionó: la
  propuesta valió a la primera, solo se corrigió la plataforma, y la base
  y el soporte siguen idénticos. Falla el diseño: la plataforma puso los
  M3 de la pinza en la cara que da al servo de inclinación, y el soporte
  de la pinza quedó construido encima de él.
- **Tres arreglos que salieron de ahí, aprobados por él el 2026-11-12.**
  A la pieza que taladra primero se le dice que lo que se atornilla
  después necesita sitio al otro lado, y se mide en su bucle
  (`medida.sin_sitio_para_lo_nuevo`); al reanudar, el banco corrige la
  pieza que no dejó el sitio y no la que cayó encima. Y dos del barrido,
  que cambian lo que el banco da por choque: dos piezas sin giro por
  medio pueden tocarse, y un giro se barre lo que pide el plan, la mitad
  a cada lado de como se dibuja (el dedo se barrió 180° pidiendo 60°).
  Rejuzgados con ellos, el pan-tilt sigue en 7 de 7 y el brazo en 8 de 8.
- **Reanudada una vez con ellos, la pinza sube a 8 de 9 y ahí se paró**
  (`banco_rejuzgado-2.md`; 0,83 USD más: 1,67 de los 2 acordados, no
  queda para otra). El banco corrigió la plataforma y no la pinza, y la
  plataforma movió los M3 a la primera. Pero los puso en su cara de
  abajo, y ahí la pinza no cabe: el dedo choca con la base al inclinar.
  La medida del sitio pide 6 mm en 20 de fondo y lo que viene mide
  85 × 73 mm y su dedo necesita 40 mm libres, que solo hay saliendo por
  la cara de fuera. Además, a la pinza nadie le dice de qué lado de los
  agujeros va, y se puso del de la cabeza. **Lo que el 8 de 9 no dice:**
  el encargo no pide los dos M3 de la pinza, y ni ella ni el dedo
  pasaron su propio bucle.
- **Dos arreglos más, aprobados por él el 2026-11-12 con 1 USD más**
  (3 de ampliación en total). Si lo que viene monta un giro, a la que
  taladra primero se le mide que quepa ese eje saliendo de los
  agujeros, y se le dice por qué caras cabe; bajo la base cuenta la
  mesa. Y a la pieza que agarra se le dice de qué lado va: donde sale
  el tornillo, no donde entra la cabeza.
- **Reanudada otra vez con ellos, la pinza baja a 0 de 9 y se paró**
  (`banco_reanudado.md`; 0,76 USD más: 2,43 de los 3, no queda para
  otra). La plataforma no cumplió en cinco intentos (taladró la pared
  del acople hacia +y en vez de ir a la cara de fuera) y el soporte de
  la pinza, rehecho contra ella, falló sus cinco construcciones; el
  dedo no se hizo. La pinza y el dedo del 8 de 9 están en el archivo.
  Los dos arreglos pasan sus tests y en el banco no han ayudado: el
  «4 mm más allá» que se le dice a la pinza es el grueso de una pared,
  no la salida de la pieza, y la mandó dentro de la plataforma. **La
  pinza queda aparcada**; seguir es otro gasto, por acordar.
- **Hecho: F10.2 (transmisión)** (2026-11-12). Un giro dice en
  `movido_por` qué motor lo mueve, si por correa o reductora y con qué
  relación; el motor va en la misma pieza que el rodamiento. El
  estudio lleva el par al eje: el NEMA 17 da 0,400 N·m según su hoja,
  y con correa 4:1 levanta 479,5 g a 150 mm, a mano y en el test. **Dos
  supuestos los puso el asistente y él no los ha decidido:** el
  rendimiento (0,9 la correa, 0,7 la reductora) y pedirle al paso a
  paso como mucho el 50 % de su par de retención. Nadie dibuja aún la
  correa ni las poleas, y no se ha corrido en el banco.
- **Hecho, sin medir en el banco: F10.3 (correa)** (2026-11-12). El kit
  dibuja la polea GT2 (`kit.polea_gt2`); del `movido_por` sale que el
  motor lleva una polea comprada de 20 dientes, la pieza que gira una
  de 20 × relación, y que los ejes van a la distancia de una correa
  cerrada. Cada pieza mide su parte y el banco cuenta la reducción por
  dientes (`reduccion`). **Tres cosas las decidió el asistente y él no
  las ha visto:** sin colisa (ejes fijos, ±0,2 mm), las correas se
  ofrecen de 5 en 5 dientes sin saber cuáles vende su tienda, y la
  ranura del diente es una aproximación (un semicírculo de 0,76 mm).
- **El encargo 14, medido, se queda en 6 de 10 y se paró** (corrida
  `1113-0216`, 0,90 USD de los 2 acordados; quedan 1,10). Hecha a mano
  sin modelo pasa lo que se puede medir; con DeepSeek el plan sale
  igual, pero el soporte se dibujó tumbado, como se imprime: el eje
  queda vertical (se pedía horizontal), la carga se queda en 134 g de
  300, y el eje del motor no asoma por delante, así que la polea del
  brazo no tiene correa posible. Al soporte no se le mide ninguna de
  las dos cosas. Además el eje del brazo entra justo en el rodamiento
  y cuenta como choque. **Por decidir con él** antes de gastar más:
  que el plan diga si un eje va horizontal o vertical, medir que el
  eje del motor asome, y qué hacer con el encaje en el rodamiento.
- **La web tardaba 30 s en abrir un proyecto del banco**: recorría las
  veinte corridas para pintar uno. Arreglado (2026-11-12): 0,7 a 5 s.
- **Docker se cayó** cuando el PC estuvo a punto de apagarse: se
  arregla cerrando Docker Desktop, `wsl --shutdown` y abriéndolo.
- **Pedido por él el 2026-11-12, para cuando acabe la Fase 10:**
  proponerle (sin escribirlas antes) tres fases: carcasas vistosas con
  superficies, el brazo de clase Arctos y el avión. La Fase 10 acaba
  en un brazo mediano funcional, no en uno que se vea como el Arctos.
- **Seis arreglos de ahí, aprobados por él el 2026-11-12:** el plan
  dice `eje` (horizontal o vertical) y se le mide a la pieza que lo
  monta; al soporte se le mide que el eje del motor asome; el
  rodamiento en el que gira una pieza no cuenta para los choques (un
  servo sí); lo que llega una pieza se mide en su malla; el sitio
  libre de un rodamiento empieza donde acaba; y al reanudar se rehace
  la pieza de abajo si es la que no vale.
- **Hecho: F10.4 (dimensionar)** (2026-11-12). El plan lleva la carga
  y lo que mide el brazo desde cada eje, y antes de dibujar se
  comprueba que cada motor puede con lo que cuelga de él. Lo impreso
  se estima en 0,2 g/mm: un supuesto.
- **Ritmo acordado con él el 2026-11-12** («es terrible la cantidad de
  tiempo que gastamos cada fase»): tests de lo que se toca mientras
  se desarrolla; la suite entera y los del host, una vez por tarea;
  la prueba a mano sin modelo en cada tarea; corrida de pago solo al
  final de cada etapa; y no esperar parado mientras corre.
- **Hecho: F10.5 (muestreo)** (2026-11-12). Con más de 8 000
  combinaciones de giros se barre una rejilla más gruesa (cada 45° con
  cinco giros: 3 125 poses de 2,5 millones) y se dice lo que no se
  probó. Una cadena de cinco giros a mano se barre en 6 s. Un choque
  que caiga entre dos puntos de esa rejilla se escapa.
- **Medido otra vez, el encargo 14 pasa 9 de 10** (corrida `1113-0423`,
  0,48 USD; 1,38 de los 2 del encargo). Solo falla el alcance: 149,1
  mm de 150. El plan reservó 150 de radio libre para un brazo de 150 y
  el brazo se quedó corto para no pasarse; nadie le mide que llegue.
  No se ha gastado en corregirlo.
- **Hechas las dos medidas del alcance, sin corrida:** el plan no puede
  reservar un radio que no deje sitio al brazo, y a la pieza de la
  punta se le mide que llega.
- **Hecho: F10.6 (módulo)** (2026-11-12, `orchestrator/modulos.py`).
  Un módulo impreso son varias piezas generadas por código más lo que
  hay que comprar; el backlog lo ve como un componente y la lista de
  materiales lo abre en lo que es. La biblioteca está vacía hasta la
  cicloidal.
- **Hecho, sin banco y sin imprimir: F10.7 (cicloidal)** (2026-11-12).
  El módulo `cicloidal-nema17-10` (y `-20`): carcasa con pernos,
  excéntrica, disco, plato de salida y tapa, generados por código. El
  perfil se compara con la fórmula publicada; construidas y giradas,
  las cinco piezas no se atraviesan (0,14 mm de holgura la de 10:1).
  Un hombro hecho a mano con ella pasa todo y levanta 866 g a 150 mm
  según el estudio. **Nada está impreso**: plástico contra plástico,
  holguras sin medir. El encargo 14b la pide y está sin correr.
- **Hecho: F10.8 (calibrar)** (2026-11-13). `intelliprint calibrar
  transmision` construye la cicloidal de prueba con cuatro discos y
  una polea. **Falta un dato suyo:** imprimirlas y apuntar en
  «Impresora» → «Holgura de las transmisiones» con cuál gira bien;
  hasta entonces las reductoras van con 0,15 mm y el plan lo avisa.
- **Preparado, sin correr: F10.9 (el brazo mediano)** (2026-11-13). El
  encargo 15 está escrito: cuatro ejes con NEMA 17 (base por correa,
  hombro con cicloidal 28:1, codo con 10:1, muñeca por correa), 350 mm
  y 300 g. A mano, los tres motores que levantan pueden con lo suyo
  (el hombro pide 2,4 N·m de 3,6). Son cinco piezas y cuatro giros:
  **el tope y la regla para parar están por acordar con él.** F9.11
  (borrador) no se ha hecho; el encargo usa lo que ya tiene ficha.
- **El encargo 14b, medido, pasa 8 de 9 a la primera** (corrida
  `1113-0605`, 0,34 USD de 1): el hombro con la cicloidal 10:1. Solo
  falla la carga, 212 g de 500, y por el vuelco: el soporte se
  atornilló a un tablero vertical y el estudio solo da por atornillada
  una base con los tornillos hacia abajo. El motor deja 875 g.
- **Decidido por él el 2026-11-13: fijada a un tablero vertical cuenta
  como atornillada** (cambia lo que mide el banco). Rejuzgado sin
  modelo, el 14b pasa 9 de 9 (875 g, lo limita el motor); el pan-tilt
  sigue en 7 de 7, el brazo en 8 de 8 y el encargo 14 en 9 de 10. No
  se mide que esos tornillos aguanten.
- **Acordado con él el 2026-11-13: el encargo 15 (el brazo mediano) se
  corre con 5 USD de tope**: una corrida y dos reanudaciones, y parar
  ahí aunque no pase.
- **El encargo 15, medido, se queda en 0 de 12 y se paró sola**
  (corrida `1113-1330`, 0,95 USD de los 5; sin reanudar). El plan
  salió bien y la base y la torreta también; el brazo superior no
  cumplió en cinco intentos y el antebrazo no pasó de los requisitos.
  Lo de fondo: el sitio de un giro se reserva como un círculo entero
  (`conjunto.radio_libre`), y con tramos largos da una torreta de
  430 mm (no cabe en la impresora, y nadie lo mide) y un codo que no
  puede tener 205 mm libres con el hombro a 150. Además el diseñador
  tumbó la pieza al centro de la cama en el último intento.
- **Arreglado de ahí:** las cifras que el sistema escribe en la
  petición de una pieza (el nombre de una ficha, lo que hace la
  vecina) ya no se le exigen como cotas (`traceability.CONTEXTO`).
- **Tres arreglos más, aprobados por él el 2026-11-13** («Sí, arregla
  y reanuda»): el sitio de un giro cuenta solo lo que queda por
  delante de la cara de salida; cada pieza mide que cabe en la
  impresora (y al reanudar se rehace la de abajo que no cabe); y el
  kit no deja girar ni mover un cuerpo que ya lleva agujeros. A mano,
  una torreta de 124 mm pasa. Rejuzgados, nada de lo que pasaba
  cambia. **Lo que se pierde:** que un brazo dé con la mesa no se
  mide.
- **Reanudado una vez con ellos, el encargo 15 sigue en 0 de 12**
  (0,14 USD más: 1,09 de los 5). La torreta se rehízo y ya cabe
  (103 × 76 × 105 mm, el hombro por fuera de la base). El brazo
  superior no pasó de los requisitos: el modelo citó como «del
  usuario» la instrucción del sistema, abreviada. Arreglado: ese
  requisito se quita (`spec.sin_lo_del_sistema`).
- **La segunda reanudación se paró a mano antes de juzgar** (1,01 USD
  más: 2,10 de los 5). Salió el brazo superior (46 × 100 × 250 mm);
  el antebrazo y la muñeca no, y en cada intento llevaban una orden
  imposible: colocar la reductora de dos piezas más abajo, que el kit
  no deja colocar. Arreglado: lo que monta una pieza a la que esta
  no se une no se le exige (`obra.ajenos`, `lejos`). Lo demás es del
  diseño: el antebrazo apoyaba en los dos aros del rodamiento.
- **Pedido por él el 2026-11-13:** si ya se sabe que una corrida va a
  fallar, no esperarla: pararla, arreglar y volver a correr. Va una
  tercera reanudación del encargo 15, dentro de los 5 USD.
- **Reanudado por tercera vez, el encargo 15 pasa 9 de 12** (0,06 USD
  más: 2,16 de los 5). El antebrazo salió a la primera corrección.
  Falla la muñeca: no se rehízo (revalidarla la dio por buena sin
  haber cumplido nunca) y está doblada hacia el codo, así que el
  brazo no se estira (288 mm de 350). Arreglado: al reanudar se
  corrige también la de encima que no salió, y a la pieza de la
  punta se le mide que pueda ponerse recta con el tramo anterior
  (**medida del asistente, él no la ha visto**; no cambia lo que
  juzga el banco).
- **Reanudado por cuarta vez, con su visto bueno, pasa 10 de 12**
  (`banco_reanudado-3.md`; 0,20 USD más: 2,36 de los 5). La muñeca
  salió al quinto intento y el brazo se mueve sin chocar. Quedan
  dos. El alcance, 340 mm de 350: el banco mide hasta los tornillos
  de la herramienta, que están a 70 mm del eje de la muñeca, y a la
  pieza se le medía la punta del plástico. Arreglado, sin correr: se
  le mide donde va la carga, y al reanudar se busca la pieza que no
  llega. Y la muñeca no se lamina como se dibuja (apoya en el canto
  de la polea): **por decidir con él** quién elige la postura al
  laminar, porque cambia lo que mide el banco.
- **Cada reanudación de pago necesita su «sí»**: el sistema de
  permisos bloqueó lanzar una apoyándose en un visto bueno anterior.
- **Reanudado por quinta vez, con su visto bueno, pasa 11 de 12**
  (`banco_reanudado-4.md`; 0,02 USD más: 2,38 de los 5). La punta
  llega a 350,0 mm y levanta 378 g; no falla nada. Queda sin medir
  «sin soportes» en la muñeca, que no se lamina como se dibuja.
  Tumbada, a mano, sí se lamina, con aviso de puentes largos.
- **«Sin soportes» no medía lo que decía** (visto el 2026-11-13): se
  apuntaba el ajuste `support_material` del perfil, que vale 0, y
  toda pieza que se laminaba salía «sin soportes», desde F1.12.
  **Decidido por él ese día:** lo dice el aviso de PrusaSlicer, y el
  juez prueba la pieza como se dibuja y apoyada en cada una de sus
  otras caras. Rejuzgado sin modelo: los diez encargos de pieza
  bajan a 51 de 52 (el soporte del HC-SR04) y el brazo mediano
  sigue en 11 de 12, ahora con un «no cumple»: la base y la muñeca
  piden soportes en todas las posturas. Lo demás no cambia.
- **El puente de PrusaSlicer hay que reiniciarlo** cuando cambia
  `scripts/host_bridge.py`: parar el `python -m scripts.host_bridge`
  y volver a lanzar `scripts\start-host-mcps.ps1`.
- **Abierto de la Fase 10:** las tres piezas que piden soportes (la
  base y la muñeca del brazo mediano y el soporte del HC-SR04;
  corregirlas es gasto, por acordar), la medida de la punta recta
  que él no ha visto, la pinza aparcada y su dato de la holgura de
  las transmisiones. Las tres fases se le propusieron y las aprobó.

**2026-11-10: Fase 9, robots con plan mecánico (ADR-020).** El usuario quiere
diseñar robots: que el desglose decida antes de dibujar qué gira sobre qué y con
cuánto sitio, qué va atornillado y con qué, y poder añadir funciones a un
invento. El plan aprobado está en `PLAN_PROYECTO.md`, Fase 9, con su orden.

- **El pan-tilt pasa sus cinco comprobaciones** (2026-11-11, corrida
  `1111-1342`, a la primera, 45 min y 0,53 USD). El de `1110-0313` chocaba
  porque el soporte dejaba 12.7 mm entre el eje de inclinación y el servo de
  abajo; ahora el plan reserva el sitio de cada giro y cada pieza lo mide en su
  propio bucle (F9.1 a F9.5). **Es una sola corrida**, y su plataforma es un
  disco coaxial con el eje, que no inclina nada: el banco lo ve desde
  F9.14 (orienta), que pide que quepa una cámara de 25 × 24 en una cara que
  mire de lado respecto al eje. Con esa exigencia y tres reanudaciones (la
  tercera, aprobada aparte por el usuario) **pasa 6 de 6**: 0,93 USD en
  total. Es un solo backlog, una sola corrida y tres correcciones dadas por
  el banco; no dice que acierte a la primera.
- **Con la tornillería contada, ese mismo pan-tilt pasa 7 de 7**, tras
  dos reanudaciones más. Al empezar a contarla quedaba en 6 de 7
  (2026-11-11, F9.6 a F9.8, rejuzgado sin modelo): de los cuatro tornillos
  de sus dos SG90 no agarra ninguno. La base no taladró nada bajo las orejas
  y el soporte taladró Ø2.2 para tornillos de 2. Ahora el plan los prevé (los
  de lo comprado salen de su ficha), cada pieza los cuenta en su bucle y el
  banco los pide. **Reanudado una vez, con su visto bueno** (47 min,
  0,53 USD; 1,46 la corrida entera): ahora los cuatro agarran, pero **sigue
  en 6 de 7**. Corregir la base rehízo el soporte y la plataforma de cero, y
  en la plataforma nueva (30 × 28.5) ya no cabe la cámara de 25 × 24; la
  buena, de 32 × 27, quedó archivada. **Reanudado otra vez, con su visto
  bueno** (15 min, 0,18 USD; 1,64 la corrida entera): la plataforma se
  rehízo desde su concepto, sin el rebaje que partía la cara, y **pasa
  7 de 7** (`banco_reanudado-5.md`). Es un solo backlog y una sola corrida,
  con cinco reanudaciones dadas por el banco; no dice que acierte a la
  primera. Cada reanudación se acuerda antes. **Falta un dato
  suyo:** el agujero de un M2 de rosca, que se apunta en «Impresora» →
  «Apuntar otro tornillo»; el Ø1.7 de ahora lo eligió el diseñador.
- **Corregir una pieza ya no tira lo de encima: lo revalida**
  (F9.9 (revalidar), 2026-11-11, `orchestrator/revalidar.py`). Lo construido
  contra la pieza corregida se queda «por revalidar» y se comprueba sin
  modelo contra la ficha nueva; solo se corrige lo que deja de valer.
  Repetida sin modelo la corrección de la base (en una copia, con el soporte
  y la plataforma del archivo), los dos siguen valiendo y la cámara cabe.
  **Con modelo no se ha ejercitado**: la reanudación que dejó el pan-tilt
  en 7 de 7 corrigió la plataforma, que no tiene piezas encima.
- **A dónde quiere llegar** (2026-11-11): a diseñar brazos como Arctos
  (6 ejes, NEMA 17 y 23, reductoras y correas) y aeronaves como las de
  Flightory (ala fija y VTOL en LW-PLA). El brazo es la Fase 10 (arriba),
  que llega hasta uno mediano; el de clase Arctos y el avión no tienen fase.
  Para el avión faltan superficies y que el laminado sea parte del diseño.
- **Los backlogs están desaparcados**, con la regla de siempre: no relanzar
  corridas enteras para probar un arreglo (`banco --reanudar`).
- **El flujo `mecanismo` ya no existe** (F9.13 (limpieza), 2026-11-11): lo
  decidió él para cuando el pan-tilt subiera. Con él se fueron `new`/`resume`
  (LangGraph), el bot propio y el QA de interfaces, que no llamaba nadie.
  Todo está en git, en la etiqueta `antes-de-fase-9`. Los mecanismos ya hechos
  se siguen viendo en la web. **Lo que se perdió:** engranajes y cadenas
  cerradas; un backlog solo sabe piezas que giran sobre un servo o un
  rodamiento, en árbol.
- **El tope de gasto ahora sí para: 3 USD una pieza y 50 USD un backlog**
  (un robot), decididos por él el 2026-11-11; eran 5 para todo. Solo lo
  comprobaba el flujo de
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
3. ~~Decidir el tope de gasto.~~ **Decidido por el usuario: 3 USD una pieza y
   50 USD un backlog** desde el 2026-11-11 (`max_usd_per_project` y
   `max_usd_per_backlog`); antes, 5 USD para todo
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
