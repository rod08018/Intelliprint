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
└── models/      modelos listos para ensamblar en FreeCAD (.FCStd + .step)
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

## `models/`: listos para ensamblar

Cada modelo se construye **en posición de montaje**: centrado en el origen y con la cara de montaje en z=0, en las mismas coordenadas que las piezas que lo alojan. Al insertar la pieza y el hardware en un ensamblaje de FreeCAD quedan montados sin crear uniones.

| Modelo | Origen de las cotas |
|---|---|
| `nema17_42x40` | Cuerpo 42.3×42.3×40, saliente Ø22×2, eje Ø5×24, 4×M3 de 4.5 mm en cuadro de 31. Simplificado: sin chaflanes ni plano en el eje |

Se regeneran con `mech_toolkit.library_models`. Comprobado contra el soporte NEMA17: intersección de 0 mm³ y distancia de 0 mm, es decir, se tocan sin atravesarse.
