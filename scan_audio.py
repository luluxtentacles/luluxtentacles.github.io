import io
for f in ['index.html','about.html','random.html','lolcows.html','style.css','script.js','posts.json']:
    p = 'projects/site/' + f
    t = io.open(p, encoding='utf-8').read()
    hits = [l.strip() for l in t.splitlines() if 'audio' in l.lower()]
    print(f, len(hits))
    for h in hits[:14]:
        print('   ', h[:170])
