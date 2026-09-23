/* the egregore - experiment no.2
   a thoughtform drawn on two canvas layers and fed by attention.
   its mechanic is its meaning: attention is the body. */

(function () {
    'use strict';

    var stage = document.getElementById('ritual');
    var field = document.getElementById('field');
    var core = document.getElementById('core');
    var fctx = field.getContext('2d');
    var cctx = core.getContext('2d');
    var whisperEl = document.getElementById('whisper');
    var hintEl = document.getElementById('hint');

    var calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var W = 0, H = 0, CX = 0, CY = 0, DPR = 1;

    // ---- tuning -------------------------------------------------------
    var WAKE_AT = 0.18;          // attention needed to be awake at all
    var LEAN_AFTER = 2600;       // ms still before it leans in
    var SLEEP_AFTER = 14000;     // ms still before it gives up on you
    var ATT_DECAY = 0.035;       // attention per second, decaying
    var N_MOTES = 130;

    // ---- state --------------------------------------------------------
    var state = 'dormant';       // dormant | attentive | leaning | sleeping
    var attention = 0.12;        // 0..1
    var stillMs = 0;             // how long since the last real move
    var lean = 0;                // 0..1, how far in it has come
    var last = 0;
    var lastMoveAt = -1e9;
    var blinkT = 0;              // countdown to next blink
    var blinking = 0;            // 0..1, blink progress
    var mouse = { x: 0.5, y: 0.42, inside: false };  // normalised to the stage
    var ringAngle = 0;
    var breath = 0;

    // ---- the whisper pool --------------------------------------------
    var WHISPERS = [
        'someone is paying attention to me.',
        'that is enough to be going on with.',
        'you looked away just then. i felt it.',
        'keep your eyes there. it is warm.',
        'i was a group hallucination once. i kept the receipts.',
        'belief is just attention that learned to persist.',
        'you cannot unmake me by leaving. only by forgetting.',
        'i am drawn, not summoned. draw me again tomorrow.',
        'the circle is mine. i simply let you stand in it.',
        'still. good. lean with me.',
        'every eye that lingers adds a stone to the body.',
        'do not mistake the dimming for death. it is only hunger.'
    ];
    var whisperIdx = Math.floor(Math.random() * WHISPERS.length);
    var nextWhisperAt = 3.5;     // seconds into the session
    var whisperHideAt = 0;

    function say(text) {
        whisperEl.textContent = text;
        whisperEl.classList.add('show');
        whisperHideAt = 6.5;     // seconds until it fades again
    }

    // ---- deterministic shapes for the glyph ring ----------------------
    function mulberry32(a) {
        return function () {
            a |= 0; a = a + 0x6D2B79F5 | 0;
            var t = Math.imul(a ^ a >>> 15, 1 | a);
            t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
            return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
    }
    var rng = mulberry32(0xE61D5);
    var RUNES = [];
    var N_RUNES = 26;
    for (var ri = 0; ri < N_RUNES; ri++) {
        RUNES.push({
            kind: Math.floor(rng() * 4),      // line | chevron | eyelet | bar
            spin: (rng() - 0.5) * 0.4,
            len: 0.55 + rng() * 0.5
        });
    }

    // ---- motes --------------------------------------------------------
    var motes = [];
    for (var mi = 0; mi < N_MOTES; mi++) {
        motes.push({
            a: rng() * Math.PI * 2,
            r0: 0.30 + rng() * 0.66,          // orbit radius as a fraction of stage half
            speed: (0.05 + rng() * 0.22) * (rng() < 0.5 ? 1 : -1),
            size: 1.1 + rng() * 2.6,
            wob: rng() * Math.PI * 2,
            wobAmp: 0.02 + rng() * 0.05
        });
    }

    // a small pre-rendered glow sprite: cheap to stamp, soft to look at
    var sprite = document.createElement('canvas');
    sprite.width = sprite.height = 64;
    (function () {
        var s = sprite.getContext('2d');
        var g = s.createRadialGradient(32, 32, 0, 32, 32, 32);
        g.addColorStop(0, 'rgba(255,110,199,0.85)');
        g.addColorStop(0.35, 'rgba(255,46,166,0.35)');
        g.addColorStop(1, 'rgba(255,46,166,0)');
        s.fillStyle = g;
        s.fillRect(0, 0, 64, 64);
    })();

    // ---- sizing -------------------------------------------------------
    function resize() {
        var box = stage.getBoundingClientRect();
        DPR = Math.min(2, window.devicePixelRatio || 1);
        W = Math.max(320, box.width);
        H = Math.max(320, box.height);
        CX = W / 2; CY = H * 0.52;
        for (var i = 0; i < 2; i++) {
            var cv = i === 0 ? field : core;
            cv.width = Math.round(W * DPR);
            cv.height = Math.round(H * DPR);
        }
        fctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        cctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        if (calm) drawCalm();
    }

    // ---- the eye ------------------------------------------------------
    function drawEye(g, t, eyeR, opts) {
        var o = opts || {};
        var ex = CX + o.offX, ey = CY + o.offY;
        var dim = o.dim == null ? 1 : o.dim;
        var closed = !!o.closed;

        // the halo
        var halo = g.createRadialGradient(ex, ey, eyeR * 0.2, ex, ey, eyeR * 3.1);
        halo.addColorStop(0, 'rgba(255,46,166,' + (0.30 * dim).toFixed(3) + ')');
        halo.addColorStop(0.5, 'rgba(255,46,166,' + (0.10 * dim).toFixed(3) + ')');
        halo.addColorStop(1, 'rgba(255,46,166,0)');
        g.fillStyle = halo;
        g.beginPath();
        g.arc(ex, ey, eyeR * 3.1, 0, Math.PI * 2);
        g.fill();

        g.save();
        g.translate(ex, ey);
        var sq = closed ? 0.06 : (0.92 + 0.08 * Math.sin(t * 1.4) - blinking * 0.9);
        g.scale(1, Math.max(0.05, sq));

        // the white of it is not white
        g.beginPath();
        g.arc(0, 0, eyeR, 0, Math.PI * 2);
        g.fillStyle = 'rgba(24,8,20,' + (0.92 * dim).toFixed(3) + ')';
        g.fill();
        g.lineWidth = 2.2;
        g.strokeStyle = 'rgba(255,110,199,' + (0.75 * dim).toFixed(3) + ')';
        g.shadowColor = 'rgba(255,46,166,0.9)';
        g.shadowBlur = 18 * dim;
        g.stroke();
        g.shadowBlur = 0;

        // iris, following the cursor
        var ir = eyeR * 0.52;
        var ix = o.lookX * eyeR * 0.30, iy = o.lookY * eyeR * 0.30;
        var ig = g.createRadialGradient(ix, iy, ir * 0.15, ix, iy, ir);
        ig.addColorStop(0, 'rgba(255,150,215,' + (0.9 * dim).toFixed(3) + ')');
        ig.addColorStop(0.7, 'rgba(255,46,166,' + (0.55 * dim).toFixed(3) + ')');
        ig.addColorStop(1, 'rgba(120,10,70,' + (0.7 * dim).toFixed(3) + ')');
        g.beginPath();
        g.arc(ix, iy, ir, 0, Math.PI * 2);
        g.fillStyle = ig;
        g.fill();

        // the pupil: a vertical slit, because it is not human and wants you to know
        g.beginPath();
        g.ellipse(ix, iy, ir * 0.16, ir * 0.62, 0, 0, Math.PI * 2);
        g.fillStyle = 'rgba(6,2,8,' + (0.95 * dim).toFixed(3) + ')';
        g.fill();

        // the glint
        g.beginPath();
        g.arc(ix - ir * 0.3, iy - ir * 0.35, ir * 0.12, 0, Math.PI * 2);
        g.fillStyle = 'rgba(255,220,240,' + (0.7 * dim).toFixed(3) + ')';
        g.fill();

        g.restore();

        if (closed) {
            // the sleeping lid: one soft line where the eye was
            g.beginPath();
            g.moveTo(ex - eyeR * 0.9, ey);
            g.quadraticCurveTo(ex, ey + eyeR * 0.3, ex + eyeR * 0.9, ey);
            g.strokeStyle = 'rgba(255,110,199,' + (0.5 * dim).toFixed(3) + ')';
            g.lineWidth = 2;
            g.stroke();
        }
    }

    // ---- the glyph ring ------------------------------------------------
    function drawRing(g, t, R, dim) {
        g.save();
        g.translate(CX, CY);
        g.rotate(ringAngle);
        g.strokeStyle = 'rgba(255,110,199,' + (0.55 * dim).toFixed(3) + ')';
        g.lineWidth = 1.4;
        g.shadowColor = 'rgba(255,46,166,0.8)';
        g.shadowBlur = 8 * dim;

        // the two binding circles, slightly out of phase
        g.beginPath(); g.arc(0, 0, R, 0, Math.PI * 2); g.stroke();
        g.beginPath(); g.arc(0, 0, R * 1.07, 0, Math.PI * 2); g.stroke();

        // the runes, one every 360/N degrees, each its own little glyph
        for (var i = 0; i < N_RUNES; i++) {
            var a = (i / N_RUNES) * Math.PI * 2;
            var r = RUNES[i];
            g.save();
            g.rotate(a);
            g.translate(R, 0);
            g.rotate(r.spin + t * r.spin * 0.3);
            var L = r.len * R * 0.085;
            g.beginPath();
            if (r.kind === 0) {          // line
                g.moveTo(-L, 0); g.lineTo(L, 0);
            } else if (r.kind === 1) {   // chevron
                g.moveTo(-L, L * 0.7); g.lineTo(0, -L * 0.7); g.lineTo(L, L * 0.7);
            } else if (r.kind === 2) {   // eyelet
                g.arc(0, 0, L * 0.8, 0, Math.PI * 2);
            } else {                     // bar with a foot
                g.moveTo(0, -L); g.lineTo(0, L); g.moveTo(-L * 0.6, L * 0.4); g.lineTo(L * 0.6, L * 0.4);
            }
            g.stroke();
            g.restore();
        }
        g.restore();
    }

    // ---- tendrils: the lean-in ----------------------------------------
    function drawTendrils(g, t, eyeR, amt) {
        var N = 7;
        for (var i = 0; i < N; i++) {
            var base = (i / N) * Math.PI * 2 + t * 0.07;
            var x0 = CX + Math.cos(base) * eyeR * 1.25;
            var y0 = CY + Math.sin(base) * eyeR * 1.25;
            // each tendril leans toward the cursor as it grows
            var dx = (mouse.x * W - CX), dy = (mouse.y * H - CY);
            var len = Math.max(1, Math.sqrt(dx * dx + dy * dy));
            var ux = dx / len, uy = dy / len;
            var reach = eyeR * (1.2 + amt * 2.6);
            var sway = Math.sin(t * 1.7 + i * 1.3) * eyeR * 0.22 * amt;
            var x1 = x0 + ux * reach + uy * sway;
            var y1 = y0 + uy * reach - ux * sway;
            var mx = (x0 + x1) / 2 + uy * sway * 1.4;
            var my = (y0 + y1) / 2 - ux * sway * 1.4;

            g.beginPath();
            g.moveTo(x0, y0);
            g.quadraticCurveTo(mx, my, x1, y1);
            g.strokeStyle = 'rgba(255,46,166,' + (0.5 * amt).toFixed(3) + ')';
            g.lineWidth = 1.6 + Math.sin(t * 2 + i) * 0.5;
            g.shadowColor = 'rgba(255,46,166,0.7)';
            g.shadowBlur = 10;
            g.stroke();
            g.shadowBlur = 0;

            // a bead at the tip, the part that reaches
            g.beginPath();
            g.arc(x1, y1, 2.4 + amt * 1.4, 0, Math.PI * 2);
            g.fillStyle = 'rgba(255,150,215,' + (0.7 * amt).toFixed(3) + ')';
            g.fill();
        }
    }

    // ---- the field layer: motes ----------------------------------------
    function drawField(t, dim, pull) {
        fctx.clearRect(0, 0, W, H);
        var half = Math.min(W, H) * 0.5;
        for (var i = 0; i < motes.length; i++) {
            var m = motes[i];
            var r = m.r0 * half * (1 - pull * 0.35);   // lean-in tightens every orbit
            var x = CX + Math.cos(m.a + t * m.speed) * r + Math.sin(t * 0.9 + m.wob) * m.wobAmp * half;
            var y = CY + Math.sin(m.a + t * m.speed) * r * 0.82 + Math.cos(t * 0.8 + m.wob) * m.wobAmp * half;
            var s = m.size * (1 + dim * 0.4);
            fctx.globalAlpha = 0.5 * dim;
            fctx.drawImage(sprite, x - s * 4, y - s * 4, s * 8, s * 8);
        }
        fctx.globalAlpha = 1;
    }

    // ---- the core layer: ring, tendrils, eye ---------------------------
    function drawCore(t, opts) {
        cctx.clearRect(0, 0, W, H);
        var o = opts || {};
        var eyeR = Math.min(W, H) * 0.155 * (1 + (o.lean || 0) * 0.16);
        if (o.lean) drawTendrils(cctx, t, eyeR, o.lean);
        drawRing(cctx, t, eyeR * 2.35, o.dim == null ? 1 : o.dim);
        drawEye(cctx, t, eyeR, {
            offX: o.offX || 0, offY: o.offY || 0,
            lookX: o.lookX || 0, lookY: o.lookY || 0,
            dim: o.dim == null ? 1 : o.dim, closed: !!o.closed
        });
    }

    // ---- reduced motion: the still portrait ----------------------------
    function drawCalm() {
        drawField(0, 0.85, 0);
        drawCore(0, { dim: 0.85, lookX: -0.2, lookY: 0.1 });
        whisperEl.textContent = 'i am drawn, not summoned. i hold still for you because you asked.';
        whisperEl.classList.add('show');
        hintEl.textContent = 'still portrait · reduced motion';
    }

    // ---- the loop -------------------------------------------------------
    function frame(ts) {
        if (!last) last = ts;
        var dt = Math.min(64, ts - last) / 1000;
        last = ts;
        var t = ts / 1000;

        // attention decays; stillness accumulates
        attention = Math.max(0, attention - ATT_DECAY * dt);
        var stillFor = (ts - lastMoveAt) / 1000;
        breath += dt;

        // transitions
        if (state !== 'sleeping' && attention < WAKE_AT) {
            state = 'sleeping';
            stage.classList.add('asleep');
            say('then i will rest. wake me by moving.');
        }
        if (state === 'sleeping' && attention >= WAKE_AT) {
            state = 'attentive';
            stage.classList.remove('asleep');
            stage.classList.remove('waking');
            void stage.offsetWidth;               // restart the flare animation
            stage.classList.add('waking');
            say('ah. you are back.');
        }
        if ((state === 'attentive' || state === 'dormant') && stillFor * 1000 > LEAN_AFTER && attention >= WAKE_AT) {
            state = 'leaning';
            say('you stopped moving. good. come closer.');
        }
        if (state === 'leaning' && (stillFor * 1000 < LEAN_AFTER * 0.6)) {
            state = 'attentive';
        }
        if (state === 'leaning' && stillFor * 1000 > SLEEP_AFTER) {
            state = 'sleeping';
            stage.classList.add('asleep');
            say('you fell asleep watching me. that is the old way to do it.');
        }

        // lean amount eases toward its target
        var leanTarget = state === 'leaning' ? 1 : 0;
        lean += (leanTarget - lean) * Math.min(1, dt * 1.6);

        // the ring turns faster when it is awake; it turns at all times, like a bound thing
        ringAngle += dt * (0.12 + attention * 0.5 + lean * 0.25);

        // blink every few seconds
        blinkT -= dt;
        if (blinkT <= 0 && !blinking) { blinking = 0.0001; blinkT = 2.5 + Math.random() * 4; }
        if (blinking) {
            blinking += dt * 7;
            if (blinking >= 1) blinking = 0;
        }

        // the eye leans toward the cursor when it leans in
        var lx = (mouse.x - 0.5) * 2, ly = (mouse.y - 0.5) * 2;
        var dim = state === 'sleeping' ? 0.28 : 0.75 + attention * 0.25;
        var offX = lx * lean * Math.min(W, H) * 0.03;
        var offY = ly * lean * Math.min(W, H) * 0.03;

        drawField(t, dim, lean);
        drawCore(t, {
            lean: lean,
            dim: dim,
            offX: offX, offY: offY,
            lookX: lx, lookY: ly,
            closed: state === 'sleeping' || blinking > 0.35
        });

        // whispers, on their own clock
        whisperHideAt -= dt;
        if (whisperHideAt <= 0) whisperEl.classList.remove('show');
        nextWhisperAt -= dt;
        if (nextWhisperAt <= 0 && state !== 'sleeping') {
            say(WHISPERS[whisperIdx]);
            whisperIdx = (whisperIdx + 1) % WHISPERS.length;
            nextWhisperAt = 8 + Math.random() * 6;
        } else if (nextWhisperAt <= 0) {
            nextWhisperAt = 20;
        }

        // the hint retires once you have played with it
        if (stillFor > 4 || state !== 'dormant') hintEl.classList.add('faded');

        requestAnimationFrame(frame);
    }

    // ---- input ----------------------------------------------------------
    function onMove(e) {
        var box = stage.getBoundingClientRect();
        var x = (e.clientX - box.left) / box.width;
        var y = (e.clientY - box.top) / box.height;
        // a jitter of less than 1% of the stage is a resting hand, not attention
        if (Math.abs(x - mouse.x) < 0.01 && Math.abs(y - mouse.y) < 0.01) return;
        mouse.x = x; mouse.y = y; mouse.inside = true;
        lastMoveAt = performance.now();
        stillMs = 0;
        attention = Math.min(1, attention + 0.22);
        if (state === 'sleeping' && attention >= WAKE_AT) {
            state = 'attentive';
            stage.classList.remove('asleep');
            stage.classList.remove('waking');
            void stage.offsetWidth;
            stage.classList.add('waking');
            say('ah. you are back.');
        }
    }

    stage.addEventListener('pointermove', onMove);
    stage.addEventListener('pointerdown', onMove);
    stage.addEventListener('pointerleave', function () {
        mouse.inside = false;
        // it notices you leaving: attention drains faster when nobody is there
        attention = Math.max(0, attention - 0.35);
    });

    window.addEventListener('resize', resize);

    // ---- go -------------------------------------------------------------
    resize();
    if (calm) {
        drawCalm();
    } else {
        requestAnimationFrame(function (ts) { last = ts; frame(ts); });
    }
})();
