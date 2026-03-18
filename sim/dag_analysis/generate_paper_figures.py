"""
generate_paper_figures.py — Generate figures for IEEE journal paper

Generates:
  1. sim/results/sensitivity_plot.png — Scheduling gap vs acceleration scenario
  2. sim/results/scenario_b_gantt.png — Gantt: Segatz vs Optimal under HW acceleration

Uses the same DAG definitions and scheduler as list_scheduler.py.
"""

import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ================================================================
#  DAG definitions (from list_scheduler.py)
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

SHA_TASKS = {"KG.1_seed_expansion"}
AES_TASKS = {
    "KG.2_gen_matrix_A", "KG.3_noise_s", "KG.4_noise_e",
    "ENC.2_gen_matrix_AT", "ENC.3_noise_r",
    "ENC.4_noise_e1", "ENC.5_noise_e2",
}

# ================================================================
#  Scheduler functions (from list_scheduler.py)
# ================================================================

def assign_weights(dag, times):
    weighted = []
    for task in dag:
        w = times.get(task["name"], 0.0)
        weighted.append({"id": task["id"], "name": task["name"],
                         "deps": list(task["deps"]), "weight": w})
    return weighted

def compute_bottom_level(dag):
    n = len(dag)
    successors = defaultdict(list)
    for task in dag:
        for dep in task["deps"]:
            successors[dep].append(task["id"])
    blevel = [0.0] * n
    for task in reversed(dag):
        tid = task["id"]
        if successors[tid]:
            blevel[tid] = task["weight"] + max(blevel[s] for s in successors[tid])
        else:
            blevel[tid] = task["weight"]
    return blevel

def list_schedule(dag, num_cores=2):
    n = len(dag)
    blevel = compute_bottom_level(dag)
    core_avail = [0.0] * num_cores
    finish_time = [0.0] * n
    scheduled = [False] * n
    schedule = []
    for _ in range(n):
        ready = []
        for task in dag:
            tid = task["id"]
            if scheduled[tid]:
                continue
            if all(scheduled[dep] for dep in task["deps"]):
                ready.append(tid)
        if not ready:
            break
        ready.sort(key=lambda t: blevel[t], reverse=True)
        best_task = ready[0]
        task = dag[best_task]
        dep_finish = max((finish_time[d] for d in task["deps"]), default=0.0)
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

def scale_times(times, sha_factor, aes_factor):
    scaled = {}
    for name, t in times.items():
        if name in SHA_TASKS:
            scaled[name] = t / sha_factor
        elif name in AES_TASKS:
            scaled[name] = t / aes_factor
        else:
            scaled[name] = t
    return scaled

# ================================================================
#  Figure 1: Sensitivity Analysis Plot
# ================================================================

def generate_sensitivity_plot(times, output_path):
    """Generate line plot: scheduling gap vs acceleration scenario."""
    
    scenarios = [
        ("No Acceleration\n(Scenario A)", 1.0, 1.0),
        ("Conservative\nSHA/4×, AES/6×\n(Scenario C)", 4.0, 6.0),
        ("ESP32 HW Accel\nSHA/6.1×, AES/9.65×\n(Scenario B)", 6.1, 9.65),
    ]
    
    ops = [
        ("Key Generation", KEYPAIR_DAG, SEGATZ_KEYPAIR),
        ("Encapsulation",  ENCAPS_DAG,  SEGATZ_ENCAPS),
        ("Decapsulation",  DECAPS_DAG,  SEGATZ_DECAPS),
    ]
    
    # Compute gaps for each scenario × operation
    results = {op_name: [] for op_name, _, _ in ops}
    
    for _, sha_f, aes_f in scenarios:
        scaled = scale_times(times, sha_f, aes_f)
        for op_name, dag_tmpl, seg_assign in ops:
            dag = assign_weights(dag_tmpl, scaled)
            _, opt_ms = list_schedule(dag)
            _, seg_ms = simulate_segatz(dag, seg_assign)
            gap = ((seg_ms - opt_ms) / opt_ms * 100) if opt_ms > 0 else 0
            results[op_name].append(gap)
    
    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(scenarios))
    width = 0.22
    
    colors = ['#2196F3', '#FF5722', '#4CAF50']
    markers = ['o', 's', '^']
    
    for i, (op_name, _, _) in enumerate(ops):
        gaps = results[op_name]
        bars = ax.bar(x + i * width, gaps, width, label=op_name,
                      color=colors[i], alpha=0.85, edgecolor='black', linewidth=0.5)
        # Add value labels on bars
        for bar, val in zip(bars, gaps):
            if val > 0.05:
                ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.15,
                        f'{val:.1f}%', ha='center', va='bottom', fontweight='bold',
                        fontsize=10)
            else:
                ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.15,
                        f'{val:.1f}%', ha='center', va='bottom', fontsize=9,
                        color='gray')
    
    scenario_labels = [s[0] for s in scenarios]
    ax.set_xticks(x + width)
    ax.set_xticklabels(scenario_labels, fontsize=9)
    ax.set_ylabel('Scheduling Gap (%)', fontsize=12, fontweight='bold')
    ax.set_title('Scheduling Gap: Segatz vs. HLFET Optimal\nAcross Hardware Acceleration Scenarios (Kyber-512)',
                 fontsize=13, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10, framealpha=0.9)
    ax.set_ylim(0, max(max(v) for v in results.values()) * 1.35)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  Sensitivity plot saved to: {output_path}")


