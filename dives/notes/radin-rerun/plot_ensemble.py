import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

RED  = (0.80, 0.20, 0.20)
BLUE = (0.20, 0.20, 0.80)
GRN  = (0.25, 0.55, 0.30)
PUR  = (0.50, 0.20, 0.50)


def _trend_line(x, slope, curve):
    """Return y-values of the least-squares line through curve."""
    intercept = np.polyfit(x, curve, 1)[1]
    return slope * x + intercept


def plot_observed(results, label="Human", save_path=None):
    """
    2x2 figure for the observed/residual sensor (Prediction 1).

    Panels:
      Top-left  : Residual ensemble curves + trend lines
      Top-right : Raw observed ensemble curves + trend lines
      Bot-left  : Time-shuffle null vs observed slope (residuals)
      Bot-right : Per-block Int-Rel label-swap null vs observed diff
    """
    x = results['x']
    t = x * 0.5   # convert samples to seconds (2 Hz)

    m_ri, m_rr = results['m_ri'], results['m_rr']
    m_oi, m_or = results['m_oi'], results['m_or']
    s_ri, s_rr = results['s_ri'], results['s_rr']
    s_oi, s_or = results['s_oi'], results['s_or']

    null_slope_ri  = results['null_slope_ri']
    null_slope_rr  = results['null_slope_rr']
    null_block_res = results['null_block_res']
    obs_diff       = results['slope_ri'].mean() - results['slope_rr'].mean()

    p_ri  = results['p_slope_ri']
    p_rr  = results['p_slope_rr']
    p_blk = results['p_block_res']

    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    fig.suptitle(f"Residual Regression Analysis — {label}", fontsize=14, fontweight='bold')

    # --- Top left: Residual ensemble ---
    ax = axes[0, 0]
    ax.plot(t, m_ri, color=RED,  lw=2,   label='Intention')
    ax.plot(t, m_rr, color=BLUE, lw=2,   label='Relax')
    ax.plot(t, _trend_line(x, s_ri, m_ri), '--', color=RED,  lw=1.5, label='Int trend')
    ax.plot(t, _trend_line(x, s_rr, m_rr), '--', color=BLUE, lw=1.5, label='Rel trend')
    ax.axhline(0, color='gray', lw=0.8, ls=':')
    ax.set_title('Residual Signal (obs - b*unobs)', fontsize=12)
    ax.set_xlabel('Time (s)'); ax.set_ylabel('Ensemble Mean')
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # --- Top right: Raw observed ---
    ax = axes[0, 1]
    ax.plot(t, m_oi, color=RED,  lw=2,   label='Intention')
    ax.plot(t, m_or, color=BLUE, lw=2,   label='Relax')
    ax.plot(t, _trend_line(x, s_oi, m_oi), '--', color=RED,  lw=1.5, label='Int trend')
    ax.plot(t, _trend_line(x, s_or, m_or), '--', color=BLUE, lw=1.5, label='Rel trend')
    ax.axhline(0, color='gray', lw=0.8, ls=':')
    ax.set_title('Raw Observed (reference)', fontsize=12)
    ax.set_xlabel('Time (s)'); ax.set_ylabel('Ensemble Mean')
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # --- Bottom left: Time-shuffle null vs observed slope ---
    ax = axes[1, 0]
    ax.hist(null_slope_ri, bins=50, color=RED,  alpha=0.4, label='Int null', edgecolor='none')
    ax.hist(null_slope_rr, bins=50, color=BLUE, alpha=0.4, label='Rel null', edgecolor='none')
    ax.axvline(s_ri, color=RED,  lw=2.5, label=f'Int slope (p={p_ri:.4f})')
    ax.axvline(s_rr, color=BLUE, lw=2.5, label=f'Rel slope (p={p_rr:.4f})')
    ax.set_title('Residual slope != 0 (time-shuffle null)', fontsize=12)
    ax.set_xlabel('Slope'); ax.set_ylabel('Count')
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # --- Bottom right: Int-Rel label-swap null ---
    ax = axes[1, 1]
    ax.hist(null_block_res, bins=50, color=PUR, alpha=0.5, label='Null dist', edgecolor='none')
    ax.axvline(obs_diff, color='black', lw=2.5, label=f'Observed diff (p={p_blk:.4f})')
    ax.set_title('Int-Rel slope difference (label-swap null)', fontsize=12)
    ax.set_xlabel('Slope Difference'); ax.set_ylabel('Count')
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")
    return fig


