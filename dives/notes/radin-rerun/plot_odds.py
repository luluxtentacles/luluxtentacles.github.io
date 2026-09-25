"""
Odds against chance from cumulative Stouffer Z.

Exports
-------
plot_odds(zO_H, zU_H, zO_AI, zU_AI, save_path=None)
    -> matplotlib Figure (2-panel: Observed, Unobserved).

Methodology
-----------
Cumulative Stouffer Z = cumsum(z) / sqrt(n).
One-tailed p = 1 - normcdf(Z).
Odds against chance = 1 / p  (log y-axis).

Use compute_session_z() from plot_cumulative_z to obtain the input arrays.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm as _norm


def plot_odds(zO_H, zU_H, zO_AI=None, zU_AI=None, save_path=None):
    """
    Plot odds against chance on a log scale (2-panel: Observed, Unobserved).

    Parameters
    ----------
    zO_H, zU_H : array  per-session z-scores for Human, Observed / Unobserved
    zO_AI, zU_AI : array or None  same for AI
    """
    col_H  = (0.15, 0.35, 0.80)
    col_AI = (0.85, 0.20, 0.20)

    def cum_z(z):
        return np.cumsum(z) / np.sqrt(np.arange(1, len(z) + 1))

    def to_odds(cz):
        p = np.clip(1.0 - _norm.cdf(cz), 1e-10, 1.0 - 1e-10)
        return 1.0 / p

    odds_O_H = to_odds(cum_z(zO_H))
    odds_U_H = to_odds(cum_z(zU_H))

    nH_vec = np.arange(1, len(zO_H) + 1)
    x_max  = len(zO_H)

    if zO_AI is not None:
        odds_O_AI = to_odds(cum_z(zO_AI))
        odds_U_AI = to_odds(cum_z(zU_AI))
        nAI_vec   = np.arange(1, len(zO_AI) + 1)
        x_max     = max(x_max, len(zO_AI))

    # Final values
    print(f"Human  OBS   odds = {odds_O_H[-1]:.0f}:1")
    print(f"Human  UNOBS odds = {odds_U_H[-1]:.0f}:1")
    if zO_AI is not None:
        print(f"AI     OBS   odds = {odds_O_AI[-1]:.1f}:1")
        print(f"AI     UNOBS odds = {odds_U_AI[-1]:.1f}:1")

    # Shared y-axis limits across both panels
    all_odds = [odds_O_H, odds_U_H]
    if zO_AI is not None:
        all_odds += [odds_O_AI, odds_U_AI]
    max_odds = max(o.max() for o in all_odds)
    y_max    = 10 ** (np.ceil(np.log10(max_odds) + 0.1))
    y_min    = 0.5

    tick_vals = [v for v in [1, 10, 100, 1000, 10000, 100000] if v <= y_max]
    tick_lbls = ['1:1', '10:1', '100:1', '1,000:1', '10,000:1', '100,000:1']
    tick_lbls = tick_lbls[:len(tick_vals)]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor='white')
    fig.subplots_adjust(wspace=0.30)

    sensors = [
        ('Observed Sensor',   odds_O_H,
         odds_O_AI if zO_AI is not None else None),
        ('Unobserved Sensor', odds_U_H,
         odds_U_AI if zO_AI is not None else None),
    ]

    for ax, (label, oH, oAI) in zip(axes, sensors):
        ax.semilogy(nH_vec, oH, '-', color=col_H,  linewidth=2, label='Human')
        if oAI is not None:
            ax.semilogy(nAI_vec, oAI, '-', color=col_AI, linewidth=2, label='AI')
        ax.axhline(1, color='black', linewidth=0.8)
        ax.set_xlim(1, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_yticks(tick_vals)
        ax.set_yticklabels(tick_lbls)
        ax.set_xlabel('Sessions (chronological)', fontsize=13)
        ax.set_ylabel('Odds against chance', fontsize=13)
        ax.text(0.97, 0.96, label, transform=ax.transAxes,
                ha='right', va='top', fontsize=14, fontweight='bold')
        if label == 'Observed Sensor':
            ax.legend(loc='upper left', fontsize=11)
        ax.tick_params(labelsize=11)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    fig.suptitle('Odds Against Chance: 1/p from cumulative Stouffer Z',
                 fontsize=14, fontweight='bold')

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {save_path}")
    return fig


if __name__ == '__main__':
    import os
    from plot_cumulative_z import compute_session_z
    data_path = "."
    gates = list(range(1, 8))

    print("Computing human z-scores...")
    zO_H, zU_H = compute_session_z(data_path, 'human', gates, 1000)
    print(f"  {len(zO_H)} valid sessions\n")

    print("Computing AI z-scores...")
    zO_AI, zU_AI = compute_session_z(data_path, 'ai', gates, 1000)
    print(f"  {len(zO_AI)} valid sessions\n")

    plot_odds(zO_H, zU_H, zO_AI, zU_AI, save_path='odds_against_chance.png')
    plt.show()
