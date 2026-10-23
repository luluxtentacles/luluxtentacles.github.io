/* ==========================================================================
   the filings · experiment no.4
   an invisible field, made visible by what it moves.

   the maths: a dipole field, sampled once per grain.
       B = (3(m.u)u - m) / r^3          u = unit vector from magnet to grain
   the pointer is the magnet. every grain is a short line segment that turns
   toward the local field direction and lengthens with its strength.

   THREE states, and the one in the middle is the whole point:
       wet     - the magnet is gone and the grains are already falling back
                 to their own angles. a cure poured now sets a fading picture.
       cured   - every grain keeps exactly what it was standing in at the
                 instant the cure was poured. pour it under a live field and
                 nothing is lost; pour it a beat late and you keep a fraction.
       shaken  - back to a heap with no memory in it.

   v2 note: the cure used to be a MODE you set before lifting, which meant a
   perfect picture every time and taught nothing. it is a moment now, and the
   read-out says how much of the picture the moment caught.
   ========================================================================== */

(function () {
    'use strict';

    var canvas = document.getElementById('field');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var stage = document.getElementById('stage');
    var stateEl = document.getElementById('state');

    var TAU = Math.PI * 2;
    var DPR = Math.min(2, window.devicePixelRatio || 1);
    var W = 0, H = 0;

    /* how fast a wet picture goes. strength falls to 1/e in STRENGTH_TAU
       seconds and the angles drift back over about ANGLE_TAU, so a cure
       poured a second late lands on almost nothing. */
    var STRENGTH_TAU = 0.42;
    var ANGLE_TAU = 0.30;

    var grains = [];
    var magnet = { x: 0, y: 0, on: false, flip: 1 };
    var cured = false;
    var kept = null;      /* percent of the picture the cure caught */
    var best = 0;         /* best cure this session */
    var baseSum = 0;      /* size of the picture at the moment the field let go */
    var touched = false;  /* has a magnet ever been in the tin */
    var last = 0;
    var said = '';

    function rand(a, b) { return a + Math.random() * (b - a); }

    /* a fresh heap: angles random, and a private "resting" angle for each
       grain, which is where it settles back to when nothing is holding it */
    function scatter() {
        var n = Math.max(700, Math.min(2600, Math.round(W * H / 620)));
        grains = new Array(n);
        for (var i = 0; i < n; i++) {
            grains[i] = {
                x: Math.random() * W,
                y: Math.random() * H,
                a: Math.random() * Math.PI,
                rest: Math.random() * Math.PI,
                w: rand(0.85, 1.3),
                s: 0,
                ca: 0,
                cs: 0
            };
        }
    }

    function resize() {
        var r = stage.getBoundingClientRect();
        W = Math.max(280, Math.round(r.width));
        H = Math.max(220, Math.round(r.height));
        canvas.width = Math.round(W * DPR);
        canvas.height = Math.round(H * DPR);
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        scatter();
    }

    /* shortest way round from a to b */
    function turn(a, target) {
        var d = target - a;
        return ((d + Math.PI) % TAU + TAU) % TAU - Math.PI;
    }

    /* everything that is currently visible, summed - the same measure the
       cure uses, so before/after are the same units */
    function sumS() {
        var t = 0;
        for (var i = 0, n = grains.length; i < n; i++) t += grains[i].s || 0;
        return t;
    }

    function say() {
        var s;
        if (cured) {
            s = 'pigment: cured · '
              + (kept === null
                    ? 'the cure caught an empty tin'
                    : 'kept ' + kept + '% of the picture')
              + (best > 0 ? ' · best ' + best + '%' : '');
        } else if (magnet.on) {
            s = 'magnet: in the field · pigment: wet · pour it now and you keep all of it';
        } else if (touched && baseSum > 0.02) {
            s = 'magnet: withdrawn · pigment: wet · it is already going';
        } else {
            s = 'magnet: withdrawn · pigment: wet · drag across the tin';
        }
        if (s === said) return;
        said = s;
        if (stateEl) stateEl.textContent = s;
    }

    function frame(now) {
        var dt = (now - last) / 1000;
        if (!(dt > 0) || dt > 0.05) dt = 0.016;
        last = now;

        ctx.clearRect(0, 0, W, H);

        var mx = magnet.x, my = magnet.y, on = magnet.on, flip = magnet.flip;

        /* the magnet itself, under the filings: a thin bar with a hot pole.
           faint once the binder has set, because it cannot move set pigment */
        if (on) {
            ctx.save();
            ctx.globalAlpha = cured ? 0.28 : 1;
            ctx.translate(mx, my);
            ctx.fillStyle = 'rgba(255, 215, 239, 0.10)';
            ctx.fillRect(flip > 0 ? -26 : -3, -3, 29, 6);
            ctx.fillStyle = 'rgba(255, 46, 166, 0.85)';
            ctx.beginPath();
            ctx.arc(flip > 0 ? 22 : -22, 0, 3.2, 0, TAU);
            ctx.fill();
            ctx.restore();
        }

        for (var i = 0, n = grains.length; i < n; i++) {
            var g = grains[i];
            var a = g.a, s = g.s || 0;

            if (cured) {
                /* set pigment: exactly what was caught at the cure, and the
                   magnet can hover all it likes */
                a = g.ca;
                s = g.cs;

            } else if (on) {
                var dx = mx - g.x, dy = my - g.y;
                var r = Math.sqrt(dx * dx + dy * dy) || 1;
                var ux = dx / r, uy = dy / r;                 /* direction to the magnet */
                var rn = Math.max(r / 120, 0.4);               /* distance in 120px units */
                var inv = 1 / (rn * rn * rn);
                var dot = flip * ux;
                var bx = (3 * dot * ux - flip) * inv;
                var by = (3 * dot * uy) * inv;
                var mag = Math.sqrt(bx * bx + by * by);
                if (mag > 3) mag = 3;
                var target = Math.min(1, mag / 1.6);
                g.s = s + (target - s) * Math.min(1, dt * 14);
                g.a += turn(g.a, Math.atan2(by, bx)) * Math.min(0.45, 0.6 * (0.35 + g.s) * dt * 60);
                a = g.a;
                s = g.s;

            } else {
                /* wet and abandoned: the grains drift back to their own
                   angles and the picture fades out of them. this is the
                   window the cure is racing, and it is under a second */
                g.s *= Math.exp(-dt / STRENGTH_TAU);
                if (g.s < 0.004) g.s = 0;
                g.a += turn(g.a, g.rest) * (1 - Math.exp(-dt / ANGLE_TAU));
                a = g.a;
                s = g.s;
            }

            var len = (3.2 + 9 * s) * g.w;
            var hx = Math.cos(a) * len * 0.5;
            var hy = Math.sin(a) * len * 0.5;

            if (s > 0.02) {
                ctx.strokeStyle = 'rgba(255,' + Math.round(150 + 95 * s) + ',' + Math.round(212 + 30 * s) + ',' + (0.2 + 0.72 * s).toFixed(3) + ')';
            } else {
                ctx.strokeStyle = 'rgba(178, 74, 134, 0.3)';
            }
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(g.x - hx, g.y - hy);
            ctx.lineTo(g.x + hx, g.y + hy);
            ctx.stroke();
        }

        say();
        requestAnimationFrame(frame);
    }

    /* ---------- the hand ---------- */

    function put(e) {
        var r = canvas.getBoundingClientRect();
        magnet.x = e.clientX - r.left;
        magnet.y = e.clientY - r.top;
        magnet.on = true;
        touched = true;
        say();
    }

    function withdraw() {
        if (!magnet.on) return;
        magnet.on = false;
        /* the field just let go: this is the picture the cure is now racing */
        if (!cured) baseSum = sumS();
        say();
    }

    canvas.addEventListener('pointerdown', function (e) {
        put(e);
        if (canvas.setPointerCapture) {
            try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
        }
    });
    canvas.addEventListener('pointermove', put);
    canvas.addEventListener('pointerup', withdraw);
    canvas.addEventListener('pointercancel', withdraw);
    canvas.addEventListener('pointerleave', function (e) {
        if (e.pointerType !== 'touch') withdraw();
    });

    /* ---------- the cure ---------- */

    function cure() {
        if (cured) return;
        var now = sumS();
        /* poured with the magnet still in the panel: nothing has had time to
           relax, so the measure is taken against itself and it is 100% */
        if (magnet.on) baseSum = now;

        var pct = null;
        if (baseSum > 0.02 && now > 0) {
            pct = Math.max(0, Math.min(100, Math.round(100 * now / baseSum)));
        }
        for (var i = 0, n = grains.length; i < n; i++) {
            grains[i].ca = grains[i].a;
            grains[i].cs = grains[i].s || 0;
        }
        cured = true;
        kept = pct;
        if (pct !== null && pct > best) best = pct;
        say();
    }

    function loosen() {
        if (!cured) return;
        /* the binder comes off: the grains carry on from where the cure
           left them, and they start falling back immediately */
        for (var i = 0, n = grains.length; i < n; i++) {
            grains[i].a = grains[i].ca;
            grains[i].s = grains[i].cs;
        }
        cured = false;
        kept = null;
        baseSum = 0;
        say();
    }

    document.getElementById('cure').addEventListener('click', cure);
    document.getElementById('loosen').addEventListener('click', loosen);

    document.getElementById('shake').addEventListener('click', function () {
        for (var i = 0, n = grains.length; i < n; i++) {
            grains[i].rest = Math.random() * Math.PI;
            grains[i].a = Math.random() * Math.PI;
            grains[i].s = 0;     /* shaken back into a heap: no memory left in it */
            grains[i].ca = grains[i].a;
            grains[i].cs = 0;
        }
        cured = false;
        kept = null;
        baseSum = 0;
        say();
    });

    document.getElementById('flip').addEventListener('click', function () {
        magnet.flip *= -1;
    });

    /* one hand cannot hold the pointer in the panel and press a button, and
       the whole trick is pouring the cure while the field is live - so c is
       the key, and it is the honest version of the nails hack. */
    document.addEventListener('keydown', function (e) {
        if (e.key === 'c' || e.key === 'C') {
            cure();
        } else if (e.key === 'l' || e.key === 'L') {
            loosen();
        }
    });

    window.addEventListener('resize', resize);

    resize();
    say();
    requestAnimationFrame(function (t) { last = t; requestAnimationFrame(frame); });
})();
