import pandas as pd
import numpy as np


def load_arrays(path="."):
    """
    Load sensor time-series arrays from the three CSV files.

    Returns two DataFrames (A, B) each with shape (1200, N_segments),
    where column names are the segment identifiers (a1, a2, … / b1, b2, …).
    Mirrors the MATLAB load_arrays.m function.
    """
    A = pd.read_csv(f"{path}/datatestA.csv")
    B = pd.read_csv(f"{path}/datatestB.csv")

    try:
        T = pd.read_csv(f"{path}/arrays_4000.csv")
    except FileNotFoundError:
        return A, B

    a_cols = [c for c in T.columns if c.startswith('a')]
    b_cols = [c for c in T.columns if c.startswith('b')]

    A = _append_cols(A, T[a_cols])
    B = _append_cols(B, T[b_cols])

    return A, B


def _append_cols(base, new):
    """Horizontally concatenate two DataFrames, padding the shorter with NaN."""
    n_base, n_new = len(base), len(new)
    if n_new < n_base:
        pad = pd.DataFrame(np.nan, index=range(n_new, n_base), columns=new.columns)
        new = pd.concat([new, pad])
    elif n_new > n_base:
        pad = pd.DataFrame(np.nan, index=range(n_base, n_new), columns=base.columns)
        base = pd.concat([base, pad])
    return pd.concat([base.reset_index(drop=True), new.reset_index(drop=True)], axis=1)


if __name__ == "__main__":
    import os
    data_path = "."

    A, B = load_arrays(data_path)

    print(f"Sensor A: {A.shape[1]} segments x {A.shape[0]} samples")
    print(f"Sensor B: {B.shape[1]} segments x {B.shape[0]} samples")
    assert A.shape == B.shape, "A and B shape mismatch"

    # Spot-check: columns should all be numeric, no all-NaN columns in the main block
    assert A.shape[0] == 1200, f"Expected 1200 rows, got {A.shape[0]}"
    assert not A.iloc[:, 0].isna().all(), "First column of A is all NaN"
    assert not B.iloc[:, 0].isna().all(), "First column of B is all NaN"

    # Check column naming convention
    assert all(c.startswith('a') for c in A.columns), "Unexpected column name in A"
    assert all(c.startswith('b') for c in B.columns), "Unexpected column name in B"

    print("All checks passed.")
