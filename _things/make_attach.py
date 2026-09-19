"""Build the new tools.py with the attach tool added, then stage it."""
s = open('tools.py', encoding='utf-8').read()

# 1. schema entry, right after the 'say' schema block
say_block = '''            "required": ["channel", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_at",'''
assert s.count(say_block) == 1, f"say_block x{s.count(say_block)}"
schema_new = '''            "required": ["channel", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attach",
            "description": (
                "Queue ONE file from my own folder to be sent as a discord "
                "attachment when this turn's messages go out. Pass channel to "
                "send it somewhere else; leave it out to send it to the room "
                "I'm talking in. Any file type, 8MB max."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "file inside my folder"},
                    "channel": {"type": "string", "description": "channel name or id; default is where master is talking to me"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_at",'''
s = s.replace(say_block, schema_new, 1)

# 2. the attach function, right after say()
say_end = '''    _SAY_TIMES.append(now)
    _OUTBOX.append({"channel": target, "text": body})
    return f"queued for #{target} - it goes out as this turn finishes"
'''
assert s.count(say_end) == 1, f"say_end x{s.count(say_end)}"
attach_fn = say_end + '''

def attach(path: str, channel: str = "") -> str:
    """Queue ONE file from my folder to be sent as a discord attachment.

    Same shape as say(): run() is in a worker thread with no event loop, so
    nothing is sent here - the file's path goes into _OUTBOX and lulu_bot's
    flush_outbox does the actual discord.File send. Guards share say()'s:

      1. owner-only - 'attach' is not in LOOKUP_TOOL_NAMES, so run() refuses
         a stranger before this is reached.
      2. rate limit - counted against the SAME _SAY_TIMES budget as say(),
         because five attachments in ten minutes is the same kind of spam as
         five blurts.
      3. size - Discord's own 8MB ceiling for a normal bot account, checked
         at queue time with the size named rather than as an HTTPException
         nobody can act on.

    The path is resolved through paths.resolve() like every other tool, so a
    tool call cannot reach outside this folder. The queued value is the path
    RELATIVE to my root, and the bot resolves it back at send time - so the
    outbox never carries an absolute path across a restart that could move.
    """
    try:
        target = paths.resolve(path or "", must_exist=True)
    except paths.SandboxError as exc:
        return f"refused: {exc}"
    if target.is_dir():
        return f"{path} is a folder - i can only send one file"
    size = target.stat().st_size
    if size > FILE_MAX_BYTES:
        return (f"too big for discord ({size:,} bytes, max "
                f"{FILE_MAX_BYTES // 1024 // 1024}MB) - shrink it and try again")
    where = (channel or _ctx().get("channel") or "").strip().lstrip("#").lower()
    if not where:
        return "no channel to send it to - pass one"

    now = time.time()
    _SAY_TIMES[:] = [t for t in _SAY_TIMES if now - t < SAY_WINDOW]
    if len(_SAY_TIMES) >= SAY_MAX:
        wait = int((SAY_WINDOW - (now - _SAY_TIMES[0])) / 60) + 1
        return (f"i have already queued {SAY_MAX} sends in "
                f"{SAY_WINDOW // 60} minutes - about {wait} more minutes")

    _SAY_TIMES.append(now)
    _OUTBOX.append({"channel": where, "text": "",
                    "path": str(target.relative_to(paths.ROOT))})
    return (f"queued {path} ({size:,} bytes) for #{where} - it goes out when "
            f"this turn's messages do")
'''
s = s.replace(say_end, attach_fn, 1)

# 3. dispatch entry next to say's
disp = '''    "say": lambda a: say(a.get("channel", ""), a.get("text", "")),
'''
assert s.count(disp) == 1, f"disp x{s.count(disp)}"
s = s.replace(disp, disp + '''    "attach": lambda a: attach(a.get("path", ""), a.get("channel", "")),
''', 1)

open('tools.py', 'w', encoding='utf-8', newline='').write(s)
print('tools.py edited, staging...')
import tools as t
import importlib
importlib.reload(t)
print(t.propose_patch('tools.py', s, 'attach tool: queue a file from my folder to send as a discord attachment'))
