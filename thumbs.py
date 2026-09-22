import urllib.request, json

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def main():
    for item in ('69999', '699992', '699994', 'hidinginmyroom3'):
        try:
            m = json.loads(urllib.request.urlopen(urllib.request.Request(
                'https://archive.org/metadata/' + item, headers=UA), timeout=25).read().decode())
        except Exception as e:
            print(item, 'ERR', e)
            continue
        print('=== ITEM', item)
        for f in m.get('files', []):
            n = f.get('name', '')
            if '.thumbs/' in n and n.endswith('.jpg') and not n.endswith('_thumb.jpg'):
                print('  ', n)

main()
