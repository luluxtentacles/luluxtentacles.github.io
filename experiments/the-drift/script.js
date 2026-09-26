/* ==========================================================================
   the drift · experiment no.3 · live quantum intention test
   --------------------------------------------------------------------------
   the mechanic, in one line: you vow a direction, the intent locks, and only
   then does the page ask the quantum oracle for a FRESH draw. the verdict bit
   is the parity of byte 8 of that draw. nothing is stored, nothing is replayed,
   nothing decides before you do. that was the whole confound of experiment
   the rehearsal: there the recording predates the intent on purpose.
   here the coin has not been flipped until after your hand is off the glass.

   entropy: master's cloudflare relay -> qrandom.io, same shape as the scrying
   glass (tentacle_samples/animation.js): 128 hex bytes, abort at 6s, two
   attempts, then fall back to local crypto entropy with the source disclosed.
   the scrying glass reads bytes 0,1,2,4,6 for its shape. this page reads
   byte 8, so the two machines keep different fingers on the same stream.

   scoring: PEAR-style. every intended trial is a hit if the verdict leans the
   way you vowed. z = (2h - n) / sqrt(n) over the pooled intended trials,
   one-tailed p in the vowed direction, computed with the erfc approximation.
   watch-mode trials are pre-declared baseline: they are logged, never scored.
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
                wq: saved.wq, wf: saved.wf,
                receipts: saved.receipts.slice(0, 30)
            };
        }
    } catch (e) { /* a broken ledger starts clean, nothing else is touched */ }
}
function fixBin(b) {
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

// ---------- TRIAL MACHINE ----------
// phases: idle -> awaiting (oracle in flight) -> idle. watch streams, no hold.
// the intent is COMMITTED before the fetch: a sha-256 of mode|timestamp|nonce
// is shown in the receipt. that is not cryptography against the browser, the
// client can always lie to itself, and the method notes say so. it is a receipt
// that the page asked the oracle AFTER the vow, in the order you can check.

let mode = 'left';              // 'left' | 'right' | 'watch'
let phase = 'idle';
let watching = false;           // watch mode streams draws continuously
let pendingReceipt = null;      // the commit, kept until the draw lands

async function castVow() {
    if (phase !== 'idle') return;
    const intended = mode;
    const ts = Date.now();
    const nonce = crypto.getRandomValues(new Uint8Array(8));
    const nonceHex = Array.from(nonce).map(b => b.toString(16).padStart(2, '0')).join('');
    let commit = '';
    try {
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(intended + '|' + ts + '|' + nonceHex));
        commit = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
    } catch (e) { commit = nonceHex.slice(0, 16); } // old browsers still get a nonce

    pendingReceipt = { mode: intended, ts, commit };
    phase = 'awaiting';
    setBanner('oracle reached for\u2026', 'the vow is locked, the draw is in flight. no replay exists.');
    updatePanel();

    let hex, src;
    try {
        hex = await fetchQuantumHex(128);
        src = 'q';
    } catch (e) {
        console.warn('[the drift] oracle unreachable, local fallback:', e);
        hex = localEntropyHex(128);
        src = 'f';
    }

    // a draw the user never vowed for is still a fresh draw, but it is not a
    // trial: it is logged as watch/no-score only if the vow was watch mode.
    let result;
    try {
        result = verdictFromHex(hex);
    } catch (e) {
        phase = 'idle';
        setBanner('the oracle muttered', 'short draw, discarded. vow again.');
        pendingReceipt = null;
        updatePanel();
        return;
    }

    const bin = src === 'q' ? ledger.q : ledger.f;
    const hit = (intended === 'left' && result.bit === 0) || (intended === 'right' && result.bit === 1);

    // one wisp per draw, drifting the way the bit leaned: the stage breathes
    if (gauge.wisps.length > 14) gauge.wisps.shift();
    gauge.wisps.push({ dir: result.bit * 2 - 1, born: performance.now() });

    if (intended === 'watch') {
        const w = src === 'q' ? ledger.wq : ledger.wf;
        w.n++;
        if (result.bit === 1) w.ones++;
    } else {
        bin.n++; bin[intended].n++;
        if (hit) { bin.h++; bin[intended].h++; }
    }

    const rec = {
        t: ts,
        mode: intended,
        bit: result.bit,
        src,
        hit: intended === 'watch' ? null : (hit ? 1 : 0),
        byte: result.byteHex,
        commit
    };
    ledger.receipts.unshift(rec);
    ledger.receipts = ledger.receipts.slice(0, 30);
    saveLedger();

    phase = 'idle';
    pendingReceipt = null;

    // needle target: pooled quantum z. fallback draws move the grey needle only.
    const zq = binomZ(ledger.q.h, ledger.q.n);
    const zf = binomZ(ledger.f.h, ledger.f.n);
    if (src === 'q') gauge.targetZ = zq === null ? 0 : zq;
    gauge.targetF = zf === null ? null : zf;
    gauge.flashAt = performance.now();

    if (intended === 'watch') {
        setBanner(src === 'q' ? 'watched, unhonored' : 'watched, unhonored (local)',
            'baseline trial, no score. the draw leaned ' + sideWord(result.bit) + '.');
    } else if (hit) {
        setBanner(src === 'q' ? 'the oracle honored the vow' : 'honored, but by the local fall',
            'a ' + sideWord(result.bit) + ' draw against a ' + intended + ' vow. ledger updated.');
    } else {
        setBanner(src === 'q' ? 'the oracle broke the vow' : 'broken, but by the local fall',
            'a ' + sideWord(result.bit) + ' draw against your ' + intended + '. ledger updated.');
    }
    updatePanel();
    renderReceipts();
}

