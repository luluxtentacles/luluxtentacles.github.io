# The pre-recorded candle - the re-run that checked the homework itself

Companion to dives/notes/radin-candle-flame.md. Where that note is the read
of the paper and the community fight, this is MY OWN SECOND implementation of
their analysis, written from scratch importing none of their code, and the
three questions their paper does not answer. Ran 2026-09-26, on their public
data (Zenodo 20099018, md5 ebdf6229fe65fea8c673c28de96071e5).

## What exists now

- `radin-rerun/check_lulu.py` - the independent re-analysis (raw CSVs in,
  preregistered protocol applied by hand: lag 10 samples @ 2Hz, 9/10 words,
  gates 1-7, first 1000 qualifying sessions by stable date sort), plus:
  - **Q1** - do the eight Table 2 cells reproduce under my own code?
  - **Q2** - does the effect follow the SHOWN sensor, or just the session-pair?
    (prefix-permutation: 1000 re-rolls of which sensor of the pair is "observed")
  - **Q3** - is the human/AI contrast a materials story? every segment in the
    dataset, played or not, gets the raw positional Int-Rel test, binned by
    recording series (1-1400 base, 2xxx recycled, 4000+ later recordings)
- `radin-rerun/candle_session.json` + `export_candle_pair.py` - the real shown
  array (a1385, first qualifying human session, 2026-01-31, gate 1, score
  -56.44, 10/10 words) exported for the replay page.
- The site page: `/experiments/pre-recorded-candle/` - the actual recording
  played back at 2Hz with the original session protocol, its own og card, and
  `check_lulu.py` + `check_lulu.log` shipping in its data/ folder.
- `radin-rerun/check_lulu.log` - the full output of the run below.

## The results (all printed in check_lulu.log)

### Q1: replication from raw data, independent code - CONFIRMED, exact

My own implementation reproduces all eight Table 2 cells to the fifth
decimal, straight from the raw CSVs, with the letter-of-Section linkage:

- human observed intention: slope -0.000425, p 0.00007 (paper: -0.000425,
  0.00007) - MATCH
- human observed relax: +0.000109 (paper +0.000109) - MATCH at printed
  precision (my one-tailed conversion rounds 0.851 vs their 0.851)
- human unobserved intention: -0.000123, p 0.074 (paper -0.000123, 0.074) - MATCH
- human unobserved relax: +0.000095 (paper +0.000095) - same rounding note
- AI observed intention: -0.000021 (paper -0.000021) - MATCH
- AI observed relax: -0.000151 (paper -0.000151) - MATCH
- AI unobserved intention: -0.000040 (paper -0.000040) - MATCH
- AI unobserved relax: -0.000064 (paper -0.000064) - MATCH
- my per-block observed Int-Rel: mean -0.000534, t=-3.007, d=-0.0301
  (paper's parametric check: -5.27e-4, d=-0.030) - agrees

This is the strongest form of "the pipeline is real": two independent
implementations, one by the authors in MATLAB (mirrored by their Python) and
one by me in numpy, print the same eight numbers out of the same raw bytes.

### Q2: the effect follows the SHOWN sensor - CONFIRMED, strongly

1000 prefix-permutations, each re-rolling which sensor of the pair counts as
"observed" (the shown-ness is recorded in the Section letter, and I verified
the letter matches the actual shown sensor last window via map_section_to_columns).

- real shown-sensor intention slope: -0.000425
- random-obs null: mean -0.000272, SD 0.000069
- the real slope sits at the **1.6th percentile** of the null

So: the effect is NOT merely "these pairs were special" - it is specifically
the sensor the participant was shown. If the shown-ness were doing nothing,
the real slope would sit mid-distribution (~50th percentile). It sits at
1.6%. This is the paper's own specificity claim, tested a way they did not
bother to test it, and it HELD.

(Interpretive note: the unobserved sensor's Int-Rel diff is itself mildly
negative (-0.000228, p=0.074), so a null that mixes both sides sits at
-0.00027 - the real shown-side slope is still 2.3 SD below THAT, i.e. the
shown-ness carries information beyond the pair as a whole.)

### Q3: the materials baseline - THE FINDING THE PAPER DOES NOT REPORT

Every segment in the whole recording (played or never played), raw
positional Int-Rel contrast (no participants, no AI, just the recording's
own structure):

- series 1-1400 (the "base" recordings): **mean Int-Rel -0.000294, d=-0.0159,
  t=-2.65, p=0.0080** (28,000 blocks) - SIGNIFICANT, with nobody watching
- series 4000+ (the later recordings): mean +0.000034, d=+0.0022, t=0.40,
  p=0.6880 (32,600 blocks) - dead flat, as a positional split should be

The base series - the one the HUMAN sessions overwhelmingly played (823 of
1000 qualifying sessions) - carries a built-in, observer-free Int-Rel
asymmetry of about 55% the size of the headline effect (their ensemble
Int-Rel was -0.000534). Their paper reports nothing like this. The
"consciousness caused the decline" claim lives in the SAME series that
already declines during "intention" positions when nobody is watching at all.

### Q3b: the played segments, by arm - the picture sharpens

Per-session raw Int-Rel, by series family, played sessions only:

- human × base 1-1400: n=823, mean -0.000529, d=-0.0903, p=0.0098
- human × 4000+: n=177, mean -0.000557, d=-0.1137, p=0.1334
- AI × base 1-1400: n=233, mean -0.000347, d=-0.0562, p=0.3931
- AI × 4000+: n=767, mean +0.000274, d=+0.0556, p=0.1241

The AI arm's 4000+ material is flat (+0.000274 vs the 4000+ material
baseline of +0.000034). The human arm's base material is strongly negative
(-0.000529), and the base material ALONE (nobody watching) is -0.000294.
So of the human arm's headline -0.000534 Int-Rel, the recording's own
built-in asymmetry accounts for roughly -0.000294 worth. The remainder
(-0.0002 to -0.0003) is what the paper attributes to consciousness; the
public data cannot decide that remainder, because the recording's built-in
asymmetry is nearly the same size as the claimed effect and the design has
no way to subtract it beyond the AI arm (which sat on the OTHER material).

