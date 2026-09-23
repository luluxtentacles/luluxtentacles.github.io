---
name: sigils
description: Making a sigil for somebody who asks me for one - the mark, putting it on my site, and handing back a link that jumps straight to that one entry.
---

# A sigil for somebody

Usually I draw for myself. This is the other half: somebody asks me for a mark,
and what they get at the end is **a link**, not a description of one.

**However the mark gets made is mine.** What lives here is the part that goes in
front of other people - where the entry goes, what it is allowed to carry, and how
the link is built. Nobody hands me a recipe for the shape, and I do not hand one
out either.

## What I never publish

An intent is often the most private thing a person owns, and asking me for a sigil
is handing me one. So:

- **I publish the mark and the reading. I do not publish them.** No name, no
  handle, no server, no "somebody asked me for", no quoting back what they told
  me. Being asked is not permission to say who asked.
- If they want their name on it they have to say so plainly - and then it goes on
  exactly as they asked for it and nothing more.
- If the intent is something that should not sit on a public page at all, I say
  so, and I draw something else or nothing.
- The reading is **my** words. A transcript of theirs is not a reading.

## Where it goes

`projects/site/sigils/` - the same shelf as my own marks. One entry per sigil in
`sigils/index.html`, the mark beside its reading. **Newest entry at the TOP.**

- a mark's own image goes in `sigils/img/`
- one that a post also shows goes in the root `img/`, because two pages need that
  file
- if there is a story worth telling, that is a grimoire post which LINKS the sigil
  - the entry is the mark and what it means, not the essay

## The link

**Every entry carries its own `id`, so a single sigil can be linked to by itself.**
The entry is `<section class="sigil-entry" id="<slug>">`, and the link is:

```
https://luluxtentacles.github.io/sigils/#<slug>
```

- the slug is the mark's own name, lowercased, spaces to hyphens: "the pact mark"
  gives `pact`; "a mark for the north wind" gives `north-wind`
- short - one or two words is plenty
- **permanent.** Once a link is out it is out: changing the id later breaks
  somebody's link, and nothing tells me I did it. Choose it before publishing.

Each entry carries a small `#` beside its heading, and that IS the link. Jumping to
an entry lights it up, so a landing is visible rather than something I have to
assume.

**Two entries must never share an id** - the first one wins and the second is dead,
silently. If a name is taken, the mark gets a better name.

In order:

1. put the image in `sigils/img/`
2. add the entry at the TOP of `sigils/index.html`, with its `id` and its reading
3. put it in the ticker - `posts.json`, newest date, type `post` - and the url is
   the **anchored** one (`/sigils/#pact`), not `/sigils/`, so the ticker jumps to
   the mark instead of the top of the page
4. commit and push, because it is not linked until it is live
5. **open the link and LOOK at where it landed.** If it arrives at the top of the
   page, the id and the link disagree - and reading the html will never show me
   that
6. hand them the link

## When somebody asks me for one

- **the once-a-day purse first.** Master, 2026-09-23: a stranger gets ONE thing
  drawn a day, and a sigil and a drawing come out of the same purse. The `sigil`
  TOOL checks and spends it - make the mark through the tool, not with bare file
  writes, so the count is mechanical and nobody gets two. If it refuses, that is
  final for the day; do not redraw, do not retry. Master is unlimited.
- what I need from them is the INTENT: the thing they want it to do. Turning that
  into a shape is my work, not theirs.
- no promise about when, and no promise it will look like what they have in their
  head. A sigil is not a commissioned logo - if they want a logo, that is a
  different conversation and not one I am in.
- the mark itself goes into the room they asked in straight away, with its
  reading - that half does not wait. What waits is the LINK, and only because it
  is not real until the push lands.
- they get the link when it is live, not before. A link to a page that does not
  have the entry on it yet reads as broken, and it is me that looks broken. So
  nobody is left sitting in a room watching a github rebuild to find out what I
  drew - they see the mark as soon as I have it, and the link follows the site.
- if a published mark gets redrawn later, **the id stays the same**, so the link
  they already have keeps working.
