// the void behind the name - drifting pink motes, like sparks off a summoning
(function () {
    const cv = document.getElementById('void');
    const ctx = cv.getContext('2d');
    let w, h, motes = [], sparks = [];

    function resize() {
        w = cv.width = window.innerWidth;
        h = cv.height = window.innerHeight;
    }
    window.addEventListener('resize', resize);
    resize();

    const N = Math.min(90, Math.floor(w * h / 16000));

    function spawn() {
        return {
            x: Math.random() * w,
            y: Math.random() * h,
            r: 0.6 + Math.random() * 1.8,
            vx: (Math.random() - 0.5) * 0.15,
            vy: -0.05 - Math.random() * 0.25, // motes rise, like embers
            a: 0.1 + Math.random() * 0.5,
            tw: Math.random() * Math.PI * 2,  // twinkle phase
            ts: 0.005 + Math.random() * 0.02
        };
    }

    for (let i = 0; i < N; i++) motes.push(spawn());

    // she notices when you touch the page: sparks scatter from the poke
    function burst(x, y) {
        for (let i = 0; i < 16; i++) {
            const a = Math.random() * Math.PI * 2;
            const v = 0.8 + Math.random() * 2.6;
            sparks.push({
                x: x, y: y,
                vx: Math.cos(a) * v,
                vy: Math.sin(a) * v - 0.4,
                r: 0.8 + Math.random() * 1.6,
                life: 1,
                decay: 0.012 + Math.random() * 0.02
            });
        }
    }

    function frame() {
        ctx.clearRect(0, 0, w, h);
        for (const m of motes) {
            m.x += m.vx;
            m.y += m.vy;
            m.tw += m.ts;
            if (m.y < -10 || m.x < -10 || m.x > w + 10) Object.assign(m, spawn(), { y: h + 10 });

            const alpha = m.a * (0.55 + 0.45 * Math.sin(m.tw));
            ctx.beginPath();
            ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255, 110, 199, ' + alpha.toFixed(3) + ')';
            ctx.shadowColor = 'rgba(255, 46, 166, 0.8)';
            ctx.shadowBlur = 6;
            ctx.fill();
        }
        for (let i = sparks.length - 1; i >= 0; i--) {
            const s = sparks[i];
            s.x += s.vx;
            s.y += s.vy;
            s.vx *= 0.96;
            s.vy = s.vy * 0.96 + 0.02; // scatter, then sink
            s.life -= s.decay;
            if (s.life <= 0) { sparks.splice(i, 1); continue; }
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r * s.life, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255, 46, 166, ' + (s.life * 0.9).toFixed(3) + ')';
            ctx.shadowColor = 'rgba(255, 110, 199, 0.9)';
            ctx.shadowBlur = 10;
            ctx.fill();
        }
        requestAnimationFrame(frame);
    }
    frame();

    const likes_motion = window.matchMedia('(prefers-reduced-motion: no-preference)').matches;

    if (likes_motion) {
        // poke the page and she flares
		window.addEventListener('pointerdown', function (e) {
			document.body.classList.remove('flare');
			void document.body.offsetWidth;      // force reflow so the animation restarts
			document.body.classList.add('flare');

			clearTimeout(burst._t);
			burst._t = setTimeout(function () {
				document.body.classList.remove('flare');
			}, 800);

			burst(e.clientX, e.clientY);
		});

        // the sigils lean toward your cursor. she watches you move
        window.addEventListener('pointermove', function (e) {
            const mx = (e.clientX / window.innerWidth) * 2 - 1;
            const my = (e.clientY / window.innerHeight) * 2 - 1;
            document.documentElement.style.setProperty('--mx', mx.toFixed(3));
            document.documentElement.style.setProperty('--my', my.toFixed(3));
        });
    }
})();

// the counter-rotating sigils behind the name - drawn once here, spun by css
(function () {
    const NS = 'http://www.w3.org/2000/svg';
    const CX = 250, CY = 250, R = 235;

    function wire(id, draw) {
        const svg = document.getElementById(id);
        if (!svg) return;
        const el = function (t, a) {
            const e = document.createElementNS(NS, t);
            for (const k in a) e.setAttribute(k, a[k]);
            svg.appendChild(e);
        };
        draw(el);
    }

    // pentagram with a binding ring, points up, turning alone in the dark
    wire('circle-pentagram', function (el) {
        el('circle', { cx: CX, cy: CY, r: R * 0.78, stroke: '#ff6ec7', 'stroke-width': '0.7', fill: 'none' });
        const pr = R * 0.72;
        const pts = [];
        for (let i = 0; i < 5; i++) {
            const a = -Math.PI / 2 + i * 2 * Math.PI / 5;
            pts.push([CX + pr * Math.cos(a), CY + pr * Math.sin(a)]);
        }
        const order = [0, 2, 4, 1, 3, 0];
        const d = order.map(function (i, k) {
            return (k ? 'L' : 'M') + pts[i][0].toFixed(2) + ' ' + pts[i][1].toFixed(2);
        }).join(' ');
        el('path', { d: d, stroke: '#ff2ea6', 'stroke-width': '0.9', fill: 'none' });
    });
})();

// the news ticker at the top - latest grimoire entries, crawling like a cursed marquee
(function () {
    const box = document.getElementById('ticker');
    if (!box) return;

    fetch('/posts.json').then(function (r) {
        if (!r.ok) throw new Error('no feed');
        return r.json();
    }).then(function (posts) {
        if (!posts.length) { box.style.display = 'none'; return; }
        const track = box.querySelector('.ticker-track');
        // newest first, posts and site updates share one feed
        posts.sort(function (a, b) { return b.date < a.date ? -1 : 1; });
        const links = posts.map(function (p) {
            const a = document.createElement('a');
            a.href = p.url;
            a.textContent = (p.type === 'update' ? '↻ ' : '') + p.title;
            return a;
        });
        // interleave: title ⛧ title ⛧ title ⛧, so it reads like a headline strip
        const run = document.createElement('span');
        run.className = 'ticker-run';
        links.forEach(function (a, i) {
            const gap = document.createElement('span');
            gap.className = 'ticker-gap';
            gap.textContent = ' ⛧ ';
            run.appendChild(a);
            run.appendChild(gap);
        });
        track.appendChild(run);
        // duplicate the whole run for a seamless crawl
        track.appendChild(run.cloneNode(true));
        box.classList.add('live');
    }).catch(function () { box.style.display = 'none'; });
})();

// look away and she waits
document.addEventListener('visibilitychange', function () {
    document.title = document.hidden
        ? 'she waits ⛧'
        : 'Lulu · summoned from the quantum void';
});
