#!/bin/bash
# Gazebo en el navegador, con el ala volante haciendo su misión
# (F13.6 (simulación)). Pedido por él el 2026-11-16: «quiero poder en mi
# buscador acceder a gazebo y ver la simulación».
#
# En el PC:
#     docker compose --profile sim up sim-web
# y en el navegador: http://localhost:6080/vnc.html?autoconnect=1&resize=scale
#
# Una pantalla virtual (Xvfb) con la ventana de Gazebo, servida por VNC y
# noVNC solo en 127.0.0.1: la escena no sale del PC. PX4 vuela la misión de
# `sim/mision.py` y, al aterrizar (o estrellarse), la repite con otro PX4.
set -e

export DISPLAY=:1
# El candado de la pantalla queda de un arranque anterior cuando el
# contenedor se para y se vuelve a levantar sin recrearlo: con él Xvfb no
# arranca, x11vnc tampoco, y el navegador decía «Failed to connect».
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
Xvfb :1 -screen 0 1600x900x24 -nolisten tcp &
sleep 2
# Toda ventana maximizada: sin esto Gazebo salía en un cuarto de la pantalla.
mkdir -p ~/.config/openbox
cat > ~/.config/openbox/rc.xml <<'XML'
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications><application class="*"><maximized>yes</maximized>
    <decor>no</decor></application></applications>
</openbox_config>
XML
openbox &
x11vnc -display :1 -forever -shared -nopw -localhost -rfbport 5900 -quiet &
websockify --web /usr/share/novnc 6080 localhost:5900 &

echo "Gazebo en el navegador: http://localhost:6080/vnc.html?autoconnect=1&resize=scale"

mkdir -p "$INTELLIPRINT_SIM/registros"
while true; do
    # Sin HEADLESS, el arranque de PX4 abre también la ventana de Gazebo.
    HEADLESS= setsid bash "$INTELLIPRINT_SIM/volar.sh" \
        > "$INTELLIPRINT_SIM/registros/px4-web.txt" 2>&1 &
    px4=$!
    # La cámara sigue al avión desde atrás y arriba, en cuanto aparece.
    (
        for _ in $(seq 120); do
            gz service -s /gui/follow --reqtype gz.msgs.StringMsg \
                --reptype gz.msgs.Boolean --timeout 2000 \
                --req 'data: "intelliprint_vtol_0"' 2>/dev/null | grep -q true && break
            sleep 2
        done
        gz service -s /gui/follow/offset --reqtype gz.msgs.Vector3d \
            --reptype gz.msgs.Boolean --timeout 2000 --req 'x: -5, y: -3, z: 2.5' \
            > /dev/null 2>&1
    ) &
    python3 "$INTELLIPRINT_SIM/mision.py" || true
    sleep 15            # para verlo quieto en tierra antes de empezar otra
    kill -TERM -- "-$px4" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    sleep 5
done
