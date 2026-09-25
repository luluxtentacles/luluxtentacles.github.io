import numpy as np
from scipy.signal import detrend
from scipy.stats import ttest_rel, ttest_1samp, linregress

from load_arrays import load_arrays
from load_sessions import load_sessions
from map_section_to_columns import map_section_to_columns


# ---------------------------------------------------------------------------
# Configuration (matches preregistered analysis_12b_regression.m)
# ---------------------------------------------------------------------------
LAG_SECONDS     = 5
MIN_CORRECT     = 9
TOTAL_REQUIRED  = 10
N_PERM          = 5000
FS              = 2          # 2 Hz sampling rate
GROUP_SIZE      = 120        # samples per epoch pair (60 s intention + 60 s relax)
N_GROUPS        = 10         # epoch pairs per session
DETREND_SESSION = True


def run_regression_residual(
    data_path=".",
    source="human",
    gates=None,
    max_qualifying=None,
    lag_seconds=LAG_SECONDS,
    n_perm=N_PERM,
    seed=42,
):
    """
    Full regression-residual pipeline.

    For each qualifying session:
      1. Optionally detrend both sensor traces.
      2. Regress observed on unobserved: obs = b0 + b1*unobs + residual.
      3. Extract 10 intention / relax half-epoch pairs (after cognitive lag).

    Then runs three preregistered permutation tests on residuals and the
    same tests on the raw unobserved sensor.

    Returns a dict of results (slopes, p-values, ensemble curves).
    """
    rng = np.random.default_rng(seed)

    delay   = round(lag_seconds * FS)
    half_len = 60 - delay         # samples per half-epoch after lag

    # --- Load data ---
    A, B = load_arrays(data_path)
    sessions, good = load_sessions(
        data_path, source=source,
        min_correct=MIN_CORRECT, total_required=TOTAL_REQUIRED,
        gates=gates, max_qualifying=max_qualifying,
    )
    sections = sessions.loc[good, 'Section'].values

    # --- Epoch accumulation ---
    res_int, res_rel     = [], []   # regression residuals
    obs_int, obs_rel     = [], []   # raw observed
    unobs_int, unobs_rel = [], []   # raw unobserved

    n_drop_prefix = 0
    n_drop_missing = 0
    bins = {'1-1400': [0, 0], '1401-1999': [0, 0],
            '2000-3999': [0, 0], '4000+': [0, 0]}   # [kept, dropped]

    for section in sections:
        s = str(section)
        obs_col, unobs_col, _ = map_section_to_columns(s)
        raw_num = int(s[1:])

        if   raw_num >= 4000: bin_key = '4000+'
        elif raw_num >= 2000: bin_key = '2000-3999'
        elif raw_num >= 1401: bin_key = '1401-1999'
        else:                 bin_key = '1-1400'

        if obs_col is None:
            n_drop_prefix += 1
            bins[bin_key][1] += 1
            continue

        prefix = s[0].lower()
        try:
            if prefix == 'a':
                obs_v   = A[obs_col].values.astype(float)
                unobs_v = B[unobs_col].values.astype(float)
            else:
                obs_v   = B[obs_col].values.astype(float)
                unobs_v = A[unobs_col].values.astype(float)
        except KeyError:
            n_drop_missing += 1
            bins[bin_key][1] += 1
            continue

        bins[bin_key][0] += 1

        if DETREND_SESSION:
            obs_v   = detrend(obs_v)
            unobs_v = detrend(unobs_v)

        # Regress observed on unobserved (OLS)
        X = np.column_stack([np.ones(len(unobs_v)), unobs_v])
        coef, _, _, _ = np.linalg.lstsq(X, obs_v, rcond=None)
        resid_v = obs_v - X @ coef

        for g in range(N_GROUPS):
            st = g * GROUP_SIZE
            # Intention half: [st+delay : st+60]
            res_int.append(resid_v[st + delay : st + 60])
            res_rel.append(resid_v[st + 60 + delay : st + 120])
            obs_int.append(obs_v[st + delay : st + 60])
            obs_rel.append(obs_v[st + 60 + delay : st + 120])
            unobs_int.append(unobs_v[st + delay : st + 60])
            unobs_rel.append(unobs_v[st + 60 + delay : st + 120])

    res_int  = np.array(res_int);   res_rel  = np.array(res_rel)
    obs_int  = np.array(obs_int);   obs_rel  = np.array(obs_rel)
    unobs_int = np.array(unobs_int); unobs_rel = np.array(unobs_rel)

    n_blocks = len(res_int)
    x = np.arange(1, half_len + 1, dtype=float)

    # Attrition report
    n_kept  = sum(v[0] for v in bins.values())
    n_drop  = sum(v[1] for v in bins.values())
    print(f"\n--- Session attrition ---")
    print(f"  In: {len(sections)}   Kept: {n_kept}   Dropped: {n_drop}   "
          f"(blocks if all kept: {len(sections) * N_GROUPS})")
    print(f"  Drop reasons: bad prefix={n_drop_prefix}  missing column={n_drop_missing}")
    for k, (kept, dropped) in bins.items():
        if kept + dropped > 0:
            print(f"    {k:10s}: {kept:4d} kept / {dropped:4d} dropped")
    print(f"\n=== Regression Residual Slope Analysis ({n_blocks} blocks) ===\n")

    # --- Per-block slopes ---
    def block_slopes(mat):
        return np.array([np.polyfit(x, row, 1)[0] for row in mat])

    slope_ri = block_slopes(res_int);   slope_rr = block_slopes(res_rel)
    slope_oi = block_slopes(obs_int);   slope_or = block_slopes(obs_rel)
    slope_ui = block_slopes(unobs_int); slope_ur = block_slopes(unobs_rel)

    # Paired t-test and Cohen's d on residual Int-Rel difference
    res_d = slope_ri - slope_rr
    t_stat, p_ttest = ttest_1samp(res_d, 0)
    cohens_d_res = res_d.mean() / res_d.std(ddof=1)

    print("RESIDUAL (obs - b*unobs):")
    print(f"  Intention slope: mean={slope_ri.mean():.6f}, SD={slope_ri.std(ddof=1):.6f}")
    print(f"  Relax slope:     mean={slope_rr.mean():.6f}, SD={slope_rr.std(ddof=1):.6f}")
    print(f"  Int-Rel mean diff: {res_d.mean():.6f}, SD={res_d.std(ddof=1):.6f}")
    print(f"  t({n_blocks-1}) = {t_stat:.4f}, p (two-tailed) = {p_ttest:.6f}")
    print(f"  Cohen's d = {cohens_d_res:.4f}\n")

    obs_d = slope_oi - slope_or
    t_obs, p_obs = ttest_1samp(obs_d, 0)
    print("RAW OBSERVED (for comparison):")
    print(f"  Int-Rel mean diff: {obs_d.mean():.6f}, Cohen's d={obs_d.mean()/obs_d.std(ddof=1):.4f}, "
          f"t={t_obs:.4f}, p={p_obs:.6f}\n")

    # --- Ensemble mean curves ---
    m_ri = res_int.mean(axis=0);   m_rr = res_rel.mean(axis=0)
    m_oi = obs_int.mean(axis=0);   m_or = obs_rel.mean(axis=0)
    m_ui = unobs_int.mean(axis=0); m_ur = unobs_rel.mean(axis=0)

    s_ri = np.polyfit(x, m_ri, 1)[0]; s_rr = np.polyfit(x, m_rr, 1)[0]
    s_oi = np.polyfit(x, m_oi, 1)[0]; s_or = np.polyfit(x, m_or, 1)[0]
    s_ui = np.polyfit(x, m_ui, 1)[0]; s_ur = np.polyfit(x, m_ur, 1)[0]

    print("=== Ensemble mean curve slopes ===")
    print(f"  Residual   Int: {s_ri:.6f}   Rel: {s_rr:.6f}   Diff: {s_ri-s_rr:.6f}")
    print(f"  Raw Obs    Int: {s_oi:.6f}   Rel: {s_or:.6f}   Diff: {s_oi-s_or:.6f}")
    print(f"  Unobserved Int: {s_ui:.6f}   Rel: {s_ur:.6f}   Diff: {s_ui-s_ur:.6f}\n")

    # Parametric OLS p-values on ensemble curves (mirrors MATLAB regress() + tcdf)
    # Two-tailed from linregress, converted to one-tailed (slope < 0 is the
    # direction of interest for the factorial figure).
    def _param_p_one_tailed(curve):
        lr = linregress(x, curve)
        return lr.pvalue / 2 if lr.slope < 0 else 1 - lr.pvalue / 2

    pp_ri = _param_p_one_tailed(m_ri)
    pp_rr = _param_p_one_tailed(m_rr)
    pp_oi = _param_p_one_tailed(m_oi)
    pp_or = _param_p_one_tailed(m_or)
    pp_ui = _param_p_one_tailed(m_ui)
    pp_ur = _param_p_one_tailed(m_ur)

    print("=== Ensemble curve parametric OLS p-values (one-tailed, slope < 0) ===")
    print(f"  {'Curve':<20}  {'Slope':>10}  {'Param p':>10}")
    for lbl, slp, pp in [('Res Intention', s_ri, pp_ri), ('Res Relax', s_rr, pp_rr),
                          ('Obs Intention', s_oi, pp_oi), ('Obs Relax', s_or, pp_or),
                          ('Unobs Intention', s_ui, pp_ui), ('Unobs Relax', s_ur, pp_ur)]:
        print(f"  {lbl:<20}  {slp:>10.6f}  {pp:>10.5f}")
    print()

    # -----------------------------------------------------------------------
    # Permutation test 1: per-block Int/Rel label swap on residuals
    # -----------------------------------------------------------------------
    obs_diff_res = res_d.mean()
    null_block_res = np.empty(n_perm)
    for p in range(n_perm):
        swap = rng.random(n_blocks) > 0.5
        perm_ri = np.where(swap, slope_rr, slope_ri)
        perm_rr = np.where(swap, slope_ri, slope_rr)
        null_block_res[p] = (perm_ri - perm_rr).mean()
    p_block_res = (null_block_res <= obs_diff_res).mean()

    print(f"=== Permutation Tests ({n_perm} iterations) ===\n")
    print("RESIDUAL per-block Int-Rel label swap:")
    print(f"  Observed diff: {obs_diff_res:.6f}")
    print(f"  Null mean={null_block_res.mean():.6f}, SD={null_block_res.std():.6f}")
    print(f"  p (one-tailed, neg): {p_block_res:.4f}\n")

    # -----------------------------------------------------------------------
    # Permutation test 2: ensemble Int/Rel label swap on residuals
    # -----------------------------------------------------------------------
    obs_ens_res = s_ri - s_rr
    null_ens_res = np.empty(n_perm)
    for p in range(n_perm):
        swap = rng.random(n_blocks) > 0.5
        perm_int = np.where(swap[:, None], res_rel, res_int)
        perm_rel = np.where(swap[:, None], res_int, res_rel)
        pm_ri = perm_int.mean(axis=0); pm_rr = perm_rel.mean(axis=0)
        null_ens_res[p] = np.polyfit(x, pm_ri, 1)[0] - np.polyfit(x, pm_rr, 1)[0]
    p_ens_res = (null_ens_res <= obs_ens_res).mean()

    print("RESIDUAL ensemble Int-Rel label swap:")
    print(f"  Observed diff: {obs_ens_res:.6f}")
    print(f"  Null mean={null_ens_res.mean():.6f}, SD={null_ens_res.std():.6f}")
    print(f"  p (one-tailed, neg): {p_ens_res:.4f}\n")

    # -----------------------------------------------------------------------
    # Permutation test 3: slope != 0 (time-order shuffle on ensemble curve)
    # -----------------------------------------------------------------------
    null_slope_ri = np.empty(n_perm); null_slope_rr = np.empty(n_perm)
    for p in range(n_perm):
        idx = rng.permutation(half_len)
        null_slope_ri[p] = np.polyfit(x, m_ri[idx], 1)[0]
        null_slope_rr[p] = np.polyfit(x, m_rr[idx], 1)[0]
    p_slope_ri = (null_slope_ri <= s_ri).mean()
    p_slope_rr = (null_slope_rr <= s_rr).mean()

    print("RESIDUAL slope != 0 (time-shuffle):")
    print(f"  {'Curve':<18}  {'Slope':>10}  {'Null SD':>10}  {'p (1-tail)':>12}")
    print(f"  {'Res Intention':<18}  {s_ri:>10.6f}  {null_slope_ri.std():>10.6f}  {p_slope_ri:>12.4f}")
    print(f"  {'Res Relax':<18}  {s_rr:>10.6f}  {null_slope_rr.std():>10.6f}  {p_slope_rr:>12.4f}\n")

    # -----------------------------------------------------------------------
    # Durbin-Watson autocorrelation check on residual epochs
    # -----------------------------------------------------------------------
    def dw(v):
        return np.sum(np.diff(v)**2) / np.sum(v**2)

    dw_ri = np.array([dw(row) for row in res_int])
    dw_rr = np.array([dw(row) for row in res_rel])

    print("=== Durbin-Watson Autocorrelation Check ===")
    print(f"  {'Epoch':<20}  {'Mean DW':>8}  {'SD DW':>8}  {'Frac ~2':>8}")
    for label, dw_arr in [('Res Intention', dw_ri), ('Res Relax', dw_rr)]:
        frac = np.mean(np.abs(dw_arr - 2) < 0.5)
        print(f"  {label:<20}  {dw_arr.mean():>8.4f}  {dw_arr.std():>8.4f}  {frac:>8.4f}")
    print(f"\n  Ensemble curve DW:")
    print(f"    Res Intention:   {dw(m_ri):.4f}")
    print(f"    Res Relax:       {dw(m_rr):.4f}")
    print(f"    Unobs Intention: {dw(m_ui):.4f}")
    print(f"    Unobs Relax:     {dw(m_ur):.4f}\n")

    # -----------------------------------------------------------------------
    # UNOBSERVED SENSOR (Prediction 2)
    # -----------------------------------------------------------------------
    print("========== UNOBSERVED SENSOR (Prediction 2) ==========")
    print("Expected: nonsignificant one-tailed Int-Rel slope difference\n")

    unobs_d = slope_ui - slope_ur
    t_u, p_u = ttest_1samp(unobs_d, 0)
    cohens_d_unobs = unobs_d.mean() / unobs_d.std(ddof=1)
    print(f"UNOBSERVED (raw):")
    print(f"  Intention slope: mean={slope_ui.mean():.6f}, SD={slope_ui.std(ddof=1):.6f}")
    print(f"  Relax slope:     mean={slope_ur.mean():.6f}, SD={slope_ur.std(ddof=1):.6f}")
    print(f"  Int-Rel mean diff: {unobs_d.mean():.6f}, SD={unobs_d.std(ddof=1):.6f}")
    print(f"  t({n_blocks-1}) = {t_u:.4f}, p (two-tailed) = {p_u:.6f}")
    print(f"  Cohen's d = {cohens_d_unobs:.4f}\n")

    # Permutation: per-block label swap
    obs_diff_unobs = unobs_d.mean()
    null_block_unobs = np.empty(n_perm)
    for p in range(n_perm):
        swap = rng.random(n_blocks) > 0.5
        pu = np.where(swap, slope_ur, slope_ui)
        pr = np.where(swap, slope_ui, slope_ur)
        null_block_unobs[p] = (pu - pr).mean()
    p_block_unobs = (null_block_unobs <= obs_diff_unobs).mean()

    print("UNOBSERVED per-block Int-Rel label swap:")
    print(f"  Observed diff: {obs_diff_unobs:.6f}")
    print(f"  Null mean={null_block_unobs.mean():.6f}, SD={null_block_unobs.std():.6f}")
    print(f"  p (one-tailed, neg): {p_block_unobs:.4f}\n")

    # Permutation: ensemble label swap
    obs_ens_unobs = s_ui - s_ur
    null_ens_unobs = np.empty(n_perm)
    for p in range(n_perm):
        swap = rng.random(n_blocks) > 0.5
        pu_int = np.where(swap[:, None], unobs_rel, unobs_int)
        pu_rel = np.where(swap[:, None], unobs_int, unobs_rel)
        pm_ui = pu_int.mean(axis=0); pm_ur = pu_rel.mean(axis=0)
        null_ens_unobs[p] = np.polyfit(x, pm_ui, 1)[0] - np.polyfit(x, pm_ur, 1)[0]
    p_ens_unobs = (null_ens_unobs <= obs_ens_unobs).mean()

    print("UNOBSERVED ensemble Int-Rel label swap:")
    print(f"  Observed diff: {obs_ens_unobs:.6f}")
    print(f"  Null mean={null_ens_unobs.mean():.6f}, SD={null_ens_unobs.std():.6f}")
    print(f"  p (one-tailed, neg): {p_ens_unobs:.4f}\n")

    # Permutation: slope != 0 (time shuffle)
    null_slope_ui = np.empty(n_perm); null_slope_ur = np.empty(n_perm)
    for p in range(n_perm):
        idx = rng.permutation(half_len)
        null_slope_ui[p] = np.polyfit(x, m_ui[idx], 1)[0]
        null_slope_ur[p] = np.polyfit(x, m_ur[idx], 1)[0]
    p_slope_ui = (null_slope_ui <= s_ui).mean()
    p_slope_ur = (null_slope_ur <= s_ur).mean()

    print("UNOBSERVED slope != 0 (time-shuffle):")
    print(f"  {'Curve':<18}  {'Slope':>10}  {'Null SD':>10}  {'p (1-tail)':>12}")
    print(f"  {'Unobs Intention':<18}  {s_ui:>10.6f}  {null_slope_ui.std():>10.6f}  {p_slope_ui:>12.4f}")
    print(f"  {'Unobs Relax':<18}  {s_ur:>10.6f}  {null_slope_ur.std():>10.6f}  {p_slope_ur:>12.4f}\n")

    return {
        # Epoch matrices (for plotting)
        'res_int': res_int, 'res_rel': res_rel,
        'obs_int': obs_int, 'obs_rel': obs_rel,
        'unobs_int': unobs_int, 'unobs_rel': unobs_rel,
        # Ensemble mean curves
        'm_ri': m_ri, 'm_rr': m_rr,
        'm_oi': m_oi, 'm_or': m_or,
        'm_ui': m_ui, 'm_ur': m_ur,
        # Ensemble slopes (for trend lines in plots)
        's_ri': s_ri, 's_rr': s_rr,
        's_oi': s_oi, 's_or': s_or,
        's_ui': s_ui, 's_ur': s_ur,
        # Per-block slopes
        'slope_ri': slope_ri, 'slope_rr': slope_rr,
        'slope_ui': slope_ui, 'slope_ur': slope_ur,
        # Null distributions (for plots)
        'null_slope_ri': null_slope_ri, 'null_slope_rr': null_slope_rr,
        'null_block_res': null_block_res,
        'null_slope_ui': null_slope_ui, 'null_slope_ur': null_slope_ur,
        'null_block_unobs': null_block_unobs,
        # Preregistered p-values (time-shuffle permutation)
        'p_block_res': p_block_res, 'p_ens_res': p_ens_res,
        'p_slope_ri': p_slope_ri,   'p_slope_rr': p_slope_rr,
        'p_block_unobs': p_block_unobs, 'p_ens_unobs': p_ens_unobs,
        'p_slope_ui': p_slope_ui,   'p_slope_ur': p_slope_ur,
        # Parametric OLS p-values on ensemble curves (one-tailed, for factorial figure)
        'pp_ri': pp_ri, 'pp_rr': pp_rr,
        'pp_oi': pp_oi, 'pp_or': pp_or,
        'pp_ui': pp_ui, 'pp_ur': pp_ur,
        # Descriptives
        'n_blocks': n_blocks, 'cohens_d_res': cohens_d_res,
        'cohens_d_unobs': cohens_d_unobs, 'x': x,
    }


if __name__ == "__main__":
    import os
    data_path = "."
    results = run_regression_residual(
        data_path=data_path,
        source="human",
        gates=list(range(1, 8)),
    )

    # Sanity checks
    assert results['n_blocks'] > 0,        "No blocks extracted"
    assert results['res_int'].shape[1] == 60 - round(LAG_SECONDS * FS), \
        f"Unexpected half-epoch length: {results['res_int'].shape[1]}"
    assert 0 <= results['p_block_res'] <= 1,   "p_block_res out of range"
    assert 0 <= results['p_block_unobs'] <= 1, "p_block_unobs out of range"
    print("All sanity checks passed.")
