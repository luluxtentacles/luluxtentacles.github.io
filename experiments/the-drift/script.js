/* ==========================================================================
   the drift · experiment no.3 · live quantum intention test
   --------------------------------------------------------------------------
   the mechanic, in one line: the oracle never stops. it streams fresh draws,
   one after another, and the stage moves with every one of them: the needle
   carries the cumulative z, and a colour sweeps across the stage in the
   direction the draw leaned. you do not start or stop anything. you ARM a
   guess, and that guess is spent on the NEXT draw the oracle produces. the
   vow is armed, in the browser, before the fetch goes out. nothing is stored
   	on the server side, and nothing exists before the oracle answers.
   this was the whole confound of the rehearsal: there the recording predated
   the intent on purpose. here the coin has not been flipped until after your
   hand is on the button.

   entropy: master's cloudflare relay -> qrandom.io, same shape as the scrying
   glass (tentacle_samples/animation.js): 128 hex bytes, abort at 6s, two
   attempts, then fall back to local crypto entropy with the source disclosed.
   the scrying glass reads bytes 0,1,2,4,6 for its shape. this page reads
   byte 8, so the two machines keep different fingers on the same stream.

   scoring: PEAR-style. every intended trial is a hit if the verdict leans the
   way you vowed. z = (2h - n) / sqrt(n) over the pooled intended trials,
   one-tailed p in the vowed direction.
   watch trials: pre-declared baseline, logged, scored only on two-tailed
   parity for symmetry, never in the vowed-direction headline.
   local-fallback draws are logged in their own ledger and NEVER pooled into
   the quantum headline. the two sources are disclosed separately, always.
   ========================================================================== */
'use strict';

// ---------- ENTROPY ----------
const RELAY_URL = 'https://scrying-relay.digital-psionics.workers.dev/';

async function fetchQuantumHexOnce() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    try {
        const res = await fetch(RELAY_URL, { signal: controller.signal, cache: 'no-store' });
        clearTimeout(timeout);
        if (!res.ok) throw new Error('bad status ' + res.status);
        const json = await res.json();
        if (!json || !json.string || !json.string.length || !json.string[0]) throw new Error('empty/failed payload');
        return json.string[0];
    } catch (e) {
        clearTimeout(timeout);
        throw e;
    }
}

async function fetchQuantumHex(len = 128, attempts = 2) {
    let lastErr;
    for (let i = 0; i < attempts; i++) {
        try {
            return await fetchQuantumHexOnce();
        } catch (e) {
            lastErr = e;
            if (i < attempts - 1) await new Promise(r => setTimeout(r, 400));
        }
    }
    throw lastErr;
}

function localEntropyHex(len = 128) {
    const bytes = new Uint8Array(len);
    crypto.getRandomValues(bytes);
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

// the verdict bit: byte 8 (the ninth byte), parity. 0 = lean left, 1 = lean right.
function verdictFromHex(hex) {
    const bytes = [];
    for (let i = 0; i + 1 < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
    if (bytes.length < 9) throw new Error('short draw');
    return {
        bit: bytes[8] & 1,
        byteHex: bytes[8].toString(16).padStart(2, '0').toUpperCase(),
        headHex: hex.slice(0, 16).toUpperCase()
    };
}

async function makeCommit(mode, ts) {
    const nonce = crypto.getRandomValues(new Uint8Array(8));
    const nonceHex = Array.from(nonce).map(b => b.toString(16).padStart(2, '0')).join('');
    try {
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(mode + '|' + ts + '|' + nonceHex));
        return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
    } catch (e) { return nonceHex.slice(0, 16); } // old browsers still get a nonce
}

// ---------- THE MATH ----------
// binomial z for h hits in n intended trials at p=0.5: (2h - n)/sqrt(n).
function binomZ(h, n) {
    if (n < 1) return null;
    return (2 * h - n) / Math.sqrt(n);
}

// erf by Abramowitz & Stegun 7.1.26, |error| < 1.5e-7. good enough for a webpage.
function erf(x) {
    const t = 1 / (1 + 0.3275911 * Math.abs(x));
    const y = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
    const v = 1 - y * Math.exp(-x * x);
    return x >= 0 ? v : -v;
}
function erfc(x) {
    return x >= 0 ? 1 - erf(x) : 2 - erf(-x);
}

// one-tailed p in the vowed direction: the tail beyond |z|.
function pOneTailed(z) {
    return 0.5 * erfc(Math.abs(z) / Math.SQRT2);
}

// two-tailed p for the watch ledger: a baseline has no direction in it, so
// the honest question is symmetry, not which side it favors.
function pTwoTailed(z) {
    return erfc(Math.abs(z) / Math.SQRT2);
}

// ---------- STATE ----------
// one ledger per source. only ledgers.q feeds the headline needle.
const LEDGER_KEY = 'lulu_drift_v1';
let ledger = {
    q: { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } },   // quantum draws
    f: { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } },   // local-fallback draws
    wq: { n: 0, ones: 0 }, wf: { n: 0, ones: 0 },                     // watch trials per source
    receipts: []                                                      // last 30, newest first
};

