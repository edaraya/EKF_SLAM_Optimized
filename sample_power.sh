#!/bin/bash
# sample_power.sh
#
# Muestrea potencia Y uso de CPU de la Kria cada ~1 segundo usando
# xmutil xlnx_platformstats. Escribe un CSV.
#
# Formato de salida de xmutil en esta Kria:
#   "SOM total power   :   4550 mW"      <- potencia total (mW)
#   "CPU0 : 3.00%" ... "CPU3 : 80.58%"   <- uso por core
#
# Uso: ./sample_power.sh <archivo_salida.csv>

OUT="${1:-/tmp/ekf_power.csv}"

echo "timestamp,som_power_mw,cpu0_pct,cpu1_pct,cpu2_pct,cpu3_pct,cpu_avg_pct" > "$OUT"

while true; do
    TS=$(date +%s.%N)

    # Potencia: pedimos power-util (incluye SOM total power)
    PWR_RAW=$(xmutil xlnx_platformstats -p "1 1" 2>/dev/null)
    SOM_MW=$(echo "$PWR_RAW" | grep "SOM total power" | grep -oE "[0-9]+" | head -1)
    SOM_MW=${SOM_MW:-0}

    # CPU: pedimos cpu-util
    CPU_RAW=$(xmutil xlnx_platformstats -c 2>/dev/null)
    C0=$(echo "$CPU_RAW" | grep "CPU0" | grep -oE "[0-9]+\.?[0-9]*" | tail -1)
    C1=$(echo "$CPU_RAW" | grep "CPU1" | grep -oE "[0-9]+\.?[0-9]*" | tail -1)
    C2=$(echo "$CPU_RAW" | grep "CPU2" | grep -oE "[0-9]+\.?[0-9]*" | tail -1)
    C3=$(echo "$CPU_RAW" | grep "CPU3" | grep -oE "[0-9]+\.?[0-9]*" | tail -1)
    C0=${C0:-0}; C1=${C1:-0}; C2=${C2:-0}; C3=${C3:-0}

    # Promedio de los 4 cores
    CAVG=$(echo "$C0 $C1 $C2 $C3" | awk '{printf "%.2f", ($1+$2+$3+$4)/4}')

    echo "${TS},${SOM_MW},${C0},${C1},${C2},${C3},${CAVG}" >> "$OUT"
    sleep 1
done
