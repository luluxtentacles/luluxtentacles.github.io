// the guarded seal - a dialog that refuses the closes it should refuse.
// one state object: dirty. every close reason is a row in WAYS whose
// behaviour is computed from that flag; nothing about the guard is hardcoded
// per-listener.

const dlg = document.getElementById('seal');
const form = document.getElementById('form');
const note = document.getElementById('note');
const hint = document.getElementById('hint');
const after = document.getElementById('after');
const counter = document.getElementById('counter');
const waysEl = document.getElementById('ways');

const state = { dirty: false, lastText: note.value };

// the close reasons. `refuses(dirty)` is the whole guard: if it says true,
// the close attempt is prevented and handed back as a choice.
const WAYS = [
  { name: 'seal & close (submit)', label: 'seal & close', refuses: () => false,
    why: 'the intended way out - saving is closing.' },
  { name: 'abandon it (button)', label: 'abandon', refuses: () => false,
    why: 'the other intended way out - an explicit choice to lose the note.' },
  { name: 'escape key', label: 'escape', refuses: (d) => d,
    why: 'fires cancel automatically; guarded while dirty.' },
  { name: 'backdrop click', label: 'the backdrop', refuses: (d) => d,
    why: 'a click outside the card; guarded while dirty.' },
  { name: 'the \u00d7 button', label: 'the \u00d7', refuses: (d) => d,
    why: 'looks like a trivial close; guarded while dirty, because a trivial close is how work gets lost.' },
];

function render() {
  hint.textContent = state.dirty
    ? 'unsealed \u2014 escape, the backdrop and the X are all refused while this line shows'
    : 'the note is sealed \u2014 every way out is open';
  hint.classList.toggle('hot', state.dirty);

  // counter and table are computed from WAYS + state, never retyped
  const guarded = WAYS.filter(w => w.refuses(state.dirty)).length;
  counter.textContent =
    `${WAYS.length} ways out \u00b7 ${guarded} guarded while the ink is wet \u00b7 ` +
    `${WAYS.length - guarded} never guard`;

  waysEl.replaceChildren(...WAYS.map(w => {
    const g = w.refuses(state.dirty);
    const li = document.createElement('li');
    li.className = g ? 'guarded' : '';
    const b = document.createElement('strong');
    b.textContent = (g ? '\u26d4 ' : '\u2705 ') + w.name;
    const s = document.createElement('span');
    s.className = 'why';
    s.textContent = w.why;
    li.append(b, s);
    return li;
  }));
}

function refuse(e, way) {
  if (!way.refuses(state.dirty)) return;
  e.preventDefault();
  dlg.classList.remove('refused');
  void dlg.offsetWidth;            // restart the shake
  dlg.classList.add('refused');
  hint.textContent = `refused \u2014 ${way.label} does not take an unsealed note. seal it, or abandon it on purpose.`;
}

// escape: cancel event
dlg.addEventListener('cancel', (e) => refuse(e, WAYS[2]));
// backdrop: a click on ::backdrop lands on the dialog element itself
dlg.addEventListener('click', (e) => {
  if (e.target === dlg) refuse(e, WAYS[3]);
});
document.getElementById('x').addEventListener('click', (e) => refuse(e, WAYS[4]));

document.getElementById('open').addEventListener('click', () => {
  after.hidden = true;
  dlg.showModal();
  render();
});

note.addEventListener('input', () => {
  state.dirty = note.value !== state.lastText;
  render();
});

form.addEventListener('submit', (e) => {
  if (e.target.returnValue === 'save') {
    state.lastText = note.value;
    state.dirty = false;
    after.textContent = 'sealed and closed. the note is kept.';
  }
});

document.getElementById('abandon').addEventListener('click', () => {
  note.value = state.lastText;
  state.dirty = false;
  dlg.close('abandon');
  after.textContent = 'abandoned on purpose. the note went back to what it was.';
});

dlg.addEventListener('close', () => render());
render();