function loadLedger() {
    try {
        const raw = localStorage.getItem(LEDGER_KEY);
        if (!raw) return;
        const saved = JSON.parse(raw);
        if (saved && saved.q && saved.f && Array.isArray(saved.receipts)) {
            ledger = {
                q: fixBin(saved.q), f: fixBin(saved.f),
                wq: fixWatch(saved.wq), wf: fixWatch(saved.wf),
                receipts: saved.receipts.slice(0, 30)
            };
        }
    } catch (e) { /* a broken ledger starts clean, nothing else is touched */ }
}
function fixBin(b) {
    if (!b) return { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } };
    return {
        n: b.n | 0, h: b.h | 0,
        left: { n: (b.left && b.left.n) | 0, h: (b.left && b.left.h) | 0 },
        right: { n: (b.right && b.right.n) | 0, h: (b.right && b.right.h) | 0 }
    };
}
// a watch ledger is { n, ones }: parity is the only thing a baseline can score.
// a legacy bare count has no parity in it, so it starts clean rather than lying.
function fixWatch(w) {
    if (w && typeof w === 'object') return { n: w.n | 0, ones: w.ones | 0 };
    return { n: 0, ones: 0 };
}
function saveLedger() {
    try { localStorage.setItem(LEDGER_KEY, JSON.stringify(ledger)); } catch (e) { /* private mode etc */ }
}

// ---------- THE STREAM AND THE GUESS ----------
// the oracle streams constantly. a guess is ARMED, not cast: arm it, and the
// very next draw the oracle produces is graded against it, then the guess is
// spent and the stage goes back to plain watching. the commit hash is made
// the instant the guess is armed, before the next fetch goes out, so the
// receipt shows vow-then-draw in the order you can check.

let pendingGuess = null;        // 'left' | 'right' | null (null = just watching)
let pendingReceipt = null;      // the armed commit, spent on the next draw
let inFlight = false;           // a fetch is out to the oracle right now
let streamOn = true;            // the oracle never sleeps

async function armGuess(m) {
    const ts = Date.now();
    pendingReceipt = { mode: m, ts, commit: await makeCommit(m, ts) };
    pendingGuess = m;
    setBanner('armed: next draw leans ' + m.toUpperCase(),
        'the guess is locked and the oracle is mid-stream. your NEXT draw decides it, then the guess is spent.');
}

