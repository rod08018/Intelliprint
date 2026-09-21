#!/bin/sh
# Arranque de Crafty (OpenClaw) en su contenedor (F0.2 (docker)).
#
# En el Mac, Crafty se monto a mano: onboarding interactivo, openclaw.json
# editado a mano con rutas absolutas y los .md copiados con cp. Nada de eso
# viajaba por git. Aqui cada arranque deja a Crafty en el mismo estado:
#
#   1. Onboarding, solo la primera vez (el estado vive en un volumen).
#   2. Sus instrucciones, copiadas del repo en cada arranque: config/openclaw/
#      manda, y un cambio alli llega con reiniciar el contenedor.
#   3. La configuracion generada desde el .env (orchestrator/crafty.py),
#      tambien en cada arranque: cambiar TELEGRAM_ALLOWED_USERS y reiniciar
#      basta para cambiar quien puede escribir.
#
# ASCII puro a proposito: ver tests/test_scripts_powershell.py.
set -eu

oc() { node /app/dist/index.js "$@"; }

: "${DEEPSEEK_API_KEY:?falta DEEPSEEK_API_KEY en .env: es el modelo con el que conversa Crafty}"
: "${TELEGRAM_BOT_TOKEN:?falta TELEGRAM_BOT_TOKEN en .env}"
: "${OPENCLAW_GATEWAY_TOKEN:?falta OPENCLAW_GATEWAY_TOKEN en .env (cualquier cadena larga y aleatoria)}"

marca="$OPENCLAW_STATE_DIR/.intelliprint-onboarded"
if [ ! -f "$marca" ]; then
    echo "[crafty] primer arranque: onboarding"
    # --secret-input-mode ref: la clave se guarda como REFERENCIA a la
    # variable de entorno, no copiada en openclaw.json. Ese archivo vive en
    # un volumen, y un volumen se copia y se inspecciona.
    oc onboard --non-interactive --accept-risk --skip-health \
        --mode local \
        --auth-choice deepseek-api-key \
        --secret-input-mode ref \
        --gateway-auth token \
        --gateway-token-ref-env OPENCLAW_GATEWAY_TOKEN \
        --skip-channels \
        --no-install-daemon
    # --use-env: el token del bot se queda en el entorno, igual que la clave.
    oc channels add --channel telegram --use-env
    touch "$marca"
fi

mkdir -p "$OPENCLAW_WORKSPACE_DIR"
cp /intelliprint/openclaw/IDENTITY.md /intelliprint/openclaw/INTELLIPRINT.md "$OPENCLAW_WORKSPACE_DIR/"

# Si la lista blanca falta, el lote no existe y Crafty NO arranca: un canal
# sin lista atenderia a cualquiera (ADR-012, F5.10 (lista)).
lote=/bootstrap/lote.json
[ -s "$lote" ] || { echo "[crafty] sin configuracion generada: mira el registro de crafty-config"; exit 1; }
oc config set --batch-json "$(cat "$lote")"

echo "[crafty] en marcha"
exec node /app/dist/index.js gateway --port 18789