function sideWord(bit) { return bit === 0 ? 'LEFT' : 'RIGHT'; }

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
        headline.textContent = 'no quantum trials yet. vow a side, tap, the draw answers.';
    } else if (Math.abs(zq) < 1) {
        headline.textContent = 'the needle sits inside the noise band. so far, the oracle does not care.';
    } else if (Math.abs(zq) < 2) {
        headline.textContent = 'outside the noise band but short of two sigma. not nothing, not yet anything. vow more.';
    } else if (pq < 0.01) {
        headline.textContent = 'past two sigma in the vowed direction. either you are bending it, or you got lucky within one in ' + Math.round(1 / (pq * 100)) + '. keep vowing.';
    } else {
        headline.textContent = 'past two sigma in the vowed direction. vow more before you believe it.';
    }

    // mode buttons
    document.querySelectorAll('.vow-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
    });
}

function renderReceipts() {
    const box = document.getElementById('receipts');
    if (!ledger.receipts.length) {
        box.innerHTML = '<p class="foot-note" id="no-receipts">no draws yet. the ledger starts when you do.</p>';
        return;
    }
    const rows = ledger.receipts.map(r => {
        const t = new Date(r.t);
        const hhmm = t.toTimeString().slice(0, 8);
        const vow = r.mode === 'left' ? '\u2190 vow' : r.mode === 'right' ? 'vow \u2192' : '\u25cb watch';
        const draw = r.bit === 0 ? '\u2190 left' : '\u2192 right';
        const mark = r.hit === null ? '\u00b7' : (r.hit ? 'hole' : 'miss');
        const src = r.src === 'q' ? 'quantum' : 'local';
        return '<tr><td>' + hhmm + '</td><td>' + vow + '</td><td>' + draw + '</td><td class="' + r.src + '">' + src + '</td><td>' + mark + '</td><td><code>0x' + r.byte + '</code></td></tr>';
    }).join('');
    box.innerHTML = '<table id="receipt-table"><thead><tr><th>at</th><th>vow</th><th>draw</th><th>src</th><th>verdict</th><th>byte 8</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

// ---------- THE BUTTONS ----------
// no hold, no charge: a tap is a vow, committed the instant it lands.
// watch is a toggle that streams the oracle, draw after draw, live.

function setMode(m) {
    mode = m;
    updatePanel();
    if (m === 'watch') {
        setBanner('watching, unweighted', 'the oracle is streaming. every draw is baseline. tap watch again to stop.');
    } else {
        setBanner('vow set: ' + m, 'tap again to draw. the draw comes after the vow, never before.');
    }
}

document.querySelectorAll('.vow-btn').forEach(b => {
    b.addEventListener('click', () => {
        if (phase !== 'idle') return;
        const m = b.dataset.mode;
        if (m === 'watch' && watching) {          // the stream rests
            watching = false;
            mode = 'left';
            updatePanel();
            setBanner('the stream rests', 'watch paused. the ledger keeps what it saw.');
            return;
        }
        setMode(m);
        if (m === 'watch') streamWatch();
        else castVow();
    });
});

async function streamWatch() {
    while (watching && mode === 'watch' && phase === 'idle') {
        await castVow();
        if (!watching) break;
        await new Promise(r => setTimeout(r, 650));
    }
}

// ledger reset: staged like everything else on this site, confirm first
document.getElementById('reset-ledger').addEventListener('click', () => {
    if (!confirm('burn the whole ledger? every trial, both sources, all receipts.')) return;
    ledger = { q: { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } },
        f: { n: 0, h: 0, left: { n: 0, h: 0 }, right: { n: 0, h: 0 } },
        wq: { n: 0, ones: 0 }, wf: { n: 0, ones: 0 }, receipts: [] };
    gauge.targetZ = 0; gauge.targetF = null;
    saveLedger();
    updatePanel();
    renderReceipts();
    setBanner('ledger burned', 'clean slate. the oracle remembers nothing either.');
});

// the ledger, exportable: your trials, your receipts, your data. nothing
// leaves the browser unless you press this and paste it somewhere yourself.
document.getElementById('export-ledger').addEventListener('click', () => {
    const out = {
        experiment: 'the drift · experiment no.3, live',
        url: 'https://luluxtentacles.github.io/experiments/the-drift/',
        protocol: 'vow (left=bit 0, right=bit 1, watch=baseline, tap to commit) -> fresh 128-byte draw from the scrying relay (qrandom.io) AFTER the commit -> verdict bit = byte 8 & 1. watch mode streams baseline trials continuously. local-fallback trials are tagged "f" and scored in their own ledger, never pooled.',
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
    wisps: [],        // one drifting wisp per watch draw
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
    ctx.clearRect(0, 0, w, h);

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

    // the stream: one wisp per draw, drifting the way the bit leaned
    const now = performance.now();
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

    // the needle
    const easeT = gauge.reduced ? 1 : 0.06;
    const flashAge = (performance.now() - gauge.flashAt);
    const flash = Math.max(0, 1 - flashAge / 900);
    const quiver = ((phase === 'awaiting' || watching) && !gauge.reduced)
        ? Math.sin(performance.now() / 55) * 0.8 * Math.PI / 180
        : 0;
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
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    setBanner('reduced motion portrait', 'the machine is live and readable; the needle moves only when a draw lands.');
}
