"""
list_scheduler.py — Optimal 2-core List Scheduling with Gantt chart

Original contribution: implements the standard List Scheduling heuristic
for 2 processors on the CRYSTALS-KYBER DAG, then compares the resulting
schedule against Segatz's empirical hand-partitioned schedule.

Generates:
  - results/optimal_schedule.png   (Gantt chart comparison)
  - results/schedule_comparison.txt (text report)

Usage:
    python list_scheduler.py [--kyber-k 2|3|4] [--results-dir results/]

Requires: matplotlib, numpy
"""

import json
import os
import sys
import argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

try:
    import matplotlib
    matplotlib.use('Agg')       # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("WARNING: matplotlib not found — Gantt chart will be skipped.")
    print("         Install with: pip install matplotlib numpy")

# ================================================================
#  DAG definitions (must match dag_tasks.h and critical_path.py)
# ================================================================

KEYPAIR_DAG = [
    {"id": 0, "name": "KG.1_seed_expansion",  "deps": []},
    {"id": 1, "name": "KG.2_gen_matrix_A",    "deps": [0]},
    {"id": 2, "name": "KG.3_noise_s",         "deps": [0]},
    {"id": 3, "name": "KG.4_noise_e",         "deps": [0]},
    {"id": 4, "name": "KG.5_ntt_s",           "deps": [2]},
    {"id": 5, "name": "KG.6_ntt_e",           "deps": [3]},
    {"id": 6, "name": "KG.7_matmul_As",       "deps": [1, 4]},
    {"id": 7, "name": "KG.8_add_reduce",      "deps": [6, 5]},
    {"id": 8, "name": "KG.9_pack",            "deps": [7]},
]

ENCAPS_DAG = [
    {"id": 0, "name": "ENC.1_unpack_pk",       "deps": []},
    {"id": 1, "name": "ENC.2_gen_matrix_AT",   "deps": [0]},
    {"id": 2, "name": "ENC.3_noise_r",         "deps": [0]},
    {"id": 3, "name": "ENC.4_noise_e1",        "deps": [0]},
    {"id": 4, "name": "ENC.5_noise_e2",        "deps": [0]},
    {"id": 5, "name": "ENC.6_ntt_r",           "deps": [2]},
    {"id": 6, "name": "ENC.7_matmul_ATr",      "deps": [1, 5]},
    {"id": 7, "name": "ENC.8_inner_tTr",       "deps": [0, 5]},
    {"id": 8, "name": "ENC.9_invntt",          "deps": [6, 7]},
    {"id": 9, "name": "ENC.10_add_errors",     "deps": [8, 3, 4]},
    {"id": 10, "name": "ENC.11_compress_pack", "deps": [9]},
]

DECAPS_DAG = [
    {"id": 0, "name": "DEC.1_decompress_ct",   "deps": []},
    {"id": 1, "name": "DEC.2_unpack_sk",       "deps": []},
    {"id": 2, "name": "DEC.3_ntt_u",           "deps": [0]},
    {"id": 3, "name": "DEC.4_inner_sTu",       "deps": [1, 2]},
    {"id": 4, "name": "DEC.5_invntt",          "deps": [3]},
    {"id": 5, "name": "DEC.6_sub_reduce",      "deps": [4]},
    {"id": 6, "name": "DEC.7_decode_msg",      "deps": [5]},
]

SEGATZ_KEYPAIR = [0, 0, 1, 1, 1, 1, 0, 0, 0]
SEGATZ_ENCAPS  = [0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 0]
SEGATZ_DECAPS  = [1, 0, 1, 0, 0, 0, 0]


def load_task_times(json_path):
    """Load measured task times from the profiler's JSON output."""
    with open(json_path, 'r') as f:
        data = json.load(f)
    times = {}
    for task in data["tasks"]:
        times[task["name"]] = task["avg_us"]
    return times


