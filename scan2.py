import io
for f in ['index.html','about.html','random.html','lolcows.html','style.css','script.js','blog/index.html','sigils/index.html','random/mothman.html','lolcows/chris-chan/index.html']:
    t = io.open('projects/site/' + f, encoding='utf-8').read()
    print('=====', f, len(t))
    print('script tags:', [l.strip() for l in t.splitlines() if '<script' in l])
    print('style tags:', [l.strip() for l in t.splitlines() if 'style.css' in l])
    print('has target global:', 'target' in t)
