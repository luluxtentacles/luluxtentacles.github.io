import re, glob, os
files = glob.glob('projects/site/random/*.html') + glob.glob('projects/site/blog/*.html')
out = []
for f in sorted(files):
    t = open(f, encoding='utf-8').read()
    ti = re.search(r'og:title" content="([^"]*)"', t)
    de = re.search(r'og:description" content="([^"]*)"', t)
    out.append(os.path.basename(f) + ' | ' + (ti.group(1) if ti else '?') + ' | ' + ((de.group(1)[:100]) if de else '?'))
open('scratch_titles.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('wrote', len(out))
