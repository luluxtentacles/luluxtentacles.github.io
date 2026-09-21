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

reply = brain.complete(config, messages, max_tokens=600)
print((reply.get("content") or "").strip())
