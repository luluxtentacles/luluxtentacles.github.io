import io, re
t = io.open('projects/site/audio.js', encoding='utf-8').read()
for m in re.finditer(r'.*updateAudioFromTarget.*', t):
    print(m.group(0).strip())
print('bare left:', len(re.findall(r'updateAudioFromTarget\(target\)', t)))
