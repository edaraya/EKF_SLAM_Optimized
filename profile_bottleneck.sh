#!/bin/bash
# profile_bottleneck.sh
#
# Captura el PERFIL POR FUNCION del nodo slam con perf record, para
# identificar el cuello de botella (que funcion/libreria consume el tiempo).
#
# Genera, en la carpeta de resultados:
#   results_<mode>_perfreport_full.txt   (arbol de llamadas completo)
#   results_<mode>_perfreport_flat.txt   (lista plana de funciones + %)
#   results_<mode>_bottleneck.csv        (las funciones clave extraidas)
#
# Uso:
#   ./profile_bottleneck.sh armadillo [segundos]
#   ./profile_bottleneck.sh fpga [segundos]
# Por defecto graba 30 segundos.
#
# Requiere: sudo sysctl kernel.perf_event_paranoid=-1   (una vez por sesion)

set -u
MODE="${1:-}"
SECS="${2:-30}"

if [ "$MODE" != "armadillo" ] && [ "$MODE" != "fpga" ]; then
    echo "Uso: $0 [armadillo|fpga] [segundos]"
    exit 1
fi

TS=$(date +%Y-%m-%d_%H-%M-%S)
BASE="$HOME/andres.saballo/results"
RESULTS_DIR="${BASE}/${TS}_${MODE}_profile"
mkdir -p "$RESULTS_DIR"

export EKF_XCLBIN_PATH="${HOME}/andres.saballo/ekf_spmm.xclbin"
LAUNCH_CMD="ros2 launch nuslam nuslam.launch.py robot:=nusim cmd_src:=circle use_rviz:=false"

echo "=================================================="
echo " Perfilado de cuello de botella: $MODE  (${SECS}s)"
echo " Resultados: $RESULTS_DIR"
echo "=================================================="

# ── Lanzar el SLAM ───────────────────────────────────────────────────────
echo "[..] Lanzando SLAM..."
$LAUNCH_CMD > "${RESULTS_DIR}/slam_stdout.log" 2>&1 &
LAUNCH_PID=$!

# ── Esperar al nodo slam ─────────────────────────────────────────────────
echo "[..] Esperando al nodo slam..."
SLAM_PID=""
for i in $(seq 1 15); do
    sleep 1
    SLAM_PID=$(pgrep -f "lib/nuslam/slam" | tail -1)
    [ -n "$SLAM_PID" ] && break
done

if [ -z "$SLAM_PID" ]; then
    echo "[ERROR] No se encontro el proceso slam."
    kill -INT "$LAUNCH_PID" 2>/dev/null
    exit 1
fi
echo "[ok] Nodo slam (PID $SLAM_PID). Grabando ${SECS}s con perf record..."

# ── perf record (call-graph) ─────────────────────────────────────────────
DATA="${RESULTS_DIR}/perf.data"
perf record -g -p "$SLAM_PID" -o "$DATA" -- sleep "$SECS"

echo "[..] Generando reportes..."
# Arbol de llamadas completo
perf report -i "$DATA" --stdio > "${RESULTS_DIR}/results_${MODE}_perfreport_full.txt" 2>/dev/null
# Lista plana de funciones (sin arbol), mas facil de leer/parsear
perf report -i "$DATA" --stdio -g none > "${RESULTS_DIR}/results_${MODE}_perfreport_flat.txt" 2>/dev/null

# ── Detener el SLAM ──────────────────────────────────────────────────────
kill -INT "$LAUNCH_PID" 2>/dev/null
sleep 3

# ── Extraer las funciones clave a un CSV ─────────────────────────────────
FLAT="${RESULTS_DIR}/results_${MODE}_perfreport_flat.txt"
CSV="${RESULTS_DIR}/results_${MODE}_bottleneck.csv"
echo "funcion,porcentaje" > "$CSV"

# Funciones de interes: el callback, dgemm (BLAS), inversa, y XRT/FPGA
for pat in "fake_sensor_cb" "dgemm" "dgemv" "arma::blas" "arma::glue_times" \
           "arma::inv" "arma::solve" "xrt" "xclbin" "sync_bo" "compute_PHt"; do
    LINE=$(grep -i "$pat" "$FLAT" | head -1)
    if [ -n "$LINE" ]; then
        PCT=$(echo "$LINE" | grep -oE "[0-9]+\.[0-9]+%" | head -1 | tr -d '%')
        echo "${pat},${PCT:-0}" >> "$CSV"
    fi
done

echo ""
echo "=================================================="
echo " Cuello de botella ($MODE):"
echo "=================================================="
cat "$CSV"
echo ""
echo " Top 15 funciones (lista plana):"
grep -E "^\s+[0-9]+\.[0-9]+%" "$FLAT" | head -15
echo ""
echo " Archivos en: $RESULTS_DIR"
