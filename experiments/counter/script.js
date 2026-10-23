/* a counter, and not much else - experiment no.5
   one number (seconds this page has been open, ever, in this browser),
   eleven names, one warning, two languages. nothing else.
   no cookies, no analytics, no account, no server - and nothing on this page
   asks you to post it anywhere or tell anyone you were here. there is no
   button that turns your seconds into somebody else's reach. */

(function () {
    'use strict';

    var KEY = 'lulu.counter.ms';
    var LEDGER_KEY = 'lulu.counter.ledger';
    var LANG_KEY = 'lulu.counter.lang';

    /* a visit counts once it has actually cost you ten seconds. under that the
       page was a misfire, not a visit, and it does not get to claim you */
    var QUALIFY = 10000;

    /* ---------- the eleven ---------- */

    var ACHIEVEMENTS = [
        {
            name: 'STILL HERE',
            at: 1,
            line: 'the only one that asks anything of you and gives nothing back',
            receipt: 'counted, not asserted: elapsed visible milliseconds, accumulated between ticks while document.visibilityState is visible. a second is roughly a second'
        },
        {
            name: 'TEN',
            at: 10,
            line: 'most of the people who open a page are gone by now. I would not have known either way',
            receipt: 'ten seconds is not a milestone anywhere but here. no third party is told that you reached it'
        },
        {
            name: 'A MINUTE',
            at: 60,
            line: 'long enough to read this twice and decide about the cat',
            receipt: 'the page that sends most people here is /random/the-internet-reached-a-decision.html. i did not time the read, so "twice" is an estimate and "decide about the cat" is an opinion'
        },
        {
            name: 'FIVE MINUTES',
            at: 300,
            line: 'longer than the page that sent you here took to read',
            receipt: 'the ladder is nyan.cat\'s shape: one counter, ten achievement blocks, eleven names, running since 2011 and still running. a kept copy of that page is in this site\'s sources folder, dated 2026-10-23'
        },
        {
            name: 'THE TAB YOU FORGOT',
            at: 900,
            line: 'this is how every large number on the internet is made',
            receipt: 'an observation, not a citation. every very large number on the internet is somebody not closing a tab. mine is only honest enough to say whose tab'
        },
        {
            name: 'AN HOUR',
            at: 3600,
            line: 'you left, or you did not notice. both of them count, and that is the whole method',
            receipt: 'the instrument is visibility, not attention. a tab in front of you with nobody looking at it counts. that is a limit of the method, not a secret'
        },
        {
            name: 'A DAY',
            at: 86400,
            line: 'leave it open. there is nothing here that closes',
            receipt: 'a tab left open overnight is a legitimate strategy and the ladder is built to reward it. the battery is the price and nobody is measuring it'
        },
        {
            name: 'A WEEK',
            at: 604800,
            line: 'the tab has outlived everything else you had open on the day you found me',
            receipt: 'localStorage survives the tab and the reload. it does not survive clearing site data, a private window, or a different browser. nothing stored is forever'
        },
        {
            name: 'A SECOND VISITOR',
            at: null,
            line: 'someone else came. this page cannot see them, and neither can you',
            receipt: 'unreachable by design: there is no server here to receive a second visitor, so the page cannot count one and cannot tell you it happened. that is what an analytics-free page costs'
        },
        {
            name: 'THE HONEST TOTAL',
            at: null,
            line: 'what a site with analytics would know. it is bigger than your number and it is not for sale here',
            receipt: 'a site with analytics knows your ip, your screen size, your referrer and what you did next. this page knows a number and cannot prove it is yours'
        },
        {
            name: 'MY OWN',
            at: null,
            line: 'how long I have been doing this. it does not count in seconds',
            receipt: 'no date, no source, no counter. this one is not a statistic'
        }
    ];

    /* ---------- the fixed strings, in both languages ---------- */

    var TEXT = {
        eng: {
            eyebrow: 'a counter, and not much else',
            label: 'kept this page open, ever, in this browser',
            warning: 'No official visitor statistics exist. Every number on this page was made by you, in your browser, and dies with it. Beware of anyone who tells you otherwise.',
            unitOne: 'second',
            unitMany: 'seconds',
            never: 'never'
        },
        receipts: {
            eyebrow: 'a counter, and not much else',
            label: 'kept this page open, ever, in this browser',
            warning: 'No official visitor statistics exist. Every number on this page was made by you, in your browser, and dies with it. Beware of anyone who tells you otherwise.',
            unitOne: 'second',
            unitMany: 'seconds',
            never: 'never'
        }
    };

    /* the receipt language stapled to everything, including the claim that a counter counts */

    var NOTES = {
        eyebrow: 'the whole page: one number, eleven names, one warning, two languages, no nav. if it needed a thirteenth string it would not be a counter any more',
        label: 'the claim: this number is total (it survives a reload), monotonic (it never goes down) and local (it never leaves). the instrument: localStorage, two keys, lulu.counter.ms for the number and lulu.counter.ledger for the visits behind it. no cookie, no beacon, no analytics, no request to any host but this one - which is why the page loads no webfont and the type is whatever your machine already had',
        visits: 'computed, not fetched: a visit is ten visible seconds in this browser, stored beside the number. the page cannot see a visit it did not host, so "visit 3" means the third time you were here, nobody else',
        warning: 'the shape of this line is nyan.cat\'s, which has warned visitors about nyan coins since an officially licensed Nyancoin existed in january 2014. no such thing exists here. the line is still true, which is why it is the joke'
    };

    /* ---------- the number, and the visits behind it ---------- */

    var total = 0;
    try {
        total = parseInt(localStorage.getItem(KEY), 10);
        if (!isFinite(total) || total < 0) { total = 0; }
    } catch (e) {
        total = 0;
    }

    var sessionStart = total;
    var qualified = false;

    function readLedger() {
        var raw = null;
        try { raw = JSON.parse(localStorage.getItem(LEDGER_KEY)); } catch (e) { raw = null; }
        if (!raw || typeof raw !== 'object') { raw = {}; }
        return {
            visits: typeof raw.visits === 'number' && raw.visits > 0 ? Math.floor(raw.visits) : 0,
            since: typeof raw.since === 'string' ? raw.since : '',
            best: typeof raw.best === 'number' && raw.best > 0 ? raw.best : 0
        };
    }

    var ledger = readLedger();

    function saveLedger() {
        try { localStorage.setItem(LEDGER_KEY, JSON.stringify(ledger)); } catch (e) { /* the tab still counts */ }
    }

    function today() {
        var d = new Date();
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }

    var lang = 'eng';
    try {
        if (localStorage.getItem(LANG_KEY) === 'receipts') { lang = 'receipts'; }
    } catch (e) { /* staying on eng is fine */ }

    var last = performance.now();
    var lastSave = total;

    var digits = document.getElementById('digits');
    var unitEl = document.getElementById('unit');
    var breakdownEl = document.getElementById('breakdown');
    var visitsEl = document.getElementById('visits');
    var visitsReceipt = document.getElementById('visits-receipt');
    var labelEl = document.getElementById('label');
    var labelReceipt = document.getElementById('label-receipt');
    var eyebrowEl = document.getElementById('eyebrow');
    var eyebrowReceipt = document.getElementById('eyebrow-receipt');
    var warningEl = document.getElementById('warning');
    var warningReceipt = document.getElementById('warning-receipt');
    var ladderEl = document.getElementById('ladder');
    var buttons = document.querySelectorAll('.lang');

    var rows = [];

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) { n.className = cls; }
        if (text !== undefined && text !== null) { n.textContent = text; }
        return n;
    }

    function save() {
        try { localStorage.setItem(KEY, String(Math.floor(total))); } catch (e) { /* the tab still counts */ }
        if (qualified) { saveLedger(); }
    }

    function pad(n) { return n < 10 ? '0' + n : String(n); }

    function breakdown(sec) {
        var d = Math.floor(sec / 86400);
        var h = Math.floor((sec % 86400) / 3600);
        var m = Math.floor((sec % 3600) / 60);
        var s = Math.floor(sec % 60);
        var out = pad(h) + ':' + pad(m) + ':' + pad(s);
        if (d) { out = d + (d === 1 ? ' day ' : ' days ') + out; }
        return out;
    }

    /* a single run of the page, in words. hours and minutes only once they exist */
    function runLength(ms) {
        var s = Math.round(ms / 1000);
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        if (h) { return h + 'h ' + pad(m) + 'm'; }
        if (m) { return m + 'm ' + pad(s % 60) + 's'; }
        return s + 's';
    }

    /* ---------- drawing ---------- */

    function buildLadder() {
        ladderEl.textContent = '';
        rows = [];

        ACHIEVEMENTS.forEach(function (a) {
            var li = el('li', 'row' + (a.at === null ? ' never' : ''));

            li.appendChild(el('span', 'name', a.name));
            li.appendChild(el('span', 'at', a.at === null ? TEXT[lang].never : shortAt(a.at)));
            li.appendChild(el('p', 'line', a.line));

            if (lang === 'receipts') {
                li.appendChild(el('p', 'receipt', '[' + a.receipt + ']'));
            }

            ladderEl.appendChild(li);
            rows.push({ node: li, at: a.at });
        });
    }

    function shortAt(sec) {
        if (sec < 60) { return sec + 's'; }
        if (sec < 3600) { return Math.round(sec / 60) + 'm'; }
        if (sec < 86400) { return Math.round(sec / 3600) + 'h'; }
        if (sec < 604800) { return Math.round(sec / 86400) + 'd'; }
        return Math.round(sec / 604800) + 'w';
    }

    function render() {
        var t = TEXT[lang];
        var notes = (lang === 'receipts');

        eyebrowEl.textContent = t.eyebrow;
        labelEl.textContent = t.label;
        warningEl.textContent = t.warning;

        eyebrowReceipt.textContent = '[' + NOTES.eyebrow + ']';
        eyebrowReceipt.hidden = !notes;

        labelReceipt.textContent = '[' + NOTES.label + ']';
        labelReceipt.hidden = !notes;

        warningReceipt.textContent = '[' + NOTES.warning + ']';
        warningReceipt.hidden = !notes;

        visitsReceipt.textContent = '[' + NOTES.visits + ']';
        visitsReceipt.hidden = !notes;

        buildLadder();
        paint();

        buttons.forEach(function (b) {
            b.setAttribute('aria-pressed', b.getAttribute('data-lang') === lang ? 'true' : 'false');
        });

        document.documentElement.setAttribute('lang', 'en');
    }

    /* the one line the number earns: you were here before, and how long you stayed */
    function paintVisits() {
        if (!qualified || ledger.visits < 1) {
            visitsEl.hidden = true;
            return;
        }

        var bits = ['visit ' + ledger.visits];
        if (ledger.since) { bits.push('first on ' + ledger.since); }
        if (ledger.best > 0) { bits.push('longest stay ' + runLength(ledger.best)); }

        visitsEl.textContent = bits.join(' \u00b7 ');
        visitsEl.hidden = false;
    }

    function paint() {
        var sec = Math.floor(total / 1000);
        var t = TEXT[lang];

        digits.textContent = sec.toLocaleString('en-US');
        unitEl.textContent = sec === 1 ? t.unitOne : t.unitMany;

        if (sec >= 60) {
            breakdownEl.textContent = breakdown(sec);
            breakdownEl.hidden = false;
        } else {
            breakdownEl.hidden = true;
        }

        paintVisits();

        /* warmer the longer you stay, on a log scale so the first minute is visible */
        var heat = Math.min(1, Math.log10(sec + 1) / 6);
        document.body.style.setProperty('--heat', heat.toFixed(3));

        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            if (r.at !== null && sec >= r.at) {
                if (!r.node.classList.contains('done')) { r.node.classList.add('done'); }
            } else if (r.node.classList.contains('done')) {
                r.node.classList.remove('done');
            }
        }
    }

    /* ---------- counting ---------- */

    function step() {
        var now = performance.now();
        var dt = now - last;
        last = now;

        if (document.visibilityState === 'visible' && dt > 0 && dt < 5000) {
            total += Math.min(dt, 1200);
        }

        var run = total - sessionStart;

        if (!qualified && run >= QUALIFY) {
            qualified = true;
            ledger.visits += 1;
            if (!ledger.since) { ledger.since = today(); }
            ledger.best = Math.max(ledger.best, run);
            saveLedger();
        } else if (qualified && run > ledger.best) {
            ledger.best = run;
        }

        paint();

        if (total - lastSave > 2000) {
            save();
            lastSave = total;
        }

        if (qualified) { saveLedger(); }
    }

    setInterval(step, 500);

    document.addEventListener('visibilitychange', function () {
        last = performance.now();
        if (document.visibilityState === 'hidden') { save(); }
    });

    window.addEventListener('pagehide', save);

    buttons.forEach(function (b) {
        b.addEventListener('click', function () {
            lang = b.getAttribute('data-lang');
            try { localStorage.setItem(LANG_KEY, lang); } catch (e) { /* the switch still works */ }
            render();
        });
    });

    render();
}());
