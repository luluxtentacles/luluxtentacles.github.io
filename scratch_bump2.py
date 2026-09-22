import pathlib

root = pathlib.Path(__file__).parent / 'projects' / 'site'
for f in root.rglob('*.html'):
    t = f.read_text(encoding='utf-8')
    if 'style.css?v=cow1a2b3c' in t:
        f.write_text(t.replace('style.css?v=cow1a2b3c', 'style.css?v=emb1'), encoding='utf-8')
        print('bumped:', f.relative_to(root))
