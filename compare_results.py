#!/usr/bin/env python3
# compare_results.py
#
# Compara una corrida Armadillo (baseline) contra una corrida FPGA y
# genera comparison_summary.csv con una columna "ganador".
#
# Uso:
#   ./compare_results.py --armadillo results/DIR_armadillo/ \
#                        --fpga      results/DIR_fpga/
#   ./compare_results.py --auto-latest         # toma las 2 mas recientes
#
# Solo usa la libreria estandar (no requiere pandas).

import argparse
import csv
import glob
import os
import re
import sys


def read_summary(results_dir, mode):
    """Lee el CSV de resumen (una fila) del slam."""
    path = os.path.join(results_dir, f"results_{mode}_summary.csv")
    if not os.path.exists(path):
        print(f"[WARN] no existe {path}")
        return {}
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def parse_perf(results_dir, mode):
    """Extrae metricas clave del archivo de perf."""
    path = os.path.join(results_dir, f"results_{mode}_perf.txt")
    out = {"cpus_utilized": None, "seconds_elapsed": None,
           "instructions": None, "cache_misses": None}
    if not os.path.exists(path):
        return out
    txt = open(path).read()

    m = re.search(r"([\d.]+)\s+CPUs utilized", txt)
    if m:
        out["cpus_utilized"] = float(m.group(1))
    m = re.search(r"([\d.]+)\s+seconds time elapsed", txt)
    if m:
        out["seconds_elapsed"] = float(m.group(1))
    m = re.search(r"([\d,]+)\s+instructions", txt)
    if m:
        out["instructions"] = int(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+)\s+cache-misses", txt)
    if m:
        out["cache_misses"] = int(m.group(1).replace(",", ""))
    return out


def parse_power(results_dir, mode):
    """Calcula potencia promedio y energia total del CSV de potencia."""
    path = os.path.join(results_dir, f"results_{mode}_power.csv")
    out = {"avg_power_w": None, "duration_s": None, "energy_j": None}
    if not os.path.exists(path):
        return out
    ts, totals = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                ts.append(float(row["timestamp"]))
                totals.append(float(row["total_power_w"]))
            except (ValueError, KeyError):
                continue
    if len(totals) >= 2:
        avg = sum(totals) / len(totals)
        dur = ts[-1] - ts[0]
        out["avg_power_w"] = avg
        out["duration_s"] = dur
        out["energy_j"] = avg * dur
    return out


def fmt(v, nd=3):
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def winner_lower(a, b):
    """Gana el menor (para tiempos, CPU, potencia, energia)."""
    if a is None or b is None:
        return "-"
    return "FPGA" if b < a else ("Armadillo" if a < b else "empate")


