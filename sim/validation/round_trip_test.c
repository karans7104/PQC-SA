/*
 * round_trip_test.c — KEM correctness and security validation
 *
 * Original contribution: simulation/validation framework for
 * CRYSTALS-KYBER implementation analysis.
 *
 * Tests:
 *   1. KEM round-trip correctness (keygen → encap → decap → compare)
 *   2. Ciphertext tamper detection (IND-CCA2 property)
 *   3. Key independence (distinct keypairs yield distinct secrets)
 *   4. Wrong secret key rejection
 *   5. NIST FIPS 203 key/ciphertext size compliance
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "params.h"
#include "kem.h"
#include "randombytes.h"

#define NUM_ITERATIONS 100

/* ================================================================
 *  TEST 1: KEM Round-Trip Correctness
 * ================================================================ */
static int test_kem_correctness(void) {
    uint8_t pk[CRYPTO_PUBLICKEYBYTES];
    uint8_t sk[CRYPTO_SECRETKEYBYTES];
    uint8_t ct[CRYPTO_CIPHERTEXTBYTES];
    uint8_t key_a[CRYPTO_BYTES], key_b[CRYPTO_BYTES];
    int failures = 0;

    printf("  [TEST 1] KEM Round-Trip Correctness (%d iterations)\n", NUM_ITERATIONS);

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        crypto_kem_keypair(pk, sk);
        crypto_kem_enc(ct, key_b, pk);
        crypto_kem_dec(key_a, ct, sk);

        if (memcmp(key_a, key_b, CRYPTO_BYTES) != 0) {
            printf("    FAIL at iteration %d\n", i + 1);
            failures++;
        }
    }

    printf("    Result: %s (%d/%d passed)\n\n",
           failures == 0 ? "PASSED" : "FAILED",
           NUM_ITERATIONS - failures, NUM_ITERATIONS);
    return failures;
}

/* ================================================================
 *  TEST 2: Ciphertext Tamper Detection (IND-CCA2)
 * ================================================================ */
static int test_ciphertext_tamper(void) {
    uint8_t pk[CRYPTO_PUBLICKEYBYTES];
    uint8_t sk[CRYPTO_SECRETKEYBYTES];
    uint8_t ct[CRYPTO_CIPHERTEXTBYTES];
    uint8_t ct_tampered[CRYPTO_CIPHERTEXTBYTES];
    uint8_t key_dec[CRYPTO_BYTES], key_tampered[CRYPTO_BYTES];
    int detected = 0;

    printf("  [TEST 2] Ciphertext Tamper Detection (%d iterations)\n", NUM_ITERATIONS);

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        crypto_kem_keypair(pk, sk);
        crypto_kem_enc(ct, key_dec, pk);    /* key_dec not used — we re-derive */

        memcpy(ct_tampered, ct, CRYPTO_CIPHERTEXTBYTES);
        ct_tampered[i % CRYPTO_CIPHERTEXTBYTES] ^= (1 << (i % 8));

        crypto_kem_dec(key_dec, ct, sk);
        crypto_kem_dec(key_tampered, ct_tampered, sk);

        if (memcmp(key_dec, key_tampered, CRYPTO_BYTES) != 0)
            detected++;
    }

    printf("    Tamper detected: %d/%d\n", detected, NUM_ITERATIONS);
    printf("    Result: %s\n\n",
           detected == NUM_ITERATIONS ? "PASSED" : "WARNING");
    return detected < NUM_ITERATIONS ? 1 : 0;
}

/* ================================================================
 *  TEST 3: Key Independence
 * ================================================================ */
static int test_key_independence(void) {
    uint8_t pk1[CRYPTO_PUBLICKEYBYTES], sk1[CRYPTO_SECRETKEYBYTES];
    uint8_t pk2[CRYPTO_PUBLICKEYBYTES], sk2[CRYPTO_SECRETKEYBYTES];
    uint8_t ct1[CRYPTO_CIPHERTEXTBYTES], ct2[CRYPTO_CIPHERTEXTBYTES];
    uint8_t key1[CRYPTO_BYTES], key2[CRYPTO_BYTES];
    int independent = 0;

    printf("  [TEST 3] Key Independence (%d iterations)\n", NUM_ITERATIONS);

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        crypto_kem_keypair(pk1, sk1);
        crypto_kem_keypair(pk2, sk2);
        crypto_kem_enc(ct1, key1, pk1);
        crypto_kem_enc(ct2, key2, pk2);

        if (memcmp(key1, key2, CRYPTO_BYTES) != 0)
            independent++;
    }

    printf("    Independent: %d/%d\n", independent, NUM_ITERATIONS);
    printf("    Result: %s\n\n",
           independent == NUM_ITERATIONS ? "PASSED" : "CONCERN");
    return independent < NUM_ITERATIONS ? 1 : 0;
}

