# library — hardware comercial

Ningún modelo debe inventar las dimensiones de un NEMA17. Todo el hardware comercial vive aquí. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 10.

Es además la fuente de la que el resolvedor de interfaces (§ 3.2) saca las cotas reales al convertir una interfaz simbólica en resuelta. Si un dato falta aquí, la interfaz no se puede resolver — y eso es preferible a que alguien lo estime.

```
library/
├── screws/      M2–M5, tuercas, insertos térmicos
├── bearings/    608zz, 623zz, 625zz
├── motors/      NEMA14, NEMA17
├── servos/      SG90, MG90S, MG996R, DS3218
├── electronics/ ESP32 DevKit, Arduino Nano, A4988, TMC2209
├── step/        modelos STEP de cada ítem
└── models/reference/  modelos DESCARGADOS de terceros, con autor y licencia
```

Cada ítem es un YAML validado contra esquema, con su STEP correspondiente:

```yaml
id: nema17_42x40
category: stepper
body_mm: {w: 42.3, h: 42.3, l: 40}
shaft_mm: {d: 5, l: 24, flat: true}
mount: {bolt: M3, pcd_square_mm: 31, pilot_d_mm: 22}
holding_torque_nm: 0.40
mass_g: 280
step: library/step/nema17_42x40.step
```

Se indexa también en Qdrant para búsqueda semántica.

## `models/reference/`: referencias independientes

Los modelos de hardware comercial **no los dibuja el sistema**: se descargan de fuentes reconocibles, con autor, licencia y huella SHA-256 (ver `models/reference/README.md`). Si el sistema dibujara también la referencia con sus propios números, que la pieza encajara no demostraría nada.

Esto ya encontró dos cosas que un modelo propio habría ocultado:
- NEMA 17 normaliza **solo la cara de montaje**. La altura del saliente (1.6 en la referencia, 2.0 en la que yo había supuesto) y el largo del eje (20 frente a 24) cambian según el fabricante.
- El QA confundía un agujero con un saliente concéntrico mayor, porque las esquinas redondeadas del motor son cilindros en el mismo eje. Arreglado: el extractor distingue caras interiores y exteriores.
