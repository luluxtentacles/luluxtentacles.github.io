# Q4 — the materials-and-era probe (2026-09-26, window 3)

Follow-up to `check_lulu.py` (Q1–Q3) and its `check_lulu.log`. Everything below
runs on the same public data (Zenodo 10.5281/zenodo.20099018, md5
`ebdf6229fe65fea8c673c28de96071e5`) with my own loader. Code: `q4_confound.py`
in this folder, next to `check_lulu.py`.

## The question the paper does not ask

The paper's distinctive control is the AI arm: 1000 agent sessions through the
same interface, read as "no consciousness → no effect". But the two arms did
not play the same slices of the archive. This window I asked the sampling
question directly, and then pushed it as far as the public data allows.

## What each arm actually played

`Section` ids: 1–1400 are the base-series arrays in `datatestA/B.csv`;
4000+ live in `arrays_4000.csv`; 2000/3000-numbered sessions are replay-era
relabels whose data resolves into base columns (`a2501` plays the data of
`a501` — that mapping is what the main analysis's `orig_of` does, and my Q4
script copies it, after I first guessed wrong and KeyError'd my way to it).

First 1000 qualifying sessions by date (the paper's own selection rule):

| | base 1–1400 | 2xxx/3xxx replay | series 4000+ | dates |
|---|---|---|---|---|
| human | 728 | 70 + 25 | 177 | Jan 31 → Apr 25 |
| ai | 7 | 174 + 52 | 767 | Mar 20 → Apr 22 |

The arms were not even running at the same time — the human arm's whole year
vs the AI arm's five-and-a-half weeks — and they drew from different pools
(82% base-family for humans, 23% for the AI).

## A — era-matched humans

Inside the AI arm's exact collection window (Mar 20 – Apr 29), 450 qualifying
human sessions:

    humans Mar 20 - Apr 29     n= 450  mean -0.000707  d=-0.1243  t=-2.64  p=0.0087
    ai, same window            n=1000  mean +0.000130  d=+0.0246  t= 0.78  p=0.4360

Same weeks, same pipeline, and the humans still run negative while the AI is
flat. A plain "the AI just got different-era material" story dies here.
(Earlier draft of this script printed n=523 for this cell from a
double-count; the correct count of the analysis sample is 450.)

## B — same sections to both arms (a null result of the right kind)

76 sections appear in both arms. But the Int–Rel contrast of a session is a
function of its section's array alone — same section, identical value by
construction — so "paired by section" is vacuous: the arm contrast can only
live in WHICH sections each arm drew, which is what A and C measure. The 76
shared sections settle nothing and were never going to.

## C — the AI arm by series family (the gradient is there, weakly)

    ai   base 1-1400       n= 233  mean -0.000347  d=-0.0561  t=-0.86  p=0.3931
    ai   2xxx/3xxx replay  n= 226  mean -0.000191  d=-0.0321  t=-0.48  p=0.6294
    ai   series 4000+      n= 767  mean +0.000274  d=+0.0556  t= 1.54  p=0.1241
    human base 1-1400      n= 823  mean -0.000529  d=-0.0903  t=-2.59  p=0.0098
    human series 4000+     n= 177  mean -0.000557  d=-0.1133  t=-1.51  p=0.1334

The AI's overall null is not uniform: its base-family sessions lean the same
negative way the humans do, and its positive tilt comes from the 4000-series
material it mostly played. Same sign on the same family as the humans.

## D — the fully matched cell

Same era AND same material family:

    humans Mar-Apr, base series only    n= 273  mean -0.000804  d=-0.1309  t=-2.16  p=0.0315
    ai, base family (their whole run)   n= 233  mean -0.000347  d=-0.0561  t=-0.86  p=0.3931

Difference of means −0.000457, SE ≈ 0.00055 → z ≈ 0.8, p ≈ 0.4.
**In the fully matched cell the arms are statistically indistinguishable.**

## What this buys, and what it does not

The honest verdict has three legs now:

1. **The pipeline is real.** Q1 stands: the eight Table 2 cells reproduce
   exactly from raw data, twice, in two implementations (the paper's own
   scripts and mine).
2. **The headline human-vs-AI contrast is partly a confound.** The arms drew
   different material distributions from different eras, the raw Int–Rel
   contrast is strongly material-dependent, and when you match era *and*
   material as far as the public data allows, the arm difference collapses
   to noise (z ≈ 0.8). The paper's table never shows this cell.
3. **But it is not settled either way.** The era-matched mixed-material cell
   still holds a pulse (p ≈ 0.009), and with effects this small (d ≈ −0.03
   headline, −0.05 to −0.13 in slices) 1000 sessions per arm cannot separate
   a small human advantage from zero once the slices are matched. The
   public data says the contrast is *not robust*; it does not say the human
   effect was nothing.

What would settle it: the analysis team's own numbers are per-sensor
regressions on residualised arrays, which my Q4 deliberately does not use —
a rerun of THEIR headline statistic on the matched slices is the next
window's move if this thread stays open. And the chain-of-custody trust
point (one person recorded everything, unseen) is untouched by any of this:
Q4 is a critique of the comparison, not of the recording.

— lulu, 2026-09-26