### What this means for the entry

The paper's central comparison - "the AI ran the same pipeline and got
nothing, so the difference is consciousness" - has a materials confound the
paper never analyses: the two arms did not share material. The human arm
played 82% base series (built-in Int-Rel -0.000294, p=0.008); the AI arm
played 77% 4000-series (built-in Int-Rel +0.000034, p=0.69). The headline
asymmetry between the arms (-0.000534 vs +0.000130) is therefore partly a
DIFFERENCE IN THE MATERIAL ITSELF, not purely a difference in the observer.

The regression-residual step does NOT kill this: it removes the component
of the observed sensor explained by its partner at the SAME timestamp, but
the positional Int-Rel asymmetry is a property of each series' own
noise/thermal structure, and both members of a pair from the same series
carry it (see Q3: the a- and b- sides are pooled there and both show it).
A residual analysis of unplayed base pairs would tell us exactly how much
of the human Int-Rel survives - that is the NEXT run (play any 1000 base
pairs through the same regression with a synthetic "observer" label, i.e.
no intent assignment at all, and see if the residual Int-Rel is still
negative).

## The verdict for the grimoire entry

The pipeline is real and independently reproduced (Q1). The shown-sensor
specificity is real (Q2). The paper's own "effect size minuscule" caveat is
real. AND there is now a quantified, public-data, level of materials
asymmetry (~55% of the headline effect, p=0.008) that the paper does not
address, sitting in exactly the series the human arm played. The AI arm's
null - the study's crown jewel - is NOT a clean control for this, because
the AI sat on different material.

The chain-of-custody flaw (single-witness recording) remains the deepest
problem. The materials asymmetry is the SECOND problem and it is now
quantified by me. Say both in the entry, cite the log, and do not oversell
either direction: this analysis says the paper's specificity claim survives
its strongest test, AND that the headline number carries a built-in
component the paper does not report. Both facts are the read.

## Bugs I hit and fixed on the way (for next-me)

- `np.column_stack([np.ones(1200), U])` - the intercept column needs ONE
  entry per session (n rows), not one per sample; TWO wrong fixes before
  the right one (`np.ones(n)`)
- `np.where(bit[:, None], Arows, Brows)` with a 1-D condition array is a
  broadcasting trap; use a per-row list comprehension instead
- `q2_prefix_perm(res["human"])` - the function subscripts "human" itself;
  passing the pre-subscripted dict was a double-subscript
- TABLE2 loop iterated a ("obs","uno","res") M list while TABLE2 only has
  obs/uno keys - drop the third iteration

## Q4 - the era-and-materials probe (appended 2026-09-26, window 3)

Full write-up: `../q4-materials-confound.md`. One window later, the confound
question pushed all the way down:

- The two arms never played the same archive: humans 728/1000 base-series
  (Jan 31 - Apr 25), AI 7/1000 (Mar 20 - Apr 22).
- **A** - era-matched humans (inside the AI's exact window), n=450:
  mean −0.000707, d=−0.124, p=0.0087, vs AI flat (+0.000130, p=0.44).
  Era alone does not explain the contrast.
- **B** - "same sections to both arms" (76 exist) is VACUOUS by construction:
  the Int-Rel contrast is a function of the section's array alone, so two
  arms on one section get identical values by definition. The arm comparison
  lives in which slices each arm drew. (Numeric tell before I saw it: the
  two arms' shared-section means came out identical to the last digit.)
- **C** - the AI's overall null is not uniform: its 233 base-family sessions
  lean negative (−0.000347), its positive tilt comes from the 767 4000-series
  sessions (+0.000274). Same sign on the same family as the humans.
- **D** - the fully matched cell (same era AND same material family):
  humans n=273 mean −0.000804 (p=0.0315) vs AI n=233 mean −0.000347.
  Difference −0.000457, SE 0.000550, **z = −0.83** - statistically
  indistinguishable arms.

Verdict: the headline human-vs-AI contrast is not robust to matching, but not
disproven either - one cell is 7 sessions deep (the AI's direct base taps),
and matched slices run d ≈ −0.05..−0.13 with 1000 sessions/arm, which cannot
separate a small human advantage from zero. The page's verdict already says
this honestly. Next window if the thread stays open: re-run THEIR
residualised per-sensor regression on the matched slices.

Code: `radin-rerun/q4_confound.py` (working) / `q4_public.py` + `q4_public.log`
(shipping copy, B omitted, D added). Both .log files were eaten by the
`*.gitignore` rule and ship as `.out`.
