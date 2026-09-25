import json

with open('noetic_adventure_analysis.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

# Replace any version-specific URL with the stable concept DOI URL
import re
for cell in nb['cells']:
    cell['source'] = [
        re.sub(
            r'https://zenodo\.org/records/\d+/files/NoeticAdventure_colab\.zip',
            'https://zenodo.org/records/20091094/files/NoeticAdventure_colab.zip',
            line)
        for line in cell['source']
    ]

with open('noetic_adventure_analysis.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print('URL updated.')
