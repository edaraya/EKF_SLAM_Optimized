#!/bin/bash
# sample_power.sh
#
# Muestrea la potencia de la Kria cada 1 segundo usando xmutil y la
# escribe en un CSV. Corre en segundo plano; se mata con su PID cuando
# termina la prueba.
#
# Uso: ./sample_power.sh <archivo_salida.csv>

OUT="${1:-/tmp/ekf_power.csv}"

echo "timestamp,ps_power_w,pl_power_w,total_power_w" > "$OUT"

while true; do
    TS=$(date +%s.%N)

    # xmutil platformstats --power imprime varias lineas; extraemos los W.
    STATS=$(xmutil platformstats --power 2>/dev/null)

    # Intentamos parsear PS y PL. Los nombres exactos pueden variar segun
    # version de xmutil; ajustamos con grep flexible.
    PS=$(echo "$STATS"  | grep -i "som total power\|ps power\|ina260"   | head -1 | grep -oE "[0-9]+\.?[0-9]*" | head -1)
    PL=$(echo "$STATS"  | grep -i "pl power\|vccint"                    | head -1 | grep -oE "[0-9]+\.?[0-9]*" | head -1)
    TOT=$(echo "$STATS" | grep -i "total"                              | head -1 | grep -oE "[0-9]+\.?[0-9]*" | head -1)

    # Defaults si no se pudo parsear
    PS=${PS:-0}
    PL=${PL:-0}
    TOT=${TOT:-0}

    echo "${TS},${PS},${PL},${TOT}" >> "$OUT"
    sleep 1
done
