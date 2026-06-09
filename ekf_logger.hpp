// ekf_logger.hpp
//
// Logger compartido para las dos versiones del slam.cpp (Armadillo y FPGA).
//
// Acumula tiempos de la operacion PHt = sigma * Hj^T y captura el estado
// final del EKF. Escribe un CSV de resumen (UNA fila) cada N iteraciones
// y al destruirse, de modo que sobrevive a un Ctrl+C.
//
// La ruta del CSV se toma de la variable de entorno EKF_CSV_PATH; si no
// existe, usa /tmp/ekf_summary.csv.

#ifndef EKF_LOGGER_HPP_
#define EKF_LOGGER_HPP_

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

#include <armadillo>

class EkfLogger {
public:
  explicit EkfLogger(const std::string &mode_name)
  : mode_(mode_name) {
    const char *env = std::getenv("EKF_CSV_PATH");
    csv_path_ = env ? std::string(env) : std::string("/tmp/ekf_summary.csv");
  }

  ~EkfLogger() {
    write_summary();  // ultimo guardado al cerrar el nodo
  }

  // ── Version Armadillo: un solo tiempo (la operacion PHt completa) ────────
  void record_op_time(double microseconds) {
    op_times_.push_back(microseconds);
    maybe_flush();
  }

  // ── Version FPGA: tres fases por separado ────────────────────────────────
  void record_fpga_times(double sync_to_us, double kernel_us,
                         double sync_from_us) {
    sync_to_times_.push_back(sync_to_us);
    kernel_times_.push_back(kernel_us);
    sync_from_times_.push_back(sync_from_us);
    op_times_.push_back(sync_to_us + kernel_us + sync_from_us);  // total
    maybe_flush();
  }

  // ── Captura el estado actual del EKF (se sobreescribe; al final queda
  //    el ultimo = estado final) ───────────────────────────────────────────
  void record_state(const arma::mat &state, const arma::mat &sigma) {
    final_theta_ = state(0);
    final_x_     = state(1);
    final_y_     = state(2);
    final_sigma_theta_ = sigma(0, 0);
    final_sigma_x_     = sigma(1, 1);
    final_sigma_y_     = sigma(2, 2);
    if (state.n_elem >= 5) {
      final_lm0_x_ = state(3);
      final_lm0_y_ = state(4);
    }
    have_state_ = true;
  }

  // ── Escribe el CSV de resumen (una fila) ─────────────────────────────────
  void write_summary() {
    if (op_times_.empty()) return;

    Stats op  = compute_stats(op_times_);
    Stats sto = sync_to_times_.empty()   ? Stats{} : compute_stats(sync_to_times_);
    Stats ker = kernel_times_.empty()    ? Stats{} : compute_stats(kernel_times_);
    Stats sfr = sync_from_times_.empty() ? Stats{} : compute_stats(sync_from_times_);

    std::ofstream f(csv_path_);
    if (!f.is_open()) return;

    // Cabecera
    f << "mode,total_iterations,"
      << "avg_op_us,min_op_us,max_op_us,std_op_us,"
      << "avg_sync_to_us,avg_kernel_us,avg_sync_from_us,"
      << "final_theta,final_x,final_y,"
      << "final_sigma_theta,final_sigma_x,final_sigma_y,"
      << "final_lm0_x,final_lm0_y\n";

    // Una fila de datos
    f << mode_ << ","
      << op_times_.size() << ","
      << op.avg << "," << op.min << "," << op.max << "," << op.std << ","
      << sto.avg << "," << ker.avg << "," << sfr.avg << ","
      << final_theta_ << "," << final_x_ << "," << final_y_ << ","
      << final_sigma_theta_ << "," << final_sigma_x_ << "," << final_sigma_y_ << ","
      << final_lm0_x_ << "," << final_lm0_y_ << "\n";

    f.close();
  }

private:
  struct Stats { double min = 0, max = 0, avg = 0, std = 0; };

  static Stats compute_stats(const std::vector<double> &v) {
    Stats s;
    s.min = std::numeric_limits<double>::max();
    s.max = 0.0;
    double sum = 0.0;
    for (double x : v) {
      s.min = std::min(s.min, x);
      s.max = std::max(s.max, x);
      sum += x;
    }
    s.avg = sum / v.size();
    double var = 0.0;
    for (double x : v) var += (x - s.avg) * (x - s.avg);
    s.std = std::sqrt(var / v.size());
    return s;
  }

  void maybe_flush() {
    // Reescribe el resumen cada 50 operaciones para sobrevivir Ctrl+C
    if (op_times_.size() % 50 == 0) write_summary();
  }

  std::string mode_;
  std::string csv_path_;

  std::vector<double> op_times_;
  std::vector<double> sync_to_times_;
  std::vector<double> kernel_times_;
  std::vector<double> sync_from_times_;

  bool   have_state_ = false;
  double final_theta_ = 0, final_x_ = 0, final_y_ = 0;
  double final_sigma_theta_ = 0, final_sigma_x_ = 0, final_sigma_y_ = 0;
  double final_lm0_x_ = 0, final_lm0_y_ = 0;
};

#endif  // EKF_LOGGER_HPP_