def to_float(d, key):
    try:
        return float(d.get(key))
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--armadillo", help="carpeta de la corrida armadillo")
    ap.add_argument("--fpga", help="carpeta de la corrida fpga")
    ap.add_argument("--auto-latest", action="store_true",
                    help="usar las 2 carpetas mas recientes")
    ap.add_argument("--output", default=None, help="ruta del CSV de salida")
    args = ap.parse_args()

    base = os.path.expanduser("~/andres.saballo/results")

    if args.auto_latest:
        arma_dirs = sorted(glob.glob(os.path.join(base, "*_armadillo")))
        fpga_dirs = sorted(glob.glob(os.path.join(base, "*_fpga")))
        if not arma_dirs or not fpga_dirs:
            print("[ERROR] no encontre carpetas _armadillo y _fpga en", base)
            sys.exit(1)
        arma_dir, fpga_dir = arma_dirs[-1], fpga_dirs[-1]
    else:
        if not args.armadillo or not args.fpga:
            print("[ERROR] pasa --armadillo y --fpga, o usa --auto-latest")
            sys.exit(1)
        arma_dir, fpga_dir = args.armadillo, args.fpga

    print(f"Armadillo: {arma_dir}")
    print(f"FPGA:      {fpga_dir}\n")

    # Leer datos
    a_sum = read_summary(arma_dir, "armadillo")
    f_sum = read_summary(fpga_dir, "fpga")
    a_perf, f_perf = parse_perf(arma_dir, "armadillo"), parse_perf(fpga_dir, "fpga")
    a_pow, f_pow = parse_power(arma_dir, "armadillo"), parse_power(fpga_dir, "fpga")

    rows = []

    # ── Tiempos ──────────────────────────────────────────────────────────
    a_op = to_float(a_sum, "avg_op_us")
    f_op = to_float(f_sum, "avg_op_us")
    speedup = (a_op / f_op) if (a_op and f_op) else None
    rows.append(["avg_op_us", fmt(a_op), fmt(f_op), winner_lower(a_op, f_op),
                 f"{speedup:.2f}x mas rapido FPGA" if speedup else "-"])

    rows.append(["avg_kernel_us", "N/A", fmt(to_float(f_sum, "avg_kernel_us")),
                 "-", "solo FPGA"])
    rows.append(["avg_sync_to_us", "N/A", fmt(to_float(f_sum, "avg_sync_to_us")),
                 "-", "solo FPGA"])
    rows.append(["avg_sync_from_us", "N/A", fmt(to_float(f_sum, "avg_sync_from_us")),
                 "-", "solo FPGA"])
    rows.append(["total_iterations", fmt(a_sum.get("total_iterations")),
                 fmt(f_sum.get("total_iterations")), "-", "-"])

    # ── CPU (perf) ───────────────────────────────────────────────────────
    a_cpu, f_cpu = a_perf["cpus_utilized"], f_perf["cpus_utilized"]
    rows.append(["cpus_utilized", fmt(a_cpu), fmt(f_cpu),
                 winner_lower(a_cpu, f_cpu),
                 f"{(1-f_cpu/a_cpu)*100:.1f}% menos CPU" if (a_cpu and f_cpu) else "-"])
    rows.append(["cache_misses", fmt(a_perf["cache_misses"]),
                 fmt(f_perf["cache_misses"]),
                 winner_lower(a_perf["cache_misses"], f_perf["cache_misses"]), "-"])

    # ── Potencia / energia ───────────────────────────────────────────────
    a_pw, f_pw = a_pow["avg_power_w"], f_pow["avg_power_w"]
    rows.append(["avg_power_w", fmt(a_pw), fmt(f_pw), winner_lower(a_pw, f_pw),
                 f"{(a_pw-f_pw):.2f} W menos" if (a_pw and f_pw) else "-"])
    a_e, f_e = a_pow["energy_j"], f_pow["energy_j"]
    rows.append(["energy_j", fmt(a_e), fmt(f_e), winner_lower(a_e, f_e),
                 f"{(1-f_e/a_e)*100:.1f}% menos energia" if (a_e and f_e) else "-"])

    # ── Estado del SLAM (equivalencia, sin ganador) ──────────────────────
    for key, label in [("final_theta", "final_theta (rad)"),
                        ("final_x", "final_x (m)"),
                        ("final_y", "final_y (m)"),
                        ("final_sigma_x", "final_sigma_x"),
                        ("final_sigma_y", "final_sigma_y"),
                        ("final_lm0_x", "final_lm0_x (m)"),
                        ("final_lm0_y", "final_lm0_y (m)")]:
        a_v, f_v = to_float(a_sum, key), to_float(f_sum, key)
        diff = abs(a_v - f_v) if (a_v is not None and f_v is not None) else None
        rows.append([label, fmt(a_v, 5), fmt(f_v, 5), "-",
                     f"dif={diff:.5f}" if diff is not None else "-"])

    # ── Imprimir tabla ───────────────────────────────────────────────────
    print(f"{'metrica':<22}{'armadillo':>14}{'fpga':>14}{'ganador':>12}   diferencia")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<22}{r[1]:>14}{r[2]:>14}{r[3]:>12}   {r[4]}")

    # ── Guardar CSV ──────────────────────────────────────────────────────
    out_path = args.output or os.path.join(base, "comparison_summary.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "armadillo", "fpga", "ganador", "diferencia"])
        w.writerows(rows)
    print(f"\nGuardado: {out_path}")


if __name__ == "__main__":
    main()
