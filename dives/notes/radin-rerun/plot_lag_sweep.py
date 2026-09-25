"""
Lag sensitivity sweep: odds against chance vs cognitive delay.

Sweeps the analysis delay from 0 to 10 seconds in 0.5-second steps.
At each lag the direct Intention-vs-Relax slope difference is tested with a
label-swap permutation (two-tailed, n_perm iterations), and odds = 1/p are
plotted for Observed and Unobserved sensors.

Preregistered lag: 5 seconds (marked with a vertical dashed line).

Exports
-------
plot_lag_sweep(data_path, source='human', gates=None, max_qualifying=1000,
               n_perm=1000, lag_range=None, rng_seed=42, save_path=None)
    -> (fig, results_dict)
"""

import numpy as np
import matplotlib.pyplot as plt

from load_arrays            import load_arrays
from load_sessions          import load_sessions
from map_section_to_columns import map_section_to_columns

_FS         = 2
_N_GROUPS   = 10
_GROUP_SIZE = 120


def plot_lag_sweep(data_path='.', source='human', gates=None,
                   max_qualifying=1000, n_perm=1000, lag_range=None,
                   rng_seed=42, save_path=None):
    """
    Returns
    -------
    fig : matplotlib Figure
    results : dict with keys lag_range, p_obs, p_unobs, n_blocks
    """
    if gates is None:
        gates = list(range(1, 8))
    if lag_range is None:
        lag_range = np.arange(0, 10.5, 0.5)

    rng = np.random.default_rng(rng_seed)

    A, B     = load_arrays(data_path)
    sessions, good = load_sessions(data_path, source=source,
                                   gates=gates, max_qualifying=max_qualifying)
    sel = sessions[good]

    # Pre-load sensor vectors for all qualifying sessions
    sess_data = []
    for _, row in sel.iterrows():
        section = str(row['Section']).strip()
        obs_col, unobs_col, _ = map_section_to_columns(section)
        if obs_col is None:
            continue
        prefix = section[0].lower()
        if prefix == 'a':
            ov = A[obs_col].values   if obs_col   in A.columns else None
            uv = B[unobs_col].values if unobs_col in B.columns else None
        elif prefix == 'b':
            ov = B[obs_col].values   if obs_col   in B.columns else None
            uv = A[unobs_col].values if unobs_col in A.columns else None
        else:
            continue
        if ov is None or uv is None:
            continue
        if np.any(np.isnan(ov)) or np.any(np.isnan(uv)):
            continue
        sess_data.append((ov, uv))

    print(f"Loaded {len(sess_data)} sessions; sweeping "
          f"{len(lag_range)} lags, {n_perm} permutations each...")

    n_lags   = len(lag_range)
    p_obs    = np.full(n_lags, np.nan)
    p_unobs  = np.full(n_lags, np.nan)
    n_blocks = 0

    for li, lag_s in enumerate(lag_range):
        delay    = round(lag_s * _FS)
        half_len = 60 - delay
        if half_len < 10:
            print(f"  Lag {lag_s:.1f}s: halfLen={half_len}, skip")
            continue

        x = np.arange(1, half_len + 1, dtype=float)

        sOI_list, sOR_list = [], []
        sUI_list, sUR_list = [], []

        for ov, uv in sess_data:
            for g in range(_N_GROUPS):
                st  = g * _GROUP_SIZE
                i0, i1 = st + delay,      st + 60
                r0, r1 = st + 60 + delay, st + 120
                if r1 > len(ov):
                    continue
                sOI_list.append(np.polyfit(x, ov[i0:i1], 1)[0])
                sOR_list.append(np.polyfit(x, ov[r0:r1], 1)[0])
                sUI_list.append(np.polyfit(x, uv[i0:i1], 1)[0])
                sUR_list.append(np.polyfit(x, uv[r0:r1], 1)[0])

        if not sOI_list:
            continue

        sOI = np.array(sOI_list)
        sOR = np.array(sOR_list)
        sUI = np.array(sUI_list)
        sUR = np.array(sUR_list)
        nb  = len(sOI)
        if li == 0 or n_blocks == 0:
            n_blocks = nb

        obs_diff   = np.mean(sOI - sOR)
        unobs_diff = np.mean(sUI - sUR)

        # Vectorised label-swap permutation
        swap      = rng.random((n_perm, nb)) > 0.5
        null_obs  = np.mean(np.where(swap, sOR, sOI) - np.where(swap, sOI, sOR), axis=1)
        null_unobs = np.mean(np.where(swap, sUR, sUI) - np.where(swap, sUI, sUR), axis=1)

        # Two-tailed
        pO = np.mean(np.abs(null_obs)   >= np.abs(obs_diff))
        pU = np.mean(np.abs(null_unobs) >= np.abs(unobs_diff))
        p_obs[li]   = max(pO, 1.0 / (n_perm + 1))
        p_unobs[li] = max(pU, 1.0 / (n_perm + 1))

        print(f"  Lag {lag_s:4.1f}s  "
              f"Obs p={p_obs[li]:.4f}  Unobs p={p_unobs[li]:.4f}")

    valid = ~np.isnan(p_obs)
    lags_v = lag_range[valid]
    pO_v   = p_obs[valid]
    pU_v   = p_unobs[valid]

    best_O = np.argmin(pO_v)
    best_U = np.argmin(pU_v)
    print(f"\nBest Obs lag:   {lags_v[best_O]:.1f}s  "
          f"p={pO_v[best_O]:.4f}  odds={1/pO_v[best_O]:.1f}:1")
    print(f"Best Unobs lag: {lags_v[best_U]:.1f}s  "
          f"p={pU_v[best_U]:.4f}  odds={1/pU_v[best_U]:.1f}:1")

    odds_O = 1.0 / pO_v
    odds_U = 1.0 / pU_v

    col_O = (0.15, 0.35, 0.80)
    col_U = (0.80, 0.20, 0.20)

    fig, ax = plt.subplots(figsize=(8, 5), facecolor='white')

    ax.plot(lags_v, odds_O, '-o', color=col_O, linewidth=2, markersize=7,
            label='Observed')
    ax.plot(lags_v, odds_U, '-o', color=col_U, linewidth=2, markersize=7,
            label='Unobserved')
    ax.axvline(5, color='black', linewidth=1.0, linestyle=':',
               label='Preregistered lag (5 s)')
    ax.set_xlabel('Lag (seconds)', fontsize=13)
    ax.set_ylabel('Odds Against Chance (1/p)', fontsize=13)
    ax.set_xlim(lag_range[0] - 0.25, lag_range[-1] + 0.25)
    ax.legend(fontsize=11)
    ax.tick_params(labelsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    n_sess = len(sess_data)
    ax.set_title(
        f'Lag Sensitivity: Odds Against Chance vs Cognitive Delay\n'
        f'({source.title()}, N = {n_sess} sessions, {n_perm} permutations; two-tailed)',
        fontsize=13, fontweight='bold')

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {save_path}")

    return fig, {
        'lag_range': lag_range, 'valid': valid,
        'p_obs': p_obs, 'p_unobs': p_unobs,
        'n_blocks': n_blocks,
    }


if __name__ == '__main__':
    import os
    data_path = "."
    fig, results = plot_lag_sweep(data_path, source='human',
                                  save_path='lag_sweep.png')
    plt.show()
