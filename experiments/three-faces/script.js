// the three faces — one draw, composed from the order the other two fell in.
// state: { seed, picked }. every reading is assembled from the table below,
// never typed per pick, so the page has an opinion it did not get from me.

const FACES = [
  {
    name: "the keeper",
    glyph: "🜃",
    epithet: "what stays",
    gift: "You were handed the face that holds. What you chose is not the door — it is the wall, and walls keep.",
    cost: "The price is motion: a keeper's year is one room, measured well.",
  },
  {
    name: "the wanderer",
    glyph: "🜁",
    epithet: "what leaves",
    gift: "You were handed the face that goes. Whatever you were carrying, the road has already taken half of it.",
    cost: "The price is company: a wanderer's map has no one's name on it but theirs.",
  },
  {
    name: "the mirror",
    glyph: "🜂",
    epithet: "what reflects",
    gift: "You were handed the face that shows. It will not answer you — it will answer as you.",
    cost: "The price is certainty: a mirror never breaks the tie, it only doubles it.",
  },
];

// the aside depends on WHICH two were left and in WHICH order they sit —
// six composed asides from three faces, keyed by the pair's layout.
const ASIDES = {
  "0,1": "Between the keeper and the wanderer, the mirror is the third thing neither of them can be.",
  "1,0": "The wanderer left before the keeper did. What you were shown left first and stayed longest.",
  "0,2": "Keeper and mirror stayed. One of them is watching you choose; the other is only watching.",
  "2,0": "The mirror stayed beside the keeper, which is the only arrangement in which neither lies.",
  "1,2": "Wanderer and mirror both stayed in the row — you picked the only face that was ever really there.",
  "2,1": "The mirror left before the wanderer, and the wanderer is still deciding. So are you.",
};

// seeded rng — mulberry32, seed shown in the url so a draw can be re-opened
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromUrl() {
  const m = location.hash.match(/s(\d+)/);
  if (m) return +m[1] | 0;
  return (Math.random() * 0xffffffff) | 0;
}

let state = { seed: seedFromUrl(), picked: null, order: [] };

const row = document.getElementById("row");
const reading = document.getElementById("reading");
const panelCard = document.getElementById("panel-card");
const panelText = document.getElementById("panel-text");
const seedOut = document.getElementById("seed-out");

function cardEl(face, i) {
  const b = document.createElement("button");
  b.className = "card";
  b.type = "button";
  b.dataset.i = i;
  b.setAttribute("aria-label", `pick ${face.name}`);
  b.innerHTML = `<span class="glyph" aria-hidden="true">${face.glyph}</span>
    <span class="name">${face.name}</span>
    <span class="epithet">${face.epithet}</span>`;
  b.addEventListener("click", () => pick(i));
  return b;
}

function renderRow() {
  const rng = mulberry32(state.seed);
  // shuffle 0..2 with the seed — the LAYOUT is the state the reading reads
  state.order = [0, 1, 2];
  for (let i = 2; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [state.order[i], state.order[j]] = [state.order[j], state.order[i]];
  }
  row.innerHTML = "";
  state.order.forEach((fi, slot) => row.appendChild(cardEl(FACES[fi], fi)));
  seedOut.textContent = state.seed >>> 0;
}

// the view-transition trick: the picked card and the panel card share ONE
// view-transition-name, so the browser animates old→new by itself.
const VT = "face";
function withTransition(fn) {
  if (document.startViewTransition) document.startViewTransition(fn);
  else fn(); // graceful fallback: plain swap, same state change
}

function pick(i) {
  if (state.picked !== null) return; // one draw per lay — re-lay to go again
  state.picked = i;
  const face = FACES[i];

  // the two left behind, in the order they sit in the row
  const others = state.order.filter((f) => f !== i);
  const aside = ASIDES[`${others[0]},${others[1]}`] || "";

  const cardHtml = `<span class="glyph" aria-hidden="true">${face.glyph}</span>
    <span class="name">${face.name}</span>
    <span class="epithet">${face.epithet}</span>`;
  const textHtml = `<h2>the reading</h2><p>${face.gift}</p><p>${face.cost}</p>
    <p class="aside">${aside}</p>`;

  // mark the picked card and the panel with the same name, then swap under
  // one transition — the browser does the morph, I do none of the drawing
  withTransition(() => {
    const pickedEl = row.querySelector(`[data-i="${i}"]`);
    pickedEl.style.viewTransitionName = VT;
    panelCard.style.viewTransitionName = VT;

    row.innerHTML = "";
    row.setAttribute("aria-hidden", "true");
    panelCard.innerHTML = cardHtml;
    panelText.innerHTML = textHtml;
    reading.hidden = false;
    document.getElementById("again").focus();
  });
}

function relayout(newSeed) {
  state = { seed: newSeed, picked: null, order: [] };
  location.hash = `s${newSeed >>> 0}`;
  reading.hidden = true;
  panelCard.style.viewTransitionName = "";
  row.removeAttribute("aria-hidden");
  renderRow();
}

document.getElementById("again").addEventListener("click", () => relayout(state.seed));
document.getElementById("relay").addEventListener("click", () => relayout((Math.random() * 0xffffffff) | 0));

// keyboard twin is built in: the cards ARE buttons, tab reaches them, enter picks.
// seed in the url means a reload comes back to the same lay.
renderRow();
