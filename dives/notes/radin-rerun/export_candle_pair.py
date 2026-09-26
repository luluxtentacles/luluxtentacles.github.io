# export one real played session's sensor pair for the pre-recorded candle page.
# the DISPLAY was driven by the stored shown array (detrended + z-scored at
# recording time) - the regression residual is analysis-side only, so both go in:
# shown = what the candle flickered to, resid = what the analyst kept.
# session: the first qualifying human session (a1385, 2026-01-31, gate 1).
import numpy as np, pandas as pd, json, sys
from scipy.signal import detrend

baseA = pd.read_csv("datatestA.csv"); baseB = pd.read_csv("datatestB.csv")
df = pd.read_csv("sessions_out.csv")
good = (df["Yes"] >= 9) & (df["Total"] == 10) & df["Gate"].isin(range(1, 8))
q = np.where(good)[0]
dates = pd.to_datetime(df["SessionDate"], errors="coerce")
order = np.argsort(dates.iloc[q].values, kind="stable")
ses = df.iloc[q[order]].reset_index(drop=True)

row = None
for r in ses.itertuples():
    if str(r.Section)[0].lower() == "a" and int(str(r.Section)[1:]) <= 1400:
        row = r; break
sec = str(row.Section); num = int(sec[1:])
A = detrend(baseA[f"a{num}"].to_numpy(float))   # the shown array, as stored
B = detrend(baseB[f"b{num}"].to_numpy(float))   # its never-shown partner
X = np.column_stack([np.ones(len(B)), B])
coef, *_ = np.linalg.lstsq(X, A, rcond=None)
a0, b1, resid = coef[0], coef[1], A - X @ coef

print(f"session {sec!r}  date {row.SessionDate}  gate {row.Gate}  "
      f"score {row.Score}  words correct {row.Yes}/10", file=sys.stderr)

def pack(v, nd=5):
    return [round(float(x), nd) for x in v]

out = {
    "section": sec,
    "date": str(row.SessionDate),
    "gate": int(row.Gate),
    "score": float(row.Score),
    "words_correct": int(row.Yes),
    "shown": pack(A),            # what the candle actually flickered to
    "resid": pack(resid),        # what the analyst kept
    "b0": round(float(a0), 6),
    "b1": round(float(b1), 6),
    "obs_rms": round(float(A.std()), 5),
}
with open("candle_session.json", "w") as f:
    json.dump(out, f)
print("wrote candle_session.json:", len(json.dumps(out)), "bytes")