# ================================================================
#  Figure 2: Scenario B Gantt Chart
# ================================================================

def draw_gantt_scenarioB(ax, schedule, dag, title, task_type_colors):
    """Draw a Gantt chart with task-type coloring for Scenario B."""
    for tid, core, start, end in schedule:
        task_name = dag[tid]["name"]
        short_name = task_name.split("_", 1)[0]
        duration = end - start
        
        # Color by task type
        if task_name in SHA_TASKS:
            color = task_type_colors['sha']
        elif task_name in AES_TASKS:
            color = task_type_colors['aes']
        else:
            color = task_type_colors['arith']
        
        bar = ax.barh(core, duration, left=start, height=0.6,
                      color=color, edgecolor='black', linewidth=0.5, alpha=0.85)
        
        if duration > 1.0:
            ax.text(start + duration / 2, core, short_name,
                    ha='center', va='center', fontsize=7, fontweight='bold')
    
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['Core 0', 'Core 1'], fontsize=9)
    ax.set_xlabel('Time (μs)', fontsize=9)
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.set_xlim(left=0)
    ax.invert_yaxis()


def generate_scenario_b_gantt(times, output_path):
    """Generate Gantt chart for Scenario B (HW accelerated) — Encapsulation only."""
    
    sha_f, aes_f = 6.1, 9.65
    scaled = scale_times(times, sha_f, aes_f)
    
    ops = [
        ("Key Generation", KEYPAIR_DAG, SEGATZ_KEYPAIR),
        ("Encapsulation",  ENCAPS_DAG,  SEGATZ_ENCAPS),
        ("Decapsulation",  DECAPS_DAG,  SEGATZ_DECAPS),
    ]
    
    task_type_colors = {
        'sha':   '#FFB74D',  # orange — SHA tasks
        'aes':   '#64B5F6',  # blue — AES tasks  
        'arith': '#81C784',  # green — arithmetic/NTT tasks
    }
    
    fig, axes = plt.subplots(3, 2, figsize=(16, 10))
    fig.suptitle('Scenario B: ESP32 Hardware Acceleration (SHA/6.1×, AES/9.65×)\nSegatz Schedule vs. HLFET Optimal',
                 fontsize=14, fontweight='bold')
    
    for row, (label, dag_tmpl, seg_assign) in enumerate(ops):
        dag = assign_weights(dag_tmpl, scaled)
        seg_sched, seg_ms = simulate_segatz(dag, seg_assign)
        opt_sched, opt_ms = list_schedule(dag)
        gap = ((seg_ms - opt_ms) / opt_ms * 100) if opt_ms > 0 else 0
        
        draw_gantt_scenarioB(axes[row][0], seg_sched, dag,
                             f'{label} — Segatz ({seg_ms:.1f} μs)', task_type_colors)
        
        gap_str = f' [gap: {gap:.1f}%]' if gap > 0.05 else ' [optimal]'
        draw_gantt_scenarioB(axes[row][1], opt_sched, dag,
                             f'{label} — HLFET Optimal ({opt_ms:.1f} μs){gap_str}',
                             task_type_colors)
    
    # Add legend
    legend_patches = [
        mpatches.Patch(color=task_type_colors['sha'], label='SHA task (accelerated)'),
        mpatches.Patch(color=task_type_colors['aes'], label='AES task (accelerated)'),
        mpatches.Patch(color=task_type_colors['arith'], label='Arithmetic/NTT task'),
    ]
    fig.legend(handles=legend_patches, loc='lower center', ncol=3,
               fontsize=10, framealpha=0.9, bbox_to_anchor=(0.5, -0.02))
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.93])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  Scenario B Gantt chart saved to: {output_path}")


# ================================================================
#  Main
# ================================================================

def main():
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "results")
    json_path = os.path.join(results_dir, "task_times_kyber512.json")
    
    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found.")
        sys.exit(1)
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    times = {task["name"]: task["avg_us"] for task in data["tasks"]}
    
    print("Generating figures for IEEE journal paper...\n")
    
    # Figure 1: Sensitivity plot
    sensitivity_path = os.path.join(results_dir, "sensitivity_plot.png")
    generate_sensitivity_plot(times, sensitivity_path)
    
    # Figure 2: Scenario B Gantt
    gantt_path = os.path.join(results_dir, "scenario_b_gantt.png")
    generate_scenario_b_gantt(times, gantt_path)
    
    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