def assign_weights(dag, times):
    """Assign measured weights to DAG tasks."""
    weighted = []
    for task in dag:
        w = times.get(task["name"], 0.0)
        weighted.append({"id": task["id"], "name": task["name"],
                         "deps": list(task["deps"]), "weight": w})
    return weighted


def compute_bottom_level(dag):
    """
    Compute the bottom level (b-level) for each task.
    b-level(t) = weight(t) + max(b-level(s) for s in successors(t))

    This is used for priority in List Scheduling (HLFET heuristic).
    """
    n = len(dag)
    successors = defaultdict(list)
    for task in dag:
        for dep in task["deps"]:
            successors[dep].append(task["id"])

    blevel = [0.0] * n

    # Compute in reverse topological order
    for task in reversed(dag):
        tid = task["id"]
        if successors[tid]:
            blevel[tid] = task["weight"] + max(blevel[s] for s in successors[tid])
        else:
            blevel[tid] = task["weight"]

    return blevel


def list_schedule(dag, num_cores=2):
    """
    Standard List Scheduling with HLFET (Highest Level First with
    Estimated Times) priority.

    Returns:
        schedule: list of (task_id, core, start_time, end_time)
        makespan: total schedule length
    """
    n = len(dag)
    blevel = compute_bottom_level(dag)

    core_avail = [0.0] * num_cores
    finish_time = [0.0] * n
    scheduled = [False] * n

    schedule = []

    for _ in range(n):
        # Find ready tasks (all deps scheduled)
        ready = []
        for task in dag:
            tid = task["id"]
            if scheduled[tid]:
                continue
            if all(scheduled[dep] for dep in task["deps"]):
                ready.append(tid)

        if not ready:
            break

        # Sort by b-level (descending) — highest priority first
        ready.sort(key=lambda t: blevel[t], reverse=True)

        # Pick the highest priority ready task
        best_task = ready[0]
        task = dag[best_task]

        # Find earliest start: max of (core available, all deps finished)
        dep_finish = max((finish_time[d] for d in task["deps"]), default=0.0)

        # Find the core that gives earliest start
        best_core = -1
        best_start = float('inf')
        for c in range(num_cores):
            start = max(core_avail[c], dep_finish)
            if start < best_start:
                best_start = start
                best_core = c

        end = best_start + task["weight"]
        schedule.append((best_task, best_core, best_start, end))
        finish_time[best_task] = end
        core_avail[best_core] = end
        scheduled[best_task] = True

    makespan = max(e for _, _, _, e in schedule) if schedule else 0
    return schedule, makespan


def simulate_segatz(dag, assignment):
    """Simulate Segatz's fixed 2-core assignment."""
    n = len(dag)
    core_time = [0.0, 0.0]
    finish_time = [0.0] * n
    schedule = []

    for task in dag:
        tid = task["id"]
        core = assignment[tid]
        dep_finish = max((finish_time[d] for d in task["deps"]), default=0.0)
        start = max(core_time[core], dep_finish)
        end = start + task["weight"]

        schedule.append((tid, core, start, end))
        finish_time[tid] = end
        core_time[core] = end

    makespan = max(e for _, _, _, e in schedule) if schedule else 0
    return schedule, makespan


def draw_gantt(ax, schedule, dag, title, colors):
    """Draw a Gantt chart on the given axes."""
    for tid, core, start, end in schedule:
        task_name = dag[tid]["name"]
        short_name = task_name.split("_", 1)[0]  # e.g. "KG.1"
        duration = end - start

        bar = ax.barh(core, duration, left=start, height=0.6,
                      color=colors[tid % len(colors)], edgecolor='black',
                      linewidth=0.5, alpha=0.85)

        # Label inside bar if it's wide enough
        if duration > 0:
            ax.text(start + duration / 2, core, short_name,
                    ha='center', va='center', fontsize=6, fontweight='bold')

    ax.set_yticks([0, 1])
    ax.set_yticklabels(['Core 0', 'Core 1'])
    ax.set_xlabel('Time (μs)')
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.set_xlim(left=0)
    ax.invert_yaxis()