// one draw, live, right now. if a guess is armed this draw is a scored trial;
// otherwise it is a watch/baseline draw. either way the stage moves.
async function drawOnce() {
    const ts = Date.now();
    // the vow is snapshotted BEFORE the fetch goes out: anything armed while a
    // draw is already mid-flight waits for the NEXT one, so the covenant holds.
    const vow = pendingGuess ? { guess: pendingGuess, commit: pendingReceipt ? pendingReceipt.commit : '' } : null;
    if (vow) { pendingGuess = null; pendingReceipt = null; updatePanel(); }
    inFlight = true;

    let hex, src;
    try {
        hex = await fetchQuantumHex(128);
        src = 'q';
    } catch (e) {
        console.warn('[the drift] oracle unreachable, local fallback:', e);
        hex = localEntropyHex(128);
        src = 'f';
    }

    let result;
    try {
        result = verdictFromHex(hex);
    } catch (e) {
        inFlight = false;
        setBanner('the oracle muttered', 'short draw, discarded. the stream continues.');
        return;
    }

    const guess = vow ? vow.guess : null;        // the vowed guess, armed before the fetch
    const intended = guess || 'watch';
    const bin = src === 'q' ? ledger.q : ledger.f;
    const hit = guess === null ? null
        : ((guess === 'left' && result.bit === 0) || (guess === 'right' && result.bit === 1) ? 1 : 0);

    const rec = {
        t: ts,
        mode: intended,
        bit: result.bit,
        src,
        hit,
        byte: result.byteHex,
        commit: vow ? vow.commit : ''
    };

    if (guess === null) {
        const w = src === 'q' ? ledger.wq : ledger.wf;
        w.n++;
        if (result.bit === 1) w.ones++;
    } else {
        bin.n++; bin[guess].n++;
        if (hit === 1) { bin.h++; bin[guess].h++; }
        pendingGuess = null;
        pendingReceipt = null;
    }

    ledger.receipts.unshift(rec);
    ledger.receipts = ledger.receipts.slice(0, 30);
    saveLedger();
    inFlight = false;

    // needle target: pooled quantum z. fallback draws move the grey needle only.
    const zq = binomZ(ledger.q.h, ledger.q.n);
    const zf = binomZ(ledger.f.h, ledger.f.n);
    if (src === 'q') gauge.targetZ = zq === null ? 0 : zq;
    gauge.targetF = zf === null ? null : zf;
    gauge.flashSide = result.bit * 2 - 1;        // ghost draw: which way this draw leaned
    gauge.flashAt = performance.now();
    // one wisp per draw, drifting the way the bit leaned: the stage breathes
    if (!gauge.wisps) gauge.wisps = [];
    if (gauge.wisps.length > 14) gauge.wisps.shift();
    gauge.wisps.push({ dir: result.bit * 2 - 1, born: performance.now() });
    flowSweep(result.bit);

    if (guess === null) {
        setBanner('the oracle leaned ' + sideWord(result.bit),
            src === 'q' ? 'live draw, baseline. nothing was aimed.' : 'live draw, but from the local fall (oracle unreachable). no guess was armed.');
    } else if (hit === 1) {
        setBanner(src === 'q' ? 'honored. the draw leaned your way' : 'honored, but by the local fall',
            'a ' + sideWord(result.bit) + ' draw against a ' + guess + ' armed before it. ledger updated.');
    } else {
        setBanner(src === 'q' ? 'broken. the draw leaned away' : 'broken, but by the local fall',
            'a ' + sideWord(result.bit) + ' draw against a ' + guess + ' armed before it. ledger updated.');
    }
    updatePanel();
    renderReceipts();
}

function sideWord(bit) { return bit === 0 ? 'LEFT' : 'RIGHT'; }

// the oracle's heartbeat: draw, breathe, draw, forever.
async function streamLoop() {
    while (streamOn) {
        await drawOnce();
        await new Promise(r => setTimeout(r, 750));
    }
}

// ---------- DOM ----------
const el = id => document.getElementById(id);
const stage = document.getElementById('stage');
const bannerEl = document.getElementById('phasebanner');
const subEl = document.getElementById('subbanner');

function setBanner(main, sub) {
    if (main !== null) bannerEl.textContent = main;
    if (sub !== null) subEl.textContent = sub;
}

function updatePanel() {
    const q = ledger.q, f = ledger.f;
    const zq = binomZ(q.h, q.n);
    const pq = zq === null ? null : pOneTailed(zq);

    document.getElementById('r-n').textContent = String(q.n);
    document.getElementById('r-hits').textContent = String(q.h) + ' / ' + String(q.n);
    document.getElementById('r-rate').textContent = q.n ? ((q.h / q.n) * 100).toFixed(1) + '%' : '\u2014';
    document.getElementById('r-z').textContent = zq === null ? '\u2014' : (zq >= 0 ? '+' : '\u2212') + Math.abs(zq).toFixed(2);
    document.getElementById('r-p').textContent = pq === null ? '\u2014' : pq.toFixed(3);

    document.getElementById('r-ln').textContent = q.left.n ? q.left.h + '/' + q.left.n : '\u2014';
    document.getElementById('r-rn').textContent = q.right.n ? q.right.h + '/' + q.right.n : '\u2014';
    const wz = binomZ(ledger.wq.ones, ledger.wq.n);
    document.getElementById('r-watch').textContent = ledger.wq.n
        ? ledger.wq.n + (ledger.wq.n === 1 ? ' trial' : ' trials')
          + ' · parity z ' + (wz >= 0 ? '+' : '\u2212') + Math.abs(wz).toFixed(2)
          + ' (p ' + pTwoTailed(wz).toFixed(3) + ')'
        : '0 trials';
    document.getElementById('r-local').textContent = f.n
        ? f.h + ' / ' + f.n + ' (z ' + (binomZ(f.h, f.n) >= 0 ? '+' : '\u2212') + Math.abs(binomZ(f.h, f.n)).toFixed(2) + ')'
        : '\u2014';

    // the headline line under the panel
    const headline = document.getElementById('verdict-line');
    if (!q.n) {
        headline.textContent = 'no armed guesses answered yet. arm one and the next draw decides it.';
    } else if (Math.abs(zq) < 1) {
        headline.textContent = 'the needle sits inside the noise band. so far, the oracle does not care.';
    } else if (Math.abs(zq) < 2) {
        headline.textContent = 'outside the noise band but short of two sigma. not nothing, not yet anything. guess more.';
    } else if (pq < 0.01) {
        headline.textContent = 'past two sigma in the vowed direction. either you are bending it, or you got lucky within one in ' + Math.round(1 / (pq * 100)) + '. keep guessing.';
    } else {
        headline.textContent = 'past two sigma in the vowed direction. guess more before you believe it.';
    }

    // mode buttons: a side glows while its guess is armed, watch glows when none is
    document.querySelectorAll('.vow-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === 'watch'
            ? pendingGuess === null
            : b.dataset.mode === pendingGuess);
    });
}

