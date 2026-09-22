import io

# --- audio.js: a11y + stale-global + compressor spec fixes ---
p = 'projects/site/audio.js'
t = io.open(p, encoding='utf-8').read()

# 1. compressor attack/release: spec range is [0,1]s, 1.2/3.0 were being
#    silently clamped by the browser anyway.
old = '''    compressor.attack.value = 1.2;
    compressor.release.value = 3.0;'''
new = '''    // attack/release live in [0, 1] seconds in the spec - anything higher is
    // silently clamped by the browser (1.2 / 3.0 just became 1 / 1). Park both
    // at the ceiling so the soft squeeze stays as slow as the spec allows.
    compressor.attack.value = 1.0;
    compressor.release.value = 1.0;'''
assert t.count(old) == 1
t = t.replace(old, new, 1)

# 2. one helper owns the button's visual + a11y state, so class and
#    aria-pressed can never drift apart (aria was stuck on "false").
old = '''function syncSliderDisplay() {
    if (!volumeSlider) return;
    volumeSlider.value = audioEnabled ? Math.round(volumeLevel * 100) : 0;
}'''
new = old + '''

// One place for the sigil's lit state: the CSS class AND the aria-pressed
// flag move together, so screen readers hear what the eye sees.
function setToggleState(on) {
    audioToggleBtn.classList.toggle("on", on);
    audioToggleBtn.setAttribute("aria-pressed", on ? "true" : "false");
}'''
assert t.count(old) == 1
t = t.replace(old, new, 1)

n_add = t.count('audioToggleBtn.classList.add("on");')
n_rem = t.count('audioToggleBtn.classList.remove("on");')
t = t.replace('audioToggleBtn.classList.add("on");', 'setToggleState(true);')
t = t.replace('audioToggleBtn.classList.remove("on");', 'setToggleState(false);')
print('toggle sites rewired:', n_add, 'on,', n_rem, 'off')
assert (n_add, n_rem) == (5, 2)

# 3. the exposed window.audioEnabled was a snapshot taken at load and went
#    stale forever after; make it a live getter.
old = '''// Expose globals (for animation.js)
window.audioEnabled = audioEnabled;
window.updateAudioFromTarget = updateAudioFromTarget;'''
new = '''// Expose globals (for animation.js). audioEnabled is a live getter so the
// published flag can never go stale the moment a toggle flips the real one.
Object.defineProperty(window, "audioEnabled", { get: () => audioEnabled });
window.updateAudioFromTarget = updateAudioFromTarget;'''
assert t.count(old) == 1
t = t.replace(old, new, 1)

io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('audio.js bytes:', len(t))

# --- script.js: cache pin bump so visitors get the fixed engine ---
p = 'projects/site/script.js'
t = io.open(p, encoding='utf-8').read()
old = "s.src = '/audio.js?v=se7hum4';"
assert t.count(old) == 1
t = t.replace(old, "s.src = '/audio.js?v=se7hum5';", 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('script.js pin bumped to se7hum5')
