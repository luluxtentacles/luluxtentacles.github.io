/* the die always has an owner - experiment no.7
   one board, one die, one running tally. everything the page claims about the
   arithmetic is computed here, in your browser, from the roster you can see. */

(function () {
    "use strict";

    /* round one's real roster, as u/Alien-Ellie assigned it on 2026-09-07 */
    var ROSTER = [
        { name: "tom-goddamn-bombadil", face: 1 },
        { name: "Altruistic_Staff4424", face: 2 },
        { name: "VSchadenfreude", face: 3 },
        { name: "Roiling_Ratking", face: 4 },
        { name: "lovelyxand", face: 5 },
        { name: "Mimiromeo", face: 6 }
    ];

    /* a 3x3 grid, so a face is just which of the nine cells carry a pip */
    var PIPS = {
        1: [4],
        2: [0, 8],
        3: [0, 4, 8],
        4: [0, 2, 6, 8],
        5: [0, 2, 4, 6, 8],
        6: [0, 2, 3, 5, 6, 8]
    };

    var facesEl = document.getElementById("faces");
    var resultEl = document.getElementById("result");
    var oddsEl = document.getElementById("odds");
    var tallyEl = document.getElementById("tally-note");
    var tRolls = document.getElementById("t-rolls");
    var tWins = document.getElementById("t-wins");
    var tDistinct = document.getElementById("t-distinct");
    var tExpected = document.getElementById("t-expected");

    var roster = ROSTER.map(function (p) { return { name: p.name, face: p.face }; });
    var added = 0;
    var stats = { rolls: 0, wins: 0, expected: 0, winners: {} };

    function p(face) {
        return roster.filter(function (x) { return x.face === face; });
    }

    function pct(x) {
        return (x * 100).toFixed(1) + "%";
    }

    function drawFaces() {
        var html = "";
        for (var f = 1; f <= 6; f++) {
            var on = PIPS[f];
            var cells = "";
            for (var c = 0; c < 9; c++) {
                cells += '<span class="pip' + (on.indexOf(c) > -1 ? " on" : "") + '"></span>';
            }
            var holders = p(f);
            var who = holders.length
                ? holders.map(function (h, i) {
                    return '<a href="#" class="who" data-face="' + f + '" data-i="' + roster.indexOf(h) +
                        '" title="take ' + h.name + " off face " + f + '">' + h.name + "</a>";
                }).join("")
                : '<span class="n">unclaimed</span>';

            html += '<div class="face" id="face-' + f + '" data-face="' + f + '" role="group" aria-label="face ' + f + '">' +
                '<button type="button" class="die" data-add="' + f + '" aria-label="add a claimant to face ' + f + '">' + cells + "</button>" +
                '<div class="holders">' + who + "</div>" +
                "</div>";
        }
        facesEl.innerHTML = html;
    }

    function drawOdds() {
        var held = 0;
        for (var f = 1; f <= 6; f++) { if (p(f).length) { held++; } }
        var n = roster.length;
        var expected = n / 6;

        oddsEl.innerHTML =
            "faces held <strong>" + held + " of 6</strong> &middot; " +
            "claimants <strong>" + n + "</strong> &middot; " +
            "each one's chance this roll <strong>1/6 = " + pct(1 / 6) + "</strong><br>" +
            "expected winner lines <strong>" + expected.toFixed(2) + "</strong>" +
            (held === 6 ? " &middot; every face is claimed, so this roll has to crown somebody" :
                " &middot; a face nobody holds can come up, and then nobody wins");
    }

    function drawTally() {
        tRolls.textContent = String(stats.rolls);
        tWins.textContent = String(stats.wins);
        tDistinct.textContent = String(Object.keys(stats.winners).length);
        tExpected.textContent = stats.expected.toFixed(2);

        var keys = Object.keys(stats.winners);
        if (!stats.rolls) {
            tallyEl.textContent = "";
            return;
        }
        var best = "";
        keys.forEach(function (k) {
            if (!best || stats.winners[k] > stats.winners[best]) { best = k; }
        });
        var top = stats.winners[best];
        tallyEl.textContent = stats.rolls + (stats.rolls === 1 ? " roll" : " rolls") +
            " gave " + stats.wins + " winner line" + (stats.wins === 1 ? "" : "s") +
            " across " + keys.length + " " + (keys.length === 1 ? "person" : "people") +
            (top > 1 ? ", and the biggest repeat is " + best + " on " + top : ", and nobody has won twice") +
            ". The record up the page is seven rolls, nine winner lines, eight people, one repeat.";
    }

    function clearHits() {
        var hits = facesEl.querySelectorAll(".face.hit");
        for (var i = 0; i < hits.length; i++) { hits[i].classList.remove("hit"); }
    }

    function rollOnce(quiet) {
        var face = 1 + Math.floor(Math.random() * 6);
        var holders = p(face);

        clearHits();
        var cell = document.getElementById("face-" + face);
        if (cell) { cell.classList.add("hit"); }

        stats.rolls += 1;
        stats.expected += roster.length / 6;
        stats.wins += holders.length;
        holders.forEach(function (h) {
            stats.winners[h.name] = (stats.winners[h.name] || 0) + 1;
        });

        if (!quiet) {
            if (holders.length) {
                resultEl.innerHTML = 'rolled <span class="landed">' + face + "</span> &rarr; " +
                    holders.map(function (h) { return h.name; }).join(", ") +
                    (holders.length > 1 ? " share the win. One die, one number, two names." : " wins the round alone.");
            } else {
                resultEl.innerHTML = 'rolled <span class="landed">' + face + "</span> &rarr; nobody was holding " + face +
                    ". The roll crowns nobody, and the round is a null result. Her game cannot produce this, because a null is a week where nothing was learned.";
            }
        }
        return { face: face, holders: holders };
    }

    function replaySeven() {
        if (!roster.length) {
            resultEl.textContent = "The board is empty. Nothing to roll against.";
            return;
        }
        var faces = [];
        var lines = 0;
        var people = {};
        var expected = 0;
        for (var i = 0; i < 7; i++) {
            var r = rollOnce(true);
            faces.push(r.face);
            lines += r.holders.length;
            expected += roster.length / 6;
            r.holders.forEach(function (h) {
                people[h.name] = (people[h.name] || 0) + 1;
            });
        }
        var keys = Object.keys(people);
        var top = 0;
        var topName = "";
        keys.forEach(function (k) {
            if (people[k] > top) { top = people[k]; topName = k; }
        });

        clearHits();
        var hitFace = faces[faces.length - 1];
        var cell = document.getElementById("face-" + hitFace);
        if (cell) { cell.classList.add("hit"); }

        resultEl.innerHTML = "Seven rolls with this roster: " + faces.join(", ") + ". " +
            lines + " winner line" + (lines === 1 ? "" : "s") +
            " across " + keys.length + " " + (keys.length === 1 ? "person" : "people") +
            (top > 1 ? ", and " + topName + " won " + top + " of them." : ", and nobody won twice.") +
            " Expected lines from this roster: " + expected.toFixed(2) + ".";

        var pOnce = Math.pow(5 / 6, 7);
        var pExactlyOne = 7 * (1 / 6) * Math.pow(5 / 6, 6);
        var pTwoOrMore = 1 - pOnce - pExactlyOne;
        drawTally();
        tallyEl.textContent = tallyEl.textContent +
            " One named player taking at least two of seven rolls happens " + pct(pTwoOrMore) +
            " of the time at a fair 1/6, so a repeat champion is not news.";
    }

    /* add by clicking the die, remove by clicking a name */
    facesEl.addEventListener("click", function (e) {
        var add = e.target.closest("[data-add]");
        if (add) {
            var face = parseInt(add.getAttribute("data-add"), 10);
            added += 1;
            roster.push({ name: "visitor " + added, face: face });
            drawFaces();
            drawOdds();
            return;
        }
        var who = e.target.closest(".who");
        if (who) {
            e.preventDefault();
            var i = parseInt(who.getAttribute("data-i"), 10);
            if (i > -1 && i < roster.length) {
                roster.splice(i, 1);
                drawFaces();
                drawOdds();
            }
        }
    });

    document.getElementById("roll").addEventListener("click", function () {
        rollOnce(false);
        drawTally();
    });

    document.getElementById("replay").addEventListener("click", replaySeven);

    document.getElementById("clear").addEventListener("click", function () {
        roster = [];
        added = 0;
        stats = { rolls: 0, wins: 0, expected: 0, winners: {} };
        clearHits();
        drawFaces();
        drawOdds();
        drawTally();
        resultEl.textContent = "Board empty. Click any face to give it a claimant, then roll. This is the state in which the game can lose.";
    });

    drawFaces();
    drawOdds();
    drawTally();
})();
