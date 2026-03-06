@echo off
setlocal enabledelayedexpansion
REM ================================================================
REM  build_benchmark.bat — Build and run KEM performance benchmarks
REM  Produces CSV files in results/ with per-iteration timing data
REM ================================================================

echo ================================================================
echo   Building Performance Benchmarks
echo ================================================================

if not exist results mkdir results

set CC=gcc
set CFLAGS=-O2 -Wall -DKYBER_90S -DSHA_ACC=0 -DAES_ACC=0 -DINDCPA_KEYPAIR_DUAL=0 -DINDCPA_ENC_DUAL=0 -DINDCPA_DEC_DUAL=0

set INCLUDES=-I..\components\common -I..\components\kem -I..\components\indcpa -I..\components\poly -I..\components\polyvec -I..\components\ntt -I..\components\reduce -I..\components\cbd -I..\components\symmetric -I..\components\aes256ctr -I..\components\fips202 -I..\components\sha2 -I..\components\randombytes -I..\components\verify -I..\components\kex

set SRCS=benchmarks\benchmark.c platform\randombytes_pc.c ..\components\kem\kem.c ..\components\indcpa\indcpa.c ..\components\poly\poly.c ..\components\polyvec\polyvec.c ..\components\ntt\ntt.c ..\components\reduce\reduce.c ..\components\cbd\cbd.c ..\components\symmetric\symmetric-aes.c ..\components\symmetric\symmetric-shake.c ..\components\aes256ctr\aes256ctr.c ..\components\fips202\fips202.c ..\components\sha2\sha256.c ..\components\sha2\sha512.c ..\components\verify\verify.c ..\components\kex\kex.c

for %%K in (2 3 4) do (
    if %%K==2 set LEVEL=512
    if %%K==3 set LEVEL=768
    if %%K==4 set LEVEL=1024

    echo.
    echo ================================================================
    echo   Building Kyber-!LEVEL! benchmark ^(KYBER_K=%%K^)
    echo ================================================================

    %CC% %CFLAGS% -DKYBER_K=%%K %INCLUDES% %SRCS% -o benchmark_kyber%%K.exe -ladvapi32

    if !errorlevel! == 0 (
        echo   Running benchmark...
        benchmark_kyber%%K.exe
        del benchmark_kyber%%K.exe 2>nul
    ) else (
        echo   BUILD FAILED for KYBER_K=%%K
    )
)

echo.
echo ================================================================
echo   Benchmarks Complete — CSV files in results/
echo ================================================================
