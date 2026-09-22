h = open('projects/site/style.css', encoding='utf-8').read()
i = h.find('.cow-hero')
print(h[max(0, i - 100):i + 500] if i >= 0 else 'not found')
