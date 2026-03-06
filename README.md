# CRYSTALS-KYBER on ESP32 — FIPS 203 Gap Analysis & DAG Scheduling

This project extends the work of **Segatz and Al Hafiz (2022)**, *"Efficient Implementation of CRYSTALS-KYBER Key Encapsulation Mechanism on ESP32"*, by adding two original research contributions:

1. **FIPS 203 Compliance Gap Analysis** — comparing the 2022 draft-era KYBER implementation against the finalized [NIST FIPS 203 (ML-KEM)](https://csrc.nist.gov/pubs/fips/203/final) standard
2. **DAG Scheduling Analysis** — modeling the Kyber algorithm as a Directed Acyclic Graph, instrumenting individual sub-task timings, and applying Critical Path Method (CPM) and List Scheduling to find the theoretically optimal 2-core schedule vs. Segatz's empirical hand-partitioned schedule

## Attribution

| Component | Source | License |
|-----------|--------|---------|
| ESP32 Kyber implementation | [github.com/fsegatz/kybesp32](https://github.com/fsegatz/kybesp32) — Segatz & Al Hafiz (2022) | Academic |
| KYBER reference code | [github.com/pq-crystals/kyber](https://github.com/pq-crystals/kyber) — Bos, Ducas, Kiltz, Lepoint, Lyubashevsky, Schwabe, Shanck, Stehlé | Public domain (CC0) |
| Simulation framework (`sim/`) | **Original contribution** — this project | — |
| FIPS 203 gap analysis | **Original contribution** — this project | — |
| DAG scheduling analysis | **Original contribution** — this project | — |

## Base Implementation Features

- **Kyber-512 / Kyber-768 / Kyber-1024** support (configurable via `KYBER_K`)
- **90s variant** using AES-256-CTR + SHA-256/512 (toggle with `KYBER_90S`)
- **Dual-core parallelization** for IND-CPA key generation, encryption, and decryption using FreeRTOS tasks
- **Hardware acceleration** for SHA-256/512 and AES-256 via ESP32's mbedtls backend
- Random number generation using ESP32's hardware RNG (`esp_fill_random`)

## Prerequisites

### ESP32 Hardware Build (original — requires hardware)
- [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/) v5.0 or later
- ESP32 development board (tested on [ESP32-S3-DevKitC-1](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/hw-reference/esp32s3/user-guide-devkitc-1.html))

### PC Simulation & Analysis (original contribution — no hardware needed)
- GCC (MinGW on Windows)
- Python 3.8+ with `matplotlib` and `numpy`

## Build Instructions

1. Set up the ESP-IDF environment following the [official guide](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/) or use the [VS Code ESP-IDF extension](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/vscode-setup.html).

2. Configure the build options in `CMakeLists.txt`:
   ```cmake
   add_compile_definitions("KYBER_90S")           # Use 90s variant
   add_compile_definitions("KYBER_K=2")            # 2=Kyber512, 3=Kyber768, 4=Kyber1024
   add_compile_definitions("SHA_ACC=1")            # 1=Use HW SHA accelerator, 0=Software
   add_compile_definitions("AES_ACC=1")            # 1=Use HW AES accelerator, 0=Software
   add_compile_definitions("INDCPA_KEYPAIR_DUAL=1")# 1=Dual-core keygen, 0=Single-core
   add_compile_definitions("INDCPA_ENC_DUAL=1")    # 1=Dual-core encryption, 0=Single-core
   add_compile_definitions("INDCPA_DEC_DUAL=0")    # 1=Dual-core decryption, 0=Single-core
   ```

3. Build, flash, and monitor:
   ```bash
   idf.py build
   idf.py -p <PORT> flash monitor
   ```

After flashing, the firmware runs a KEM round-trip (keygen → encapsulation → decapsulation) and reports cycle counts over the serial interface.

## Project Structure

```
├── components/                 # Base Kyber implementation (Segatz & Al Hafiz 2022)
│   ├── aes256ctr/              AES-256 in CTR mode
│   ├── cbd/                    Centered Binomial Distribution sampling
│   ├── common/                 Shared parameters and config (params.h)
│   ├── fips202/                SHAKE-128/256, SHA3-256/512 (Keccak)
│   ├── indcpa/                 IND-CPA public-key encryption (+ dual-core variants)
│   ├── kem/                    Key Encapsulation Mechanism (keygen, enc, dec)
│   ├── kex/                    Key Exchange protocols (UAKE, AKE)
│   ├── ntt/                    Number Theoretic Transform
│   ├── poly/                   Polynomial operations
│   ├── polyvec/                Polynomial vector operations
│   ├── randombytes/            RNG wrapper using esp_fill_random
│   ├── reduce/                 Montgomery and Barrett reduction
│   ├── sha2/                   SHA-256 and SHA-512
│   ├── symmetric/              Symmetric primitive abstractions (AES/SHAKE)
│   └── verify/                 Constant-time comparison and conditional move
├── main/                       # ESP32 entry point
├── sim/                        # *** ORIGINAL CONTRIBUTION ***
│   ├── platform/
│   │   └── randombytes_pc.c    Windows CryptoAPI RNG shim
│   ├── validation/
│   │   ├── round_trip_test.c   KEM correctness tests
│   │   └── kat_vectors/        NIST ACVP Known Answer Test vectors
│   ├── benchmarks/
│   │   ├── benchmark.c         Timing benchmarks (keygen, encap, decap)
│   │   └── task_profiler.c     Individual sub-task timing for DAG analysis
│   ├── dag_analysis/
│   │   ├── dag_tasks.h         Task dependency graph definitions
│   │   ├── critical_path.py    Critical Path Method (CPM) computation
│   │   └── list_scheduler.py   Optimal 2-core List Scheduling + Gantt chart
│   ├── results/                Output CSVs, PNGs, analysis reports (gitignored)
│   ├── build_validation.bat    Build and run correctness tests
│   ├── build_benchmark.bat     Build and run timing benchmarks
│   └── build_profiler.bat      Build task profiler + run DAG analysis
├── docs/
│   └── NIST.FIPS.203.pdf       FIPS 203 standard document
├── CMakeLists.txt              Top-level ESP-IDF build config
└── README.md
```

## Configuration Options

| Define | Values | Description |
|--------|--------|-------------|
| `KYBER_K` | `2`, `3`, `4` | Security level: Kyber-512, 768, or 1024 |
| `KYBER_90S` | defined/undefined | Use AES+SHA (90s) variant vs SHAKE variant |
| `SHA_ACC` | `0`, `1` | Enable ESP32 hardware SHA accelerator |
| `AES_ACC` | `0`, `1` | Enable ESP32 hardware AES accelerator |
| `INDCPA_KEYPAIR_DUAL` | `0`, `1` | Dual-core key pair generation |
| `INDCPA_ENC_DUAL` | `0`, `1` | Dual-core encryption |
| `INDCPA_DEC_DUAL` | `0`, `1` | Dual-core decryption |

## ESP32 Hardware Benchmark Results (Segatz & Al Hafiz 2022)

Tested on ESP32-S3-DevKitC-1 at 160 MHz, ESP-IDF v5.0, GCC 8.4.0, Kyber-512 (90s variant):

| Configuration | Key Generation | Encapsulation | Decapsulation | Speedup |
|--------------|---------------|---------------|---------------|---------|
| Single-core (baseline) | 2,439,083 | 2,736,256 | 2,736,256 | 1.00x |
| Dual-core | 2,007,689 | 2,243,652 | 2,471,286 | ~1.21x |
| Dual-core + HW accel | 1,414,389 | 1,490,784 | 1,756,638 | ~1.84x |

## Running the Analysis Pipeline

```bash
cd sim

# 1. Correctness validation
build_validation.bat

# 2. Performance benchmarks
build_benchmark.bat

# 3. Full DAG analysis pipeline (profile + CPM + scheduling)
build_profiler.bat
```

### Output Files

| File | Description |
|------|-------------|
| `results/task_times_kyber512.csv` | Per-subtask timing data (Kyber-512) |
| `results/task_times_kyber768.csv` | Per-subtask timing data (Kyber-768) |
| `results/task_times_kyber1024.csv` | Per-subtask timing data (Kyber-1024) |
| `results/critical_path_analysis.txt` | CPM analysis report |
| `results/optimal_schedule.png` | Gantt chart: optimal vs. Segatz schedule |
| `results/benchmark_kyberXXX.csv` | Raw benchmark timing data |

## References

1. Segatz, F. & Al Hafiz, K. (2022). *Efficient Implementation of CRYSTALS-KYBER Key Encapsulation Mechanism on ESP32*. [github.com/fsegatz/kybesp32](https://github.com/fsegatz/kybesp32)
2. Bos, J. et al. *CRYSTALS-Kyber: a CCA-secure module-lattice-based KEM*. [pq-crystals.org/kyber](https://pq-crystals.org/kyber/)
3. NIST. *FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard*. 2024. [csrc.nist.gov/pubs/fips/203/final](https://csrc.nist.gov/pubs/fips/203/final)

