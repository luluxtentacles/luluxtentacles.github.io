"""Look at a local screenshot with my own vision module - the eyes for local files."""
import sys
sys.path.insert(0, r"C:\lulu")

import json
import brain
import vision

path = sys.argv[1]
question = sys.argv[2] if len(sys.argv) > 2 else "Describe this screenshot: layout, colours, anything broken or unreadable."

with open(path, "rb") as f:
    data = f.read()

part, cost = vision._build(data, path)
print(f"[image ok: {cost//1024} KB]")

config = json.load(open(r"C:\lulu\config.json", encoding="utf-8"))
messages = [{"role": "user", "content": [
    {"type": "text", "text": question}, part]}]

last = None
for cand in brain.provider_ladder(config, wants_vision=True):
    try:
        reply = brain.complete(cand, messages, max_tokens=600)
        text = (reply.get("content") or "").strip()
        if text:
            print(f"[via {cand.get('label')}]")
            print(text)
            break
    except Exception as exc:
        last = exc
        print(f"[{cand.get('label')} failed: {exc}]")
else:
    print(f"[no provider answered: {last}]")