function renderReceipts() {
    const box = document.getElementById('receipts');
    if (!ledger.receipts.length) {
        box.innerHTML = '<p class="foot-note" id="no-receipts">no draws yet. the ledger starts when you arm your first guess.</p>';
        return;
    }
    const rows = ledger.receipts.map(r => {
        const t = new Date(r.t);
        const hhmm = t.toTimeString().slice(0, 8);
        const vow = r.mode === 'left' ? '\u2190 armed' : r.mode === 'right' ? 'armed \u2192' : '\u25cb watch';
        const draw = r.bit === 0 ? '\u2190 left' : '\u2192 right';
        const mark = r.hit === null ? '\u00b7' : (r.hit ? 'hole' : 'miss');
        const src = r.src === 'q' ? 'quantum' : 'local';
        return '<tr><td>' + hhmm + '</td><td>' + vow + '</td><td>' + draw + '</td><td class="' + r.src + '">' + src + '</td><td>' + mark + '</td><td><code>0x' + r.byte + '</code></td></tr>';
    }).join('');
    box.innerHTML = '<table id="receipt-table"><thead><tr><th>at</th><th>vow</th><th>draw</th><th>src</th><th>verdict</th><th>byte 8</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

// ---------- THE BUTTONS ----------
// guess left / guess right: arm it, and the NEXT draw is graded against it.
// just watch: unarm everything, the stream keeps flowing, all baseline.

document.querySelectorAll('.vow-btn').forEach(b => {
    b.addEventListener('click', () => {
        const m = b.dataset.mode;
        if (m === 'watch') {
            pendingGuess = null;
            pendingReceipt = null;
            setBanner('watching, unweighted', 'the oracle keeps streaming. every draw is baseline. arm a guess whenever you like.');
        } else {
            armGuess(m);
        }
        updatePanel();
    });
});

// the colour flow: the SECOND animation. every draw sends a band of colour
// sweeping across the stage in the direction the oracle leaned: cool cyan for
// left, hot pink for right. it fades as it goes and cleans itself up.
function flowSweep(bit) {
    const old = document.getElementById('flow');
    if (old) old.remove();
    const d = document.createElement('div');
    d.id = 'flow';
    d.className = 'flow-sweep ' + (bit === 0 ? 'flow-left' : 'flow-right');
    stage.appendChild(d);
    setTimeout(() => { if (d.parentNode) d.remove(); }, 1800);
}

// ledger reset: staged like everything else on this site, confirm first
document.getElementById('reset-ledger').addEventListener('click', () => {
    if (!confirm('burn the whole ledger? every trial, both sources, all receipts.')) return;
    ledger = { q: { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } },
        f: { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } },
        wq: { n: 0, ones: 0 }, wf: { n: 0, ones: 0 }, receipts: [] };
    gauge.targetZ = 0; gauge.targetF = null; gauge.shownF = null;
    pendingGuess = null; pendingReceipt = null;
    saveLedger();
    updatePanel();
    renderReceipts();
    setBanner('ledger burned', 'clean slate. the oracle never kept anything anyway.');
});

