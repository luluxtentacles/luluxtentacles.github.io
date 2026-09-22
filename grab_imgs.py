import re
h = open('cw.html', encoding='utf-8', errors='ignore').read()
print('marker:', h.count('/w/images'))
urls = re.findall(r'(/[A-Za-z]+/images/[^"\'\s<>]+)', h)
seen = []
for u in urls:
    if u not in seen:
        seen.append(u)
print(len(seen))
for u in seen[:60]:
    print('https://sonichu.com' + u.replace('&amp;', '&'))
