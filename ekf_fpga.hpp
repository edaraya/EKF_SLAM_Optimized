// ekf_fpga.hpp
//
// Wrapper que reemplaza la operacion sigma * Hj^T de Armadillo por una
// llamada al kernel HLS en el FPGA (Kria KV260).
//
// Uso:
//   EkfFpga fpga;                          // carga el xclbin una vez
//   arma::mat PHt = fpga.compute_PHt(sigma, Hj);   // n x 2
//   double t_to   = fpga.last_sync_to_us;
//   double t_ker  = fpga.last_kernel_us;
//   double t_from = fpga.last_sync_from_us;
//
// La ruta del xclbin se toma de EKF_XCLBIN_PATH; si no existe, usa
// el default de abajo.

#ifndef EKF_FPGA_HPP_
#define EKF_FPGA_HPP_

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>

#include <armadillo>

#include "xrt/xrt_bo.h"
#include "xrt/xrt_device.h"
#include "xrt/xrt_kernel.h"

class EkfFpga {
public:
  // Tamanos maximos del kernel (deben coincidir con ekf_hls.h)
  static constexpr int MAX_LANDMARKS  = 50;
  static constexpr int MAX_N_STATE    = 2 * MAX_LANDMARKS + 3;   // 103
  static constexpr int HJ_ACTIVE_COLS = 5;
  static constexpr int MAX_SIGMA_SIZE = MAX_N_STATE * MAX_N_STATE;
  static constexpr int HJ_VALS_SIZE   = 2 * HJ_ACTIVE_COLS;      // 10
  static constexpr int HJ_IDX_SIZE    = HJ_ACTIVE_COLS;          // 5
  static constexpr int MAX_PHT_SIZE   = MAX_N_STATE * 2;         // 206

  EkfFpga() {
    const char *env = std::getenv("EKF_XCLBIN_PATH");
    std::string xclbin = env ? std::string(env)
                             : std::string("/home/ubuntu/andres.saballo/ekf_spmm.xclbin");

    device_ = xrt::device(0);
    uuid_   = device_.load_xclbin(xclbin);
    kernel_ = xrt::kernel(device_, uuid_, "ekf_spmm");

    // Reservar buffers (una sola vez, se reutilizan en cada llamada)
    bo_pht_     = xrt::bo(device_, MAX_PHT_SIZE   * sizeof(float), kernel_.group_id(0));
    bo_sigma0_  = xrt::bo(device_, MAX_SIGMA_SIZE * sizeof(float), kernel_.group_id(1));
    bo_sigma1_  = xrt::bo(device_, MAX_SIGMA_SIZE * sizeof(float), kernel_.group_id(2));
    bo_sigma2_  = xrt::bo(device_, MAX_SIGMA_SIZE * sizeof(float), kernel_.group_id(3));
    bo_sigma3_  = xrt::bo(device_, MAX_SIGMA_SIZE * sizeof(float), kernel_.group_id(4));
    bo_sigma4_  = xrt::bo(device_, MAX_SIGMA_SIZE * sizeof(float), kernel_.group_id(5));
    bo_hj_vals_ = xrt::bo(device_, HJ_VALS_SIZE   * sizeof(float), kernel_.group_id(6));
    bo_hj_idx_  = xrt::bo(device_, HJ_IDX_SIZE    * sizeof(int),   kernel_.group_id(7));

    pht_map_     = bo_pht_.map<float*>();
    sigma0_map_  = bo_sigma0_.map<float*>();
    sigma1_map_  = bo_sigma1_.map<float*>();
    sigma2_map_  = bo_sigma2_.map<float*>();
    sigma3_map_  = bo_sigma3_.map<float*>();
    sigma4_map_  = bo_sigma4_.map<float*>();
    hj_vals_map_ = bo_hj_vals_.map<float*>();
    hj_idx_map_  = bo_hj_idx_.map<int*>();
  }

