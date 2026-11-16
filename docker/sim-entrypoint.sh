#!/bin/bash
# Arranque del contenedor de simulación (F13.6 (simulación)).
#
# El modelo y la aeronave de PX4 se generan en el repositorio (`sim/`) y se
# montan; aquí se enlazan donde PX4 los busca. Un enlace y no una copia:
# regenerar el modelo en el PC se ve dentro sin reiniciar nada.
set -e

source /opt/ros/jazzy/setup.bash
source /opt/ros_ws/install/setup.bash

MODELOS="$PX4_DIR/Tools/simulation/gz/models"
AERONAVES="$PX4_DIR/build/px4_sitl_default/etc/init.d-posix/airframes"

if [ -d "$INTELLIPRINT_SIM/modelos" ]; then
    for m in "$INTELLIPRINT_SIM"/modelos/*/; do
        ln -sfn "${m%/}" "$MODELOS/$(basename "$m")"
    done
fi
if [ -d "$INTELLIPRINT_SIM/px4" ]; then
    for a in "$INTELLIPRINT_SIM"/px4/*_gz_*; do
        [ -e "$a" ] && ln -sf "$a" "$AERONAVES/$(basename "$a")"
    done
fi

exec "$@"
