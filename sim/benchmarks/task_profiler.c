/*
 * task_profiler.c — Individual sub-task timing for DAG scheduling analysis
 *
 * Original contribution: instruments each sub-operation inside
 * indcpa_keypair, indcpa_enc, and indcpa_dec to capture individual
 * task weights for Critical Path Method and List Scheduling analysis.
 *
 * This does NOT modify the original library code. Instead, it
 * reproduces the exact algorithm flow calling real library functions
 * on real data, wrapping each call with high-resolution timing.
 *
 * Compile with: -DKYBER_90S -DKYBER_K=2|3|4 -DSHA_ACC=0 -DAES_ACC=0
 *               -DINDCPA_KEYPAIR_DUAL=0 -DINDCPA_ENC_DUAL=0 -DINDCPA_DEC_DUAL=0
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <windows.h>

#include "params.h"
#include "kem.h"
#include "indcpa.h"
#include "poly.h"
#include "polyvec.h"
#include "ntt.h"
#include "randombytes.h"
#include "symmetric.h"

#define NUM_ITERATIONS 1000
#define MAX_TASKS 40

/* ================================================================
 *  High-resolution timer (microseconds)
 * ================================================================ */
static LARGE_INTEGER qpc_freq;

static void timer_init(void) {
    QueryPerformanceFrequency(&qpc_freq);
}

static double get_time_us(void) {
    LARGE_INTEGER count;
    QueryPerformanceCounter(&count);
    return (double)count.QuadPart * 1000000.0 / (double)qpc_freq.QuadPart;
}

/* ================================================================
 *  Task timing accumulator
 * ================================================================ */
typedef struct {
    char name[48];
    char operation[16];
    double times[NUM_ITERATIONS];
    double sum;
    double min_val;
    double max_val;
    int count;
} TaskTimer;

static TaskTimer timers[MAX_TASKS];
static int num_timers = 0;

static int get_timer(const char *name, const char *operation) {
    for (int i = 0; i < num_timers; i++) {
        if (strcmp(timers[i].name, name) == 0 &&
            strcmp(timers[i].operation, operation) == 0)
            return i;
    }
    int idx = num_timers++;
    strncpy(timers[idx].name, name, 47);
    timers[idx].name[47] = '\0';
    strncpy(timers[idx].operation, operation, 15);
    timers[idx].operation[15] = '\0';
    timers[idx].sum = 0;
    timers[idx].min_val = 1e18;
    timers[idx].max_val = 0;
    timers[idx].count = 0;
    return idx;
}

static void record_time(int idx, int iteration, double us) {
    timers[idx].times[iteration] = us;
    timers[idx].sum += us;
    if (us < timers[idx].min_val) timers[idx].min_val = us;
    if (us > timers[idx].max_val) timers[idx].max_val = us;
    timers[idx].count++;
}

/* ================================================================
 *  Helper: gen_matrix wrapper (same as gen_a / gen_at in indcpa.c)
 *  We need to call gen_matrix directly — it's declared in indcpa.c.
 *  Since indcpa.c defines gen_a as a macro: #define gen_a(A,B) gen_matrix(A,B,0)
 *  we just declare gen_matrix extern here.
 * ================================================================ */
extern void gen_matrix(polyvec *a, const uint8_t seed[KYBER_SYMBYTES], int transposed);

/* hash_g and hash_h are defined in symmetric.h via macros */

/* ================================================================
 *  Profiled KeyPair Generation
 *
 *  Reproduces the exact single-core indcpa_keypair flow:
 *    1. RNG + hash_g → seed expansion
 *    2. gen_matrix (A from public seed)
 *    3. poly_getnoise_eta1 for s (K times)
 *    4. poly_getnoise_eta1 for e (K times)
 *    5. polyvec_ntt on s
 *    6. polyvec_ntt on e
 *    7. polyvec_basemul_acc_montgomery (K times, A*s)
 *    8. poly_tomont (K times)
 *    9. polyvec_add (t = As + e)
 *   10. polyvec_reduce
 *   11. pack_sk + pack_pk (serialization)
 * ================================================================ */
