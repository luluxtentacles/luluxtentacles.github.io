import io
p = 'projects/site/style.css'
t = io.open(p, encoding='utf-8').read()
old = '''#volume-pop {
    width: 1.9rem;
    height: 8rem;'''
new = '''#volume-pop {
    position: relative;   /* the slider inside is stood on end and centred against this */
    width: 1.9rem;
    height: 8rem;'''
assert t.count(old) == 1
t = t.replace(old, new, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('fixed')
