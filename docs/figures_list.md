# Figures and Tables List

This document lists all figures and tables referenced in or recommended for the research paper.

---

## Tables (included in paper body)

### Table 1: Task Execution Times for Kyber-512 (PC Platform)
- **Location**: Section 4.1 (Results — Task Profiling Results)
- **Description**: All 27 sub-task average, minimum, and maximum execution times measured over 1000 iterations on the PC simulation platform. Organized by operation (KeyGen: 9 tasks, Encaps: 11 tasks, Decaps: 7 tasks).
- **Data Source**: `sim/results/task_times_kyber512.csv`

### Table 2: Critical Path Analysis for Kyber-512
- **Location**: Section 4.2 (Results — Critical Path Analysis)
- **Description**: Total work, critical path length, CP/Work ratio, and maximum theoretical speedup for each KEM operation.
- **Data Source**: Computed from `sim/results/schedule_comparison.txt`

### Table 3: Scheduling Comparison Across Three Scenarios (Kyber-512)
- **Location**: Section 4.3 (Results — Scheduling Analysis)
- **Description**: Segatz vs. HLFET optimal makespan for all three KEM operations under three timing scenarios: (A) PC baseline, (B) ESP32 HW acceleration (SHA/6.1x, AES/9.65x), (C) Conservative acceleration (SHA/4x, AES/6x). Shows gap percentage and speedup over sequential.
- **Data Source**: `sim/results/schedule_comparison.txt` and `sim/results/sensitivity_analysis.txt`

### Table 4: FIPS 203 Compliance Gaps
- **Location**: Section 4.4 (Results — FIPS 203 Gap Analysis)
- **Description**: All nine identified gaps between the implementation and FIPS 203, with severity classification (Critical/Moderate/Minor/Informational) and specific FIPS 203 algorithm/section references.
- **Data Source**: `sim/validation/fips203_gap_analysis.md`

---

## Recommended Figures (to be created for publication)

### Figure 1: Task Execution Time Breakdown (Bar Chart)
- **Description**: Stacked or grouped bar chart showing the relative contribution of each sub-task to total operation time for KeyGen, Encaps, and Decaps. Highlights the dominance of KG.1 (seed expansion, 64.9%) in KeyGen and ENC.2 (matrix generation, 48.5%) in Encaps.
- **Data Source**: `sim/results/task_times_kyber512.csv`
- **Suggested Style**: Horizontal stacked bars with color coding by task type (SHA, AES, NTT, arithmetic).

### Figure 2: Key Generation DAG
- **Description**: Directed acyclic graph showing all 9 KeyGen sub-tasks with precedence edges and execution time weights. The critical path (KG.1→KG.2→KG.7→KG.8→KG.9) should be highlighted in bold or a distinct color. Core assignments should be shown (e.g., via node shading for Core 0 vs Core 1).
- **Data Source**: `sim/dag/dag_tasks.h` and `sim/results/schedule_comparison.txt`

### Figure 3: Encapsulation DAG
- **Description**: Directed acyclic graph showing all 11 Encaps sub-tasks with precedence edges and weights. Critical path (ENC.1→ENC.2→ENC.7→ENC.9→ENC.10→ENC.11) highlighted. Shows where the Segatz and optimal schedules differ under HW acceleration.
- **Data Source**: `sim/dag/dag_tasks.h` and `sim/results/schedule_comparison.txt`

### Figure 4: Decapsulation DAG
- **Description**: Directed acyclic graph showing all 7 Decaps sub-tasks. Critical path (DEC.1→DEC.3→DEC.4→DEC.5→DEC.6→DEC.7) highlighted. Demonstrates the near-serial structure explaining the low 1.03x speedup.
- **Data Source**: `sim/dag/dag_tasks.h` and `sim/results/schedule_comparison.txt`

### Figure 5: Scheduling Gap vs. Hardware Acceleration Factor
- **Description**: Line plot showing the scheduling gap percentage (y-axis) as a function of AES/SHA acceleration factor (x-axis) for all three KEM operations. Demonstrates that the gap is 0% with no acceleration and increases as acceleration grows, with encapsulation diverging most at 6.7% under Scenario B.
- **Data Source**: `sim/results/sensitivity_analysis.txt` (three data points per operation)

### Figure 6: Gantt Chart — Segatz vs. Optimal Schedule (Encapsulation, Scenario B)
- **Description**: Side-by-side Gantt charts showing task placement on Core 0 and Core 1 for the Segatz schedule and the HLFET optimal schedule of the encapsulation operation under Scenario B (HW-accelerated) timing. Visually demonstrates where the 6.7% gap arises from suboptimal task placement.
- **Data Source**: `sim/results/schedule_comparison.txt` (detailed core assignments)

### Figure 7: FIPS 203 Compliance Gap Severity Distribution (Pie Chart)
- **Description**: Pie or donut chart showing the distribution of gaps by severity: 3 Critical, 3 Moderate, 2 Minor, 1 Informational. Simple visual summary for the compliance audit.
- **Data Source**: `sim/validation/fips203_gap_analysis.md`

### Figure 8: KAT Divergence Results
- **Description**: Visual summary (table or heatmap) showing divergence test results: 20/20 different public keys and shared secrets between original and FIPS 203-corrected versions across all three parameter sets (K=2, K=3, K=4). Also shows that both versions independently pass round-trip consistency.
- **Data Source**: KAT test output from `sim/validation/kat_test.c`

---

## Notes for Figure Production

- All figures should be produced at publication quality (300+ DPI for raster, or vector format preferred).
- Color scheme should be accessible (colorblind-safe palette recommended).
- DAG figures (2-4) can be produced using Graphviz, TikZ, or similar tools.
- Charts (1, 5, 6) can be produced using matplotlib, gnuplot, or similar.
- All data values used in figures must match the numbers in the paper exactly.
