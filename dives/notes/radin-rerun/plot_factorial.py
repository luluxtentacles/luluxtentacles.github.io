import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LogNorm
import matplotlib.colorbar as mcolorbar
import matplotlib.cm as mcm


def _p_color(p):
    """
    Map a one-tailed p-value to an RGB face color.
    >= 0.05 : light gray gradient (null region)
     < 0.05 : pale-red -> deep-red gradient (significant region)
    Matches the MATLAB pColor() helper in plot_factorial_2x2x2.m.
    """
    p = max(p, 1e-5)
    if p >= 0.05:
        t = (np.log10(p) - np.log10(0.05)) / (np.log10(1.0) - np.log10(0.05))
        return np.array([0.92, 0.90, 0.90]) * (1 - t) + np.array([0.96, 0.96, 0.96]) * t
    else:
        t = (np.log10(0.05) - np.log10(p)) / (np.log10(0.05) - np.log10(1e-4))
        t = np.clip(t, 0, 1)
        pale = np.array([0.99, 0.84, 0.81])
        deep = np.array([0.55, 0.05, 0.05])
        return pale * (1 - t) + deep * t


def _text_color(rgb):
    luma = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return 'white' if luma < 0.55 else 'black'


def _stars(p):
    if p < 0.001: return '***'
    if p < 0.01:  return '**'
    if p < 0.05:  return '*'
    return ''