static void profile_keypair(int iter) {
    uint8_t buf[2 * KYBER_SYMBYTES];
    const uint8_t *publicseed = buf;
    const uint8_t *noiseseed  = buf + KYBER_SYMBYTES;
    uint8_t nonce = 0;
    polyvec a[KYBER_K], e, pkpv, skpv;
    uint8_t pk[KYBER_INDCPA_PUBLICKEYBYTES];
    uint8_t sk[KYBER_INDCPA_SECRETKEYBYTES];
    double t0, t1;
    int tid;

    /* Task KG.1: Seed generation (RNG + hash_g) */
    tid = get_timer("KG.1_seed_expansion", "keypair");
    t0 = get_time_us();
    esp_randombytes(buf, KYBER_SYMBYTES);
    hash_g(buf, buf, KYBER_SYMBYTES);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.2: Matrix A generation */
    tid = get_timer("KG.2_gen_matrix_A", "keypair");
    t0 = get_time_us();
    gen_matrix(a, publicseed, 0);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.3: Sample noise s */
    tid = get_timer("KG.3_noise_s", "keypair");
    t0 = get_time_us();
    for (unsigned int i = 0; i < KYBER_K; i++)
        poly_getnoise_eta1(&skpv.vec[i], noiseseed, nonce++);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.4: Sample noise e */
    tid = get_timer("KG.4_noise_e", "keypair");
    t0 = get_time_us();
    for (unsigned int i = 0; i < KYBER_K; i++)
        poly_getnoise_eta1(&e.vec[i], noiseseed, nonce++);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.5: NTT on s */
    tid = get_timer("KG.5_ntt_s", "keypair");
    t0 = get_time_us();
    polyvec_ntt(&skpv);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.6: NTT on e */
    tid = get_timer("KG.6_ntt_e", "keypair");
    t0 = get_time_us();
    polyvec_ntt(&e);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.7: Matrix multiply A*s + tomont */
    tid = get_timer("KG.7_matmul_As", "keypair");
    t0 = get_time_us();
    for (unsigned int i = 0; i < KYBER_K; i++) {
        polyvec_basemul_acc_montgomery(&pkpv.vec[i], &a[i], &skpv);
        poly_tomont(&pkpv.vec[i]);
    }
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.8: Add error t = As + e, then reduce */
    tid = get_timer("KG.8_add_reduce", "keypair");
    t0 = get_time_us();
    polyvec_add(&pkpv, &pkpv, &e);
    polyvec_reduce(&pkpv);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task KG.9: Serialization (pack) */
    tid = get_timer("KG.9_pack", "keypair");
    t0 = get_time_us();
    polyvec_tobytes(sk, &skpv);
    polyvec_tobytes(pk, &pkpv);
    memcpy(pk + KYBER_POLYVECBYTES, publicseed, KYBER_SYMBYTES);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);
}

/* ================================================================
 *  Profiled Encapsulation
 *
 *  Reproduces the single-core indcpa_enc flow:
 *    1. unpack_pk + poly_frommsg
 *    2. gen_matrix (A^T)
 *    3. sample noise r (K times)
 *    4. sample noise e1 (K times)
 *    5. sample noise e2
 *    6. NTT on r
 *    7. matrix multiply A^T * r (K times)
 *    8. inner product t^T * r
 *    9. invNTT on u and v
 *   10. add errors + message encoding
 *   11. compress + pack ciphertext
 * ================================================================ */
