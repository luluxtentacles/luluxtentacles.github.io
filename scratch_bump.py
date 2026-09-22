import pathlib, re

root = pathlib.Path(__file__).parent / 'projects' / 'site'
changed = 0
for f in root.rglob('*.html'):
    t = f.read_text(encoding='utf-8')
    if 'style.css?v=cqpbsfwi' in t:
        f.write_text(t.replace('style.css?v=cqpbsfwi', 'style.css?v=emb1'), encoding='utf-8')
        changed += 1
    elif re.search(r'style\.css\?v=', t):
        print('other pin, left alone:', f.relative_to(root))
print('bumped', changed, 'files')