def generate_gantt_chart(results, output_path):
    """Generate a multi-panel Gantt chart comparing schedules."""
    if not HAS_MPL:
        return

    fig, axes = plt.subplots(3, 2, figsize=(16, 10))
    fig.suptitle('CRYSTALS-KYBER DAG Scheduling: Segatz vs Optimal',
                 fontsize=14, fontweight='bold')

    colors = plt.cm.Set3(np.linspace(0, 1, 12))

    ops = ["keypair", "encaps", "decaps"]
    op_labels = ["Key Generation", "Encapsulation", "Decapsulation"]

    for row, (op, label) in enumerate(zip(ops, op_labels)):
        r = results[op]
        dag = r["dag"]
        segatz_sched = r["segatz_schedule"]
        optimal_sched = r["optimal_schedule"]
        segatz_ms = r["segatz_makespan"]
        optimal_ms = r["optimal_makespan"]

        draw_gantt(axes[row][0], segatz_sched, dag,
                   f'{label} — Segatz ({segatz_ms:.1f} μs)', colors)
        draw_gantt(axes[row][1], optimal_sched, dag,
                   f'{label} — List Sched ({optimal_ms:.1f} μs)', colors)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Gantt chart saved to: {output_path}")


def analyze_one(name, dag_template, times, segatz_assignment):
    """Run list scheduling and Segatz simulation for one operation."""
    dag = assign_weights(dag_template, times)
    total_work = sum(t["weight"] for t in dag)

    optimal_sched, optimal_ms = list_schedule(dag)
    segatz_sched, segatz_ms = simulate_segatz(dag, segatz_assignment)

    return {
        "dag": dag,
        "total_work": total_work,
        "optimal_schedule": optimal_sched,
        "optimal_makespan": optimal_ms,
        "segatz_schedule": segatz_sched,
        "segatz_makespan": segatz_ms,
    }