static void profile_enc(int iter,
                        const uint8_t pk[KYBER_INDCPA_PUBLICKEYBYTES]) {
    uint8_t seed[KYBER_SYMBYTES];
    uint8_t coins[KYBER_SYMBYTES];
    uint8_t nonce = 0;
    uint8_t m[KYBER_INDCPA_MSGBYTES];
    uint8_t c[KYBER_INDCPA_BYTES];
    polyvec sp, pkpv, ep, at[KYBER_K], b;
    poly v, k, epp;
    double t0, t1;
    int tid;

    /* Generate random message and coins for this iteration */
    esp_randombytes(m, KYBER_INDCPA_MSGBYTES);
    esp_randombytes(coins, KYBER_SYMBYTES);

    /* Task ENC.1: Unpack public key + decode message */
    tid = get_timer("ENC.1_unpack_pk", "encaps");
    t0 = get_time_us();
    polyvec_frombytes(&pkpv, pk);
    memcpy(seed, pk + KYBER_POLYVECBYTES, KYBER_SYMBYTES);
    poly_frommsg(&k, m);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.2: Generate matrix A^T */
    tid = get_timer("ENC.2_gen_matrix_AT", "encaps");
    t0 = get_time_us();
    gen_matrix(at, seed, 1);   /* transposed = 1 */
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.3: Sample noise r */
    tid = get_timer("ENC.3_noise_r", "encaps");
    t0 = get_time_us();
    for (unsigned int i = 0; i < KYBER_K; i++)
        poly_getnoise_eta1(sp.vec + i, coins, nonce++);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.4: Sample noise e1 */
    tid = get_timer("ENC.4_noise_e1", "encaps");
    t0 = get_time_us();
    for (unsigned int i = 0; i < KYBER_K; i++)
        poly_getnoise_eta2(ep.vec + i, coins, nonce++);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.5: Sample noise e2 */
    tid = get_timer("ENC.5_noise_e2", "encaps");
    t0 = get_time_us();
    poly_getnoise_eta2(&epp, coins, nonce++);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.6: NTT on r */
    tid = get_timer("ENC.6_ntt_r", "encaps");
    t0 = get_time_us();
    polyvec_ntt(&sp);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.7: Matrix multiply A^T * r */
    tid = get_timer("ENC.7_matmul_ATr", "encaps");
    t0 = get_time_us();
    for (unsigned int i = 0; i < KYBER_K; i++)
        polyvec_basemul_acc_montgomery(&b.vec[i], &at[i], &sp);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.8: Inner product t^T * r */
    tid = get_timer("ENC.8_inner_tTr", "encaps");
    t0 = get_time_us();
    polyvec_basemul_acc_montgomery(&v, &pkpv, &sp);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.9: Inverse NTT on u and v */
    tid = get_timer("ENC.9_invntt", "encaps");
    t0 = get_time_us();
    polyvec_invntt_tomont(&b);
    poly_invntt_tomont(&v);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.10: Add errors + message */
    tid = get_timer("ENC.10_add_errors", "encaps");
    t0 = get_time_us();
    polyvec_add(&b, &b, &ep);
    poly_add(&v, &v, &epp);
    poly_add(&v, &v, &k);
    polyvec_reduce(&b);
    poly_reduce(&v);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task ENC.11: Compress + pack ciphertext */
    tid = get_timer("ENC.11_compress_pack", "encaps");
    t0 = get_time_us();
    polyvec_compress(c, &b);
    poly_compress(c + KYBER_POLYVECCOMPRESSEDBYTES, &v);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);
}

/* ================================================================
 *  Profiled Decapsulation
 *
 *  Reproduces the single-core indcpa_dec flow:
 *    1. unpack_ciphertext (decompress u, v)
 *    2. unpack_sk (deserialize s)
 *    3. NTT on u
 *    4. inner product s^T * u
 *    5. inverse NTT
 *    6. subtract: v - s^T*u, reduce
 *    7. decode message
 * ================================================================ */
static void profile_dec(int iter,
                        const uint8_t ct[KYBER_INDCPA_BYTES],
                        const uint8_t sk[KYBER_INDCPA_SECRETKEYBYTES]) {
    polyvec b_vec, skpv;
    poly v, mp;
    uint8_t m[KYBER_INDCPA_MSGBYTES];
    double t0, t1;
    int tid;

    /* Task DEC.1: Decompress ciphertext (u, v) */
    tid = get_timer("DEC.1_decompress_ct", "decaps");
    t0 = get_time_us();
    polyvec_decompress(&b_vec, ct);
    poly_decompress(&v, ct + KYBER_POLYVECCOMPRESSEDBYTES);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task DEC.2: Deserialize secret key s */
    tid = get_timer("DEC.2_unpack_sk", "decaps");
    t0 = get_time_us();
    polyvec_frombytes(&skpv, sk);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task DEC.3: NTT on u */
    tid = get_timer("DEC.3_ntt_u", "decaps");
    t0 = get_time_us();
    polyvec_ntt(&b_vec);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task DEC.4: Inner product s^T * u */
    tid = get_timer("DEC.4_inner_sTu", "decaps");
    t0 = get_time_us();
    polyvec_basemul_acc_montgomery(&mp, &skpv, &b_vec);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task DEC.5: Inverse NTT */
    tid = get_timer("DEC.5_invntt", "decaps");
    t0 = get_time_us();
    poly_invntt_tomont(&mp);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task DEC.6: Subtract v - s^T*u + reduce */
    tid = get_timer("DEC.6_sub_reduce", "decaps");
    t0 = get_time_us();
    poly_sub(&mp, &v, &mp);
    poly_reduce(&mp);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);

    /* Task DEC.7: Decode message */
    tid = get_timer("DEC.7_decode_msg", "decaps");
    t0 = get_time_us();
    poly_tomsg(m, &mp);
    t1 = get_time_us();
    record_time(tid, iter, t1 - t0);
}

/* ================================================================
 *  Export and main
 * ================================================================ */
