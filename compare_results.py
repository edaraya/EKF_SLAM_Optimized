#!/usr/bin/env python3
# compare_results.py
#
# Compara una corrida Armadillo (baseline) contra una corrida FPGA y
# genera comparison_summary.csv con una columna "ganador".
#
# Lee tres fuentes por corrida:
#   - results_<mode>_summary.csv  (tiempos + estado del slam)
#   - results_<mode>_power.csv    (potencia + CPU via xmutil)
#   - results_<mode>_perf.txt     (cache, IPC, branches via perf)
#
# Uso:
#   ./compare_results.py --armadillo DIR --fpga DIR
#   ./compare_results.py --auto-latest

import argparse
import csv
import glob
import os
import re
import sys


def read_summary(d, mode):
    path = os.path.join(d, f"results_{mode}_summary.csv")
    if not os.path.exists(path):
        print(f"[WARN] no existe {path}")
        return {}
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def parse_power_cpu(d, mode):
    """Potencia (mW->W) y CPU (%) promedio + energia, desde xmutil CSV."""
    path = os.path.join(d, f"results_{mode}_power.csv")
    out = {"avg_power_w": None, "avg_cpu_pct": None,
           "duration_s": None, "energy_j": None}
    if not os.path.exists(path):
        return out
    ts, pwr, cpu = [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                p = float(row["som_power_mw"])
                if p > 0:
                    pwr.append(p)
                    cpu.append(float(row["cpu_avg_pct"]))
                    ts.append(float(row["timestamp"]))
            except (ValueError, KeyError):
                continue
    if pwr:
        avg_w = (sum(pwr) / len(pwr)) / 1000.0
        out["avg_power_w"] = avg_w
        out["avg_cpu_pct"] = sum(cpu) / len(cpu)
        if len(ts) >= 2:
            out["duration_s"] = ts[-1] - ts[0]
            out["energy_j"] = avg_w * out["duration_s"]
    return out


def parse_perf(d, mode):
    """Extrae contadores micro-arquitectonicos del archivo de perf."""
    path = os.path.join(d, f"results_{mode}_perf.txt")
    out = {"instructions": None, "cycles": None, "ipc": None,
           "cache_misses": None, "cache_miss_rate": None,
           "branch_misses": None, "context_switches": None}
    if not os.path.exists(path):
        return out
    txt = open(path).read()

    def grab(pat):
        m = re.search(pat, txt)
        return int(m.group(1).replace(",", "").replace(".", "")) if m else None

    out["instructions"]     = grab(r"([\d.,]+)\s+instructions")
    out["cycles"]           = grab(r"([\d.,]+)\s+cycles")
    out["cache_misses"]     = grab(r"([\d.,]+)\s+cache-misses")
    out["branch_misses"]    = grab(r"([\d.,]+)\s+branch-misses")
    out["context_switches"] = grab(r"([\d.,]+)\s+context-switches")

    # IPC y cache-miss-rate los suele imprimir perf en la misma linea
    m = re.search(r"#\s+([\d.]+)\s+insn per cycle", txt)
    if m:
        out["ipc"] = float(m.group(1))
    m = re.search(r"#\s+([\d.]+)\s*% of all cache refs", txt)
    if m:
        out["cache_miss_rate"] = float(m.group(1))
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


def tof(d, k):
    try:
        return float(d.get(k))
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
        a_dirs = sorted(glob.glob(os.path.join(base, "*_armadillo")))
        f_dirs = sorted(glob.glob(os.path.join(base, "*_fpga")))
        if not a_dirs or not f_dirs:
            print("[ERROR] faltan carpetas _armadillo o _fpga en", base)
            sys.exit(1)
        arma_dir, fpga_dir = a_dirs[-1], f_dirs[-1]
    else:
        if not args.armadillo or not args.fpga:
            print("[ERROR] pasa --armadillo y --fpga, o usa --auto-latest")
            sys.exit(1)
        arma_dir, fpga_dir = args.armadillo, args.fpga

    print(f"Armadillo: {arma_dir}")
    print(f"FPGA:      {fpga_dir}\n")

    a_s, f_s = read_summary(arma_dir, "armadillo"), read_summary(fpga_dir, "fpga")
    a_pc, f_pc = parse_power_cpu(arma_dir, "armadillo"), parse_power_cpu(fpga_dir, "fpga")
    a_pf, f_pf = parse_perf(arma_dir, "armadillo"), parse_perf(fpga_dir, "fpga")

    rows = []

    # ── Tiempos de la operacion PHt ──────────────────────────────────────
    a_op, f_op = tof(a_s, "avg_op_us"), tof(f_s, "avg_op_us")
    sp = (a_op / f_op) if (a_op and f_op) else None
    rows.append(["avg_op_us", fmt(a_op), fmt(f_op), winner_lower(a_op, f_op),
                 f"{sp:.2f}x mas rapido FPGA" if sp else "-"])
    rows.append(["min_op_us", fmt(tof(a_s, "min_op_us")), fmt(tof(f_s, "min_op_us")),
                 winner_lower(tof(a_s, "min_op_us"), tof(f_s, "min_op_us")), "-"])
    rows.append(["avg_kernel_us", "N/A", fmt(tof(f_s, "avg_kernel_us")), "-", "solo FPGA"])
    rows.append(["avg_sync_to_us", "N/A", fmt(tof(f_s, "avg_sync_to_us")), "-", "solo FPGA"])
    rows.append(["avg_sync_from_us", "N/A", fmt(tof(f_s, "avg_sync_from_us")), "-", "solo FPGA"])
    rows.append(["total_iterations", fmt(a_s.get("total_iterations")),
                 fmt(f_s.get("total_iterations")), "-", "-"])

    # ── CPU y potencia (xmutil) ──────────────────────────────────────────
    a_cpu, f_cpu = a_pc["avg_cpu_pct"], f_pc["avg_cpu_pct"]
    rows.append(["avg_cpu_pct", fmt(a_cpu), fmt(f_cpu), winner_lower(a_cpu, f_cpu),
                 f"{(a_cpu-f_cpu):.1f}% menos CPU" if (a_cpu and f_cpu) else "-"])
    a_pw, f_pw = a_pc["avg_power_w"], f_pc["avg_power_w"]
    rows.append(["avg_power_w", fmt(a_pw), fmt(f_pw), winner_lower(a_pw, f_pw),
                 f"{(a_pw-f_pw):.2f} W" if (a_pw and f_pw) else "-"])
    a_e, f_e = a_pc["energy_j"], f_pc["energy_j"]
    rows.append(["energy_j", fmt(a_e), fmt(f_e), winner_lower(a_e, f_e),
                 f"{(1-f_e/a_e)*100:.1f}% menos energia" if (a_e and f_e) else "-"])

    # ── perf (micro-arquitectura del proceso slam) ───────────────────────
    a_cm, f_cm = a_pf["cache_misses"], f_pf["cache_misses"]
    rows.append(["cache_misses", fmt(a_cm), fmt(f_cm), winner_lower(a_cm, f_cm), "-"])
    a_ipc, f_ipc = a_pf["ipc"], f_pf["ipc"]
    rows.append(["ipc_insn_per_cycle", fmt(a_ipc), fmt(f_ipc),
                 winner_lower(f_ipc, a_ipc) if (a_ipc and f_ipc) else "-",
                 "mayor es mejor"])
    a_bm, f_bm = a_pf["branch_misses"], f_pf["branch_misses"]
    rows.append(["branch_misses", fmt(a_bm), fmt(f_bm), winner_lower(a_bm, f_bm), "-"])
    a_cs, f_cs = a_pf["context_switches"], f_pf["context_switches"]
    rows.append(["context_switches", fmt(a_cs), fmt(f_cs), winner_lower(a_cs, f_cs), "-"])

    # ── Estado del SLAM (equivalencia) ───────────────────────────────────
    for key, label in [("final_theta", "final_theta (rad)"),
                        ("final_x", "final_x (m)"),
                        ("final_y", "final_y (m)"),
                        ("final_sigma_x", "final_sigma_x"),
                        ("final_sigma_y", "final_sigma_y"),
                        ("final_lm0_x", "final_lm0_x (m)"),
                        ("final_lm0_y", "final_lm0_y (m)")]:
        a_v, f_v = tof(a_s, key), tof(f_s, key)
        diff = abs(a_v - f_v) if (a_v is not None and f_v is not None) else None
        rows.append([label, fmt(a_v, 5), fmt(f_v, 5), "-",
                     f"dif={diff:.5f}" if diff is not None else "-"])

    # ── Imprimir ─────────────────────────────────────────────────────────
    print(f"{'metrica':<22}{'armadillo':>14}{'fpga':>14}{'ganador':>12}   diferencia")
    print("-" * 84)
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
