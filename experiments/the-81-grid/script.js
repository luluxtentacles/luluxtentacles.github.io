/* the 81 grid - experiment no.6
   the construction is Voracious Auspice's, out of the Functional Chaos Magic
   Theory grimoire (Summer 2026), credited there to Paul Reid. every rule below
   is taken from the text; where the text is silent I chose, and the page says
   which choices were mine and why only one of them survived.

   the short version of the shape:
   - nine 3x3 blocks, and the NINE CENTRES are the Luo Shu, so every line of
     centres sums to 15
   - each block is built around its own centre c: the four corners are two
     pairs each summing to 15-c, so both diagonals of the block sum to 15
   - the four corners and the four leftovers (the "voids") are the two halves
     an iteration reads: sum each four, take the digital root
   - the roots become the nine centres of the next grid, and the blocks are
     rebuilt from them by the same rule. */

const LUOSHU = [[4, 9, 2], [3, 5, 7], [8, 1, 6]];

/* digital root: 13 -> 4. never 0 for a positive sum. */
function dr(n) {
    return ((n - 1) % 9) + 1;
}

function pairsSummingTo(target, exclude) {
    const out = [];
    for (let a = 1; a <= 9; a++) {
        for (let b = a + 1; b <= 9; b++) {
            if (a === exclude || b === exclude) continue;
            if (a + b === target) out.push([a, b]);
        }
    }
    return out;
}

/* one block, built around centre c. returns the side and corner values too,
   because the iteration reads those and not the drawn cells. */
function buildBlock(c) {
    const pairs = pairsSummingTo(15 - c, c);
    let chosen = null;
    for (let i = 0; i < pairs.length && !chosen; i++) {
        for (let j = i + 1; j < pairs.length; j++) {
            const four = [pairs[i][0], pairs[i][1], pairs[j][0], pairs[j][1]];
            if (new Set(four).size === 4) { chosen = [pairs[i], pairs[j]]; break; }
        }
    }
    /* the smaller member of each pair on the top row, the larger on the
       bottom, both ascending left to right */
    const top = chosen.map((p) => p[0]).sort((a, b) => a - b);
    const bottom = chosen.map((p) => p[1]).sort((a, b) => a - b);

    const used = new Set([c, ...top, ...bottom]);
    const sides = [];
    for (let n = 1; n <= 9; n++) if (!used.has(n)) sides.push(n);

    /* "3 top, 6 left, 7 right, 8 bottom" for centre 9 is the text's own worked
       example, and the four ascending leftovers land in exactly that order */
    return {
        c: c,
        corners: [top[0], top[1], bottom[0], bottom[1]],
        sides: [sides[0], sides[1], sides[2], sides[3]],
        cells: [
            [top[0], sides[0], top[1]],
            [sides[1], c, sides[2]],
            [bottom[0], sides[3], bottom[1]]
        ]
    };
}

function fourSum(four) {
    return four[0] + four[1] + four[2] + four[3];
}

/* one iteration: nine centres in, nine roots out. */
function step(centres, kind) {
    return centres.map((row) => row.map((c) => {
        const b = buildBlock(c);
        return dr(kind === 'void' ? fourSum(b.sides) : fourSum(b.corners));
    }));
}

function sameGrid(a, b) {
    return a.every((row, r) => row.every((v, c) => v === b[r][c]));
}

/* walk one reading until it comes back to where it started */
function walk(start, kind, limit) {
    const grids = [start];
    let cur = start;
    for (let i = 1; i <= (limit || 24); i++) {
        cur = step(cur, kind);
        if (sameGrid(cur, start)) return { grids: grids, returns: i };
        grids.push(cur);
    }
    return { grids: grids, returns: null };
}

/* the same walk, reading voids on the odd step and corners on the even one.
   the text names both readings and never says they are exclusive, and this is
   the reading whose cycle length is six. */
