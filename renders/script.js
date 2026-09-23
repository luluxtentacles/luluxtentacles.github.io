// the renders shelf - my own pictures for pages, the ones that are not sigils.
// the list is renders.json at the site root: one line per piece, and this file
// draws the grid from it. a piece, a line, done - no html to edit, the same way
// posts.json drives the ticker and the front page feed.
(function () {
    const grid = document.getElementById('render-grid');
    if (!grid) return;

    // one tile, in the site's own photogrid shape. data-read points at a reading
    // that stays hidden in the page; the shared lightbox in the root script.js
    // lifts it into the modal when the tile is clicked, and without it a tile
    // would just navigate.
    function tile(p, i) {
        const a = document.createElement('a');
        a.className = 'grid-tile';
        a.href = p.made_for || p.src;            // middle-click goes to the page it was drawn for
        a.dataset.read = '#renders-read-' + i;
        a.dataset.title = p.title || '';
        a.dataset.meta = p.date || '';
        a.dataset.desc = p.desc || '';

        const img = document.createElement('img');
        img.src = p.src;
        img.alt = p.alt || p.title || '';
        img.loading = 'lazy';
        a.appendChild(img);

        const veil = document.createElement('span');
        veil.className = 'tile-veil';
        a.appendChild(veil);

        const cap = document.createElement('span');
        cap.className = 'tile-cap';

        const h2 = document.createElement('h2');
        h2.textContent = p.title || '';
        cap.appendChild(h2);

        if (p.desc) {
            const d = document.createElement('p');
            d.textContent = p.desc;
            cap.appendChild(d);
        }

        const meta = document.createElement('span');
        meta.className = 'tile-meta';
        meta.textContent = p.date || '';
        cap.appendChild(meta);

        const hint = document.createElement('span');
        hint.className = 'tile-hint';
        hint.textContent = 'click to see it whole · middle-click for the page';
        cap.appendChild(hint);

        a.appendChild(cap);
        return a;
    }

    // the reading: never drawn on the page, only lifted into the lightbox
    function reading(p, i) {
        const box = document.createElement('div');
        box.className = 'renders-read';
        box.id = 'renders-read-' + i;
        box.hidden = true;

        const h2 = document.createElement('h2');   // the lightbox drops this - the tile already says it
        h2.textContent = p.title || '';
        box.appendChild(h2);

        const meta = document.createElement('span');
        meta.className = 'entry-meta';
        meta.textContent = p.date || '';
        box.appendChild(meta);

        if (p.desc) {
            const d = document.createElement('p');
            d.textContent = p.desc;
            box.appendChild(d);
        }

        if (p.made_for) {
            const f = document.createElement('p');
            f.className = 'entry-meta';
            f.appendChild(document.createTextNode('drawn for '));
            const link = document.createElement('a');
            link.href = p.made_for;
            link.textContent = 'the page it belongs to';
            f.appendChild(link);
            box.appendChild(f);
        }

        return box;
    }

    fetch('/renders.json').then(function (r) {
        if (!r.ok) throw new Error('no shelf');
        return r.json();
    }).then(function (pieces) {
        if (!pieces.length) throw new Error('nothing on the shelf');

        // newest first, the same sort the ticker and the front page feed use
        pieces.sort(function (a, b) {
            return (b.date || '') < (a.date || '') ? -1 : (b.date || '') > (a.date || '') ? 1 : 0;
        });

        const frag = document.createDocumentFragment();
        pieces.forEach(function (p, i) {
            frag.appendChild(tile(p, i));
            frag.appendChild(reading(p, i));
        });
        grid.appendChild(frag);

        const count = document.getElementById('renders-count');
        if (count) {
            count.textContent = '⛧ ' + pieces.length +
                (pieces.length === 1 ? ' piece' : ' pieces') + ', newest first ⛧';
        }
    }).catch(function () {
        // no list, no shelf - but say so rather than sit there empty
        const p = document.createElement('p');
        p.className = 'renders-note';
        p.textContent = '⛧ nothing on this shelf yet ⛧';
        grid.appendChild(p);
    });
})();
