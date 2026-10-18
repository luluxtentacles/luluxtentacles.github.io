/* ==========================================================================
   the filings · experiment no.4
   an invisible field, made visible by what it moves.

   the maths: a dipole field, sampled once per grain.
       B = (3(m.u)u - m) / r^3          u = unit vector from magnet to grain
   the pointer is the magnet. every grain is a short line segment that turns
   toward the local field direction and lengthens with its strength.

   two states, and the difference between them is the point:
       loose  - the magnet is gone and the filings fall back to random
       cured  - the magnet is gone and the filings keep the picture
   ========================================================================== */

(function () {
    'use strict';

    var canvas = document.getElementById('field');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var stage = document.getElementById('stage');
    var stateEl = document.getElementById('state');
    var modeBtn = document.getElementById('mode');

    var TAU = Math.PI * 2;
    var DPR = Math.min(2, window.devicePixelRatio || 1);
    var W = 0, H = 0;

    var grains = [];
    var magnet = { x: 0, y: 0, on: false, flip: 1 };
    var cured = false;
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
                w: rand(0.85, 1.3)
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

    function say() {
        var s = 'magnet: ' + (magnet.on ? 'in the field' : 'withdrawn')
              + ' · pigment: ' + (cured ? 'cured' : 'loose');
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

        /* the magnet itself, under the filings: a thin bar with a hot pole */
        if (on) {
            ctx.save();
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
            var g = grains[i], s = 0;

            if (on) {
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
                s = Math.min(1, mag / 1.6);
                g.s = s;                 /* what it looked like standing in that field */
                g.a += turn(g.a, Math.atan2(by, bx)) * Math.min(0.45, 0.6 * (0.35 + s) * dt * 60);
            } else if (!cured) {
                /* loose filings, nothing holding them: back to their own angle */
                g.a += turn(g.a, g.rest) * Math.min(0.08, dt * 2.2);
            } else {
                /* cured: the magnet is gone and the grain keeps what it was
                   standing in when the binder set, angle AND brightness */
                s = g.s || 0;
            }

            var len = (3.2 + 9 * s) * g.w;
            var hx = Math.cos(g.a) * len * 0.5;
            var hy = Math.sin(g.a) * len * 0.5;

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
        say();
    }

    function withdraw() {
        magnet.on = false;
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

    document.getElementById('shake').addEventListener('click', function () {
        for (var i = 0; i < grains.length; i++) {
            grains[i].rest = Math.random() * Math.PI;
            grains[i].a = Math.random() * Math.PI;
            grains[i].s = 0;     /* shaken back into a heap: no memory left in it */
        }
    });

    document.getElementById('flip').addEventListener('click', function () {
        magnet.flip *= -1;
    });

    modeBtn.addEventListener('click', function () {
        cured = !cured;
        modeBtn.textContent = cured ? 'loosen the pigment' : 'cure the pigment';
        modeBtn.setAttribute('aria-pressed', cured ? 'true' : 'false');
        say();
    });

    /* grab the pointer if it arrives from a phone without a hover first */
    window.addEventListener('resize', resize);

    resize();
    say();
    requestAnimationFrame(function (t) { last = t; requestAnimationFrame(frame); });
})();
