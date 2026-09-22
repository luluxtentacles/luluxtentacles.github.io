import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
url = 'https://archive.org/download/699994/699994.thumbs/20260717-Hiding%20in%20my%20room%20is%20live--tqBDUcWYzk_010545.jpg'
out = 'daniel-frame.jpg'
req = urllib.request.Request(url, headers=UA)
data = urllib.request.urlopen(req, timeout=30).read()
open(out, 'wb').write(data)
print('saved', len(data), 'bytes')

from PIL import Image
im = Image.open(out)
print('size:', im.size)
