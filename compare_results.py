#!/usr/bin/env python3
# compare_results.py
#
# Compara una corrida Armadillo (baseline) contra una corrida FPGA y
# genera comparison_summary.csv con una columna "ganador".
#
# Uso:
#   ./compare_results.py --armadillo results/DIR_armadillo/ \
#                        --fpga      results/DIR_fpga/
#   ./compare_results.py --auto-latest
#
# Solo usa la libreria estandar (no requiere pandas).

import argparse
import csv
import glob
import os
import sys


def read_summary(results_dir, mode):
    path = os.path.join(results_dir, f"results_{mode}_summary.csv")
    if not os.path.exists(path):
        print(f"[WARN] no existe {path}")
        return {}
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def parse_power_cpu(results_dir, mode):
    """Lee el CSV de xmutil: potencia (mW) y CPU (%) promedio + energia."""
    path = os.path.join(results_dir, f"results_{mode}_power.csv")
    out = {"avg_power_w": None, "avg_cpu_pct": None,
           "duration_s": None, "energy_j": None}
    if not os.path.exists(path):
        return out
    ts, pwr_mw, cpu = [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                p = float(row["som_power_mw"])
                c = float(row["cpu_avg_pct"])
                t = float(row["timestamp"])
                # ignorar muestras en cero (lecturas fallidas)
                if p > 0:
                    pwr_mw.append(p)
                    ts.append(t)
                    cpu.append(c)
            except (ValueError, KeyError):
                continue
    if pwr_mw:
        avg_w = (sum(pwr_mw) / len(pwr_mw)) / 1000.0  # mW -> W
        out["avg_power_w"] = avg_w
        out["avg_cpu_pct"] = sum(cpu) / len(cpu)
        if len(ts) >= 2:
            dur = ts[-1] - ts[0]
            out["duration_s"] = dur
            out["energy_j"] = avg_w * dur
    return out


def fmt(v, nd=3):
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def winner_lower(a, b):
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
    ap.add_argument("--armadillo")
    ap.add_argument("--fpga")
    ap.add_argument("--auto-latest", action="store_true")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    base = os.path.expanduser("~/andres.saballo/results")

    if args.auto_latest:
        arma_dirs = sorted(glob.glob(os.path.join(base, "*_armadillo")))
        fpga_dirs = sorted(glob.glob(os.path.join(base, "*_fpga")))
        if not arma_dirs or not fpga_dirs:
            print("[ERROR] faltan carpetas _armadillo o _fpga en", base)
            sys.exit(1)
        arma_dir, fpga_dir = arma_dirs[-1], fpga_dirs[-1]
    else:
        if not args.armadillo or not args.fpga:
            print("[ERROR] pasa --armadillo y --fpga, o usa --auto-latest")
            sys.exit(1)
        arma_dir, fpga_dir = args.armadillo, args.fpga

    print(f"Armadillo: {arma_dir}")
    print(f"FPGA:      {fpga_dir}\n")

    a_sum = read_summary(arma_dir, "armadillo")
    f_sum = read_summary(fpga_dir, "fpga")
    a_pc = parse_power_cpu(arma_dir, "armadillo")
    f_pc = parse_power_cpu(fpga_dir, "fpga")

    rows = []

    # ── Tiempos de la operacion PHt ──────────────────────────────────────
    a_op = to_float(a_sum, "avg_op_us")
    f_op = to_float(f_sum, "avg_op_us")
    speedup = (a_op / f_op) if (a_op and f_op) else None
    rows.append(["avg_op_us", fmt(a_op), fmt(f_op), winner_lower(a_op, f_op),
                 f"{speedup:.2f}x mas rapido FPGA" if speedup else "-"])
    rows.append(["min_op_us", fmt(to_float(a_sum, "min_op_us")),
                 fmt(to_float(f_sum, "min_op_us")),
                 winner_lower(to_float(a_sum, "min_op_us"),
                              to_float(f_sum, "min_op_us")), "-"])
    rows.append(["avg_kernel_us", "N/A", fmt(to_float(f_sum, "avg_kernel_us")),
                 "-", "solo FPGA"])
    rows.append(["avg_sync_to_us", "N/A", fmt(to_float(f_sum, "avg_sync_to_us")),
                 "-", "solo FPGA"])
    rows.append(["avg_sync_from_us", "N/A", fmt(to_float(f_sum, "avg_sync_from_us")),
                 "-", "solo FPGA"])
    rows.append(["total_iterations", fmt(a_sum.get("total_iterations")),
                 fmt(f_sum.get("total_iterations")), "-", "-"])

    # ── CPU y potencia (xmutil) ──────────────────────────────────────────
    a_cpu, f_cpu = a_pc["avg_cpu_pct"], f_pc["avg_cpu_pct"]
    rows.append(["avg_cpu_pct", fmt(a_cpu), fmt(f_cpu), winner_lower(a_cpu, f_cpu),
                 f"{(a_cpu-f_cpu):.1f}% menos CPU" if (a_cpu and f_cpu) else "-"])
    a_pw, f_pw = a_pc["avg_power_w"], f_pc["avg_power_w"]
    rows.append(["avg_power_w", fmt(a_pw), fmt(f_pw), winner_lower(a_pw, f_pw),
                 f"{(a_pw-f_pw):.2f} W menos" if (a_pw and f_pw) else "-"])
    a_e, f_e = a_pc["energy_j"], f_pc["energy_j"]
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
    print("-" * 82)
    for r in rows:
        print(f"{r[0]:<22}{r[1]:>14}{r[2]:>14}{r[3]:>12}   {r[4]}")

    out_path = args.output or os.path.join(base, "comparison_summary.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "armadillo", "fpga", "ganador", "diferencia"])
        w.writerows(rows)
    print(f"\nGuardado: {out_path}")


if __name__ == "__main__":
    main()
