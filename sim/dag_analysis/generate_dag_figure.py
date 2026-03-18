"""
generate_dag_figure.py — Generate DAG diagrams for IEEE journal paper

Generates publication-quality DAG diagrams for all three KEM operations
with critical path highlighted, node weights, and dependency edges.

Output: sim/results/dag_keygen.png (and dag_encaps.png, dag_decaps.png)
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
import matplotlib.patheffects as pe
import numpy as np

# ================================================================
#  DAG definitions
# ================================================================

KEYPAIR_DAG = [
    {"id": 0, "name": "KG.1_seed_expansion",  "deps": [],     "short": "KG.1", "label": "Seed Expansion\n(SHA-512)"},
    {"id": 1, "name": "KG.2_gen_matrix_A",    "deps": [0],    "short": "KG.2", "label": "Gen Matrix A\n(AES-CTR)"},
    {"id": 2, "name": "KG.3_noise_s",         "deps": [0],    "short": "KG.3", "label": "Noise s\n(AES-CTR)"},
    {"id": 3, "name": "KG.4_noise_e",         "deps": [0],    "short": "KG.4", "label": "Noise e\n(AES-CTR)"},
    {"id": 4, "name": "KG.5_ntt_s",           "deps": [2],    "short": "KG.5", "label": "NTT(s)"},
    {"id": 5, "name": "KG.6_ntt_e",           "deps": [3],    "short": "KG.6", "label": "NTT(e)"},
    {"id": 6, "name": "KG.7_matmul_As",       "deps": [1, 4], "short": "KG.7", "label": "A·ŝ"},
    {"id": 7, "name": "KG.8_add_reduce",      "deps": [6, 5], "short": "KG.8", "label": "Add+Reduce"},
    {"id": 8, "name": "KG.9_pack",            "deps": [7],    "short": "KG.9", "label": "Pack Keys"},
]

ENCAPS_DAG = [
    {"id": 0, "name": "ENC.1_unpack_pk",       "deps": [],        "short": "ENC.1",  "label": "Unpack pk"},
    {"id": 1, "name": "ENC.2_gen_matrix_AT",   "deps": [0],       "short": "ENC.2",  "label": "Gen Matrix Aᵀ\n(AES-CTR)"},
    {"id": 2, "name": "ENC.3_noise_r",         "deps": [0],       "short": "ENC.3",  "label": "Noise r\n(AES-CTR)"},
    {"id": 3, "name": "ENC.4_noise_e1",        "deps": [0],       "short": "ENC.4",  "label": "Noise e₁\n(AES-CTR)"},
    {"id": 4, "name": "ENC.5_noise_e2",        "deps": [0],       "short": "ENC.5",  "label": "Noise e₂\n(AES-CTR)"},
    {"id": 5, "name": "ENC.6_ntt_r",           "deps": [2],       "short": "ENC.6",  "label": "NTT(r)"},
    {"id": 6, "name": "ENC.7_matmul_ATr",      "deps": [1, 5],    "short": "ENC.7",  "label": "Aᵀ·r̂"},
    {"id": 7, "name": "ENC.8_inner_tTr",       "deps": [0, 5],    "short": "ENC.8",  "label": "t̂ᵀ·r̂"},
    {"id": 8, "name": "ENC.9_invntt",          "deps": [6, 7],    "short": "ENC.9",  "label": "InvNTT"},
    {"id": 9, "name": "ENC.10_add_errors",     "deps": [8, 3, 4], "short": "ENC.10", "label": "Add Errors"},
    {"id": 10, "name": "ENC.11_compress_pack", "deps": [9],       "short": "ENC.11", "label": "Compress\n+Pack"},
]

DECAPS_DAG = [
    {"id": 0, "name": "DEC.1_decompress_ct",   "deps": [],  "short": "DEC.1", "label": "Decompress ct"},
    {"id": 1, "name": "DEC.2_unpack_sk",       "deps": [],  "short": "DEC.2", "label": "Unpack sk"},
    {"id": 2, "name": "DEC.3_ntt_u",           "deps": [0], "short": "DEC.3", "label": "NTT(u)"},
    {"id": 3, "name": "DEC.4_inner_sTu",       "deps": [1, 2], "short": "DEC.4", "label": "ŝᵀ·û"},
    {"id": 4, "name": "DEC.5_invntt",          "deps": [3], "short": "DEC.5", "label": "InvNTT"},
    {"id": 5, "name": "DEC.6_sub_reduce",      "deps": [4], "short": "DEC.6", "label": "Sub+Reduce"},
    {"id": 6, "name": "DEC.7_decode_msg",      "deps": [5], "short": "DEC.7", "label": "Decode Msg"},
]

SHA_TASKS = {"KG.1_seed_expansion"}
AES_TASKS = {
    "KG.2_gen_matrix_A", "KG.3_noise_s", "KG.4_noise_e",
    "ENC.2_gen_matrix_AT", "ENC.3_noise_r",
    "ENC.4_noise_e1", "ENC.5_noise_e2",
}


def get_critical_path_set(dag, times):
    """Return set of task IDs on the critical path."""
    n = len(dag)
    weights = [times.get(t["name"], 0.0) for t in dag]
    
    # Forward pass
    est = [0.0] * n
    eft = [0.0] * n
    for t in dag:
        tid = t["id"]
        dep_finish = max((eft[d] for d in t["deps"]), default=0.0)
        est[tid] = dep_finish
        eft[tid] = dep_finish + weights[tid]
    
    makespan = max(eft)
    
    # Backward pass
    successors = defaultdict(list)
    for t in dag:
        for d in t["deps"]:
            successors[d].append(t["id"])
    
    lft = [makespan] * n
    lst = [0.0] * n
    for t in reversed(dag):
        tid = t["id"]
        if successors[tid]:
            lft[tid] = min(lst[s] for s in successors[tid])
        else:
            lft[tid] = makespan
        lst[tid] = lft[tid] - weights[tid]
    
    cp_set = set()
    for t in dag:
        tid = t["id"]
        slack = lst[tid] - est[tid]
        if abs(slack) < 1e-9:
            cp_set.add(tid)
    
    return cp_set


def compute_layout(dag):
    """Compute (x, y) positions for each node using topological layering."""
    n = len(dag)
    
    # Compute layer (longest path from source to this node)
    layer = [0] * n
    for t in dag:
        tid = t["id"]
        if t["deps"]:
            layer[tid] = max(layer[d] + 1 for d in t["deps"])
    
    # Group by layer
    layers = defaultdict(list)
    for t in dag:
        layers[layer[t["id"]]].append(t["id"])
    
    max_layer = max(layers.keys())
    
    # Assign positions
    positions = {}
    for ly, nodes in layers.items():
        num = len(nodes)
        for i, nid in enumerate(nodes):
            x = ly * 2.5
            # Center vertically
            y = -(i - (num - 1) / 2) * 2.0
            positions[nid] = (x, y)
    
    return positions


def draw_dag(ax, dag, times, title, cp_set, positions):
    """Draw a single DAG on the given axes."""
    
    # Colors
    color_sha = '#FF9800'      # orange
    color_aes = '#42A5F5'      # blue
    color_arith = '#66BB6A'    # green
    color_cp_edge = '#D32F2F'  # red for critical path
    color_edge = '#9E9E9E'     # gray for normal edges
    
    node_radius = 0.55
    
    # Draw edges first (behind nodes)
    for t in dag:
        tid = t["id"]
        x1, y1 = positions[tid]
        for dep_id in t["deps"]:
            x0, y0 = positions[dep_id]
            
            is_cp_edge = dep_id in cp_set and tid in cp_set
            
            # Calculate edge start/end to be at node boundary
            dx = x1 - x0
            dy = y1 - y0
            dist = np.sqrt(dx**2 + dy**2)
            if dist > 0:
                ux, uy = dx / dist, dy / dist
            else:
                ux, uy = 1, 0
            
            sx = x0 + ux * node_radius
            sy = y0 + uy * node_radius
            ex = x1 - ux * node_radius
            ey = y1 - uy * node_radius
            
            if is_cp_edge:
                ax.annotate("", xy=(ex, ey), xytext=(sx, sy),
                           arrowprops=dict(arrowstyle='->', color=color_cp_edge,
                                          lw=2.5, shrinkA=0, shrinkB=0))
            else:
                ax.annotate("", xy=(ex, ey), xytext=(sx, sy),
                           arrowprops=dict(arrowstyle='->', color=color_edge,
                                          lw=1.2, shrinkA=0, shrinkB=0))
    
    # Draw nodes
    for t in dag:
        tid = t["id"]
        x, y = positions[tid]
        weight = times.get(t["name"], 0.0)
        
        # Node color
        if t["name"] in SHA_TASKS:
            color = color_sha
        elif t["name"] in AES_TASKS:
            color = color_aes
        else:
            color = color_arith
        
        is_cp = tid in cp_set
        
        # Draw circle
        circle = plt.Circle((x, y), node_radius, 
                           facecolor=color, 
                           edgecolor=color_cp_edge if is_cp else '#333333',
                           linewidth=3.0 if is_cp else 1.5,
                           alpha=0.9, zorder=10)
        ax.add_patch(circle)
        
        # Task name (short)
        ax.text(x, y + 0.12, t["short"], ha='center', va='center',
                fontsize=8, fontweight='bold', color='white', zorder=11,
                path_effects=[pe.withStroke(linewidth=2, foreground='black')])
        
        # Weight
        ax.text(x, y - 0.22, f'{weight:.1f} μs', ha='center', va='center',
                fontsize=6.5, color='white', zorder=11,
                path_effects=[pe.withStroke(linewidth=1.5, foreground='black')])
    
    ax.set_title(title, fontsize=12, fontweight='bold', pad=10)
    ax.set_aspect('equal')
    ax.axis('off')
    
    # Set limits with padding
    all_x = [positions[t["id"]][0] for t in dag]
    all_y = [positions[t["id"]][1] for t in dag]
    margin = 1.2
    ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
    ax.set_ylim(min(all_y) - margin, max(all_y) + margin)


def main():
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "results")
    json_path = os.path.join(results_dir, "task_times_kyber512.json")
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    times = {task["name"]: task["avg_us"] for task in data["tasks"]}
    
    print("Generating DAG diagrams...\n")
    
    dags = [
        ("Key Generation", KEYPAIR_DAG, "dag_keygen.png"),
        ("Encapsulation", ENCAPS_DAG, "dag_encaps.png"),
        ("Decapsulation", DECAPS_DAG, "dag_decaps.png"),
    ]
    
    # Generate individual DAG figures
    for title, dag, filename in dags:
        cp_set = get_critical_path_set(dag, times)
        positions = compute_layout(dag)
        
        # Figure size based on DAG complexity
        n_layers = max(positions[t["id"]][0] for t in dag) / 2.5 + 1
        fig_w = max(8, n_layers * 2.5)
        n_rows = max(sum(1 for t in dag if positions[t["id"]][0] == positions[dag[0]["id"]][0]) 
                     for _ in [0])
        max_nodes_in_layer = 0
        layers = defaultdict(list)
        for t in dag:
            lx = positions[t["id"]][0]
            layers[lx].append(t["id"])
        max_nodes_in_layer = max(len(v) for v in layers.values())
        fig_h = max(4, max_nodes_in_layer * 1.8)
        
        fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
        
        # Total work and CP info
        total_work = sum(times.get(t["name"], 0.0) for t in dag)
        cp_len = sum(times.get(t["name"], 0.0) for t in dag if t["id"] in cp_set)
        cp_ratio = cp_len / total_work * 100 if total_work > 0 else 0
        
        full_title = (f'{title} DAG (Kyber-512)\n'
                      f'Total Work: {total_work:.2f} μs | '
                      f'Critical Path: {cp_len:.2f} μs ({cp_ratio:.1f}%)')
        
        draw_dag(ax, dag, times, full_title, cp_set, positions)
        
        # Legend
        legend_patches = [
            mpatches.Patch(color='#FF9800', label='SHA task'),
            mpatches.Patch(color='#42A5F5', label='AES-CTR task'),
            mpatches.Patch(color='#66BB6A', label='Arithmetic/NTT'),
            mpatches.Patch(facecolor='none', edgecolor='#D32F2F', linewidth=2.5, label='Critical path'),
        ]
        ax.legend(handles=legend_patches, loc='lower right', fontsize=8,
                 framealpha=0.9, edgecolor='gray')
        
        plt.tight_layout()
        outpath = os.path.join(results_dir, filename)
        plt.savefig(outpath, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved: {outpath}")
    
    # Also generate a combined 3-panel figure
    fig, axes = plt.subplots(3, 1, figsize=(14, 16))
    fig.suptitle('CRYSTALS-Kyber Task Dependency DAGs with Critical Paths (Kyber-512)',
                 fontsize=14, fontweight='bold', y=0.98)
    
    for idx, (title, dag, _) in enumerate(dags):
        cp_set = get_critical_path_set(dag, times)
        positions = compute_layout(dag)
        
        total_work = sum(times.get(t["name"], 0.0) for t in dag)
        cp_len = sum(times.get(t["name"], 0.0) for t in dag if t["id"] in cp_set)
        cp_ratio = cp_len / total_work * 100 if total_work > 0 else 0
        
        panel_title = (f'{title} — Work: {total_work:.1f} μs, '
                       f'CP: {cp_len:.1f} μs ({cp_ratio:.0f}%)')
        
        draw_dag(axes[idx], dag, times, panel_title, cp_set, positions)
    
    # Shared legend
    legend_patches = [
        mpatches.Patch(color='#FF9800', label='SHA task'),
        mpatches.Patch(color='#42A5F5', label='AES-CTR task'),
        mpatches.Patch(color='#66BB6A', label='Arithmetic/NTT'),
        mpatches.Patch(facecolor='none', edgecolor='#D32F2F', linewidth=2.5, label='Critical path'),
    ]
    fig.legend(handles=legend_patches, loc='lower center', ncol=4,
              fontsize=10, framealpha=0.9, bbox_to_anchor=(0.5, 0.005))
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    combined_path = os.path.join(results_dir, "dag_combined.png")
    plt.savefig(combined_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Saved combined: {combined_path}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
