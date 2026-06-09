#!/bin/bash
# run_benchmark.sh
#
# Lanza una corrida del EKF SLAM y recoge:
#   - tiempos de la operacion PHt + estado final  (los escribe slam.cpp via EkfLogger)
#   - potencia + uso de CPU                         (sample_power.sh via xmutil)
#
# Uso:
#   ./run_benchmark.sh armadillo     # corrida baseline (CPU)
#   ./run_benchmark.sh fpga          # corrida acelerada (FPGA)
#
# Vos cronometras: presiona Ctrl+C cuando quieras terminar.

set -u
MODE="${1:-}"

if [ "$MODE" != "armadillo" ] && [ "$MODE" != "fpga" ]; then
    echo "Uso: $0 [armadillo|fpga]"
    exit 1
fi

# ── Carpeta de resultados con timestamp ──────────────────────────────────
TS=$(date +%Y-%m-%d_%H-%M-%S)
BASE="$HOME/andres.saballo/results"
RESULTS_DIR="${BASE}/${TS}_${MODE}"
mkdir -p "$RESULTS_DIR"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Variables de entorno que lee el slam.cpp ─────────────────────────────
export EKF_CSV_PATH="${RESULTS_DIR}/results_${MODE}_summary.csv"
export EKF_XCLBIN_PATH="${HOME}/andres.saballo/ekf_spmm.xclbin"

LAUNCH_CMD="ros2 launch nuslam nuslam.launch.py robot:=nusim cmd_src:=circle use_rviz:=false"

echo "=================================================="
echo " Corrida: $MODE"
echo " Resultados: $RESULTS_DIR"
echo "=================================================="

# ── Iniciar muestreo de potencia + CPU en segundo plano ──────────────────
bash "${SCRIPT_DIR}/sample_power.sh" "${RESULTS_DIR}/results_${MODE}_power.csv" &
POWER_PID=$!
echo "[ok] Muestreo de potencia/CPU iniciado (PID $POWER_PID)"

# ── Limpieza al recibir Ctrl+C ───────────────────────────────────────────
cleanup() {
    echo ""
    echo "Deteniendo prueba..."
    [ -n "${LAUNCH_PID:-}" ] && kill -INT "$LAUNCH_PID" 2>/dev/null
    kill "$POWER_PID" 2>/dev/null
    sleep 4   # darle tiempo al slam a escribir el CSV final
    echo ""
    echo "=================================================="
    echo " Listo. Archivos en:"
    echo "   $RESULTS_DIR"
    ls -la "$RESULTS_DIR"
    echo "=================================================="
    exit 0
}
trap cleanup INT

# ── Lanzar el SLAM en segundo plano ──────────────────────────────────────
echo "[..] Lanzando SLAM..."
$LAUNCH_CMD > "${RESULTS_DIR}/slam_stdout.log" 2>&1 &
LAUNCH_PID=$!

echo ""
echo ">>> Prueba en marcha. Presiona Ctrl+C cuando quieras terminar. <<<"
echo ""

wait "$LAUNCH_PID"
cleanup
