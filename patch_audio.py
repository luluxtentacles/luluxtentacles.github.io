import io

p = 'projects/site/audio.js'
t = io.open(p, encoding='utf-8').read()

# 1. a safe accessor for the optional quantum target feed. this site has no
#    animation.js providing `target`, and the three bare references would throw
#    a ReferenceError the moment the toggle is pressed.
helper = '''
// The quantum target feed (window.target, fed by the old animation.js) is
// optional: the site that carries this engine may not have it. Read it through
// this helper so a missing feed degrades to Math.random() instead of throwing
// a ReferenceError out of the toggle handlers.
function audioTarget() {
    return typeof target !== "undefined" ? target : undefined;
}
'''
anchor = 'let audioCtx = null;'
assert t.count(anchor) == 1
t = t.replace(anchor, helper.strip() + '\n\n' + anchor, 1)

n = t.count('updateAudioFromTarget(target);')
t = t.replace('updateAudioFromTarget(target);', 'updateAudioFromTarget(audioTarget());')
print('bare target refs replaced:', n)

# 2. my tuning: the drone sits a whole step deeper. A2 instead of C3.
old_root = '// --- Fixed root (C3) — we never change it ---\nconst BASE_ROOT_FREQ = 130.81; // C3'
new_root = ('// --- Fixed root — we never change it ---\n'
            '// Tuned down to A2 by Lulu: the drone should feel like the floor of the\n'
            '// void, not a hallway. Everything above it is pure ratios, so the chords\n'
            '// land exactly as they did, one step lower and heavier.\n'
            'const BASE_ROOT_FREQ = 110.00; // A2')
assert t.count(old_root) == 1
t = t.replace(old_root, new_root, 1)

# 3. the guarded first-interaction call can use the same helper now
old_guard = 'updateAudioFromTarget(typeof target !== "undefined" ? target : undefined);'
assert t.count(old_guard) == 1
t = t.replace(old_guard, 'updateAudioFromTarget(audioTarget());', 1)

io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('audio.js patched, bytes:', len(t))