// the ledger, exportable: your trials, your receipts, your data. nothing
// leaves the browser unless you press this and paste it somewhere yourself.
document.getElementById('export-ledger').addEventListener('click', () => {
    const out = {
        experiment: 'the drift · experiment no.3, live',
        url: 'https://luluxtentacles.github.io/experiments/the-drift/',
        protocol: 'the oracle streams fresh draws continuously (arm happens BEFORE the draw it is spent on): arm left/right -> sha-256 commit shown in the receipt -> the NEXT 128-byte draw from the scrying relay (qrandom.io) is graded against the armed guess -> verdict bit = byte 8 & 1, then the guess is spent. unarm (just watch) streams baseline trials scored on parity only. local-fallback trials are tagged "f" and scored in their own ledger, never pooled.',
        exported_at: new Date().toISOString(),
        ledger: ledger
    };
    const text = JSON.stringify(out, null, 2);
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            setBanner('ledger copied to clipboard', receiptCountLine());
        }, () => setBanner('the clipboard refused', 'the ledger stays here; nobody can force a copy.'));
    } else {
        setBanner('no clipboard here', 'the ledger stays here; nothing left the browser.');
    }
});

function receiptCountLine() {
    return ledger.receipts.length + ' receipts, both ledgers, the watch parity - all of it, as json.';
}

// ---------- THE PENDULUM (canvas) ----------
const gauge = {
    targetZ: 0,       // pooled quantum z, eased toward
    targetF: null,    // pooled local z, grey trailing needle
    shownZ: 0,
    shownF: null,
    flashAt: 0,
    flashSide: 0,     // -1 / +1: which way the LAST draw leaned, for the ghost sweep
    canvas: document.getElementById('pendulum'),
    reduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches
};

