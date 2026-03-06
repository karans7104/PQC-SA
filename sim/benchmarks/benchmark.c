/*
 * benchmark.c — KEM performance benchmarks across all security levels
 *
 * Original contribution: timing framework for CRYSTALS-KYBER
 * performance analysis on PC (Windows).
 *
 * Measures keygen, encapsulation, decapsulation over many iterations
 * and exports raw timing data to CSV for statistical analysis.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <windows.h>
#include "params.h"
#include "kem.h"
#include "randombytes.h"

#define NUM_ITERATIONS 1000

static double get_time_us(void) {
    LARGE_INTEGER freq, count;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&count);
    return (double)count.QuadPart * 1000000.0 / (double)freq.QuadPart;
}

int main(void) {
    uint8_t pk[CRYPTO_PUBLICKEYBYTES];
    uint8_t sk[CRYPTO_SECRETKEYBYTES];
    uint8_t ct[CRYPTO_CIPHERTEXTBYTES];
    uint8_t key_a[CRYPTO_BYTES], key_b[CRYPTO_BYTES];

    double keygen_times[NUM_ITERATIONS];
    double enc_times[NUM_ITERATIONS];
    double dec_times[NUM_ITERATIONS];

    printf("=============================================================\n");
    printf("  CRYSTALS-KYBER Performance Benchmark\n");
    printf("  Variant: %s | KYBER_K=%d\n", CRYPTO_ALGNAME, KYBER_K);
    printf("  Iterations: %d\n", NUM_ITERATIONS);
    printf("=============================================================\n\n");

    /* Warmup */
    for (int w = 0; w < 10; w++) {
        crypto_kem_keypair(pk, sk);
        crypto_kem_enc(ct, key_b, pk);
        crypto_kem_dec(key_a, ct, sk);
    }

    printf("Running %d iterations...\n\n", NUM_ITERATIONS);

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        double t0 = get_time_us();
        crypto_kem_keypair(pk, sk);
        double t1 = get_time_us();
        crypto_kem_enc(ct, key_b, pk);
        double t2 = get_time_us();
        crypto_kem_dec(key_a, ct, sk);
        double t3 = get_time_us();

        keygen_times[i] = t1 - t0;
        enc_times[i]    = t2 - t1;
        dec_times[i]    = t3 - t2;
    }

    /* Statistics */
    double kg_sum = 0, enc_sum = 0, dec_sum = 0;
    double kg_min = keygen_times[0], kg_max = keygen_times[0];
    double enc_min = enc_times[0], enc_max = enc_times[0];
    double dec_min = dec_times[0], dec_max = dec_times[0];

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        kg_sum  += keygen_times[i];
        enc_sum += enc_times[i];
        dec_sum += dec_times[i];
        if (keygen_times[i] < kg_min) kg_min = keygen_times[i];
        if (keygen_times[i] > kg_max) kg_max = keygen_times[i];
        if (enc_times[i] < enc_min)   enc_min = enc_times[i];
        if (enc_times[i] > enc_max)   enc_max = enc_times[i];
        if (dec_times[i] < dec_min)   dec_min = dec_times[i];
        if (dec_times[i] > dec_max)   dec_max = dec_times[i];
    }

    printf("  %-20s %12s %12s %12s\n", "Operation", "Avg(us)", "Min(us)", "Max(us)");
    printf("  %-20s %12.2f %12.2f %12.2f\n", "Key Generation",
           kg_sum / NUM_ITERATIONS, kg_min, kg_max);
    printf("  %-20s %12.2f %12.2f %12.2f\n", "Encapsulation",
           enc_sum / NUM_ITERATIONS, enc_min, enc_max);
    printf("  %-20s %12.2f %12.2f %12.2f\n", "Decapsulation",
           dec_sum / NUM_ITERATIONS, dec_min, dec_max);
    printf("\n");

    /* CSV export */
    char csv_name[64];
    snprintf(csv_name, sizeof(csv_name), "results/benchmark_kyber%d.csv",
             KYBER_K == 2 ? 512 : KYBER_K == 3 ? 768 : 1024);

    FILE *csv = fopen(csv_name, "w");
    if (csv) {
        fprintf(csv, "iteration,keygen_us,encapsulation_us,decapsulation_us\n");
        for (int i = 0; i < NUM_ITERATIONS; i++)
            fprintf(csv, "%d,%.2f,%.2f,%.2f\n", i + 1,
                    keygen_times[i], enc_times[i], dec_times[i]);
        fclose(csv);
        printf("  Results exported to: %s\n", csv_name);
    }

    printf("=============================================================\n");
    return 0;
}