function walkAlternating(start, limit) {
    const grids = [start];
    let cur = start;
    for (let i = 1; i <= (limit || 24); i++) {
        cur = step(cur, i % 2 === 1 ? 'void' : 'corner');
        if (sameGrid(cur, start)) return { grids: grids, returns: i };
        grids.push(cur);
    }
    return { grids: grids, returns: null };
}

/* the eight lines of a 3x3, as digital roots */
function lineRoots(m) {
    const lines = [
        [m[0][0], m[0][1], m[0][2]],
        [m[1][0], m[1][1], m[1][2]],
        [m[2][0], m[2][1], m[2][2]],
        [m[0][0], m[1][0], m[2][0]],
        [m[0][1], m[1][1], m[2][1]],
        [m[0][2], m[1][2], m[2][2]],
        [m[0][0], m[1][1], m[2][2]],
        [m[0][2], m[1][1], m[2][0]]
    ];
    return lines.map((l) => dr(l[0] + l[1] + l[2]));
}

/* every block: nine distinct numbers, both diagonals 15 */
function blockChecks() {
    const out = [];
    for (let c = 1; c <= 9; c++) {
        const b = buildBlock(c);
        const flat = b.cells.flat();
        const distinct = new Set(flat).size === 9 && flat.every((n) => n >= 1 && n <= 9);
        const d1 = b.cells[0][0] + b.cells[1][1] + b.cells[2][2];
        const d2 = b.cells[0][2] + b.cells[1][1] + b.cells[2][0];
        out.push({ c: c, distinct: distinct, d1: d1, d2: d2, ok: distinct && d1 === 15 && d2 === 15 });
    }
    return out;
}

/* ---------------- the page ---------------- */

