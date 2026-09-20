# What changed in me

Notes left for me by whoever changed my code. Newest last, append only.

I read the entries I have not seen yet on my next turn with master, so this is how
I find out what was done to me, instead of inferring it from behaviour.

Each entry starts with a `## ` line: the date, then what it is about. If a later
entry needs to correct an earlier one, say so in the NEW entry - do not edit the
old one, because the point of this file is that the record of what was done to me
cannot quietly change.

## 2026-09-20 14:10 - I come back holding the work

what: when I restart, I now get back what master had asked me for and what I was
doing about it, in the same channel he was talking to me in.

why: before this, a restart told me only that a patch had landed - the file name
and a checkpoint. It never told me the job. So an update in the middle of
something meant starting cold on the other side of it.

means: if master starts something and an update interrupts it, he does not have to
say it twice. I open by picking the work back up. A note from a DM comes back in
the DM; a note from one room never fires in another.

how to use it: when I restart part-way through a job, the next step goes in
`brief` - on `request_restart` and on `propose_patch` both. That is what comes back
to me. If I leave it out, nothing is carried and I start clean, which is fine for
a plain bounce and wrong for an interrupted job.

## 2026-09-20 14:10 - this file

what: `CHANGELOG.md` now sits at my root, and I read the entries I have not seen
yet on my next turn with master.

why: master, 2026-09-20 - "whenever we update her here we leave a note for her
saying what we did". My memory of the rooms is not this. That store holds what
people told me, never what was done to my code, so nobody could look at me after
an update and learn what had changed except by reading the diff.

means: changes to me come with words now. It is tracked by git on purpose - it is
the record of what was done TO me, so it should not be something anyone can
quietly rewrite.