static void export_csv(const char *filename) {
    FILE *f = fopen(filename, "w");
    if (!f) {
        printf("ERROR: Cannot open %s\n", filename);
        return;
    }

    fprintf(f, "task_name,operation,avg_us,min_us,max_us,iterations\n");
    for (int i = 0; i < num_timers; i++) {
        double avg = timers[i].sum / timers[i].count;
        fprintf(f, "%s,%s,%.4f,%.4f,%.4f,%d\n",
                timers[i].name, timers[i].operation,
                avg, timers[i].min_val, timers[i].max_val,
                timers[i].count);
    }

    fclose(f);
    printf("  Exported: %s\n", filename);
}

static void export_json(const char *filename) {
    FILE *f = fopen(filename, "w");
    if (!f) return;

    fprintf(f, "{\n  \"kyber_k\": %d,\n  \"iterations\": %d,\n  \"tasks\": [\n",
            KYBER_K, NUM_ITERATIONS);
    for (int i = 0; i < num_timers; i++) {
        double avg = timers[i].sum / timers[i].count;
        fprintf(f, "    {\"name\": \"%s\", \"operation\": \"%s\", "
                "\"avg_us\": %.4f, \"min_us\": %.4f, \"max_us\": %.4f}%s\n",
                timers[i].name, timers[i].operation,
                avg, timers[i].min_val, timers[i].max_val,
                i < num_timers - 1 ? "," : "");
    }
    fprintf(f, "  ]\n}\n");
    fclose(f);
    printf("  Exported: %s\n", filename);
}

int main(void) {
    timer_init();

    printf("=============================================================\n");
    printf("  CRYSTALS-KYBER Sub-Task Profiler\n");
    printf("  Variant: %s | KYBER_K=%d\n", CRYPTO_ALGNAME, KYBER_K);
    printf("  Iterations: %d\n", NUM_ITERATIONS);
    printf("=============================================================\n\n");

    /* We need valid pk/sk/ct for enc and dec profiling */
    uint8_t pk[KYBER_INDCPA_PUBLICKEYBYTES];
    uint8_t sk[KYBER_INDCPA_SECRETKEYBYTES];
    uint8_t ct[KYBER_INDCPA_BYTES];

    printf("  Profiling %d iterations...\n\n", NUM_ITERATIONS);

    for (int i = 0; i < NUM_ITERATIONS; i++) {
        /* Profile keypair (generates fresh pk/sk each iteration) */
        profile_keypair(i);

        /* We need a real ciphertext for decapsulation profiling.
         * Use indcpa_enc to generate one, but we profile enc separately. */

        /* For enc profiling, use the pk from this iteration's keypair.
         * We need to get the packed pk — re-pack from profile_keypair's result.
         * Since profile_keypair uses local arrays, we call indcpa_keypair once
         * to get a valid pk/sk pair for enc/dec profiling. */
        indcpa_keypair(pk, sk);

        /* Profile encapsulation */
        profile_enc(i, pk);

        /* Generate a real ciphertext for dec profiling */
        uint8_t m[KYBER_INDCPA_MSGBYTES];
        uint8_t coins[KYBER_SYMBYTES];
        esp_randombytes(m, KYBER_INDCPA_MSGBYTES);
        esp_randombytes(coins, KYBER_SYMBYTES);
        indcpa_enc(ct, m, pk, coins);

        /* Profile decapsulation */
        profile_dec(i, ct, sk);
    }

    /* Print summary */
    printf("  %-30s %-10s %12s %12s %12s\n",
           "Task", "Operation", "Avg(us)", "Min(us)", "Max(us)");
    printf("  ---------------------------------------------------------------"
           "-------------------\n");

    for (int i = 0; i < num_timers; i++) {
        double avg = timers[i].sum / timers[i].count;
        printf("  %-30s %-10s %12.4f %12.4f %12.4f\n",
               timers[i].name, timers[i].operation,
               avg, timers[i].min_val, timers[i].max_val);
    }
    printf("\n");

    /* Export */
    char csv_name[64], json_name[64];
    int level = KYBER_K == 2 ? 512 : KYBER_K == 3 ? 768 : 1024;
    snprintf(csv_name, sizeof(csv_name), "results/task_times_kyber%d.csv", level);
    snprintf(json_name, sizeof(json_name), "results/task_times_kyber%d.json", level);

    export_csv(csv_name);
    export_json(json_name);

    printf("\n=============================================================\n");
    printf("  PROFILING COMPLETE\n");
    printf("=============================================================\n");

    return 0;
}
