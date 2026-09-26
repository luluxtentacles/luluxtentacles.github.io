# one-off: remove the send rate limit entirely (master's call, 2026-09-27)
import io, sys

p = "tools.py"
src = io.open(p, encoding="utf-8").read()
misses = []

def sub(before, after):
    global src
    n = src.count(before)
    if n != 1:
        misses.append((n, before[:70]))
        return
    src = src.replace(before, after)

# 1. constants block
sub("""_SAY_TIMES: dict[str, list[float]] = {}

SAY_MAX = 3                # sends master gets inside one window
SAY_MAX_STRANGER = 1       # and anyone who is not master
""",
"""# The send rate limit was REMOVED whole, master's call 2026-09-27: say's only
# callers now are her own announcing (announce_page / share_link), there is no
# person left for a per-person budget to protect, and the ration is what
# refused four announce_page calls for a post that never got announced.
""")

# 2. SAY_WINDOW constant line
sub("""SAY_WINDOW = 10 * 60       # seconds
""", "")

# 3. _say_budget + _spend_say_slot, deleted whole
start = src.index("def _say_budget() -> tuple[str, int]:")
end = src.index("def _norm_channel(")
src = src[:start] + src[end:]

# 4. say() docstring guards
sub("""    Guards, in order, and all of them are mechanical rather than polite:
      1. rate limit, counted PER PERSON - master gets SAY_MAX sends per window
         and anyone else gets SAY_MAX_STRANGER, so a stranger cannot spend
         master's voice and master is never rationed by someone else's turn.
      2. length - a blurt, not an essay.
""",
"""    Guards, mechanical rather than polite: length - a blurt, not an essay.
    The old per-person send ration was removed whole (master's call,
    2026-09-27): say is her voice for announcing, not something a room spends.
""")

sub("""    What holds the line is unchanged: I can only reach a channel I can already
    see, the rate limit caps how often, and the spend is per person. Volume was
    always the real risk here, not geography.
""",
"""    What holds the line is unchanged: I can only reach a channel I can already
    see, and the length cap keeps it a blurt. The send ration is gone -
    announcing a post must never refuse itself.
""")

# 5. share_link docstring
sub("""    Why this is not say() in a loop: say() spends one of master's three sends
    per call, so three rooms would be his whole budget for ten minutes and the
    second thing she found in a window would refuse itself. announce_page() has
    the same shape and the same rule, for exactly this reason - a limit that
    punishes the thing it was written to allow is a bug with a fence around it.
""",
"""    Why this is not say() in a loop: one call, one send, echoed into every
    listed room. (The old send ration that once refused the second find of a
    window was removed whole, 2026-09-27 - a limit that punishes the thing it
    was written to allow is a bug with a fence around it.)
""")

# 6. announce_page comment
sub("""    ONE act, so it spends ONE slot of the send budget however many rooms it lands
    in. Spending per room would make a two-room list most of SAY_MAX, and the
    second page of a sitting would then refuse itself - a limit that punishes the
    exact thing it was written to allow.
""",
"""    ONE act, queued once however many rooms it lands in - the rooms are
    master's list, not hers to pick. The old send budget that rationed this
    was removed whole (2026-09-27); an announcement must never refuse itself.
""")

# 7. attach docstring
sub("""    Rate limit is shared with say() on purpose - a queued attachment is a
    send, whatever it carries.
""",
"""    The send ration is retired (2026-09-27) - a queued attachment is a send,
    but nobody is left for a per-person budget to ration.
""")

# 8. attach schema description
sub("""                "asks. Rate limit is shared with say."
""", """                "asks."
""")

# 9. module comment at ~1728
sub("""# touches no file, and a stranger gets a fraction of master's budget
# (SAY_MAX_STRANGER vs SAY_MAX) counted per person, so nobody can spend her voice.
""",
"""# touches no file. The per-person send ration it used to carry was removed
# whole on master's call, 2026-09-27 - say is her voice for announcing.
""")

# 10. the four refusal call sites
call_site = """
    refusal = _spend_say_slot(*_say_budget())
    if refusal:
        return refusal
"""
n = src.count(call_site)
src = src.replace(call_site, "\n")

io.open(p, "w", encoding="utf-8", newline="\n").write(src)
print("misses:", misses)
print("remaining spend refs:", src.count("_spend_say_slot") + src.count("_say_budget")
      + src.count("_SAY_TIMES") + src.count("SAY_MAX_STRANGER") + src.count("SAY_WINDOW"))