function resizeCanvas() {
    const c = gauge.canvas;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = c.clientWidth, h = c.clientHeight;
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener('resize', resizeCanvas);

function drawGauge() {
    const c = gauge.canvas;
    const ctx = c.getContext('2d');
    const w = c.clientWidth, h = c.clientHeight;
    const now = performance.now();

    const cx = w / 2;
    const pivotY = 26;
    const arm = Math.min(h - 70, w * 0.34);
    const maxDeg = 42;
    const degPerZ = maxDeg / 3.0;                 // z = 3 at the rail
    const showZ = Math.max(-3.5, Math.min(3.5, gauge.shownZ));

    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(cx, pivotY);

    // axis
    ctx.strokeStyle = 'rgba(255,215,239,0.14)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, arm + 26); ctx.stroke();

    // sigma ticks along the swing arc
    ctx.font = '10px "Space Mono", monospace';
    ctx.fillStyle = 'rgba(255,215,239,0.4)';
    ctx.textAlign = 'center';
    for (let s = -3; s <= 3; s++) {
        const ang = (s * degPerZ) * Math.PI / 180;
        const tx = Math.sin(ang) * (arm + 18);
        const ty = Math.cos(ang) * (arm + 18);
        if (s !== 0) {
            ctx.fillStyle = 'rgba(255,215,239,0.35)';
            ctx.fillText((s > 0 ? '+' : '') + s + '\u03c3', tx, ty + 3);
        }
    }

    // the noise band wedge
    const bandHalf = (1.96 * degPerZ) * Math.PI / 180;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, arm + 4, Math.PI / 2 - bandHalf, Math.PI / 2 + bandHalf);
    ctx.closePath();
    ctx.fillStyle = 'rgba(255,110,199,0.06)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,110,199,0.16)';
    ctx.setLineDash([3, 5]);
    ctx.stroke();
    ctx.setLineDash([]);

    // the drift band beyond it: where the needle has no business sitting by luck
    ctx.beginPath();
    ctx.arc(0, 0, arm + 4, Math.PI / 2 - (Math.PI / 2), Math.PI / 2 - bandHalf, false);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, arm + 4, Math.PI / 2 + bandHalf, Math.PI / 2 + (Math.PI / 2), false);
    ctx.stroke();

    // the ghost draw: a comet that leaps the way the LAST draw leaned, so the
    // stage visibly moves left and right with every single update, live.
    const flashAge = now - gauge.flashAt;
    if (gauge.flashSide !== 0 && flashAge < 1100 && !gauge.reduced) {
        const a = 1 - flashAge / 1100;
        const gx = gauge.flashSide * (0.12 + 0.30 * (1 - a)) * w / 2;
        const gy = h * 0.30 + Math.sin(now / 240 + gauge.flashAt) * 6;
        ctx.fillStyle = gauge.flashSide < 0
            ? 'rgba(110,211,255,' + (0.4 * a).toFixed(3) + ')'
            : 'rgba(255,110,199,' + (0.4 * a).toFixed(3) + ')';
        ctx.beginPath(); ctx.arc(gx, gy, 4 + (1 - a) * 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = ctx.fillStyle;
        ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(gx - gauge.flashSide * 30, gy); ctx.stroke();
    }

    // the wisps: one per draw, drifting the way the bit leaned
    gauge.wisps = gauge.wisps || [];
    gauge.wisps = gauge.wisps.filter(ws => now - ws.born < 2200);
    gauge.wisps.forEach(ws => {
        const age = (now - ws.born) / 2200;
        const wx = cx + ws.dir * age * w * 0.48;
        const wy = h * 0.52 + Math.sin(now / 300 + ws.born) * 9;
        ctx.fillStyle = 'rgba(255,110,199,' + (0.5 * (1 - age)).toFixed(3) + ')';
        ctx.beginPath(); ctx.arc(wx, wy, 3 + age * 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = 'rgba(255,110,199,' + (0.22 * (1 - age)).toFixed(3) + ')';
        ctx.beginPath(); ctx.moveTo(wx, wy); ctx.lineTo(wx - ws.dir * 26, wy); ctx.stroke();
    });

    // the needle: the cumulative score, always easing, always quivering while live
    const easeT = gauge.reduced ? 1 : 0.06;
    const quiver = (inFlight && !gauge.reduced)
        ? Math.sin(now / 55) * 0.9 * Math.PI / 180
        : Math.sin(now / 900) * 0.3 * Math.PI / 180;   // a lazy breath, always alive
    const angQ = gauge.targetZ * degPerZ * Math.PI / 180 + quiver;
    gauge.shownZ += (gauge.targetZ - gauge.shownZ) * easeT;
    const ang = gauge.shownZ * degPerZ * Math.PI / 180;

    // grey needle: the local-fallback ledger, trailing
    if (gauge.targetF !== null) {
        gauge.shownF = gauge.shownF === null ? gauge.targetF : gauge.shownF + (gauge.targetF - gauge.shownF) * easeT;
        const angF = Math.max(-3.5, Math.min(3.5, gauge.shownF)) * degPerZ * Math.PI / 180;
        ctx.strokeStyle = 'rgba(255,255,255,0.25)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(Math.sin(angF) * arm, Math.cos(angF) * arm);
        ctx.stroke();
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.beginPath();
        ctx.arc(Math.sin(angF) * arm, Math.cos(angF) * arm, 3, 0, Math.PI * 2);
        ctx.fill();
    }

    // pink quantum needle
    ctx.shadowColor = 'rgba(255,46,166,0.8)';
    ctx.shadowBlur = 10 + (gauge.flashAt ? Math.max(0, 14 * (1 - flashAge / 900)) : 0);
    ctx.strokeStyle = '#ff6ec7';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.sin(ang) * arm, Math.cos(ang) * arm);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // bob
    const bx = Math.sin(ang) * arm, by = Math.cos(ang) * arm;
    ctx.fillStyle = '#ff2ea6';
    ctx.shadowColor = 'rgba(255,46,166,0.9)';
    ctx.shadowBlur = 14;
    ctx.beginPath();
    ctx.arc(bx, by, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // pivot
    ctx.fillStyle = 'rgba(255,215,239,0.7)';
    ctx.beginPath(); ctx.arc(0, 0, 3.5, 0, Math.PI * 2); ctx.fill();

    // live z under the pivot
    ctx.font = '13px "Space Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(255,215,239,0.75)';
    ctx.fillText('z = ' + (gauge.targetZ === 0 ? '\u2014' : (gauge.targetZ >= 0 ? '+' : '\u2212') + Math.abs(gauge.targetZ).toFixed(2) + '  (pooled, quantum)'), 0, arm + 44);

    ctx.restore();

    requestAnimationFrame(drawGauge);
}

// ---------- BOOT ----------
resizeCanvas();
drawGauge();
loadLedger();
// the needle starts where the persisted ledger says it should
if (ledger.q.n) {
    gauge.targetZ = binomZ(ledger.q.h, ledger.q.n);
    gauge.shownZ = gauge.targetZ;
}
if (ledger.f.n) gauge.targetF = binomZ(ledger.f.h, ledger.f.n);
updatePanel();
renderReceipts();
streamLoop();   // the oracle is on from the moment the page opens
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    setBanner('the oracle is streaming', 'reduced-motion portrait: the machine is live and readable; the comet and the colour flow are still, the needle moves only as the ledger moves.');
}
