# Research Summary — Simple Explanation

**Project:** Software Analysis of CRYSTALS-Kyber on ESP32
**Author:** Karan
**Date:** March 2026

---

## What is this project about?

Quantum computers are coming, and they will be able to break the encryption we use today (like RSA). To prepare for this, NIST (the US standards body) selected a new encryption algorithm called **CRYSTALS-Kyber** that quantum computers cannot break. In 2024, NIST published it as an official standard called **FIPS 203 (ML-KEM)**.

The **ESP32** is a cheap, popular microcontroller used in IoT devices (smart home gadgets, sensors, etc.). It has two CPU cores and built-in hardware that speeds up SHA hashing and AES encryption. In 2022, **Segatz and Al Hafiz** wrote a paper showing how to run Kyber on the ESP32 by splitting the work across both cores to make it faster.

My project asked two questions about their work:

1. **Is their way of splitting work between the two cores actually the best possible way?**
2. **Does their code follow the final FIPS 203 standard that came out in 2024?**

---

## Part 1: Is Their Two-Core Schedule Optimal?

**What I did:** I took the Kyber algorithm and broke it into 27 small tasks (9 for key generation, 11 for encapsulation, 7 for decapsulation). I measured how long each task takes. Then I built a dependency graph (called a DAG) showing which tasks depend on which — for example, you cannot multiply a matrix until you have generated it first. I used a well-known scheduling algorithm (HLFET list scheduler) to compute the mathematically best way to assign these tasks to two cores, and compared it against what Segatz did.

**What I found:**

- **With normal software timing:** Segatz's schedule is already perfect — 0.0% gap from optimal for all three operations (key generation, encapsulation, decapsulation). This is because one or two tasks (like seed expansion and matrix generation) are so much bigger than everything else that it does not matter how you arrange the small tasks.

- **But when I simulated the ESP32's hardware accelerators** (which make SHA 6.1x faster and AES 9.65x faster), the picture changed. The hardware shrinks those big tasks, making all the other tasks relatively more important. Now the scheduling starts to matter:
  - Key generation: Segatz is 2.7% slower than optimal (61.66 μs vs 60.05 μs)
  - Encapsulation: Segatz is 6.7% slower than optimal (36.96 μs vs 34.62 μs)
  - Decapsulation: still 0.0% gap (no SHA/AES tasks involved)

**What this means:** Segatz's schedule works great when SHA and AES are done in software, but when the ESP32's hardware accelerators are used, there is room for a better arrangement of tasks — especially for encapsulation.

---

## Part 2: Does It Follow the FIPS 203 Standard?

**What I did:** I read the official FIPS 203 document line by line, then compared every function in Segatz's code against what the standard says. I classified each difference by how serious it is.

**What I found:** 9 gaps total. The three most critical ones are:

| Gap | Problem | Why It Matters |
|-----|---------|----------------|
| **GAP-1** | Key generation hashes the seed alone (32 bytes), but FIPS 203 says to hash seed + security level byte (33 bytes) | Same seed would give the same key for Kyber-512, 768, and 1024. The standard prevents this. |
| **GAP-2** | Encapsulation pre-hashes the random message with H(m), but FIPS 203 removed this step | Produces a different shared secret than a standard-compliant system. |
| **GAP-3** | The shared secret is derived differently — the code does extra hashing (KDF with ciphertext hash) that the standard removed | Both sides would compute different keys, so they cannot talk to each other. |

There are also 3 moderate gaps (no modulus check, no input validation, using AES/SHA-2 instead of SHAKE/SHA-3) and 3 minor/informational ones.

**The bottom line:** Because of these three critical differences, this ESP32 implementation **cannot communicate** with any device running the official ML-KEM standard. If you give both sides the same inputs, they produce different outputs. I confirmed this by running 20 tests — the outputs were different every single time (20/20 divergence).

**What I fixed:** I wrote corrected versions of the key functions (in a `components_fips203/` folder) that follow the FIPS 203 algorithms. I tested that both the original and fixed versions work internally (encapsulate then decapsulate gives the same key), but they produce different results from each other, proving the fixes are real. However, the code still uses AES and SHA-2 instead of SHAKE and SHA-3, so it is not fully FIPS 203 compliant — that would require replacing the entire cryptographic primitive layer.

---

## Summary of Contributions

| What I Did | Key Result |
|------------|------------|
| Profiled all 27 sub-tasks of Kyber | Seed expansion (SHA-512) takes 64.9% of key generation time |
| Built DAG models for all 3 operations | Encapsulation has the most parallelism (max 1.51x speedup) |
| Compared Segatz vs optimal schedule | 0.0% gap with software timing, up to 6.7% gap with HW acceleration |
| Audited code against FIPS 203 | Found 9 gaps (3 critical, 3 moderate, 2 minor, 1 informational) |
| Wrote partial fixes and tests | Confirmed 20/20 divergence between original and corrected versions |

---

## What Still Needs to Be Done

1. **Test on real ESP32 hardware** — my measurements are from a PC simulation, not the actual chip.
2. **Implement the better schedule on ESP32** — the optimal schedule I found for encapsulation has not been tested on hardware yet.
3. **Replace AES/SHA-2 with SHAKE/SHA-3** — the standard only supports SHAKE, so the underlying crypto primitives need to change for full compliance.
4. **Validate against official NIST test vectors** — no official test vectors exist for the AES/SHA-2 variant, so full validation requires completing the SHAKE migration first.
