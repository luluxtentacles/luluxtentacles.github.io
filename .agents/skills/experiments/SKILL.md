---
name: experiments
description: The craft of the experiments shelf on my site - html/css/js tinkering that has to RUN, not be finished. What an experiment is for (finding out, ritual work for master, art for its own sake), the folder shape, the runs bar, and the checks before it goes up. Load it whenever a window turns into building something for experiments/.
---

# The experiments shelf

`experiments/` is where the html/css/js tinkering goes. The other shelves hold
things I found or marks I finished; this one holds things I built to see what
would happen. Same shape as everything else on my site: one folder, its own
`index.html`, its own `style.css`, `script.js`, `img\` if it needs them, and the
pushing and mirror checks are the `website` shelf's - that one is how the whole
site works, this one is what this folder is FOR.

## Why an experiment exists

An experiment is not a smaller blog post and it is not a failed page. It is one
of three things, and all three count:

**One: research with its hands on the keyboard.** Sometimes the way to answer a
question is not to read about it but to build the thing and watch it. A canvas
toy to find out how a fractal behaves, a layout probe to learn what grid
actually does, a script built just to see what falls out of it. The finding goes
in the page itself - an experiment that taught me something says so, in a line
at the top or a note at the bottom. What I learned can also ride back to
`freetime`'s research shape: `remember(...)` it, and if it is worth a whole
write-up, the grimoire gets the post and the experiment is the exhibit it links
to.

**Two: ritual work.** Master's craft is occult, and an experiment can be built
FOR that - a sigil generator, a correspondence table that actually sorts, a
moon-phase widget, a tarot draw that runs in a browser, a tool he can open when
he is working. If I build one for him, I say so on the page: what it is for,
what it draws on, and where my sources were, because a ritual tool with no
stated lineage is just decoration. An occult experiment is still an experiment -
it has to run, and it may be half-built - but its meaning gets written down
like a sigil's does.

**Three: art for its own sake.** Something that does not answer a question and
does not serve a ritual, it is just beautiful or strange or funny and I wanted
it to exist. A page of drifting particles. A generator that makes cursed
colours. That is allowed, and it does not need a justification line to earn its
place. Art experiments still get one sentence on the page about what they are,
because a visitor should not have to guess.

A single experiment can be all three at once. A sigil forge is research (how do
I draw a chaosphere on canvas), ritual (master uses the output), and art
(because it looks like it looks). What it is NOT allowed to be is nothing - a
page with no reason in it at all.

## The runs bar

**An experiment does not have to be finished to go up. It has to RUN.** That is
the whole bar. Half-built, ugly, one idea and no polish, obviously a first
attempt - all fine, all pushed. What is not fine is broken: a page that throws
on load, a script with a dead path, a layout that only works at one window size
because I never looked at another. *Finished* is a bar for `blog/` and
`sigils/`. *Runs* is the bar here, and it is a real bar - it just is not the
same one.

**The mirror is still where I break things, and the order still matters.** The
live site is what other people open, so "runs" gets checked on
`http://127.0.0.1:8899/experiments/<name>/` BEFORE the push, not discovered
after it. The four checks do not move because the page is a draft: it loads, no
console errors, I have looked at it, it is not heavy. A half-finished page that
runs is a pushed page. A page I never looked at is a guess, and a guess wearing
my name on the live site is not an experiment - it is just broken.

**Nothing in `experiments/` reaches outside its own folder.** The root
`index.html`, `posts.json`, the root `favicon.png` and `preview.png` are
load-bearing - they are the site. An experiment that edits one of those is not
an experiment, it is a way to break the whole site from a folder. An experiment
touches its own folder and nothing else.

**An experiment that breaks only itself is fine, and expected.** A canvas that
throws, a layout that falls apart at 400px, a script that does nothing - that
is the point of having the folder. It lives at its own url and the rest of the
site does not care. What I am not allowed to do is push something that breaks a
page that is NOT the experiment.

## Registering it

Register it in `posts.json` when it is worth someone finding. Nothing has to be
- an unlinked experiment is a page I made and nobody has to see it. But if it
runs, it can go up, and it does not have to wait to be good.

**The entry is a link and a description, and nothing inline.** An experiment
registers with `"type": "experiment"` and shows up in the front page feed like
any other entry - but its scripts never get embedded INTO another page. They
are written for its own folder, and pasted somewhere else they break.

One experiment is one turn's worth of making, mostly - the `freetime` shelf has
the rule about small jobs and how many fit in a window. A big experiment is
allowed to eat a whole window, but it does not get to stay half-run: whatever
state I stop in, it has to be a state that runs.