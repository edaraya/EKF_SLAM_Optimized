#!/bin/bash
# profile_bottleneck.sh
#
# Captura el perfil por funcion del nodo slam con perf record y genera
# TRES vistas:
#   results_<mode>_self.txt       <- lista por SELF time (dgemm_ al tope) [LA CLAVE]
#   results_<mode>_callgraph.txt  <- arbol de llamadas (fake_sensor_cb -> arma -> dgemm)
#   results_<mode>_bottleneck.csv <- funciones clave extraidas (por self)
#
# Uso:
#   ./profile_bottleneck.sh armadillo [segundos]
#   ./profile_bottleneck.sh fpga [segundos]
#
# Requiere: sudo sysctl kernel.perf_event_paranoid=-1

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

echo "[..] Lanzando SLAM..."
$LAUNCH_CMD > "${RESULTS_DIR}/slam_stdout.log" 2>&1 &
LAUNCH_PID=$!

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

DATA="${RESULTS_DIR}/perf.data"
perf record -g --call-graph dwarf -p "$SLAM_PID" -o "$DATA" -- sleep "$SECS"

# Detener el SLAM antes de generar reportes (libera CPU para que perf report sea rapido)
kill -INT "$LAUNCH_PID" 2>/dev/null
sleep 3

echo "[..] Generando reportes..."
SELF="${RESULTS_DIR}/results_${MODE}_self.txt"
CG="${RESULTS_DIR}/results_${MODE}_callgraph.txt"

# 1) VISTA POR SELF (la clave: dgemm_ al tope, como en la imagen)
perf report -i "$DATA" --stdio --no-children --percent-limit 0.5 2>/dev/null > "$SELF"

# 2) ARBOL de llamadas (contexto: fake_sensor_cb -> arma -> dgemm)
perf report -i "$DATA" --stdio --percent-limit 1 2>/dev/null > "$CG"

# ── Extraer funciones clave de la vista por SELF ─────────────────────────
CSV="${RESULTS_DIR}/results_${MODE}_bottleneck.csv"
echo "funcion,self_pct" > "$CSV"

extract() {
    local pat="$1"
    # En la vista --no-children, la 1ra columna de % ES el self
    local line pct
    line=$(grep -m1 -- "$pat" "$SELF")
    if [ -n "$line" ]; then
        pct=$(echo "$line" | grep -oE "[0-9]+\.[0-9]+%" | head -1 | tr -d '%')
        echo "${pat},${pct:-0}" >> "$CSV"
    fi
}

extract "dgemm"
extract "dgemv"
extract "dtrsm"
extract "fake_sensor_cb"
extract "compute_PHt"
extract "xrt::"
extract "sync"
extract "Cdr::serialize"
extract "cdr_serialize"

echo ""
echo "=================================================="
echo " Cuello de botella ($MODE) - por SELF time:"
echo "=================================================="
cat "$CSV"
echo ""
echo " --- Top 20 funciones por SELF (como la imagen) ---"
grep -E "^\s+[0-9]+\.[0-9]+%" "$SELF" | head -20
echo ""
echo " Archivos en: $RESULTS_DIR"
echo "   * results_${MODE}_self.txt      <- vista por self (para el TFG)"
echo "   * results_${MODE}_callgraph.txt <- arbol de llamadas"
echo "   * results_${MODE}_bottleneck.csv <- funciones clave"
