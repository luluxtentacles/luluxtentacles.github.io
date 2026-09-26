# Independent re-analysis of Radin & Cline (Physics Essays 2026, "Noetic Adventure")
# MY OWN implementation - imports none of their code. Raw CSVs in, preregistered
# protocol applied (lag 5s @ 2Hz, minCorrect 9/10, gates 1-7, first 1000 qualifying
# sessions by date, stable sort), and three questions their paper does not answer:
#   Q1  do the eight Table 2 cells reproduce from raw data under my own code?
#   Q2  does the effect follow the SHOWN sensor, or just the session-pair?
#       (prefix-permutation null: randomly re-choose which of the pair is 'observed')
#   Q3  is the human/AI contrast a materials story? every segment in the dataset,
#       played or not, gets the same Int-vs-Rel block test, binned by series family.
import numpy as np
import pandas as pd
from scipy.signal import detrend
from scipy.stats import linregress, ttest_1samp

LAG = 10                       # 5 s lag at 2 Hz
HALF = 60 - LAG                # 50 samples per half-epoch
K, SEED = 1000, 2026

TABLE2 = {
    ("human", "obs", "intention"): (-0.000425, 0.00007),
    ("human", "obs", "relax"):     (+0.000109, 0.851),
    ("human", "uno", "intention"): (-0.000123, 0.074),
    ("human", "uno", "relax"):     (+0.000095, 0.832),
    ("ai",    "obs", "intention"): (-0.000021, 0.430),
    ("ai",    "obs", "relax"):     (-0.000151, 0.098),
    ("ai",    "uno", "intention"): (-0.000040, 0.325),
    ("ai",    "uno", "relax"):     (-0.000064, 0.287),
}

print("loading segments ...")
baseA = pd.read_csv("datatestA.csv"); baseB = pd.read_csv("datatestB.csv")
arr4 = pd.read_csv("arrays_4000.csv")
segA = {c: (arr4[c].to_numpy(float) if c in arr4 else baseA[c].to_numpy(float))
        for c in set(list(baseA.columns) + list(arr4.columns)) if c.startswith("a")}
segB = {c: (arr4[c].to_numpy(float) if c in arr4 else baseB[c].to_numpy(float))
        for c in set(list(baseB.columns) + list(arr4.columns)) if c.startswith("b")}
print(f"segments: A={len(segA)} B={len(segB)}")

Ii = np.concatenate([np.arange(120*g + LAG, 120*g + 60) for g in range(10)])
Ir = np.concatenate([np.arange(120*g + 60 + LAG, 120*g + 120) for g in range(10)])
xx = np.arange(1, HALF + 1, dtype=float); xx -= xx.mean()
SXX = (xx * xx).sum()

def slope_of(curve):
    lr = linregress(np.arange(1, HALF + 1, dtype=float), curve)
    return lr.slope, (lr.pvalue / 2 if lr.slope < 0 else 1 - lr.pvalue / 2)

def load(source, cap=1000):
    fn = "sessions_out.csv" if source == "human" or source == "ai" else None
    fn = "sessions_out.csv" if source == "human" else "sessions_out_AI.csv"
    df = pd.read_csv(fn)
    good = (df["Yes"] >= 9) & (df["Total"] == 10) & df["Gate"].isin(range(1, 8))
    q = np.where(good)[0]
    dates = pd.to_datetime(df["SessionDate"], errors="coerce")
    order = np.argsort(dates.iloc[q].values, kind="stable")   # date-only, stable
    return df.iloc[q[order][:cap]].reset_index(drop=True)

def orig_of(section):
    num = int(str(section)[1:])
    return num if num >= 4000 else (num - 2000 if num >= 2000 else num)