/* ================================================================
 *  TEST 4: Wrong Secret Key Rejection
 * ================================================================ */
static int test_wrong_sk(void) {
    uint8_t pk[CRYPTO_PUBLICKEYBYTES], sk[CRYPTO_SECRETKEYBYTES];
    uint8_t pk2[CRYPTO_PUBLICKEYBYTES], sk2[CRYPTO_SECRETKEYBYTES];
    uint8_t ct[CRYPTO_CIPHERTEXTBYTES];
    uint8_t key_enc[CRYPTO_BYTES], key_wrong[CRYPTO_BYTES];
    int rejected = 0;

    printf("  [TEST 4] Wrong Secret Key Rejection (%d iterations)\n", NUM_ITERATIONS);

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        crypto_kem_keypair(pk, sk);
        crypto_kem_keypair(pk2, sk2);
        crypto_kem_enc(ct, key_enc, pk);
        crypto_kem_dec(key_wrong, ct, sk2);

        if (memcmp(key_enc, key_wrong, CRYPTO_BYTES) != 0)
            rejected++;
    }

    printf("    Rejected: %d/%d\n", rejected, NUM_ITERATIONS);
    printf("    Result: %s\n\n",
           rejected == NUM_ITERATIONS ? "PASSED" : "CRITICAL FAILURE");
    return rejected < NUM_ITERATIONS ? 1 : 0;
}

/* ================================================================
 *  TEST 5: NIST FIPS 203 Key Size Compliance
 * ================================================================ */
static int test_key_sizes(void) {
    int fail = 0;
    printf("  [TEST 5] Key Size Verification (NIST FIPS 203)\n");

#if KYBER_K == 2
    int exp_pk = 800, exp_sk = 1632, exp_ct = 768;
    const char *level = "Kyber-512 (ML-KEM-512)";
#elif KYBER_K == 3
    int exp_pk = 1184, exp_sk = 2400, exp_ct = 1088;
    const char *level = "Kyber-768 (ML-KEM-768)";
#elif KYBER_K == 4
    int exp_pk = 1568, exp_sk = 3168, exp_ct = 1568;
    const char *level = "Kyber-1024 (ML-KEM-1024)";
#endif

    printf("    Level: %s (KYBER_K=%d)\n", level, KYBER_K);
    printf("    Public key:  %4d bytes (expected %d) %s\n", CRYPTO_PUBLICKEYBYTES, exp_pk,
           CRYPTO_PUBLICKEYBYTES == exp_pk ? "OK" : "MISMATCH");
    printf("    Secret key:  %4d bytes (expected %d) %s\n", CRYPTO_SECRETKEYBYTES, exp_sk,
           CRYPTO_SECRETKEYBYTES == exp_sk ? "OK" : "MISMATCH");
    printf("    Ciphertext:  %4d bytes (expected %d) %s\n", CRYPTO_CIPHERTEXTBYTES, exp_ct,
           CRYPTO_CIPHERTEXTBYTES == exp_ct ? "OK" : "MISMATCH");
    printf("    Shared key:  %4d bytes (expected 32) %s\n", CRYPTO_BYTES,
           CRYPTO_BYTES == 32 ? "OK" : "MISMATCH");

    if (CRYPTO_PUBLICKEYBYTES != exp_pk || CRYPTO_SECRETKEYBYTES != exp_sk ||
        CRYPTO_CIPHERTEXTBYTES != exp_ct || CRYPTO_BYTES != 32)
        fail = 1;

    printf("    Result: %s\n\n", fail == 0 ? "PASSED" : "FAILED");
    return fail;
}

/* ================================================================ */
int main(void) {
    int total_failures = 0;

    printf("=============================================================\n");
    printf("  CRYSTALS-KYBER Validation Suite\n");
    printf("  Variant: %s | KYBER_K=%d\n", CRYPTO_ALGNAME, KYBER_K);
    printf("  Iterations per test: %d\n", NUM_ITERATIONS);
    printf("=============================================================\n\n");

    total_failures += test_kem_correctness();
    total_failures += test_ciphertext_tamper();
    total_failures += test_key_independence();
    total_failures += test_wrong_sk();
    total_failures += test_key_sizes();

    printf("=============================================================\n");
    printf("  %s\n", total_failures == 0 ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
    printf("=============================================================\n");

    return total_failures > 0 ? 1 : 0;
}