def plot_factorial(res_human, res_ai, save_path=None):
    """
    2x2x2 factorial summary figure: agent x sensor x epoch.

    Each cell shows the preregistered one-tailed permutation p-value
    (ensemble slope < 0, time-shuffle test) and the ensemble slope.

    Cell layout (left->right, top->bottom):
      [H-Obs-Int] [H-Obs-Rel] [AI-Obs-Int] [AI-Obs-Rel]
      [H-Un-Int]  [H-Un-Rel]  [AI-Un-Int]  [AI-Un-Rel]

    Only Human x Observed x Intention is predicted significant.
    """
    # 8 cells: (sensor, epoch, agent) -> (p, slope)
    # sensor: 0=Observed (raw), 1=Unobserved (raw)
    # epoch:  0=Intention, 1=Relax
    # agent:  0=Human, 1=AI
    # Observed row uses raw observed slopes (illustrative, no regression).
    # Unobserved row uses raw unobserved slopes.
    # Parametric OLS p-values (one-tailed, slope < 0) to match MATLAB figure.
    cells = {
        (0, 0, 0): (res_human['pp_oi'], res_human['s_oi']),
        (0, 1, 0): (res_human['pp_or'], res_human['s_or']),
        (0, 0, 1): (res_ai['pp_oi'],    res_ai['s_oi']),
        (0, 1, 1): (res_ai['pp_or'],    res_ai['s_or']),
        (1, 0, 0): (res_human['pp_ui'], res_human['s_ui']),
        (1, 1, 0): (res_human['pp_ur'], res_human['s_ur']),
        (1, 0, 1): (res_ai['pp_ui'],    res_ai['s_ui']),
        (1, 1, 1): (res_ai['pp_ur'],    res_ai['s_ur']),
    }

    n_human = res_human['n_blocks'] // 10
    n_ai    = res_ai['n_blocks'] // 10

    fig = plt.figure(figsize=(13, 7.5), facecolor='white')
    ax  = fig.add_axes([0.09, 0.10, 0.80, 0.64])
    ax.set_xlim(0, 4); ax.set_ylim(0, 2); ax.axis('off')

    # Drawing order: top row = Observed (y0=1), bottom = Unobserved (y0=0)
    # columns 0-3: H-Int, H-Rel, AI-Int, AI-Rel
    col_order  = [(0,0,0), (0,1,0), (0,0,1), (0,1,1),
                  (1,0,0), (1,1,0), (1,0,1), (1,1,1)]
    grid_pos   = [(0,1), (1,1), (2,1), (3,1),
                  (0,0), (1,0), (2,0), (3,0)]   # (col_idx, row_idx y0)

    for key, (x0, y0) in zip(col_order, grid_pos):
        p, slope = cells[key]
        fc  = _p_color(p)
        tc  = _text_color(fc)
        st  = _stars(p)

        rect = mpatches.FancyBboxPatch(
            (x0, y0), 1, 1,
            boxstyle="square,pad=0",
            facecolor=fc,
            edgecolor=(0.55, 0.55, 0.55), linewidth=0.5,
            transform=ax.transData, clip_on=False
        )
        ax.add_patch(rect)

        p_str = f'p = {p:.5f}' if p < 0.001 else f'p = {p:.3f}'
        ax.text(x0 + 0.5, y0 + 0.62, p_str,
                ha='center', va='center', fontsize=14,
                fontweight='bold', color=tc)
        ax.text(x0 + 0.5, y0 + 0.32, f'slope = {slope:+.5f}',
                ha='center', va='center', fontsize=10, color=tc)
        if st:
            ax.text(x0 + 0.93, y0 + 0.93, st,
                    ha='right', va='top', fontsize=16,
                    fontweight='bold', color=tc)

    # Green border on predicted cell: Human x Observed x Intention (col=0, y0=1)
    pred = mpatches.FancyBboxPatch(
        (0, 1), 1, 1,
        boxstyle="square,pad=0",
        facecolor='none',
        edgecolor=(0.10, 0.55, 0.15), linewidth=4,
        transform=ax.transData, clip_on=False, zorder=5
    )
    ax.add_patch(pred)
    ax.text(0.05, 1.05, 'predicted significant',
            ha='left', va='bottom', fontsize=9,
            fontstyle='italic', fontweight='bold',
            color=(0.10, 0.55, 0.15), zorder=6)

    # Heavy separator between Human and AI blocks
    ax.plot([2, 2], [0, 2], 'k-', linewidth=2.5)

    # Column labels (epoch) below grid
    for i, lbl in enumerate(['Intention', 'Relax', 'Intention', 'Relax']):
        ax.text(i + 0.5, -0.09, lbl, ha='center', va='top', fontsize=12)

    # Block headers above grid
    ax.text(1.0, 2.18, f'HUMAN  (n = {n_human} sessions)',
            ha='center', va='bottom', fontsize=15, fontweight='bold')
    ax.text(3.0, 2.18, f'AI  (n = {n_ai} sessions)',
            ha='center', va='bottom', fontsize=15, fontweight='bold')
    ax.plot([0.05, 1.95], [2.10, 2.10], 'k-', linewidth=1.5)
    ax.plot([2.05, 3.95], [2.10, 2.10], 'k-', linewidth=1.5)

    # Row labels (rotated, left side)
    # ax spans figure y=[0.10, 0.74]; grid data y=[0, 2]
    # Observed row center (data y=1.5) -> fig y = 0.10 + 0.64*0.75 = 0.58
    # Unobserved row center (data y=0.5) -> fig y = 0.10 + 0.64*0.25 = 0.26
    fig.text(0.045, 0.58, 'OBSERVED sensor',
             ha='center', va='center', fontsize=12, fontweight='bold',
             rotation=90)
    fig.text(0.045, 0.26, 'UNOBSERVED sensor',
             ha='center', va='center', fontsize=12, fontweight='bold',
             rotation=90)

    # Title and subtitle
    fig.text(0.5, 0.93,
             '2 × 2 × 2 factorial: agent × sensor × epoch',
             ha='center', va='center', fontsize=16, fontweight='bold')
    fig.text(0.5, 0.88,
             'cell = one-tailed p-value (ensemble slope < 0); raw sensor slopes, parametric OLS',
             ha='center', va='center', fontsize=11, color=(0.3, 0.3, 0.3))

    # --- Colorbar (right side) ---
    cb_ax = fig.add_axes([0.905, 0.10, 0.018, 0.64])
    n_grad = 256
    p_grad = np.logspace(0, -5, n_grad)   # p from 1 to 1e-5, top to bottom
    rgb_grad = np.array([_p_color(p) for p in p_grad])
    cb_img = rgb_grad[::-1].reshape(n_grad, 1, 3)  # flip: small p at bottom
    cb_ax.imshow(cb_img, aspect='auto', extent=[0, 1, 0, 1], origin='lower')
    cb_ax.set_xlim(0, 1); cb_ax.set_ylim(0, 1)
    cb_ax.set_xticks([]); cb_ax.set_yticks([])

    # Tick marks on colorbar
    tick_ps = [1.0, 0.5, 0.1, 0.05, 0.01, 0.001, 1e-4]
    for tp in tick_ps:
        ypos = (np.log10(max(tp, 1e-5)) - np.log10(1e-5)) / (np.log10(1.0) - np.log10(1e-5))
        cb_ax.plot([1, 1.3], [ypos, ypos], 'k-', linewidth=0.8,
                   transform=cb_ax.transData, clip_on=False)
        lbl = f'{tp:.0e}' if tp < 0.001 else f'{tp:g}'
        cb_ax.text(1.5, ypos, lbl, fontsize=9, va='center',
                   transform=cb_ax.transData, clip_on=False)

    cb_ax.text(0.5, 1.08, 'p-value', ha='center', fontsize=10,
               fontweight='bold', transform=cb_ax.transAxes)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {save_path}")
    return fig


if __name__ == "__main__":
    import os
    from regression_residual import run_regression_residual

    data_path = "."

    print("Running human analysis (cap: 1000)...")
    res_h = run_regression_residual(
        data_path, source="human",
        gates=list(range(1, 8)),
        max_qualifying=1000,
    )

    print("\nRunning AI analysis (cap: 1000)...")
    res_ai = run_regression_residual(
        data_path, source="ai",
        gates=list(range(1, 8)),
        max_qualifying=1000,
    )

    plot_factorial(res_h, res_ai, save_path="factorial_2x2x2.png")
    print("Done.")
    plt.show()