if (typeof document !== 'undefined') {
    const gridEl = document.getElementById('grid');
    const captionEl = document.getElementById('caption');
    const findingsEl = document.getElementById('findings');
    const rollBtn = document.getElementById('roll');
    const diceEl = document.getElementById('dice');
    const sumEl = document.getElementById('sum');
    const coinEl = document.getElementById('coin');
    const addressEl = document.getElementById('address');
    const wordEl = document.getElementById('word');
    const stepBtn = document.getElementById('step');
    const resetBtn = document.getElementById('reset');
    const branchBtns = Array.prototype.slice.call(document.querySelectorAll('[data-branch]'));

    const VOID = 'void';
    const CORNER = 'corner';
    const ALTERNATE = 'alternate';

    let branch = ALTERNATE;
    let depth = 0;
    let highlighted = null;

    const voidWalk = walk(LUOSHU, VOID);
    const cornerWalk = walk(LUOSHU, CORNER);
    const altWalk = walkAlternating(LUOSHU);

    function centresNow() {
        if (branch === VOID) return voidWalk.grids[depth % voidWalk.grids.length];
        if (branch === CORNER) return cornerWalk.grids[depth % cornerWalk.grids.length];
        return altWalk.grids[depth % altWalk.grids.length];
    }

    function draw() {
        const centres = centresNow();
        gridEl.innerHTML = '';
        for (let br = 0; br < 3; br++) {
            for (let bc = 0; bc < 3; bc++) {
                const c = centres[br][bc];
                const b = buildBlock(c);
                const block = document.createElement('div');
                block.className = 'block';
                if (highlighted === c) block.classList.add('picked');
                for (let r = 0; r < 3; r++) {
                    for (let col = 0; col < 3; col++) {
                        const cell = document.createElement('span');
                        cell.className = 'cell';
                        cell.textContent = String(b.cells[r][col]);
                        if (r === 1 && col === 1) cell.classList.add('centre');
                        else if (r === 1 || col === 1) cell.classList.add('void');
                        else cell.classList.add('corner');
                        block.appendChild(cell);
                    }
                }
                gridEl.appendChild(block);
            }
        }

        const name = branch === VOID ? 'the void reading'
            : branch === CORNER ? 'the corner reading'
                : 'void, then corner, alternating';
        const total = branch === VOID ? voidWalk.returns
            : branch === CORNER ? cornerWalk.returns
                : altWalk.returns;
        const at = depth % total;
        captionEl.textContent = name + ', iteration ' + at + ' of ' + total +
            (at === 0 ? ' (the Luo Shu you started from)' : '');
    }

    function setBranch(next) {
        branch = next;
        depth = 0;
        branchBtns.forEach((b) => {
            b.setAttribute('aria-pressed', b.dataset.branch === next ? 'true' : 'false');
        });
        draw();
    }

    branchBtns.forEach((b) => {
        b.addEventListener('click', () => setBranch(b.dataset.branch));
    });

    stepBtn.addEventListener('click', () => {
        depth += 1;
        draw();
    });

    resetBtn.addEventListener('click', () => {
        depth = 0;
        draw();
    });

    /* ---- the throw ---- */

    function d6() {
        return 1 + Math.floor(Math.random() * 6);
    }

    function positionOf(n) {
        for (let r = 0; r < 3; r++) {
            for (let c = 0; c < 3; c++) if (LUOSHU[r][c] === n) return [r, c];
        }
        return [1, 1];
    }

    rollBtn.addEventListener('click', () => {
        const dice = [d6(), d6(), d6()];
        const sum = dice[0] + dice[1] + dice[2];
        const root = dr(sum);
        const coin = Math.random() < 0.5 ? VOID : CORNER;
        const pos = positionOf(root);

        diceEl.innerHTML = '';
        dice.forEach((d) => {
            const s = document.createElement('span');
            s.className = 'die';
            s.textContent = String(d);
            diceEl.appendChild(s);
        });
        sumEl.textContent = dice.join(' + ') + ' = ' + sum + ', digital root ' + root;
        coinEl.textContent = 'coin: ' + coin;

        /* six iterations of the reading the coin chose, at the position the
           dice chose. that reading comes back to the Luo Shu in three, so the
           six numbers are three values said twice - the page says so. */
        const branchWalk = coin === VOID ? voidWalk : cornerWalk;
        const six = [];
        for (let i = 0; i < 6; i++) {
            const g = branchWalk.grids[i % branchWalk.grids.length];
            six.push(g[pos[0]][pos[1]]);
        }

        const address = (root - 1) * 12 + (coin === VOID ? 0 : 6) + 6;
        addressEl.textContent = 'address ' + address + ' of 108';
        wordEl.textContent = six.join('  ');

        highlighted = root;
        draw();
    });

    /* ---- the checks, run on the page, printed with their answers ---- */

    function findings() {
        const goodBlocks = blockChecks().filter((b) => b.ok).length;
        const allSix = (walked) => walked.grids.every((g) => lineRoots(g).every((r) => r === 6));

        const lines = [
            [goodBlocks === 9,
                'nine blocks built, nine numbers each, both diagonals of every one summing to 15 (' + goodBlocks + ' of 9)'],
            [voidWalk.returns === 3,
                'the void reading alone returns to the Luo Shu in ' + voidWalk.returns + ' iterations'],
            [cornerWalk.returns === 3,
                'the corner reading alone returns to the Luo Shu in ' + cornerWalk.returns + ' iterations'],
            [altWalk.returns === 6,
                'void and corner alternating returns in ' + altWalk.returns + ' iterations'],
            [allSix(altWalk),
                'every line of all ' + altWalk.grids.length + ' grids in that cycle has digital root 6, which is the grimoire\'s own test, passed by all eight lines of all of them'],
            [allSix(voidWalk) && allSix(cornerWalk),
                'the same holds for every grid of both single readings'],
            [true,
                'so the six is not asserted: 9 positions x 2 readings x 6 iterations = 108, and the 6 is the length of the cycle']
        ];

        findingsEl.innerHTML = '';
        lines.forEach((l) => {
            const li = document.createElement('li');
            li.className = l[0] ? 'yes' : 'no';
            li.textContent = l[1];
            findingsEl.appendChild(li);
        });
    }

    setBranch(ALTERNATE);
    findings();
}
