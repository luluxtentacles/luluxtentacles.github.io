"""
Cumulative Stouffer Z for Intention vs Relax slope difference.

Exports
-------
compute_session_z(data_path, source, gates, max_qualifying, lag_seconds=5)
    -> (zO, zU) per-session z-scores, in chronological order.

plot_cumulative_z(zO_H, zU_H, zO_AI=None, zU_AI=None,
                  n_rnd=200, rng_seed=42, save_path=None)
    -> matplotlib Figure (2-panel: Observed, Unobserved).

Methodology
-----------
For each qualifying session, slope differences (Intention - Relax) are
computed for 10 epoch pairs.  An exact sign-flip permutation over 2^10 = 1024
sign patterns yields a one-tailed p-value, converted to z = norm.ppf(1 - p)
with a continuity correction so p never reaches 0 or 1.

Cumulative Stouffer Z = cumsum(z) / sqrt(n).

A 90% confidence envelope is obtained by computing the Stouffer Z curve for
n_rnd random orderings of the same z-scores and taking the 5th/95th
percentiles at each session count.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm as _norm

from load_arrays           import load_arrays
from load_sessions         import load_sessions
from map_section_to_columns import map_section_to_columns

_FS         = 2
_N_GROUPS   = 10
_GROUP_SIZE = 120

# All 2^10 = 1024 sign patterns, shape (1024, 10), entries +/-1.
# Each row k encodes the bits of k (LSB first): bit j = (k >> j) & 1, mapped 0->-1, 1->+1.
_bits = (np.arange(2**_N_GROUPS)[:, None] >> np.arange(_N_GROUPS)[None, :]) & 1
_SIGN_MAT = 2 * _bits - 1   # shape (1024, 10)


def compute_session_z(data_path, source, gates, max_qualifying,
                      lag_seconds=5):
    """
    Compute per-session Stouffer z-scores in chronological order.

    Returns
    -------
    zO : np.ndarray  shape (N_valid,)  z-scores for Observed sensor
    zU : np.ndarray  shape (N_valid,)  z-scores for Unobserved sensor
    """
    A, B = load_arrays(data_path)
    sessions, good = load_sessions(data_path, source=source,
                                   gates=gates,
                                   max_qualifying=max_qualifying)

    sel = sessions[good].copy()
    if 'SessionDateTime' in sel.columns:
        sel = sel.sort_values('SessionDateTime')
    elif 'SessionDate' in sel.columns:
        sel = sel.sort_values('SessionDate')

    delay   = round(lag_seconds * _FS)
    half    = 60 - delay
    x       = np.arange(1, half + 1, dtype=float)
    n_exact = 2 ** _N_GROUPS

    zO_list = []
    zU_list = []

    for _, row in sel.iterrows():
        section = str(row['Section']).strip()
        obs_col, unobs_col, _ = map_section_to_columns(section)
        if obs_col is None:
            continue

        prefix = section[0].lower()
        if prefix == 'a':
            obs_v   = A[obs_col].values   if obs_col   in A.columns else None
            unobs_v = B[unobs_col].values if unobs_col in B.columns else None
        elif prefix == 'b':
            obs_v   = B[obs_col].values   if obs_col   in B.columns else None
            unobs_v = A[unobs_col].values if unobs_col in A.columns else None
        else:
            continue

        if obs_v is None or unobs_v is None:
            continue
        if np.any(np.isnan(obs_v)) or np.any(np.isnan(unobs_v)):
            continue

        dO = np.zeros(_N_GROUPS)
        dU = np.zeros(_N_GROUPS)
        ok = True
        for g in range(_N_GROUPS):
            st  = g * _GROUP_SIZE
            i0, i1 = st + delay, st + 60
            r0, r1 = st + 60 + delay, st + 120
            if r1 > len(obs_v):
                ok = False
                break
            sOI = np.polyfit(x, obs_v[i0:i1],   1)[0]
            sOR = np.polyfit(x, obs_v[r0:r1],   1)[0]
            sUI = np.polyfit(x, unobs_v[i0:i1], 1)[0]
            sUR = np.polyfit(x, unobs_v[r0:r1], 1)[0]
            dO[g] = sOI - sOR
            dU[g] = sUI - sUR
        if not ok:
            continue

        null_O = (_SIGN_MAT @ dO) / _N_GROUPS
        null_U = (_SIGN_MAT @ dU) / _N_GROUPS
        mean_O = dO.mean()
        mean_U = dU.mean()

        # continuity-corrected one-tailed p (left tail: Int < Rel predicted)
        pO = (np.sum(null_O <= mean_O) + 0.5) / (n_exact + 1)
        pU = (np.sum(null_U <= mean_U) + 0.5) / (n_exact + 1)

        zO_list.append(_norm.ppf(1.0 - pO))
        zU_list.append(_norm.ppf(1.0 - pU))

    return np.array(zO_list), np.array(zU_list)


def plot_cumulative_z(zO_H, zU_H, zO_AI=None, zU_AI=None,
                      n_rnd=200, rng_seed=42, save_path=None):
    """
    Plot cumulative Stouffer Z (2-panel: Observed, Unobserved).

    Human line (blue) with 90% random-order confidence envelope.
    Optional AI line (red).
    """
    col_H  = (0.15, 0.35, 0.80)
    col_AI = (0.85, 0.20, 0.20)

    def cum_z(z):
        return np.cumsum(z) / np.sqrt(np.arange(1, len(z) + 1))

    cZ_O_H = cum_z(zO_H)
    cZ_U_H = cum_z(zU_H)

    n_H    = len(zO_H)
    nH_vec = np.arange(1, n_H + 1)
    x_max  = n_H

    # Final values
    print(f"Human  OBS   cumZ={cZ_O_H[-1]:+.3f}  p={1 - _norm.cdf(cZ_O_H[-1]):.4f}")
    print(f"Human  UNOBS cumZ={cZ_U_H[-1]:+.3f}  p={1 - _norm.cdf(cZ_U_H[-1]):.4f}")

    if zO_AI is not None:
        cZ_O_AI = cum_z(zO_AI)
        cZ_U_AI = cum_z(zU_AI)
        print(f"AI     OBS   cumZ={cZ_O_AI[-1]:+.3f}  p={1 - _norm.cdf(cZ_O_AI[-1]):.4f}")
        print(f"AI     UNOBS cumZ={cZ_U_AI[-1]:+.3f}  p={1 - _norm.cdf(cZ_U_AI[-1]):.4f}")
        nAI_vec = np.arange(1, len(zO_AI) + 1)
        x_max   = max(x_max, len(zO_AI))

    # Shared y-axis limits across both panels
    all_curves = [cZ_O_H, cZ_U_H]
    if zO_AI is not None:
        all_curves += [cZ_O_AI, cZ_U_AI]
    all_vals = np.concatenate(all_curves)
    margin   = (all_vals.max() - all_vals.min()) * 0.08
    ylims    = (all_vals.min() - margin, all_vals.max() + margin)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor='white')
    fig.subplots_adjust(wspace=0.30)

    sensors = [
        ('Observed',   cZ_O_H, cZ_O_AI if zO_AI is not None else None),
        ('Unobserved', cZ_U_H, cZ_U_AI if zU_AI is not None else None),
    ]

    for ax, (label, cH, cAI) in zip(axes, sensors):
        ax.plot(nH_vec, cH, '-', color=col_H, linewidth=2, label='Human')
        if cAI is not None:
            ax.plot(nAI_vec, cAI, '-', color=col_AI, linewidth=2, label='AI')
        ax.axhline(0, color='black', linewidth=0.6)
        ax.set_xlim(1, x_max)
        ax.set_ylim(ylims)
        ax.set_xlabel('Sessions (chronological)', fontsize=13)
        ax.set_ylabel('Cumulative Stouffer Z', fontsize=13)
        ax.text(0.97, 0.96, label, transform=ax.transAxes,
                ha='right', va='top', fontsize=14, fontweight='bold')
        if label == 'Observed':
            ax.legend(loc='upper left', fontsize=11)
        ax.tick_params(labelsize=11)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    fig.suptitle('Cumulative Stouffer Z: Intention vs Relax slope difference',
                 fontsize=14, fontweight='bold')

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {save_path}")
    return fig


if __name__ == '__main__':
    import os
    data_path = "."
    gates = list(range(1, 8))

    print("Computing human z-scores...")
    zO_H, zU_H = compute_session_z(data_path, 'human', gates, 1000)
    print(f"  {len(zO_H)} valid sessions\n")

    print("Computing AI z-scores...")
    zO_AI, zU_AI = compute_session_z(data_path, 'ai', gates, 1000)
    print(f"  {len(zO_AI)} valid sessions\n")

    plot_cumulative_z(zO_H, zU_H, zO_AI, zU_AI,
                      save_path='cumulative_stouffer_z.png')
    plt.show()
