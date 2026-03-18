# Research Summary

**Project:** Software Analysis of CRYSTALS-Kyber ESP32 Implementation: Scheduling Optimality and FIPS 203 Compliance  
**Author:** Karan  
**Date:** March 2026

---

## Research Questions

This project addresses two formally defined questions about an existing dual-core CRYSTALS-Kyber implementation on the ESP32 microcontroller (Segatz and Al Hafiz, 2022):

1. **Is the empirical dual-core task assignment a provably optimal schedule?** Specifically, does the two-core partitioning achieve the minimum possible execution time (makespan) as defined by the critical path lower bound of the task dependency graph?

2. **Does the implementation conform to the finalized FIPS 203 (ML-KEM) standard published by NIST in August 2024?** If not, what are the specific deviations, how severe are they, and do they prevent interoperability with conforming implementations?

---

## Contribution 1: Formal Scheduling Analysis

We decomposed the three Kyber KEM operations into 27 sub-tasks (9 for key generation, 11 for encapsulation, 7 for decapsulation), measured execution times, and constructed directed acyclic graphs (DAGs) encoding task dependencies. We then computed the mathematically optimal two-processor schedule using the HLFET list scheduling algorithm and compared it against the Segatz assignment.

**Baseline result (software-only timing):** The Segatz schedule achieves optimal makespan with a 0.0% gap across all three operations. We proved that this is not coincidental but structural: when the critical-path-to-total-work ratio exceeds approximately 85%, any valid assignment that places critical-path tasks on one core achieves the lower bound. We term this condition *scheduling saturation*. Key generation (87.5% ratio) and decapsulation (96.9%) are saturated; encapsulation (66.0%) is the only operation where scheduling decisions are non-trivial. This formal characterization is the theoretical baseline that makes the sensitivity analysis meaningful — without establishing 0.0% first, the gap under acceleration has no reference point.

**Sensitivity analysis (hardware acceleration model):** We developed an analytical model that predicts scheduling behavior under ESP32 hardware acceleration. The model scales task weights by the speedup ratios reported by Segatz (6.1× for SHA, 9.65× for AES), representing how hardware accelerators compress the dominant hash and cipher tasks relative to polynomial arithmetic. Under these conditions, the scheduling gap opens:

- Key generation: 2.7% gap (Segatz 61.66 μs vs. optimal 60.05 μs)
- Encapsulation: 6.7% gap (Segatz 36.96 μs vs. optimal 34.62 μs)
- Decapsulation: 0.0% gap (no SHA/AES tasks, unaffected by acceleration)

The model makes a falsifiable prediction: encapsulation performance on ESP32 hardware is recoverable by approximately 6.7% through adoption of the HLFET-optimal task assignment. This prediction is testable through on-hardware implementation.

---

## Contribution 2: FIPS 203 Compliance Audit

We present the first systematic compliance audit of an ESP32 Kyber implementation against the finalized FIPS 203 standard — no prior work could have conducted this audit, as FIPS 203 was published in August 2024. The audit compared every function in the source code against the corresponding FIPS 203 algorithm, producing a gap taxonomy with severity classification and algorithm-level citations.

**Findings:** 9 gaps total — 3 Critical, 3 Moderate, 2 Minor, 1 Informational. The three critical gaps all affect shared secret computation:

| Gap | Issue | Impact |
|-----|-------|--------|
| **GAP-1** | Key generation hashes seed alone (32 bytes) instead of seed + parameter byte (33 bytes) as specified in FIPS 203 Algorithm 13 | Same seed produces identical keys across security levels |
| **GAP-2** | Encapsulation pre-hashes random message with H(m), a step FIPS 203 Algorithm 17 removed | Different shared secret from same randomness |
| **GAP-3** | Shared secret derived via KDF(K'‖H(c)) instead of direct K; implicit rejection uses wrong construction | Both sides compute different keys — interoperation impossible |

**Validation:** We implemented algorithmic fixes in `components_fips203/` and confirmed through divergence testing that the original and corrected versions produce different outputs in 20 out of 20 trials across all three parameter sets (Kyber-512, 768, 1024), while both versions maintain internal round-trip consistency. This gap taxonomy is a reusable artifact applicable to any implementation derived from the 2022 pq-crystals reference codebase.

---

## Summary of Contributions

| Contribution | Key Result |
|-------------|------------|
| Formal scheduling analysis of 27 sub-tasks across 3 KEM operations | Segatz schedule is provably optimal under software timing (0.0% gap) |
| Identification of scheduling saturation condition | CP/Work ratio > 85% makes any valid 2-core assignment optimal |
| Parameterized sensitivity model of hardware acceleration | Gap opens to 6.7% for encapsulation under ESP32 HW acceleration |
| First systematic FIPS 203 compliance audit of ESP32 Kyber | 9 gaps identified with severity taxonomy and algorithm-level citations |
| Divergence testing across all parameter sets | 20/20 confirmed divergence validates gap findings |

---

## Limitations

All timing measurements were obtained on a PC simulation platform, not ESP32 hardware. The scheduling analysis is therefore based on relative task weights rather than absolute hardware timings. The sensitivity model applies uniform scaling factors per task category, which approximates but does not perfectly replicate per-task hardware behavior. The FIPS 203 algorithmic fixes retain 90s symmetric primitives (SHA-2, AES) rather than the mandated SHA-3/SHAKE, demonstrating correct algorithmic structure without achieving full primitive-level compliance.

---

## Future Work

Three natural extensions follow from this analysis. First, on-hardware validation of the HLFET-optimal schedule on ESP32 would confirm or refine the predicted 6.7% improvement for encapsulation. Second, migration of the symmetric primitive layer from AES/SHA-2 to SHA-3/SHAKE would complete FIPS 203 compliance and enable validation against NIST's official ML-KEM test vectors. Third, algorithmic optimization of matrix A generation — which dominates the critical path across all scenarios — would yield larger absolute speedups than any scheduling rearrangement.
