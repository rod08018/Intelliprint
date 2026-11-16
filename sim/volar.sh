#!/bin/bash
# PX4 SITL con el ala volante de Intelliprint en Gazebo (F13.6 (simulación)).
#
# Dentro del contenedor `sim` (o `sim-gui`, para ver Gazebo):
#     docker compose --profile sim run --rm sim sim/volar.sh
# Sin ventanas si HEADLESS=1 (el servicio `sim` lo pone). PX4 manda su MAVLink
# a la estación de tierra en el UDP 14550; QGroundControl en el PC lo recibe
# por el 18570 que publica el compose.
#
# El modelo y la aeronave salen de `python -m sim.generar` y el arranque del
# contenedor los enlaza donde PX4 los busca.
set -e

if [ ! -f "$INTELLIPRINT_SIM/modelos/intelliprint_vtol/meshes/cuerpo.stl" ]; then
    echo "Falta el modelo: python -m sim.generar workspace/projects/<carpeta> sim" >&2
    exit 1
fi

RAIZ="$PX4_DIR/build/px4_sitl_default"
mkdir -p "$RAIZ/rootfs"
cd "$RAIZ/rootfs"
export PX4_SYS_AUTOSTART=4100
export PX4_SIM_MODEL=gz_intelliprint_vtol
# -d: sin la consola interactiva de PX4 (en un contenedor sin terminal se
# cerraría al leer el fin de la entrada).
exec "$RAIZ/bin/px4" -d "$RAIZ/etc" "$@"
