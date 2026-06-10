#!/usr/bin/env python3
# compare_bottleneck.py
#
# Compara el perfil por funcion (cuello de botella) entre la corrida
# Armadillo y la FPGA. Lee los CSV generados por profile_bottleneck.sh.
#
# Uso:
#   ./compare_bottleneck.py --armadillo DIR_armadillo_profile \
#                           --fpga      DIR_fpga_profile
#   ./compare_bottleneck.py --auto-latest

import argparse
import csv
import glob
import os
import sys


def read_bottleneck(d, mode):
    """Lee results_<mode>_bottleneck.csv -> dict {funcion: porcentaje}."""
    path = os.path.join(d, f"results_{mode}_bottleneck.csv")
    out = {}
    if not os.path.exists(path):
        print(f"[WARN] no existe {path}")
        return out
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                out[row["funcion"]] = float(row["porcentaje"])
            except (ValueError, KeyError):
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--armadillo")
    ap.add_argument("--fpga")
    ap.add_argument("--auto-latest", action="store_true")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    base = os.path.expanduser("~/andres.saballo/results")

    if args.auto_latest:
        a = sorted(glob.glob(os.path.join(base, "*_armadillo_profile")))
        f = sorted(glob.glob(os.path.join(base, "*_fpga_profile")))
        if not a or not f:
            print("[ERROR] faltan carpetas *_armadillo_profile o *_fpga_profile")
            sys.exit(1)
        arma_dir, fpga_dir = a[-1], f[-1]
    else:
        if not args.armadillo or not args.fpga:
            print("[ERROR] pasa --armadillo y --fpga, o usa --auto-latest")
            sys.exit(1)
        arma_dir, fpga_dir = args.armadillo, args.fpga

    print(f"Armadillo: {arma_dir}")
    print(f"FPGA:      {fpga_dir}\n")

    a_bt = read_bottleneck(arma_dir, "armadillo")
    f_bt = read_bottleneck(fpga_dir, "fpga")

    # Union de funciones, ordenadas por % del baseline (descendente)
    funcs = sorted(set(a_bt) | set(f_bt),
                   key=lambda k: a_bt.get(k, 0), reverse=True)

    print(f"{'funcion':<22}{'armadillo %':>14}{'fpga %':>12}   interpretacion")
    print("-" * 72)
    rows = []
    for fn in funcs:
        av = a_bt.get(fn)
        fv = f_bt.get(fn)
        a_str = f"{av:.2f}" if av is not None else "ausente"
        f_str = f"{fv:.2f}" if fv is not None else "ausente"

        # interpretacion
        if av is not None and fv is not None:
            if fv < av * 0.5:
                interp = "se redujo mucho"
            elif fv < av:
                interp = "se redujo"
            elif fv > av:
                interp = "aumento"
            else:
                interp = "igual"
        elif av is not None and fv is None:
            interp = "desaparecio en FPGA"
        elif av is None and fv is not None:
            interp = "nuevo en FPGA (XRT/kernel)"
        else:
            interp = "-"

        print(f"{fn:<22}{a_str:>14}{f_str:>12}   {interp}")
        rows.append([fn, a_str, f_str, interp])

    out_path = args.output or os.path.join(base, "comparison_bottleneck.csv")
    with open(out_path, "w", newline="") as fout:
        w = csv.writer(fout)
        w.writerow(["funcion", "armadillo_pct", "fpga_pct", "interpretacion"])
        w.writerows(rows)
    print(f"\nGuardado: {out_path}")

    # Resumen de dgemm (la clave del TFG)
    dg_a = a_bt.get("dgemm")
    dg_f = f_bt.get("dgemm")
    if dg_a is not None:
        print("\n--- Resumen para el TFG ---")
        if dg_f is not None:
            print(f"dgemm (BLAS) paso de {dg_a:.1f}% a {dg_f:.1f}% del tiempo del proceso.")
        else:
            print(f"dgemm (BLAS) era {dg_a:.1f}% en baseline y ya no aparece como cuello en FPGA.")


if __name__ == "__main__":
    main()
