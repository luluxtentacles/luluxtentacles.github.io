// The Taixuanjing caster - lulu, 2026-11-14.
// One state object, one render. The 81 names come from the 九九 table in the
// zh.wikipedia article on 太玄, read row-major: 方 picks the row, 州/部/家
// subdivide it by the rhyme 推玄筭.

const NAMES = [
  '中','周','礥','閑','少','戾','上','干','𤕠',
  '羨','差','童','增','銳','達','交','䎡','傒',
  '從','進','釋','格','夷','樂','爭','務','事',
  '更','斷','毅','裝','眾','密','親','斂','彊',
  '睟','盛','居','法','應','迎','遇','竈','大',
  '廓','文','禮','逃','唐','常','度','永','昆',
  '減','唫','守','翕','聚','積','飾','疑','視',
  '沈','内','去','晦','瞢','窮','割','止','堅',
  '成','䦯','失','劇','馴','將','難','勤','養'
];

// weights per line, top to bottom (方,州,部,家): the rhyme's 27,9,3,1.
const WEIGHTS = [27, 9, 3, 1];
const POS = ['方', '州', '部', '家'];

// a cast: four line values 0..2 (天,地,人), plus the dice that produced them.
const state = { lines: null, dice: null, seed: null };

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// one throw of a d6 per line, the I Ching's coin mapping: 1-2 heaven, 3-4 earth, 5-6 man.
function roll(rng) {
  return [0, 1, 2, 3].map(() => {
    const d = 1 + Math.floor(rng() * 6);
    return { die: d, line: Math.floor((d - 1) / 2) };
  });
}

function indexOf(lines) {
  return lines.reduce((n, v, i) => n + v * WEIGHTS[i], 0); // 0..80
}

function render() {
  const g = document.getElementById('glyph');
  g.innerHTML = '';
  if (!state.lines) {
    g.innerHTML = '<div class="ln" style="opacity:.15"></div>'.repeat(4);
    document.getElementById('name').textContent = '—';
    document.getElementById('sum').textContent = '—';
    document.getElementById('dice').textContent = 'four dice, four lines. cast.';
    ['fang','zhou','bu','jia'].forEach(id => {
      document.getElementById('v-' + id).textContent = '—';
      document.getElementById('p-' + id).textContent = '—';
    });
    return;
  }
  const NAMES_LINE = ['tiān 天', 'dì 地', 'rén 人'];
  state.lines.forEach((v, i) => {
    const ln = document.createElement('div');
    ln.className = 'ln' + (v === 1 ? ' earth' : v === 2 ? ' man' : '');
    g.appendChild(ln);
  });
  const idx = indexOf(state.lines);
  document.getElementById('name').textContent = NAMES[idx];
  const uc = String.fromCodePoint(0x1D306 + idx);
  const ucEl = document.getElementById('uc');
  ucEl.textContent = uc + ' U+' + (0x1D306 + idx).toString(16).toUpperCase();
  ucEl.title = 'the same glyph in the Unicode Tai Xuan Jing block (which misnames the rén line "earth" in English)';

  let total = 0;
  ['fang','zhou','bu','jia'].forEach((id, i) => {
    const v = state.lines[i] + 1; // the rhyme counts 1..3
    const part = state.lines[i] * WEIGHTS[i];
    total += part;
    document.getElementById('v-' + id).textContent = v + ' (' + NAMES_LINE[state.lines[i]] + ')';
    document.getElementById('p-' + id).textContent = v === 1 ? '+0' : '+' + part;
  });
  document.getElementById('sum').textContent = total + 1 + ' of 81 — ' + NAMES[idx];
  document.getElementById('dice').textContent =
    'throw: ' + state.dice.map((d, i) => POS[i] + '=' + d.die).join(', ')
    + ' (1–2 天 · 3–4 地 · 5–6 人)';

  document.querySelectorAll('.cell').forEach((c, i) =>
    c.classList.toggle('hit', i === idx));
}

function buildGrid() {
  const cells = document.getElementById('cells');
  cells.innerHTML = '';
  NAMES.forEach((n, idx) => {
    const cell = document.createElement('button');
    cell.className = 'cell';
    cell.setAttribute('aria-label', n + ', number ' + (idx + 1));
    const lines = [
      Math.floor(idx / 27),
      Math.floor(idx / 9) % 3,
      Math.floor(idx / 3) % 3,
      idx % 3
    ];
    const mini = document.createElement('div');
    mini.className = 'mini';
    lines.forEach(v => {
      const i = document.createElement('i');
      if (v === 1) i.className = 'e';
      if (v === 2) i.className = 'm';
      mini.appendChild(i);
    });
    const b = document.createElement('b');
    b.textContent = n;
    const no = document.createElement('span');
    no.className = 'no';
    no.textContent = idx + 1;
    cell.append(mini, b, no);
    cell.addEventListener('click', () => {
      state.lines = lines;
      state.dice = lines.map(v => ({ die: v * 2 + 1 + (v === 2 ? 1 : 0), line: v }));
      render();
    });
    cells.appendChild(cell);
  });
}

document.getElementById('cast').addEventListener('click', () => {
  const seedEl = document.getElementById('seed');
  let seed = seedEl.value.trim();
  if (seed === '') seed = String(Date.now() % 1000000);
  const n = parseInt(seed, 10);
  if (Number.isNaN(n)) { seedEl.value = ''; return; }
  state.seed = n;
  seedEl.value = n;
  const rng = mulberry32(n);
  const r = roll(rng);
  state.lines = r.map(x => x.line);
  state.dice = r;
  render();
});

document.getElementById('toggle-grid').addEventListener('click', (e) => {
  const grid = document.getElementById('grid');
  grid.hidden = !grid.hidden;
  e.target.setAttribute('aria-pressed', String(!grid.hidden));
  e.target.textContent = grid.hidden ? 'show all 81' : 'hide the 81';
});

buildGrid();
render();