def main():
    parser = argparse.ArgumentParser(
        description="List Scheduling analysis for Kyber DAG")
    parser.add_argument("--kyber-k", type=int, choices=[2, 3, 4], default=2,
                        help="Security level (2=512, 3=768, 4=1024)")
    parser.add_argument("--results-dir", type=str, default="results",
                        help="Directory containing task_times JSON files")
    args = parser.parse_args()

    level = {2: 512, 3: 768, 4: 1024}[args.kyber_k]
    json_path = os.path.join(args.results_dir, f"task_times_kyber{level}.json")

    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found. Run task_profiler first.")
        sys.exit(1)

    times = load_task_times(json_path)

    results = {}
    results["keypair"] = analyze_one("Key Generation", KEYPAIR_DAG, times,
                                      SEGATZ_KEYPAIR)
    results["encaps"] = analyze_one("Encapsulation", ENCAPS_DAG, times,
                                     SEGATZ_ENCAPS)
    results["decaps"] = analyze_one("Decapsulation", DECAPS_DAG, times,
                                     SEGATZ_DECAPS)

    # Print comparison report
    report = []
    report.append("=" * 70)
    report.append(f"  List Scheduling Analysis — Kyber-{level}")
    report.append("=" * 70)

    for op_name in ["keypair", "encaps", "decaps"]:
        r = results[op_name]
        report.append("")
        report.append(f"  {op_name.upper()}")
        report.append(f"  {'─' * 60}")
        report.append(f"    Total work:          {r['total_work']:>10.2f} μs")
        report.append(f"    Single-core time:    {r['total_work']:>10.2f} μs")
        report.append(f"    Segatz 2-core:       {r['segatz_makespan']:>10.2f} μs")
        report.append(f"    List Sched 2-core:   {r['optimal_makespan']:>10.2f} μs")

        if r['segatz_makespan'] > 0:
            seg_speedup = r['total_work'] / r['segatz_makespan']
            report.append(f"    Segatz speedup:      {seg_speedup:>10.2f}x")
        if r['optimal_makespan'] > 0:
            opt_speedup = r['total_work'] / r['optimal_makespan']
            report.append(f"    Optimal speedup:     {opt_speedup:>10.2f}x")
        if r['optimal_makespan'] > 0 and r['segatz_makespan'] > 0:
            gap_pct = ((r['segatz_makespan'] - r['optimal_makespan'])
                       / r['optimal_makespan'] * 100)
            report.append(f"    Gap (Segatz→Optimal):{gap_pct:>10.1f}%")

        # Show task assignments for both schedules
        report.append("")
        report.append("    Segatz assignment:")
        for tid, core, start, end in r["segatz_schedule"]:
            tname = r["dag"][tid]["name"]
            report.append(f"      Core {core}: {tname:<30s} "
                          f"[{start:.1f} → {end:.1f}] ({end-start:.1f} μs)")

        report.append("")
        report.append("    List Scheduling assignment:")
        for tid, core, start, end in r["optimal_schedule"]:
            tname = r["dag"][tid]["name"]
            report.append(f"      Core {core}: {tname:<30s} "
                          f"[{start:.1f} → {end:.1f}] ({end-start:.1f} μs)")

    report_text = "\n".join(report)
    print(report_text)

    # Save text report
    txt_path = os.path.join(args.results_dir, "schedule_comparison.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(report_text + "\n")
    print(f"\n  Report saved to: {txt_path}")

    # Generate Gantt chart
    if HAS_MPL:
        png_path = os.path.join(args.results_dir, "optimal_schedule.png")
        generate_gantt_chart(results, png_path)

    # Run sensitivity analysis if profiler data is available
    run_sensitivity_analysis(times, args.results_dir, level)

    return 0


# ================================================================
#  Sensitivity Analysis — ESP32 hardware accelerator simulation
# ================================================================

# Tasks that use SHA/AES primitives in the 90s variant:
#   SHA-512:      KG.1_seed_expansion (hash_g)
#   AES-256-CTR:  KG.2_gen_matrix_A, KG.3_noise_s, KG.4_noise_e,
#                 ENC.2_gen_matrix_AT, ENC.3_noise_r,
#                 ENC.4_noise_e1, ENC.5_noise_e2
# Decapsulation has ZERO SHA/AES calls at the IND-CPA level.

SHA_TASKS = {"KG.1_seed_expansion"}
AES_TASKS = {
    "KG.2_gen_matrix_A", "KG.3_noise_s", "KG.4_noise_e",
    "ENC.2_gen_matrix_AT", "ENC.3_noise_r",
    "ENC.4_noise_e1", "ENC.5_noise_e2",
}


def scale_times(times, sha_factor, aes_factor):
    """Return a new times dict with SHA/AES tasks scaled down."""
    scaled = {}
    for name, t in times.items():
        if name in SHA_TASKS:
            scaled[name] = t / sha_factor
        elif name in AES_TASKS:
            scaled[name] = t / aes_factor
        else:
            scaled[name] = t
    return scaled


def critical_path_length(dag):
    """Compute the critical path length of a weighted DAG."""
    n = len(dag)
    est = [0.0] * n  # earliest start time
    for task in dag:
        tid = task["id"]
        dep_finish = max((est[d] + dag[d]["weight"] for d in task["deps"]),
                         default=0.0)
        est[tid] = dep_finish
    return max(est[tid] + dag[tid]["weight"] for tid in range(n))


def critical_path_tasks(dag):
    """Return the list of task names on the critical path."""
    n = len(dag)

    # Forward pass — earliest start/finish
    est = [0.0] * n
    eft = [0.0] * n
    for task in dag:
        tid = task["id"]
        dep_finish = max((eft[d] for d in task["deps"]), default=0.0)
        est[tid] = dep_finish
        eft[tid] = dep_finish + task["weight"]

    makespan = max(eft)

    # Backward pass — latest start/finish
    successors = defaultdict(list)
    for task in dag:
        for d in task["deps"]:
            successors[d].append(task["id"])

    lft = [makespan] * n
    lst = [0.0] * n
    for task in reversed(dag):
        tid = task["id"]
        if successors[tid]:
            lft[tid] = min(lst[s] for s in successors[tid])
        else:
            lft[tid] = makespan
        lst[tid] = lft[tid] - task["weight"]

    # Critical tasks have zero slack
    cp = []
    for task in dag:
        tid = task["id"]
        slack = lst[tid] - est[tid]
        if abs(slack) < 1e-9:
            cp.append(task["name"])
    return cp


def run_sensitivity_analysis(times, results_dir, level):
    """
    Sensitivity analysis: how does the ESP32 hardware SHA/AES accelerator
    affect scheduling?
    
    From Segatz et al. 2022:
      SHA-256 speedup: 10.44x,  SHA-512: 6.1x,  AES: 9.65x
    
    Scenarios:
      A — PC weights (baseline, no accelerator)
      B — SHA tasks /6.1, AES tasks /9.65 (ESP32 HW accelerator)
      C — SHA tasks /4, AES tasks /6 (conservative estimate)
    """

    scenarios = [
        ("A: PC baseline (no HW accel)", 1.0, 1.0),
        ("B: ESP32 HW accel (SHA/6.1, AES/9.65)", 6.1, 9.65),
        ("C: Conservative (SHA/4, AES/6)", 4.0, 6.0),
    ]

    ops = [
        ("keypair", KEYPAIR_DAG, SEGATZ_KEYPAIR),
        ("encaps",  ENCAPS_DAG,  SEGATZ_ENCAPS),
        ("decaps",  DECAPS_DAG,  SEGATZ_DECAPS),
    ]

    report = []
    report.append("")
    report.append("=" * 70)
    report.append(f"  Sensitivity Analysis — Kyber-{level}")
    report.append(f"  Effect of ESP32 SHA/AES hardware accelerator on scheduling")
    report.append("=" * 70)
    report.append("")
    report.append("  SHA-accelerated tasks:  KG.1_seed_expansion (SHA-512)")
    report.append("  AES-accelerated tasks:  KG.2_gen_matrix_A, KG.3_noise_s,")
    report.append("    KG.4_noise_e, ENC.2_gen_matrix_AT, ENC.3_noise_r,")
    report.append("    ENC.4_noise_e1, ENC.5_noise_e2")
    report.append("  Unaffected: all NTT, arithmetic, serialization tasks")
    report.append("  Unaffected: entire Decapsulation (zero SHA/AES calls)")
    report.append("")

    # Collect per-scenario results for comparison
    all_results = {}  # scenario_label -> {op -> {cp_tasks, cp_len, ...}}

    for scenario_label, sha_f, aes_f in scenarios:
        report.append(f"  {'─' * 66}")
        report.append(f"  {scenario_label}")
        report.append(f"  {'─' * 66}")

        scaled = scale_times(times, sha_f, aes_f)
        scenario_data = {}

        for op_name, dag_template, segatz_assign in ops:
            dag = assign_weights(dag_template, scaled)
            total_work = sum(t["weight"] for t in dag)
            cp_len = critical_path_length(dag)
            cp_tasks = critical_path_tasks(dag)
            _, opt_ms = list_schedule(dag)
            _, seg_ms = simulate_segatz(dag, segatz_assign)

            scenario_data[op_name] = {
                "total_work": total_work,
                "cp_length": cp_len,
                "cp_tasks": cp_tasks,
                "optimal_ms": opt_ms,
                "segatz_ms": seg_ms,
            }

            seg_speedup = total_work / seg_ms if seg_ms > 0 else 0
            opt_speedup = total_work / opt_ms if opt_ms > 0 else 0
            gap_pct = ((seg_ms - opt_ms) / opt_ms * 100) if opt_ms > 0 else 0

            report.append(f"    {op_name.upper():<12s}  "
                          f"work={total_work:>8.2f}  "
                          f"CP={cp_len:>8.2f}  "
                          f"Segatz={seg_ms:>8.2f}  "
                          f"ListSched={opt_ms:>8.2f}  "
                          f"gap={gap_pct:>5.1f}%  "
                          f"speedup={opt_speedup:.2f}x")

            # Show scaled weights for SHA/AES tasks
            if sha_f > 1.0 or aes_f > 1.0:
                changed = []
                for t in dag:
                    orig = times.get(t["name"], 0.0)
                    if abs(t["weight"] - orig) > 0.01:
                        changed.append(
                            f"      {t['name']:<30s} "
                            f"{orig:>8.2f} → {t['weight']:>8.2f} μs "
                            f"(/{orig/t['weight']:.1f}x)")
                if changed:
                    report.append("      Scaled tasks:")
                    report.extend(changed)

        all_results[scenario_label] = scenario_data
        report.append("")

    # ── Cross-scenario comparison ──
    report.append("=" * 70)
    report.append("  CROSS-SCENARIO COMPARISON")
    report.append("=" * 70)

    scenario_labels = [s[0] for s in scenarios]
    baseline_label = scenario_labels[0]

    for op_name, _, _ in ops:
        report.append(f"\n  {op_name.upper()}:")
        baseline_cp = all_results[baseline_label][op_name]["cp_tasks"]

        # Check if critical path changes
        cp_changed = False
        for label in scenario_labels[1:]:
            other_cp = all_results[label][op_name]["cp_tasks"]
            if other_cp != baseline_cp:
                cp_changed = True
                report.append(f"    ⚠ Critical path CHANGES under {label}:")
                report.append(f"      Baseline: {' → '.join(baseline_cp)}")
                report.append(f"      Changed:  {' → '.join(other_cp)}")

        if not cp_changed:
            report.append(f"    Critical path is INVARIANT across all scenarios:")
            report.append(f"      {' → '.join(baseline_cp)}")

        # Check if gap opens up
        gaps = []
        for label in scenario_labels:
            d = all_results[label][op_name]
            gap = ((d["segatz_ms"] - d["optimal_ms"]) / d["optimal_ms"] * 100
                   if d["optimal_ms"] > 0 else 0)
            gaps.append((label, gap, d["segatz_ms"], d["optimal_ms"]))

        any_nonzero = any(abs(g[1]) > 0.05 for g in gaps)
        if any_nonzero:
            report.append(f"    ⚠ Segatz gap OPENS under accelerated scenarios:")
            for label, gap, seg, opt in gaps:
                marker = " ← GAP" if abs(gap) > 0.05 else ""
                report.append(
                    f"      {label}: "
                    f"Segatz={seg:.2f} vs Optimal={opt:.2f} "
                    f"(gap={gap:.1f}%){marker}")
        else:
            report.append(f"    Segatz remains optimal across all scenarios "
                          f"(gap=0.0%)")

        # Show speedup trend
        report.append(f"    Speedup trend (List Sched 2-core vs single-core):")
        for label in scenario_labels:
            d = all_results[label][op_name]
            sp = d["total_work"] / d["optimal_ms"] if d["optimal_ms"] > 0 else 0
            report.append(f"      {label}: {sp:.2f}x")

    report.append("")

    report_text = "\n".join(report)
    print(report_text)

    txt_path = os.path.join(results_dir, "sensitivity_analysis.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(report_text + "\n")
    print(f"\n  Sensitivity analysis saved to: {txt_path}")


if __name__ == "__main__":
    sys.exit(main())
