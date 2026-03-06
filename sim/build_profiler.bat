@echo off
setlocal enabledelayedexpansion
REM ================================================================
REM  build_profiler.bat — Build task profiler, run DAG analysis
REM
REM  Pipeline:
REM    1. Compile and run task_profiler for Kyber-512, 768, 1024
REM    2. Run critical_path.py for each level
REM    3. Run list_scheduler.py for each level
REM ================================================================

echo ================================================================
echo   CRYSTALS-KYBER DAG Analysis Pipeline
echo ================================================================

if not exist results mkdir results

set CC=gcc
set CFLAGS=-O2 -Wall -DKYBER_90S -DSHA_ACC=0 -DAES_ACC=0 -DINDCPA_KEYPAIR_DUAL=0 -DINDCPA_ENC_DUAL=0 -DINDCPA_DEC_DUAL=0

set INCLUDES=-I..\components\common -I..\components\kem -I..\components\indcpa -I..\components\poly -I..\components\polyvec -I..\components\ntt -I..\components\reduce -I..\components\cbd -I..\components\symmetric -I..\components\aes256ctr -I..\components\fips202 -I..\components\sha2 -I..\components\randombytes -I..\components\verify -I..\components\kex

set SRCS=benchmarks\task_profiler.c platform\randombytes_pc.c ..\components\kem\kem.c ..\components\indcpa\indcpa.c ..\components\poly\poly.c ..\components\polyvec\polyvec.c ..\components\ntt\ntt.c ..\components\reduce\reduce.c ..\components\cbd\cbd.c ..\components\symmetric\symmetric-aes.c ..\components\symmetric\symmetric-shake.c ..\components\aes256ctr\aes256ctr.c ..\components\fips202\fips202.c ..\components\sha2\sha256.c ..\components\sha2\sha512.c ..\components\verify\verify.c ..\components\kex\kex.c

REM ================================================================
REM  Step 1: Compile and run task profiler for each security level
REM ================================================================

for %%K in (2 3 4) do (
    if %%K==2 set LEVEL=512
    if %%K==3 set LEVEL=768
    if %%K==4 set LEVEL=1024

    echo.
    echo ================================================================
    echo   Step 1: Profiling Kyber-!LEVEL! ^(KYBER_K=%%K^)
    echo ================================================================

    %CC% %CFLAGS% -DKYBER_K=%%K %INCLUDES% %SRCS% -o profiler_kyber%%K.exe -ladvapi32

    if !errorlevel! == 0 (
        profiler_kyber%%K.exe
        del profiler_kyber%%K.exe 2>nul
    ) else (
        echo   BUILD FAILED for KYBER_K=%%K
        goto :error
    )
)

REM ================================================================
REM  Step 2: Run Critical Path Analysis
REM ================================================================

echo.
echo ================================================================
echo   Step 2: Critical Path Analysis
echo ================================================================

for %%K in (2 3 4) do (
    python dag_analysis\critical_path.py --kyber-k %%K --results-dir results
    if !errorlevel! neq 0 (
        echo   WARNING: critical_path.py failed for KYBER_K=%%K
    )
)

REM ================================================================
REM  Step 3: List Scheduling Analysis
REM ================================================================

echo.
echo ================================================================
echo   Step 3: List Scheduling Analysis
echo ================================================================

for %%K in (2 3 4) do (
    python dag_analysis\list_scheduler.py --kyber-k %%K --results-dir results
    if !errorlevel! neq 0 (
        echo   WARNING: list_scheduler.py failed for KYBER_K=%%K
    )
)

echo.
echo ================================================================
echo   DAG Analysis Pipeline Complete
echo   Output files in results/:
echo     - task_times_kyber512.csv / .json
echo     - task_times_kyber768.csv / .json
echo     - task_times_kyber1024.csv / .json
echo     - critical_path_analysis.txt
echo     - schedule_comparison.txt
echo     - optimal_schedule.png
echo ================================================================
goto :eof

:error
echo.
echo   Pipeline aborted due to build failure.
exit /b 1