def plot_unobserved(results, label="Human", save_path=None):
    """
    2x2 figure for the unobserved sensor (Prediction 2 / control).

    Panels:
      Top-left  : Unobserved ensemble curves + trend lines
      Top-right : Residual Int vs Unobserved Int (magnitude comparison)
      Bot-left  : Time-shuffle null vs observed slope (unobserved)
      Bot-right : Per-block Int-Rel label-swap null vs observed diff (unobserved)
    """
    x = results['x']
    t = x * 0.5

    m_ri = results['m_ri']
    m_ui, m_ur = results['m_ui'], results['m_ur']
    s_ri = results['s_ri']
    s_ui, s_ur = results['s_ui'], results['s_ur']

    null_slope_ui    = results['null_slope_ui']
    null_slope_ur    = results['null_slope_ur']
    null_block_unobs = results['null_block_unobs']
    obs_diff_unobs   = results['slope_ui'].mean() - results['slope_ur'].mean()

    p_ui  = results['p_slope_ui']
    p_ur  = results['p_slope_ur']
    p_blk = results['p_block_unobs']

    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    fig.suptitle(f"Unobserved Sensor Control — {label}", fontsize=14, fontweight='bold')

    # --- Top left: Unobserved ensemble ---
    ax = axes[0, 0]
    ax.plot(t, m_ui, color=RED,  lw=2,   label='Intention')
    ax.plot(t, m_ur, color=BLUE, lw=2,   label='Relax')
    ax.plot(t, _trend_line(x, s_ui, m_ui), '--', color=RED,  lw=1.5, label='Int trend')
    ax.plot(t, _trend_line(x, s_ur, m_ur), '--', color=BLUE, lw=1.5, label='Rel trend')
    ax.axhline(0, color='gray', lw=0.8, ls=':')
    ax.set_title('Unobserved Sensor (no feedback)', fontsize=12)
    ax.set_xlabel('Time (s)'); ax.set_ylabel('Ensemble Mean')
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # --- Top right: Residual Int vs Unobserved Int ---
    ax = axes[0, 1]
    ax.plot(t, m_ri, color=RED, lw=2,   label='Residual Int (test)')
    ax.plot(t, m_ui, color=GRN, lw=2,   label='Unobserved Int (control)')
    ax.plot(t, _trend_line(x, s_ri, m_ri), '--', color=RED, lw=1.5)
    ax.plot(t, _trend_line(x, s_ui, m_ui), '--', color=GRN, lw=1.5)
    ax.axhline(0, color='gray', lw=0.8, ls=':')
    ax.set_title('Intention: Residual vs Unobserved', fontsize=12)
    ax.set_xlabel('Time (s)'); ax.set_ylabel('Ensemble Mean')
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    # --- Bottom left: Time-shuffle null ---
    ax = axes[1, 0]
    ax.hist(null_slope_ui, bins=50, color=RED,  alpha=0.4, label='Int null', edgecolor='none')
    ax.hist(null_slope_ur, bins=50, color=BLUE, alpha=0.4, label='Rel null', edgecolor='none')
    ax.axvline(s_ui, color=RED,  lw=2.5, label=f'Int slope (p={p_ui:.4f})')
    ax.axvline(s_ur, color=BLUE, lw=2.5, label=f'Rel slope (p={p_ur:.4f})')
    ax.set_title('Unobserved slope != 0 (time-shuffle null)', fontsize=12)
    ax.set_xlabel('Slope'); ax.set_ylabel('Count')
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # --- Bottom right: Int-Rel label-swap null ---
    ax = axes[1, 1]
    ax.hist(null_block_unobs, bins=50, color=PUR, alpha=0.5, label='Null dist', edgecolor='none')
    ax.axvline(obs_diff_unobs, color='black', lw=2.5, label=f'Observed diff (p={p_blk:.4f})')
    ax.set_title('Unobserved Int-Rel slope difference (label-swap null)', fontsize=12)
    ax.set_xlabel('Slope Difference'); ax.set_ylabel('Count')
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")
    return fig


if __name__ == "__main__":
    import os
    from regression_residual import run_regression_residual

    data_path = "."

    print("Running human analysis...")
    res_h = run_regression_residual(data_path, source="human", gates=list(range(1, 8)))
    plot_observed(res_h,   label="Human", save_path="human_observed.png")
    plot_unobserved(res_h, label="Human", save_path="human_unobserved.png")

    print("\nRunning AI analysis (cap=500)...")
    res_ai = run_regression_residual(data_path, source="ai", gates=list(range(1, 8)), max_qualifying=500)
    plot_observed(res_ai,   label="AI (N=500)", save_path="ai_observed.png")
    plot_unobserved(res_ai, label="AI (N=500)", save_path="ai_unobserved.png")

    print("\nAll plots saved.")
    plt.show()
