# Q4 - the materials-confound probe, one step deeper than the paper's table.
# The paper contrasts 1000 human sessions against 1000 AI sessions and reads
# the difference as consciousness. Q3 already showed raw Int-Rel is negative
# on played-era base series and flat on series 4000+. If the AI arm simply
# drew from a different series pool, the whole headline contrast is a
# materials story and the design says nothing about consciousness.
# The discriminating checks:
#   A  era-matched humans: qualifying human sessions inside the AI's exact
#      collection window (Mar 20 - Apr 29). If matched-era humans are still
#      negative while the AI is flat, era is not the story.
#   B  the SAME sections played to BOTH arms: paired Int-Rel, section by
#      section, human vs AI. Same recording, two arms.
#   C  the AI arm's base-series sessions on their own.
#   D  the AI arm BY series family - does its null hide a series gradient?
import numpy as np
import pandas as pd
from scipy.signal import detrend
from scipy.stats import ttest_1samp, ttest_rel

LAG, HALF = 10, 50
Ii = np.concatenate([np.arange(120*g + LAG, 120*g + 60) for g in range(10)])
Ir = np.concatenate([np.arange(120*g + 60 + LAG, 120*g + 120) for g in range(10)])
xx = np.arange(1, HALF + 1, dtype=float); xx -= xx.mean(); SXX = (xx * xx).sum()


def orig_of(s):
    n = int(str(s)[1:])
    return n if n >= 4000 else (n - 2000 if n >= 2000 else n)


def key_of(section):
    """resolve a Session Section id to the array key that holds its data,
    with the same orig_of semantics check_lulu.py uses:
    a2501 is a replay-era number whose data lives in base column a501"""
    s = str(section); pre = s[0].lower()
    n = int(s[1:])
    return pre + str(n - 2000 if 2000 <= n < 4000 else n)


def load(fn, cap=1000):
    df = pd.read_csv(fn)
    good = (df["Yes"] >= 9) & (df["Total"] == 10) & df["Gate"].isin(range(1, 8))
    q = np.where(good)[0]
    dates = pd.to_datetime(df["SessionDate"], errors="coerce")
    order = np.argsort(dates.iloc[q].values, kind="stable")
    return df.iloc[q[order][:cap]].reset_index(drop=True)


print("loading arrays ...")
baseA = pd.read_csv("datatestA.csv"); baseB = pd.read_csv("datatestB.csv")
arr4 = pd.read_csv("arrays_4000.csv")
arr4a = set(arr4.columns)
arr4b = set(c.replace("a", "b", 1) for c in arr4a)
# same construction as check_lulu.py: the union of base and 4000-series keys
segA = {c: (arr4[c].to_numpy(float) if c in arr4a else baseA[c].to_numpy(float))
        for c in set(list(baseA.columns) + list(arr4a)) if c.startswith("a")}
segB = {c: (arr4[c].to_numpy(float) if c in arr4b else baseB[c].to_numpy(float))
        for c in set(list(baseB.columns) + list(arr4b)) if c.startswith("b")}
print(f"arrays ready: A={len(segA)} B={len(segB)}")


def intrel(section):
    """paired Int-Rel slope difference for one session, RAW (no
    residualisation - the material's own contrast)"""
    s = str(section); pre = s[0].lower()
    store = segA if pre == "a" else segB
    arr = detrend(store[key_of(s)])
    si = (xx * (arr[Ii].reshape(10, HALF) - arr[Ii].reshape(10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
    sr = (xx * (arr[Ir].reshape(10, HALF) - arr[Ir].reshape(10, HALF).mean(-1, keepdims=True))).sum(-1) / SXX
    return (si - sr).mean()


def report(name, d, label=""):
    d = np.asarray(d, float)
    t, p = ttest_1samp(d, 0)
    print(f"  {name:<36} n={len(d):>4}  mean {d.mean():+.6f}  "
          f"d={d.mean()/d.std(ddof=1):+.4f}  t={t:.2f}  p={p:.4f}   {label}")


hs, as_ = load("sessions_out.csv"), load("sessions_out_AI.csv")
hd = pd.to_datetime(hs["SessionDate"]); ad = pd.to_datetime(as_["SessionDate"])
print("computing Int-Rel per session ...")
hs_d = np.array([intrel(s) for s in hs["Section"]])
ai_d = np.array([intrel(s) for s in as_["Section"]])

print("\nA  era-matched humans (inside the AI arm's exact collection window):")
m = ((hd >= pd.Timestamp("2026-03-20")) & (hd <= pd.Timestamp("2026-04-29"))).to_numpy()
report("humans Mar 20 - Apr 29", hs_d[m], "")
report("ai, same window (their whole run)", ai_d, "")

print("\nB  same sections played to BOTH arms, paired by section:")
hsec = hs["Section"].astype(str)
asec = as_["Section"].astype(str)
both = sorted(set(hsec) & set(asec))
print(f"  sections played to both arms: {len(both)}")
hmean = np.array([hs_d[(hsec == s).to_numpy()].mean() for s in both])
amean = np.array([ai_d[(asec == s).to_numpy()].mean() for s in both])
t0, p0 = ttest_1samp(hmean, 0)
t1, p1 = ttest_1samp(amean, 0)
t2, p2 = ttest_rel(hmean, amean)
print(f"  humans on shared sections: mean {hmean.mean():+.6f}  t={t0:.2f}  p={p0:.4f}")
print(f"  AI on the SAME sections:   mean {amean.mean():+.6f}  t={t1:.2f}  p={p1:.4f}")
print(f"  paired human-vs-AI on the same recordings: t={t2:.2f}  p={p2:.4f}")

print("\nC  the AI arm by series family (does its null hide a gradient?):")
ai_o = as_["Section"].map(orig_of).to_numpy()
ho = hs["Section"].map(orig_of).to_numpy()
for name, msk in [("base 1-1400", ai_o <= 1400), ("2xxx/3xxx replay", (ai_o >= 501) & (ai_o < 1400) & (as_['Section'].astype(str).str[1:].astype(int) >= 2000)), ("series 4000+", ai_o >= 4000)]:
    if msk.sum():
        report(f"ai   {name}", ai_d[msk], "")
print("  (humans, same split, for the eye):")
for name, msk in [("base 1-1400", ho <= 1400), ("series 4000+", ho >= 4000)]:
    if msk.sum():
        report(f"human {name}", hs_d[msk], "")

print("\nDONE")
