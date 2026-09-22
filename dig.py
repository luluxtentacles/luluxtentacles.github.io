import urllib.request, json, re

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def grab(u, raw=False):
    r = urllib.request.Request(u, headers=UA)
    try:
        d = urllib.request.urlopen(r, timeout=25).read()
        return d if raw else d.decode('utf-8', 'ignore')
    except Exception as e:
        return 'ERR ' + str(e)

def main():
    # archive.org item thumbnails
    for item in ('69999', '699992', 'hidinginmyroom3'):
        h = grab('https://archive.org/metadata/' + item)
        if h.startswith('ERR'):
            print(item, 'ERR', h)
            continue
        m = json.loads(h)
        files = m.get('files', [])
        thumbs = [f['name'] for f in files if f.get('format', '').lower().startswith(('thumbnail', 'jpeg'))]
        print('ITEM', item, 'server:', m.get('server'), 'dir:', m.get('dir'))
        for t in thumbs[:10]:
            print('   thumb:', t)

    # reddit search
    for q in ('https://www.reddit.com/search.json?q=%22hiding+in+my+room%22+daniel&limit=15',
              'https://www.reddit.com/search.json?q=%22hidinginmyroom%22&limit=15'):
        h = grab(q)
        print('=== reddit', q[40:90])
        if h.startswith('ERR'):
            print('   ERR', h)
            continue
        try:
            d = json.loads(h)
        except Exception as e:
            print('   bad json', str(e), h[:200])
            continue
        for c in d.get('data', {}).get('children', []):
            p = c['data']
            print('  r/' + p.get('subreddit', '?'), '|', p.get('title', '')[:80], '|', p.get('url', ''), '|', p.get('permalink', ''))

main()
