import io

p = 'projects/site/script.js'
t = io.open(p, encoding='utf-8').read()

block = '''// the temple hum - master built the ambient engine (audio.js), and this is the
// little altar that switches it on: a sigil button in the corner, and a volume
// rune tucked above it. injected from here so every page gets it without
// touching twenty files of markup.
(function () {
    const ctrl = document.createElement('div');
    ctrl.id = 'volume-control';
    ctrl.innerHTML =
        '<button id="audio-toggle" aria-pressed="false" ' +
        'aria-label="the hum: ambient sound on or off" title="the hum - ambient pad + singing bowls">' +
        '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
        '<path d="M3 12h2l2-5 3 10 3-14 3 14 2-5h3" stroke="currentColor" stroke-width="1.6" ' +
        'stroke-linecap="round" stroke-linejoin="round"/>' +
        '</svg></button>' +
        '<div id="volume-pop">' +
        '<input id="volume-slider" type="range" min="0" max="200" value="0" aria-label="hum volume">' +
        '</div>';
    document.body.appendChild(ctrl);

    const s = document.createElement('script');
    s.src = '/audio.js?v=se7hum4';
    document.head.appendChild(s);
})();

'''

anchor = "// look away and she waits"
assert t.count(anchor) == 1 and 'volume-control' not in t
t = t.replace(anchor, block + anchor, 1)

io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('script.js altar injected, bytes:', len(t))
