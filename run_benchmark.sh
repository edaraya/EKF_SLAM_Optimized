#!/bin/bash
# run_benchmark.sh
#
# Lanza una corrida del EKF SLAM y recoge:
<<<<<<< HEAD
#   - tiempos de la operacion PHt + estado final  (los escribe slam.cpp via EkfLogger)
#   - potencia + uso de CPU                         (sample_power.sh via xmutil)
=======
#   - tiempos de la operacion PHt           (los escribe el slam.cpp via EkfLogger)
#   - estado final del SLAM                 (idem)
#   - perfil de CPU con perf                 (perf stat adjuntado al nodo)
#   - consumo de potencia                    (sample_power.sh en background)
>>>>>>> 0243932aad2d770a28f55130c96e363ad5304d2c
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

<<<<<<< HEAD
# ── Variables de entorno que lee el slam.cpp ─────────────────────────────
export EKF_CSV_PATH="${RESULTS_DIR}/results_${MODE}_summary.csv"
export EKF_XCLBIN_PATH="${HOME}/andres.saballo/ekf_spmm.xclbin"

=======
# ── Variables de entorno que lee el slam.cpp (EkfLogger / EkfFpga) ───────
export EKF_CSV_PATH="${RESULTS_DIR}/results_${MODE}_summary.csv"
export EKF_XCLBIN_PATH="${HOME}/andres.saballo/ekf_spmm.xclbin"

# ── Comando de lanzamiento (igual para ambas versiones) ──────────────────
>>>>>>> 0243932aad2d770a28f55130c96e363ad5304d2c
LAUNCH_CMD="ros2 launch nuslam nuslam.launch.py robot:=nusim cmd_src:=circle use_rviz:=false"

echo "=================================================="
echo " Corrida: $MODE"
echo " Resultados: $RESULTS_DIR"
<<<<<<< HEAD
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
=======
echo " CSV resumen: $EKF_CSV_PATH"
echo "=================================================="

# ── Iniciar muestreo de potencia en segundo plano ────────────────────────
bash "${SCRIPT_DIR}/sample_power.sh" "${RESULTS_DIR}/results_${MODE}_power.csv" &
POWER_PID=$!
echo "[ok] Muestreo de potencia iniciado (PID $POWER_PID)"

# ── Funcion de limpieza al recibir Ctrl+C ────────────────────────────────
cleanup() {
    echo ""
    echo "Deteniendo prueba..."
    # Detener perf (escribe sus stats al recibir SIGINT)
    [ -n "${PERF_PID:-}" ] && kill -INT "$PERF_PID" 2>/dev/null
    # Detener el nodo slam (gatilla el destructor -> escribe CSV final)
    [ -n "${LAUNCH_PID:-}" ] && kill -INT "$LAUNCH_PID" 2>/dev/null
    # Detener muestreo de potencia
    kill "$POWER_PID" 2>/dev/null
    sleep 4   # darles tiempo a perf y al slam a escribir
>>>>>>> 0243932aad2d770a28f55130c96e363ad5304d2c
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

<<<<<<< HEAD
=======
# ── Esperar a que aparezca el proceso del nodo slam ──────────────────────
echo "[..] Esperando a que arranque el nodo slam..."
SLAM_PID=""
for i in $(seq 1 15); do
    sleep 1
    SLAM_PID=$(pgrep -f "lib/nuslam/slam" | tail -1)
    [ -n "$SLAM_PID" ] && break
done

if [ -z "$SLAM_PID" ]; then
    echo "[ERROR] No se encontro el proceso slam. Revisa ${RESULTS_DIR}/slam_stdout.log"
    cleanup
fi
echo "[ok] Nodo slam corriendo (PID $SLAM_PID)"

# ── Adjuntar perf al nodo slam ───────────────────────────────────────────
# Si perf falla por permisos: sudo sysctl kernel.perf_event_paranoid=-1
perf stat -p "$SLAM_PID" -o "${RESULTS_DIR}/results_${MODE}_perf.txt" &
PERF_PID=$!
echo "[ok] perf adjuntado (PID $PERF_PID)"

>>>>>>> 0243932aad2d770a28f55130c96e363ad5304d2c
echo ""
echo ">>> Prueba en marcha. Presiona Ctrl+C cuando quieras terminar. <<<"
echo ""

<<<<<<< HEAD
=======
# ── Esperar hasta que el usuario interrumpa ──────────────────────────────
>>>>>>> 0243932aad2d770a28f55130c96e363ad5304d2c
wait "$LAUNCH_PID"
cleanup
