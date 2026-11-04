/* the seal that is never pressed - experiment no.8
   one line of text wrapped around a clay cylinder, laid out by glyph width so
   nothing is stretched: the turn is just cosine. several lines of it, so the
   construction is also the point - you can never read the whole inscription at
   once, because half of it is always round the back. */

(() => {
    'use strict';

    const cv = document.getElementById('seal');
    if (!cv) return;
    const ctx = cv.getContext('2d');

    const stage = document.getElementById('stage');
    const slotsBox = document.getElementById('slots');
    const pressBtn = document.getElementById('press');
    const impression = document.getElementById('impression');
    const stripEl = document.getElementById('strip');
    const verdictEl = document.getElementById('verdict');

    /* the incantation is Hulbazizi 18 as it stands on the Nineveh 1 amulet,
       translated in Bacskay & Niederreiter (JMC 40, 2022), with the name slot
       live. the male determinative is the superscript m. */
    const BEFORE = 'Incantation: Sirius is his name, who utters the battle cry in battle, who shows the way, who brings everything to perfection. He is the divine mace, raised from the furious weapons. Do not approach, do not come near ';
    const AFTER = '! Attacker, attacker, do not come near!';

    /* det is the male determinative - one wedge, written in transliteration as
       a raised m - and on the blank ones it is the only thing in the slot. */
    const SLOTS = {
        name:    { det: true, text: 'Šamaš-killanni, son of his god' },
        formula: { det: true, text: 'So-and-so, son of So-and-so' },
        blank:   { det: true, text: '' }
    };

    function slotHTML(key) {
        const s = SLOTS[key];
        const det = s.det ? '<sup class="det">m</sup>' : '';
        return det + s.text;
    }

    const VERDICTS = {
        name: 'No figure came off it, no frieze, nothing a seal would give you. What it gave you is the subject of the sentence: <strong>a man, named, with his god.</strong>',
        formula: 'The space fills with <strong>so-and-so, son of so-and-so</strong> &mdash; the placeholder of the ritual texts, standing where a name belongs. Somebody made this in numbers and did not stop to ask who would wear it.',
        blank: 'A raised <strong>m</strong> &mdash; the male determinative, one wedge, saying only that the wearer was a man &mdash; and the rest of the space left empty. <strong>The spell protects a gap.</strong> Two of the eighteen published amulets were found exactly like this.'
    };

    let current = 'name';
    let lines = [];
    let fontSize = 15;
    let R = 180;
    let W = 0, H = 0, cx = 0;
    let rot = 0;
    let dragging = false, lastX = 0, lastT = 0;

    /* ---------- text into lines ---------- */

    function buildChars(key) {
        const s = SLOTS[key];
        const out = [];
        const push = (str, slot, det) => {
            for (const ch of str) out.push({ ch, slot: !!slot, det: !!det });
        };
        push(BEFORE, false, false);
        if (s.det) push('m', true, true);
        push(s.text, true, false);
        push(AFTER, false, false);
        return out;
    }

    const mainFont = s => `${s}px Georgia, "Iowan Old Style", "Times New Roman", serif`;
    const detFont = s => `italic ${Math.max(6, s * 0.66)}px Georgia, "Times New Roman", serif`;

    /* one line's worth of glyphs, measured. the object's radius then comes OUT
       of the text instead of the other way round: if a ring wraps the whole
       circumference exactly once, the size of the amulet is whatever that
       sentence measures, and nothing on it is ever stretched. */
    function measure(size) {
        ctx.font = `${size}px Georgia, "Iowan Old Style", "Times New Roman", serif`;

        const chars = buildChars(current);
        const words = [];
        let word = [];
        for (const c of chars) {
            word.push(c);
            if (c.ch === ' ') { words.push(word); word = []; }
        }
        if (word.length) words.push(word);

        let total = 0;
        for (const w of words) {
            let wd = 0;
            for (const c of w) {
                ctx.font = c.det ? detFont(size) : mainFont(size);
                c.w = Math.max(ctx.measureText(c.ch).width, 0.55);
                wd += c.w;
            }
            w.width = wd;
            total += wd;
        }
        return { words, total };
    }

    function layout(words, targetWidth) {
        const groups = [];
        let group = [], acc = 0;
        for (const w of words) {
            if (acc > 0 && acc + w.width > targetWidth) {
                groups.push(group);
                group = [];
                acc = 0;
            }
            group.push(w);
            acc += w.width;
        }
        if (group.length) groups.push(group);

        return groups.map(g => {
            let x = 0;
            const cs = [];
            for (const w of g) {
                for (const c of w) {
                    cs.push({ ch: c.ch, slot: c.slot, det: c.det, pos: x + c.w / 2 });
                    x += c.w;
                }
            }
            return { chars: cs, width: x, y: 0 };
        });
    }

    /* split into exactly n rings, each as full as it can be without spilling
       into n+1. a plain greedy pass leaves a stub line of three words, and a
       stub ring on a cylinder looks like a mistake rather than an inscription */
    function balanced(words, total, n) {
        let lo = total / (n + 1), hi = total;
        let best = layout(words, hi);
        for (let i = 0; i < 26; i++) {
            const t = (lo + hi) / 2;
            const g = layout(words, t);
            if (g.length > n) {
                lo = t;
            } else {
                best = g;
                hi = t;
            }
        }
        return best;
    }

    function fit() {
        const top = H * 0.20, bot = H * 0.80;
        const bodyH = bot - top;

        let size = Math.max(11, Math.min(20, W * 0.029));
        let m = measure(size);

        let Rmax = Math.min(W * 0.42, 250);
        let n = Math.max(2, Math.ceil(m.total / (2 * Math.PI * Rmax)));

        /* if that many rings will not fit down the object, the writing has to
           get smaller instead of the amulet getting taller */
        while (n > 2 && bodyH / (n + 1) < size * 1.7 && size > 9) {
            size -= 0.5;
            m = measure(size);
            n = Math.max(2, Math.ceil(m.total / (2 * Math.PI * Rmax)));
        }

        const perRing = m.total / n;
        R = perRing / (2 * Math.PI);
        Rmax = Math.min(W * 0.42, 250);
        if (R > Rmax) {
            R = Rmax;
            n = Math.ceil(m.total / (2 * Math.PI * R));
        }

        fontSize = size;
        lines = balanced(m.words, m.total, n);

        /* the radius comes off the WIDEST ring, so no line can run past its own
           starting point and print over itself at the seam */
        const widest = lines.reduce((a, l) => Math.max(a, l.width), 0);
        R = Math.min(widest / (2 * Math.PI), W * 0.45);

        const gap = bodyH / (lines.length + 1);
        lines.forEach((l, i) => { l.y = top + gap * (i + 1); });
    }

    /* ---------- drawing ---------- */

    let grain = null;

    function makeGrain() {
        const tile = document.createElement('canvas');
        tile.width = tile.height = 96;
        const g = tile.getContext('2d');
        const img = g.createImageData(96, 96);
        for (let i = 0; i < img.data.length; i += 4) {
            const v = 104 + Math.random() * 52;
            img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
            img.data[i + 3] = 255;
        }
        g.putImageData(img, 0, 0);
        grain = ctx.createPattern(tile, 'repeat');
    }

    function barrel() {
        const top = H * 0.20, bot = H * 0.80;
        const ry = Math.max(9, Math.min(24, R * 0.14));

        ctx.beginPath();
        ctx.ellipse(cx, bot, R, ry, 0, 0, Math.PI * 2);
        ctx.fillStyle = '#452c1d';
        ctx.fill();

        /* fired clay, not metal and not a lamp: a wide soft falloff with the
           light off to the left, no specular spike, then grain over the top */
        const body = ctx.createLinearGradient(cx - R, 0, cx + R, 0);
        body.addColorStop(0.00, '#4e3527');
        body.addColorStop(0.14, '#7d5a44');
        body.addColorStop(0.36, '#ae8769');
        body.addColorStop(0.52, '#bf9776');
        body.addColorStop(0.70, '#a87f61');
        body.addColorStop(0.90, '#775640');
        body.addColorStop(1.00, '#452e22');
        ctx.fillStyle = body;
        ctx.fillRect(cx - R, top, R * 2, bot - top);

        if (grain) {
            ctx.save();
            ctx.beginPath();
            ctx.rect(cx - R, top, R * 2, bot - top);
            ctx.clip();
            ctx.globalCompositeOperation = 'overlay';
            ctx.globalAlpha = 0.55;
            ctx.fillStyle = grain;
            ctx.fillRect(cx - R, top, R * 2, bot - top);
            ctx.restore();
        }

        /* the lid and the base bite the light off at each end */
        const ends = ctx.createLinearGradient(0, top, 0, bot);
        ends.addColorStop(0.00, 'rgba(40, 24, 16, 0.45)');
        ends.addColorStop(0.10, 'rgba(40, 24, 16, 0)');
        ends.addColorStop(0.90, 'rgba(40, 24, 16, 0)');
        ends.addColorStop(1.00, 'rgba(30, 18, 12, 0.55)');
        ctx.fillStyle = ends;
        ctx.fillRect(cx - R, top, R * 2, bot - top);

        ctx.beginPath();
        ctx.moveTo(cx, 6);
        ctx.lineTo(cx, top);
        ctx.strokeStyle = 'rgba(214, 190, 165, 0.55)';
        ctx.lineWidth = 1.1;
        ctx.stroke();

        ctx.beginPath();
        ctx.ellipse(cx, top, R, ry, 0, 0, Math.PI * 2);
        const lid = ctx.createLinearGradient(cx - R, 0, cx + R, 0);
        lid.addColorStop(0.00, '#5c3d2a');
        lid.addColorStop(0.38, '#e3bf9d');
        lid.addColorStop(0.72, '#b98a67');
        lid.addColorStop(1.00, '#4d3222');
        ctx.fillStyle = lid;
        ctx.fill();

        ctx.beginPath();
        ctx.ellipse(cx, top, Math.max(4.5, R * 0.05), Math.max(2.6, ry * 0.40), 0, 0, Math.PI * 2);
        ctx.fillStyle = '#170f09';
        ctx.fill();
    }

    function inscription() {
        ctx.save();
        ctx.beginPath();
        ctx.rect(cx - R, H * 0.20, R * 2, H * 0.60);
        ctx.clip();

        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.shadowColor = 'rgba(255, 231, 208, 0.32)';
        ctx.shadowOffsetY = 1;

        for (const line of lines) {
            for (const c of line.chars) {
                const theta = c.pos / R + rot;
                const co = Math.cos(theta);
                if (co <= 0.17) continue;
                const x = cx + R * Math.sin(theta);

                ctx.save();
                ctx.translate(x, line.y - (c.det ? fontSize * 0.30 : 0));
                ctx.scale(co, 1);
                ctx.globalAlpha = Math.min(1, 0.05 + Math.pow(co, 0.7) * 1.1);
                ctx.fillStyle = c.slot ? '#8a2708' : '#3f2716';
                ctx.font = c.det ? detFont(fontSize) : mainFont(fontSize);
                ctx.fillText(c.ch, 0, 0);
                ctx.restore();
            }
        }
        ctx.restore();
        ctx.shadowColor = 'transparent';
        ctx.shadowOffsetY = 0;
        ctx.globalAlpha = 1;
    }

    function turn(t) {
        const dt = lastT ? Math.min(0.05, (t - lastT) / 1000) : 0;
        lastT = t;

        if (!dragging) rot += dt * 0.09;

        ctx.clearRect(0, 0, W, H);
        cx = W / 2;
        barrel();
        inscription();

        requestAnimationFrame(turn);
    }

    /* ---------- size ---------- */

    function resize() {
        const rect = cv.getBoundingClientRect();
        if (!rect.width) return;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        W = rect.width;
        H = rect.height;
        cv.width = Math.round(W * dpr);
        cv.height = Math.round(H * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        cx = W / 2;
        if (!grain) makeGrain();
        fit();
    }

    /* ---------- turning it ---------- */

    cv.tabIndex = 0;

    cv.addEventListener('pointerdown', e => {
        dragging = true;
        lastX = e.clientX;
        cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', e => {
        if (!dragging) return;
        rot += (e.clientX - lastX) / R;
        lastX = e.clientX;
    });
    const release = () => { dragging = false; };
    cv.addEventListener('pointerup', release);
    cv.addEventListener('pointercancel', release);
    cv.addEventListener('keydown', e => {
        if (e.key === 'ArrowLeft') { rot -= 0.15; e.preventDefault(); }
        if (e.key === 'ArrowRight') { rot += 0.15; e.preventDefault(); }
    });

    /* ---------- the slot ---------- */

    function setSlot(key) {
        current = key;
        for (const b of slotsBox.querySelectorAll('button')) {
            b.setAttribute('aria-pressed', String(b.dataset.slot === key));
        }
        fit();
        if (impression.classList.contains('took')) {
            stripEl.innerHTML = slotHTML(key);
            verdictEl.innerHTML = VERDICTS[key];
        }
    }

    slotsBox.addEventListener('click', e => {
        const b = e.target.closest('button[data-slot]');
        if (b) setSlot(b.dataset.slot);
    });

    /* ---------- pressing it ---------- */

    pressBtn.addEventListener('click', () => {
        stage.classList.add('pressing');
        pressBtn.disabled = true;
        window.setTimeout(() => {
            stage.classList.remove('pressing');
            impression.classList.add('took');
            stripEl.innerHTML = slotHTML(current);
            verdictEl.innerHTML = VERDICTS[current];
            pressBtn.disabled = false;
            pressBtn.textContent = 'press it again';
        }, 380);
    });

    /* ---------- go ---------- */

    let rt = null;
    window.addEventListener('resize', () => {
        window.clearTimeout(rt);
        rt = window.setTimeout(resize, 160);
    });

    resize();
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(resize);
    }
    requestAnimationFrame(turn);
})();
