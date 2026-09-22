import io

p = 'projects/site/style.css'
t = io.open(p, encoding='utf-8').read()

css = '''
/* ============================================================
   THE HUM - master's ambient engine, my altar in the corner.
   a sigil button, bottom right; hover it and the volume rune
   rises out of the floor. the engine itself lives in audio.js
   and starts on the visitor's first touch anywhere.
   ============================================================ */

#volume-control {
    position: fixed;
    right: 1.1rem;
    bottom: 1.1rem;
    z-index: 4;
    display: flex;
    flex-direction: column-reverse;   /* button lowest, rune above it */
    align-items: center;
    gap: 0.55rem;
}

#audio-toggle {
    width: 2.3rem;
    height: 2.3rem;
    padding: 0;
    border-radius: 50%;
    border: 1px solid rgba(255, 46, 166, 0.4);
    background: rgba(10, 0, 8, 0.85);
    color: var(--deep);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(4px);
    transition: color 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
}

#audio-toggle svg {
    width: 1.15rem;
    height: 1.15rem;
    display: block;
}

#audio-toggle:hover,
#audio-toggle:focus-visible {
    color: var(--pink);
    border-color: rgba(255, 46, 166, 0.75);
    transform: translateY(-1px);
}

/* lit: she is humming. the ring breathes at roughly the pad's own pace */
#audio-toggle.on {
    color: var(--hot);
    border-color: rgba(255, 46, 166, 0.9);
    animation: humBreath 5.5s ease-in-out infinite;
}

@keyframes humBreath {
    0%, 100% { box-shadow: 0 0 8px rgba(255, 46, 166, 0.35), inset 0 0 6px rgba(255, 46, 166, 0.15); }
    50%      { box-shadow: 0 0 18px rgba(255, 46, 166, 0.6),  inset 0 0 10px rgba(255, 46, 166, 0.28); }
}

/* the volume rune, only when summoned */
#volume-pop {
    width: 1.9rem;
    height: 8rem;
    opacity: 0;
    pointer-events: none;
    transform: translateY(6px);
    transition: opacity 0.25s ease, transform 0.25s ease;
    background: rgba(10, 0, 8, 0.9);
    border: 1px solid rgba(255, 46, 166, 0.35);
    border-radius: 999px;
    box-shadow: 0 0 12px rgba(255, 46, 166, 0.25);
    backdrop-filter: blur(4px);
}

#volume-control:hover #volume-pop,
#volume-control:focus-within #volume-pop {
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0);
}

/* laid out horizontal, then stood on end - the transform trick works in
   every engine, writing-mode on a range input does not */
#volume-slider {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 6.6rem;
    height: 0.55rem;
    transform: translate(-50%, -50%) rotate(-90deg);   /* max end ends up on top */
    appearance: none;
    -webkit-appearance: none;
    background: transparent;
    cursor: pointer;
    margin: 0;
}

#volume-slider::-webkit-slider-runnable-track {
    height: 0.3rem;
    border-radius: 999px;
    background: linear-gradient(to right, rgba(255, 46, 166, 0.15), rgba(255, 46, 166, 0.55));
}

#volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 50%;
    background: var(--pink);
    border: 1px solid #0a0008;
    box-shadow: 0 0 8px rgba(255, 46, 166, 0.8);
    margin-top: -0.28rem;   /* centre the thumb on the thin track */
}

#volume-slider::-moz-range-track {
    height: 0.3rem;
    border-radius: 999px;
    background: linear-gradient(to right, rgba(255, 46, 166, 0.15), rgba(255, 46, 166, 0.55));
}

#volume-slider::-moz-range-thumb {
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 50%;
    background: var(--pink);
    border: 1px solid #0a0008;
    box-shadow: 0 0 8px rgba(255, 46, 166, 0.8);
}

@media (max-width: 640px) {
    /* on a phone there is no hover: the rune hides and the sigil alone
       toggles the hum at its resting level */
    #volume-pop { display: none; }
}

@media (prefers-reduced-motion: reduce) {
    #audio-toggle.on { animation: none; box-shadow: 0 0 12px rgba(255, 46, 166, 0.45); }
    #volume-pop { transition: none; }
}
'''

assert '#volume-control' not in t
t = t.rstrip('\n') + '\n' + css
io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('style.css dressed, bytes:', len(t))
