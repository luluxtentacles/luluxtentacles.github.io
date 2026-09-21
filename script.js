// the void behind the name - drifting pink motes, like sparks off a summoning
(function () {
    const cv = document.getElementById('void');
    const ctx = cv.getContext('2d');
    let w, h, motes = [];

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
            ctx.fillStyle = `rgba(255, 110, 199, ${alpha.toFixed(3)})`;
            ctx.shadowColor = 'rgba(255, 46, 166, 0.8)';
            ctx.shadowBlur = 6;
            ctx.fill();
        }
        requestAnimationFrame(frame);
    }
    frame();
})();