def run():
    results = {}
    for arm in ("human", "ai"):
        ses = load(arm)
        n = len(ses)
        Arows = np.array([detrend(segA[f"a{orig_of(r.Section)}"]) for r in ses.itertuples()])
        Brows = np.array([detrend(segB[f"b{orig_of(r.Section)}"]) for r in ses.itertuples()])
        bit = np.array([str(r.Section)[0].lower() == "a" for r in ses.itertuples()])
        # pick per-session rows, one flag per session riding ROWS:
        # O[k] = Arows[k] when the session's shown sensor is the A-side, else Brows[k]
        O = np.array([Arows[k] if bit[k] else Brows[k] for k in range(n)])
        U = np.array([Brows[k] if bit[k] else Arows[k] for k in range(n)])
        # intercept is ONE PER SESSION (a length-n column), not per sample -
        # this was np.ones(1200) then np.ones(O.shape[1]), both of which made a
        # 1200-long vector that column_stack refused to put beside 1000 rows
        X = np.column_stack([np.ones(n), U])
        coef, *_ = np.linalg.lstsq(X, O, rcond=None)
        R = O - X @ coef
        print(f"\n===== {arm.upper()}  (N={n} sessions, {n*10} blocks) =====")
        curves = {}
        for tag, M in [("obs", O), ("uno", U)]:
            mi = M[:, Ii].reshape(n, 10, HALF).mean(axis=(0, 1))
            mr = M[:, Ir].reshape(n, 10, HALF).mean(axis=(0, 1))
            for ep, c in [("intention", mi), ("relax", mr)]:
                sl, p = slope_of(c)
                ref = TABLE2[(arm, tag, ep)]
                ok = "MATCH" if (abs(sl - ref[0]) < 2e-6 and abs(p - ref[1]) < 2e-4) else "diff"
                print(f"  {tag:<4} {ep:<9} slope {sl:+.6f}   p {p:.5f}   "
                      f"[paper {ref[0]:+.6f} p {ref[1]:.3f}] {ok}")
                curves[f"{tag}_{ep}"] = c
                if tag == "res" and armed_flag(arm, ep):
                    results[ep] = c
        # per-block paired t on observed Int-Rel slopes (their parametric check)
        si = (xx * (O[:, Ii].reshape(n, 10, HALF) -
                    O[:, Ii].reshape(n, 10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
        sr = (xx * (O[:, Ir].reshape(n, 10, HALF) -
                    O[:, Ir].reshape(n, 10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
        d = (si - sr).ravel(); t, p = ttest_1samp(d, 0)
        print(f"  per-block observed Int-Rel: mean {d.mean():+.6f} t={t:.3f} "
              f"d={d.mean()/d.std(ddof=1):+.4f}")
        results[arm] = {"ses": ses, "A": Arows, "B": Brows, "curves": curves}
    return results

def armed_flag(arm, ep):
    return False  # placeholder, never taken

def q2_prefix_perm(res):
    ses, Arows, Brows = res["human"]["ses"], res["human"]["A"], res["human"]["B"]
    n = len(ses)
    bit = np.array([str(r.Section)[0].lower() == "a" for r in ses.itertuples()])
    real_sl, _ = slope_of(np.where(bit[:, None], Arows, Brows)[:, Ii]
                          .reshape(n, 10, HALF).mean(axis=(0, 1)))
    rng = np.random.default_rng(SEED)
    null = np.empty(K)
    Ared, Bred = Arows[:, Ii], Brows[:, Ii]
    for j in range(K):
        b = rng.random(n) < 0.5
        null[j] = slope_of(np.where(b[:, None], Ared, Bred)
                           .reshape(n, 10, HALF).mean(axis=(0, 1)))[0]
    pct = (null < real_sl).mean() * 100
    print(f"\nQ2 prefix-permutation, human arm, {K} re-rolls of which sensor was 'shown':")
    print(f"  real shown-sensor intention slope {real_sl:+.6f}")
    print(f"  random-obs null mean {null.mean():+.6f} SD {null.std():.6f}")
    print(f"  real sits at {pct:.2f}% percentile of null "
          f"(~50% = pair effect only; ~<5% = truly shown-side)")

def q3_material():
    print("\nQ3 material baseline: every segment, raw (not residualised) Int-Rel contrast")
    rows, bins = [], []
    for prefix in ("a", "b"):
        store = segA if prefix == "a" else segB
        for c in sorted(store, key=lambda s: int(s[1:])):
            num = int(c[1:])
            rows.append(store[c])
            bins.append(0 if num <= 1400 else (1 if num <= 1999 else 2))
    mat = np.vstack(rows)
    si = (xx * (mat[:, Ii].reshape(-1, 10, HALF) -
                mat[:, Ii].reshape(-1, 10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
    sr = (xx * (mat[:, Ir].reshape(-1, 10, HALF) -
                mat[:, Ir].reshape(-1, 10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
    d = (si - sr).ravel()
    bin_of = np.repeat(np.array(bins), 10)
    for name, idx in [("1-1400", 0), ("1401-1999", 1), ("4000+", 2)]:
        dd = d[bin_of == idx]
        t, p = ttest_1samp(dd, 0)
        print(f"  series {name:<10} blocks {len(dd):>6}  mean {dd.mean():+.6f}  "
              f"SD {dd.std():.6f}  d={dd.mean()/dd.std():+.4f}  t={t:.2f}  p={p:.4f}")

def played_split(res):
    print("\nQ3b played segments: per-session raw Int-Rel, by series family")
    for arm in ("human", "ai"):
        ses = res[arm]["ses"]
        O = np.where(np.array([str(r.Section)[0].lower() == "a" for r in ses.itertuples()])[:, None],
                     res[arm]["A"], res[arm]["B"])
        si = (xx * (O[:, Ii].reshape(-1, 10, HALF) -
                    O[:, Ii].reshape(-1, 10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
        sr = (xx * (O[:, Ir].reshape(-1, 10, HALF) -
                    O[:, Ir].reshape(-1, 10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
        d = (si - sr).mean(axis=1)
        series = np.array([orig_of(r.Section) for r in ses.itertuples()])
        base = series <= 1400
        rec = (series >= 1401) & (series <= 1999)
        s4 = series >= 4000
        for name, m in [("base 1-1400", base), ("recycled 2xxx", rec), ("4000+", s4)]:
            if m.sum():
                t, p = ttest_1samp(d[m], 0)
                print(f"  {arm:<6} {name:<12} n={int(m.sum()):>4}  mean Int-Rel "
                      f"{d[m].mean():+.6f}  d={d[m].mean()/d[m].std():+.4f}  p={p:.4f}")

if __name__ == "__main__":
    res = run()
    q2_prefix_perm(res)      # NOT res["human"]: the function subscripts 'human' itself
    q3_material()
    played_split(res)
    print("\nDONE")
