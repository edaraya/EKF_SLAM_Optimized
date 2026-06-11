#!/bin/bash
# profile_bottleneck.sh
#
# Captura el PERFIL POR FUNCION del nodo slam con perf record y genera
# la vista de ARBOL DE LLAMADAS (call-graph), que es donde se evidencia
# el cuello de botella del EKF (fake_sensor_cb -> Armadillo -> dgemm).
#
# Genera en la carpeta de resultados:
#   results_<mode>_callgraph.txt    (arbol de llamadas; la vista clave)
#   results_<mode>_flat.txt         (lista plana por self, complementaria)
#   results_<mode>_bottleneck.csv   (funciones clave extraidas del arbol)
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
# -g  : habilita call-graph (arbol de llamadas)
# --call-graph dwarf : mejor reconstruccion del arbol con C++
perf record -g --call-graph dwarf -p "$SLAM_PID" -o "$DATA" -- sleep "$SECS"

echo "[..] Generando reportes..."
# ARBOL de llamadas (la vista clave para el cuello de botella)
perf report -i "$DATA" --stdio --percent-limit 1 2>/dev/null \
    > "${RESULTS_DIR}/results_${MODE}_callgraph.txt"
# Lista plana por self (complementaria)
perf report -i "$DATA" --stdio -g none --percent-limit 0.5 2>/dev/null \
    > "${RESULTS_DIR}/results_${MODE}_flat.txt"

kill -INT "$LAUNCH_PID" 2>/dev/null
sleep 3

# ── Extraer funciones clave DEL ARBOL ────────────────────────────────────
CG="${RESULTS_DIR}/results_${MODE}_callgraph.txt"
CSV="${RESULTS_DIR}/results_${MODE}_bottleneck.csv"
echo "funcion,porcentaje_arbol" > "$CSV"

# Funcion auxiliar: busca un patron en el arbol y saca el primer % de su linea
extract() {
    local pat="$1"
    local line pct
    line=$(grep -m1 -- "$pat" "$CG")
    if [ -n "$line" ]; then
        # el % en el arbol aparece como  --NN.NN%--  o como  NN.NN%
        pct=$(echo "$line" | grep -oE "[0-9]+\.[0-9]+%" | head -1 | tr -d '%')
        echo "${pat},${pct:-0}" >> "$CSV"
    fi
}

extract "fake_sensor_cb"
extract "glue_times"
extract "eglue_minus"
extract "dgemm"
extract "arma::inv"
extract "arma::solve"
extract "compute_PHt"
extract "xrt::"
extract "Cdr::serialize"

echo ""
echo "=================================================="
echo " Cuello de botella ($MODE) - extraido del arbol:"
echo "=================================================="
cat "$CSV"
echo ""
echo " --- Contexto del arbol (fake_sensor_cb y lo que cuelga) ---"
grep -A 30 "fake_sensor_cb" "$CG" | head -35
echo ""
echo " Archivos en: $RESULTS_DIR"