  // Calcula PHt = sigma * Hj^T en el FPGA.
  //   sigma : n x n  (covarianza, simetrica)
  //   Hj    : 2 x n  (Jacobiano sparse, 5 columnas activas)
  //   return: n x 2
  arma::mat compute_PHt(const arma::mat &sigma, const arma::mat &Hj) {
    const int n_state = static_cast<int>(sigma.n_rows);
    if (n_state > MAX_N_STATE) {
      throw std::runtime_error("n_state excede MAX_N_STATE del kernel");
    }

    using clk = std::chrono::steady_clock;
    auto us = [](clk::time_point a, clk::time_point b) {
      return std::chrono::duration<double, std::micro>(b - a).count();
    };

    // ── 1) Detectar las 5 columnas activas de Hj ───────────────────────────
    // (columnas con algun valor distinto de cero)
    int idx[HJ_ACTIVE_COLS];
    int found = 0;
    for (int c = 0; c < n_state && found < HJ_ACTIVE_COLS; ++c) {
      if (Hj(0, c) != 0.0 || Hj(1, c) != 0.0) {
        idx[found++] = c;
      }
    }
    // Si por algun motivo hay menos de 5, rellenar con la ultima
    for (int m = found; m < HJ_ACTIVE_COLS; ++m) idx[m] = (found > 0) ? idx[found - 1] : 0;

    // ── 2) Preparar buffers (esto cuenta como parte de "sync_to") ──────────
    auto t0 = clk::now();

    // sigma a row-major float (sigma es simetrica, pero copiamos explicito)
    for (int i = 0; i < n_state; ++i)
      for (int k = 0; k < n_state; ++k)
        sigma0_map_[i * n_state + k] = static_cast<float>(sigma(i, k));
    std::memcpy(sigma1_map_, sigma0_map_, MAX_SIGMA_SIZE * sizeof(float));
    std::memcpy(sigma2_map_, sigma0_map_, MAX_SIGMA_SIZE * sizeof(float));
    std::memcpy(sigma3_map_, sigma0_map_, MAX_SIGMA_SIZE * sizeof(float));
    std::memcpy(sigma4_map_, sigma0_map_, MAX_SIGMA_SIZE * sizeof(float));

    for (int m = 0; m < HJ_ACTIVE_COLS; ++m) {
      hj_idx_map_[m]                   = idx[m];
      hj_vals_map_[m]                  = static_cast<float>(Hj(0, idx[m]));
      hj_vals_map_[HJ_ACTIVE_COLS + m] = static_cast<float>(Hj(1, idx[m]));
    }

    bo_sigma0_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    bo_sigma1_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    bo_sigma2_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    bo_sigma3_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    bo_sigma4_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    bo_hj_vals_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    bo_hj_idx_.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    auto t1 = clk::now();
    last_sync_to_us = us(t0, t1);

    // ── 3) Lanzar kernel ───────────────────────────────────────────────────
    auto t2 = clk::now();
    auto run = kernel_(bo_pht_,
                       bo_sigma0_, bo_sigma1_, bo_sigma2_, bo_sigma3_, bo_sigma4_,
                       bo_hj_vals_, bo_hj_idx_, n_state);
    run.wait();
    auto t3 = clk::now();
    last_kernel_us = us(t2, t3);

    // ── 4) Traer resultado y armar arma::mat ───────────────────────────────
    auto t4 = clk::now();
    bo_pht_.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    arma::mat PHt(n_state, 2);
    for (int i = 0; i < n_state; ++i) {
      PHt(i, 0) = pht_map_[i * 2 + 0];
      PHt(i, 1) = pht_map_[i * 2 + 1];
    }
    auto t5 = clk::now();
    last_sync_from_us = us(t4, t5);

    return PHt;
  }

  double last_sync_to_us   = 0.0;
  double last_kernel_us    = 0.0;
  double last_sync_from_us = 0.0;

private:
  xrt::device device_;
  xrt::uuid   uuid_;
  xrt::kernel kernel_;

  xrt::bo bo_pht_, bo_sigma0_, bo_sigma1_, bo_sigma2_, bo_sigma3_, bo_sigma4_;
  xrt::bo bo_hj_vals_, bo_hj_idx_;

  float *pht_map_     = nullptr;
  float *sigma0_map_  = nullptr;
  float *sigma1_map_  = nullptr;
  float *sigma2_map_  = nullptr;
  float *sigma3_map_  = nullptr;
  float *sigma4_map_  = nullptr;
  float *hj_vals_map_ = nullptr;
  int   *hj_idx_map_  = nullptr;
};

#endif  // EKF_FPGA_HPP_
