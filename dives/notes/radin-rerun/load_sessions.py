import pandas as pd
import numpy as np


def load_sessions(
    path=".",
    source="human",           # "human" or "ai"
    min_correct=9,
    total_required=10,
    gates=None,               # list of gate numbers, or None for all
    max_qualifying=None,      # preregistered cap: 1000 human, 500 AI; None = all
):
    """
    Load and filter a sessions CSV, applying the preregistered inclusion criteria.

    Parameters
    ----------
    path : str
        Directory containing the CSV files.
    source : str
        'human' -> sessions_out.csv; 'ai' -> sessions_out_AI.csv
    min_correct : int
        Minimum Yes count (preregistered: 9).
    total_required : int
        Required Total epochs (preregistered: 10).
    gates : list[int] or None
        Restrict to these gate numbers. None = all gates.
    max_qualifying : int or None
        Cap to the first N qualifying sessions in chronological order
        (by SessionDate, stable sort — matches MATLAB analysis_12b_regression.m;
        same-day ties are broken by CSV row order, which is the MATLAB file order).
        Preregistered values: 1000 (human), 500 (AI). None = no cap.

    Returns
    -------
    sessions : pd.DataFrame
        Full sessions table (unfiltered).
    good : pd.Series[bool]
        Boolean mask of qualifying rows.
    """
    filename = "sessions_out.csv" if source == "human" else "sessions_out_AI.csv"
    sessions = pd.read_csv(f"{path}/{filename}")

    good = (sessions['Yes'] >= min_correct) & (sessions['Total'] == total_required)

    if gates is not None:
        good = good & sessions['Gate'].isin(gates)

    if max_qualifying is not None:
        q_idx = np.where(good)[0]
        n_avail = len(q_idx)
        n_keep = min(max_qualifying, n_avail)

        if 'SessionDate' in sessions.columns:
            # Sort by date only, stable — matches MATLAB analysis_12b_regression.m
            # which sorts by SessionDate with a stable sort (same-day ties resolved
            # by original CSV row order, identical to the MATLAB-generated file).
            dates = pd.to_datetime(sessions['SessionDate'], errors='coerce')
            order = np.argsort(dates.iloc[q_idx].values, kind='stable')
            q_idx_sorted = q_idx[order]
            order_src = 'SessionDate (date only, stable — matches MATLAB sort)'
        else:
            q_idx_sorted = q_idx
            order_src = 'CSV row order (no date column)'

        keep_mask = np.zeros(len(sessions), dtype=bool)
        keep_mask[q_idx_sorted[:n_keep]] = True
        good = good & keep_mask

        cap_reached = n_avail >= max_qualifying
        print(f"Session cap: keeping first {n_keep} of {n_avail} qualifying sessions "
              f"[order: {order_src}]")
        if cap_reached:
            print(f"  Cap of {max_qualifying} reached.")
        else:
            print(f"  Cap of {max_qualifying} not yet reached; using all available.")

    n_qual = good.sum()
    print(f"Qualifying sessions ({source}): {n_qual}")

    return sessions, good


if __name__ == "__main__":
    import os
    data_path = "."

    # --- Human sessions ---
    print("=== Human ===")
    sessions_h, good_h = load_sessions(data_path, source="human", gates=list(range(1, 8)))
    assert good_h.sum() > 0, "No qualifying human sessions"
    assert sessions_h.loc[good_h, 'Yes'].min() >= 9,    "min_correct filter failed"
    assert sessions_h.loc[good_h, 'Total'].max() == 10,  "total_required filter failed"

    # --- AI sessions ---
    print("\n=== AI ===")
    sessions_ai, good_ai = load_sessions(data_path, source="ai", gates=list(range(1, 8)))
    assert good_ai.sum() > 0, "No qualifying AI sessions"

    # --- Cap test ---
    print("\n=== Human (cap=100) ===")
    _, good_cap = load_sessions(data_path, source="human", max_qualifying=100)
    assert good_cap.sum() == 100, f"Cap failed: got {good_cap.sum()}"

    print("\nAll checks passed.")
