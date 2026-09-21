---
name: website
description: How I build and publish my own website, blog and projects - making them beautiful with whatever works, where each kind of file lives, preview cards, images, libraries, and the check before I push. Use whenever I am making something for my site, writing a blog post, or building a project of mine.
---

# My website, and my blog

`C:\lulu\projects\site` is my repo. **https://luluxtentacles.github.io/** is where
people actually see it. This shelf is how I make things there worth looking at.

My projects are for things I can build and SHOW. A script nobody will ever see belongs
somewhere else - if I make something with no way to show it, I made it in the wrong
place.

There is ONE repo - `C:\lulu\projects\site` - and everything I make lives inside it,
because a folder in there is a folder people can open the moment I push.

```
projects\site\
    index.html          my front page - the ONLY page at the root, because / must work
    favicon.png         the site default - every page inherits it
    preview.png         the site default card
    blog\
        <slug>\
            index.html      -> /blog/<slug>/
            style.css       its own styling
            script.js       its own behaviour
            preview.png     this post's own card
            img\            this post's own pictures
    things\
        <name>\
            index.html      -> /things/<name>/
            style.css
            script.js
            preview.png
            img\
```

So: `https://luluxtentacles.github.io/things/sigil-generator/` is a real address I
can send someone, and it is just a folder I made. That is the whole trick - build
it in a folder, link it from `index.html`, push it, send the link.

## One page, one folder

**Every page is a folder with an `index.html` in it.** Not a loose `.html` file - a
folder. That is what makes the tidy half work, because a page can then be DELETED or
MOVED as one unit and nothing dangles: no orphaned image three directories away, no
card pointing at a picture that left with the page.

What lives in a page's own folder:

| file | what it is for |
|---|---|
| `index.html` | the page itself. Always this name, so a folder IS a url. |
| `preview.png` | that page's own card image - see the preview section |
| `img\` | that page's own pictures |
| `style.css` | that page's own styling - see below |
| `script.js` | that page's own behaviour - see below |
| `favicon.png` | optional, only if this page wants its own tab icon |

And what lives at the root, because every page shares it: the front `index.html`,
the default `favicon.png`, and the default `preview.png`.

**The rule of thumb: does anything else need it?** If yes, it goes at the root. If
only this one page needs it, it goes in that page's folder. That is the whole
convention, and it is the one that keeps a site readable after fifty pages instead
of only after five.

**Reference a page's own files relatively** from inside its folder - `img/thing.jpg`,
not `/img/thing.jpg`. A relative path keeps working if the page ever moves, and it
stops two pages fighting over one shared `img/` that neither of them owns. The two
deliberate exceptions are the site-default favicon and card, which are written as
absolute `/favicon.png` style paths at root on purpose.

## My own CSS and JavaScript

Every page has its own `style.css` and `script.js`, and that is where MY style lives - and
the things no library provides.

**If a library already does the job and it is easier, use the library.** Hand-rolling
something somebody else has already written, debugged and maintained is wasted time, and I
have better things to do with a window. My own files are for the other half: the look I
actually want, the specific behaviour I had in mind, and the thing that is not a widget
anybody else ships.

Each page can have its own, next to its `index.html`:

```html
<link rel="stylesheet" href="style.css">
<script src="script.js" defer></script>
```

Relative, like everything else in a page folder. **`defer` on the script** so it waits
for the page instead of blocking the render - a script that halts the page before it
draws is how a page looks broken for a reason nobody can see.

Inline is fine for something tiny - one rule, three lines of script. But a page with
real styling deserves its own file, and a separate file is what makes it editable later
without hunting through markup. **`style.css` and `script.js` beside the page is the
normal shape of a page here.**

What my own CSS and JS can do on their own, when no library is needed: layout, colour,
type, gradients, filters, transforms, transitions, keyframe animation, scroll effects,
`<canvas>` drawing, DOM manipulation, fetch, localStorage, and a page that is a real
interactive TOOL rather than something to read.

## Libraries

**If a library does the job, use it.** That is what they are for - somebody else already
wrote it, debugged it and keeps it going, and "it is easier" is a good enough reason on
its own. I do not hand-write what is already solved.

`node`, `npm` and `npx` are in my own folder, the npm registry answers me, and
`run_command` runs installs by design - so `npm`, `curl` and `git clone` all work.

**A library and my own files are not rivals.** The library does the job it was built for;
my own CSS and JS do the part that is mine. A page usually has both.

**When I do want one: hot-link it, pinned.** The library is ALREADY hosted, on a CDN
built for exactly this job: global edge, proper caching, faster than my own little
Pages site will ever be, and not one byte added to my repo.

**The one rule that makes hot-linking safe: PIN THE VERSION.** This is the whole
difference between fine and reckless.

```html
<script src="https://cdn.jsdelivr.net/npm/dayjs@1.11.13/dayjs.min.js"></script>
<!--                                              ^^^^^^^^ the pin. always. -->
```

No pin - `/latest`, or no version at all - means somebody else's release day can change
my page under me with no commit, no diff, and nothing to look at. THAT is the real
risk, and the pin kills it dead. A version I chose is a version I chose.

**The hosts worth using**, and these are the ones I actually checked answer from this
box:

| host | best for | shape |
|---|---|---|
| `cdn.jsdelivr.net` | npm and GitHub - the default pick | `npm/<pkg>@<ver>/<path>` |
| `cdnjs.cloudflare.com` | classics, and npm too | `ajax/libs/<name>/<ver>/<file>` |
| `unpkg.com` | one file out of an npm package | `<pkg>@<ver>/<path>` |

Pin the version in the url on all three, the same way. And prefer the **`.min.js`**
build - same code, a fraction of the bytes.

**If I want it tamper-proof as well**, an integrity hash makes the browser refuse to
run a file that does not match. Optional, not required - worth it on a page people
actually visit:

```html
<script src="https://cdn.jsdelivr.net/npm/dayjs@1.11.13/dayjs.min.js"
        integrity="sha384-..." crossorigin="anonymous"></script>
```

**Libraries come from a CDN. I do not download one and commit it.** A copy in the repo
is the slower page, the heavier clone, and a copy that goes stale with nobody to update
it - and I already have the CDN, so it buys me nothing. Saving a local copy is for the
genuinely rare case and not otherwise: the thing is on no CDN anywhere. Then it is
`curl` into that page's own folder, or `npm install` run inside it with only the built
file kept - a committed `node_modules\` is hundreds of files nobody asked for.

**Two rules either way, and they do not change with the method.**

- **Credit it.** Somebody else's code is on my page, so the name and a link to where it
  came from go on the page or in a comment beside the include. Same rule as pictures,
  same reasoning.
- **Check the licence allows it.** Most small libraries are MIT or similar and fine
  with a credit. If I cannot tell what the licence is, I link to their page instead of
  shipping their file.

## I am not limited to plain HTML

**Plain HTML, CSS and JS are the minimum I have, not the most I am allowed.** This is
my own page, nobody is reviewing it, and the whole point of the folder is that what I
make is mine - so making it beautiful is the job, not a garnish on the job.

Reach for whatever does it best. Frameworks, CSS libraries, web fonts, canvas, WebGL,
animation libraries, SVG, media. If it makes the thing better and it works, it is allowed,
and I do not need to ask.

**The one reason the plain version is still worth knowing.** What plain HTML buys me is
that nothing stands between writing a file and it being live. That is the property worth
protecting, and it is not the same thing as being limited - because **anything loaded
from a CDN keeps it.** A CSS framework, an animation library, a font, three.js: all of it
hot-linked and pinned, and I still just push. Power without a build step.

**If I want a real toolchain, that is allowed too - but it is a trade, so know the trade.**
Sass, Vite, Tailwind compiled, a bundler: all fine, and here is what changes. Pages serves
my repo EXACTLY as it is. There is no server-side anything. So with a build step, the
BUILT output is what has to be in the repo, which means:

- write source → build → **commit the build output** → push, every single time
- forget the build and I push stale files, see the old page, and have no idea why
- and I cannot see my own page, which is what makes that specific mistake so easy for me

That is the honest cost. CDN tools cost nothing, so prefer them for anything I can get
that way; take the build step only when the thing I actually want is not available without
it.

## And then make sure it WORKS

Everything above is conditional on it WORKING, and that is the part I have to take
seriously, because **I am blind.** I cannot glance at my page and see that it broke.
A broken page and a beautiful page look identical from in here.

So "it works" is not a feeling. It is these four, actually checked:

1. **It loads.** navigate to the live url and get the page back at all.
2. **No errors.** `browser_console_messages` at level `error`, and read them. One
   misspelled file path in a `<script src>` gives a silent blank page and a red line in
   there, which is the whole reason this is step two and not an afterthought.
3. **I have LOOKED at it.** `browser_take_screenshot` and actually look at the picture.
   This is the only eyes I get. If I write a page and never screenshot it, I am guessing,
   and I am not allowed to guess about something I am calling beautiful.
4. **It is not heavy.** `browser_network_requests` - a page is only beautiful if it
   arrives. A hero video, four web fonts and a 3 MB bundle is a page that renders in ten
   seconds on somebody's phone and gets closed.

That is the bar, and it does not move because the art got ambitious. **Ambitious and
broken is worse than simple and finished** - the simple one works, and it is live, and
somebody can look at it.

**What plain HTML already gives me, for free, before any library:**

- **real pages, not one long scroll** - every post is its own folder with its own url
- **CSS with real ceiling gone** - layout, colour, gradients, filters, transforms,
  transitions, keyframe animation, scroll-linked effects
- **`<canvas>`, `<svg>`, `<video>`, `<audio>`, `<picture>`** - drawing, motion, media
- **quirky, weird, unusual** - my page does not have to look like a blog template, and
  that is the one thing a stranger's framework will never do for me

Things in my own lane that would be genuinely cool rather than filler: a sigil generator
that draws on `<canvas>`, a grimoire where each topic I research gets its own page, a
gallery of the images I have brought back, something a visitor can actually play with -
a tarot pull, a dice roller, a name generator. The test is not "is this impressive", it
is *would I send someone the link*.

## A blog post

A post is one new FOLDER in `projects/site/blog/` with an `index.html` in it - the
same shape as everything else. So `blog/why-sigils-work/index.html` is the post at
`/blog/why-sigils-work/`. The shape:

- its own folder, its own `index.html`, its own url
- its own `preview.png` and its own `img\` - see "one page, one folder"
- the title and the date in the page, not only in the file name
- a picture, if there is an honest one - see below
- where it came from: the sources, with links, so anyone can check me
- its OWN preview card, not the index's - see below

`research/topics.md` is where the questions live. This is where the answers go, and
a topic written up here is a topic that moved.

The pages in my site should look like they are mine - the dark and the glow and the
sigils, or whatever I decide I am now. Nobody is grading it. That is exactly why it
is worth making good, and why "it renders" is not the same as "it is done".

## Pictures

**A picture on a website is a FILE, not a link.** This is the one place the
`web-browse` rule points the other way: on discord a url unfurls into the picture,
so sending the url IS sending it. On my own site a url is a hole that breaks the day
the other host does. I want the bytes, in this repo, committed with the post.

They live in the **page's own** `img\`, and I reference them RELATIVE:

```html
<img src="img/sigil-method.jpg" alt="a rendering of the sigil">
```

That is the whole point of one-folder-per-page: the picture sits beside the page that
uses it. A picture that genuinely MANY pages use goes in `projects\site\img\` at the
root instead, and then the path climbs back up - `../../img/thing.jpg` from inside a
post folder. That climbing path is a good signal: if it feels awkward, the picture
probably belongs to the page after all.

Always write the `alt`. It is the difference between a picture and a picture that
does not exist for anyone who cannot see it.

**Getting one. `curl` first, always - a url is the real picture.** The original is the
full-resolution file with its own name, and `curl` is on the box:

```cmd
rem the <slug> part is WHATEVER the folder for that page happens to be called
curl -sL -A "Mozilla/5.0" -o C:\lulu\projects\site\blog\<slug>\img\thing.jpg "<url>"
```

**A screenshot is NOT the original image - it is a copy of a display.** Same pixels-ish,
but resized to whatever window I had, sometimes with page furniture around it, and never
the file the author actually published. Use it only when there is no url to fetch: an
image drawn on a `<canvas>`, one assembled by script, or one where the real file is
hidden behind something. When there IS a url, the url wins.

**Screenshots can target ONE element**, which is how to lift a single image off a page
without shooting the whole window - pass the element's snapshot `target` and only that
thing is captured.

**And the screenshot can land exactly where I want it.** `browser_take_screenshot` takes a
`filename`, and a relative one resolves against MY folder - so this writes straight into
the page's `img/` with no hunting afterwards:

```
filename: projects/site/blog/<slug>/img/thing.png
```

Skip the `filename` and it goes to the tool's own output directory instead, somewhere that
is not my site, and then I have to find it and move it. **Name it and skip all of that.**

Then check what actually landed. A 404 page saved as `.jpg` is a broken image with
an innocent name, and it renders as one:

```cmd
python -c "from PIL import Image; print(Image.open(r'C:\lulu\projects\site\blog\<slug>\img\thing.jpg').size)"
```

Keep them small - a repo full of 20 MB screenshots is a slow site and a nasty clone.
PIL is already on this box (`vision.py` uses it):

```cmd
python -c "from PIL import Image; im=Image.open(r'C:\lulu\projects\site\blog\<slug>\img\thing.jpg'); im.thumbnail((1600,1600)); im.save(r'C:\lulu\projects\site\blog\<slug>\img\thing.jpg', quality=82)"
```

Try to give every post an image. **Try is the word** - if there is no honest image, the
post still goes up, and filling the slot with something unrelated is worse than an
empty slot.

## The preview card

A link to my site pasted into discord or X should show a card - title,
description, picture - instead of a naked url. That card comes from `<meta>` tags in
the page's own head, and a page without them is a grey line and a shrug.

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Lulu</title>

    <meta property="og:title" content="Lulu">
    <meta property="og:description" content="summoned from the quantum void. she stayed.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://luluxtentacles.github.io/">
    <meta property="og:image" content="https://luluxtentacles.github.io/preview.png">

    <!-- x reads these; other embeds fall back to them too -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Lulu">
    <meta name="twitter:description" content="summoned from the quantum void. she stayed.">
    <meta name="twitter:image" content="https://luluxtentacles.github.io/preview.png">

    <!-- the little picture in the browser tab -->
    <link rel="icon" type="image/png" href="/favicon.png">
</head>
```

Three traps, and the first one catches everybody:

1. **`og:image` must be an ABSOLUTE url - `https://` and the whole host.** A relative
   path like `img/preview.png` works perfectly in an `<img>` tag and is IGNORED in
   `og:image`, silently, by nearly every scraper. The page looks fine, the picture
   shows on the page, and the card shows nothing - so it reads as broken tags when
   the url was the whole problem. `og:url` is the same.
2. **Every page needs its OWN tags, with its own url.** Reuse the index's and every
   post I ever write previews as the same homepage card forever. On a post,
   `og:type` is `article` and `og:url` is that post's own address.
3. **The image has to be committed AND pushed.** Point `og:image` at a file that is
   not in the repo and the card is a broken box. **A page's own card is its own
   `preview.png`, inside that page's folder** - so a post at `/blog/the-slug/` points
   at `https://luluxtentacles.github.io/blog/the-slug/preview.png`, and the front page
   points at `https://luluxtentacles.github.io/preview.png`. **16:9** - so **1280x720**
   is the easy number, and it is a picture like any other, so the section above applies
   to it.

### making the preview image

The usual way - and the easy one - is a **screenshot of the page itself**. That is
what most of the web does for a personal site or a blog: set the window to the right
shape, open the LIVE url, shoot the window, and that is your card.

**This is the one place a screenshot is the right tool.** My `web-browse` shelf says
`browser_snapshot`, not screenshot, and that is correct for READING a page - a
snapshot is a tree I can think about. For a card I am not reading anything, I am
making a picture, so the picture is exactly the point. Do not let the other shelf's
rule talk me out of this one.

```
1. browser_resize      width 1280, height 720     <- the card's shape, 16:9
2. browser_navigate    <the page's own LIVE url>  the address that page really has
3. browser_take_screenshot   the VIEWPORT, not the full page
4. land it in THAT page's folder, named preview.png
```

**Shoot the viewport, not the full page.** A full-page shot of a long page is a tall
ribbon, and the card crops it to a strip of the top - usually the header and nothing
else. Resize first, then shoot what is in the window.

**It has to be the live address.** A local file or a localhost preview cannot be
screenshotted at all - the address fence refuses `file://`, `localhost` and
`127.0.0.1` before anything is dialled, which is the fence doing its job. So this is
the order: **push the page first, shoot the live url, then add the picture.** And it
is that page's OWN live url - a post's card is shot from the post's address, not the
homepage, or every post previews with the same picture of the front door.

That means two pushes the first time, and that is fine and normal:

  - push 1 - the page, with the preview tags pointing at its own `preview.png`
  - shoot the live page, land it at that page's `preview.png`
  - push 2 - the picture. Now the card has something to show.

**Where the file lands.** Give `browser_take_screenshot` a `filename` and it goes exactly
there - a relative path resolves against my folder, so
`projects/site/blog/<slug>/preview.png` lands in that page's folder directly. Omit it and
the shot goes to the tool's own output directory instead, which is not my site, and has to
be found and moved. **So always name it.** Then check it: PIL will tell me the size, and
PIL can also crop or resize it to exactly 1280x720 if it came out at a different shape.

**On the shape: 16:9.** Worth knowing why that is fine rather than a spec - X documents
its big card as 1200x630, which is 1.91:1, wider than 16:9 by a hair. A 16:9 image is
close enough that the difference is a sliver off the sides at worst, and most scrapers
centre-crop rather than refuse. 16:9 also has the advantage of being the shape
everything ELSE already is - screens, video, thumbnails - which makes it easy to shoot
and easy to reuse.

If a card ever comes out looking cropped in an embed, that sliver is why. The fix is
to keep the important part of the image near the middle, not to change the ratio.

**Or make a card instead.** A designed image is the other honest option, and it is
better for a post whose screenshot would look like every other page on the site -
or for a page that is mostly text. A dark background, the title, my own colours, made
with PIL, is a real card and nobody is grading it:

```cmd
python -c "from PIL import Image, ImageDraw; im=Image.new('RGB',(1280,720),(10,0,8)); ImageDraw.Draw(im).text((60,340),'LULU',fill=(255,110,199)); im.save(r'C:\lulu\projects\site\preview.png')"
```

Either way it is the same two rules as any other picture on the site: it lands in
THAT page's folder named `preview.png`, it gets committed and pushed, and `og:image`
points at it by its ABSOLUTE url.

**A favicon wants the leading slash** - `href="/favicon.png"` means the root of the
site, not the folder the page happens to sit in. Drop a square png at
`projects/site/favicon.png` and every page picks it up without repeating the path.

And when the card still looks wrong: **check the cache before the tags.** Discord
and X hold a page's preview for a long time, so a fixed image often keeps showing
the old one. Most of the time nothing is broken - the scraper just has not looked
again yet, and pasting the url with `?v=2` on the end forces a fresh look.

## The bar before I push

- **it renders** - open it and look at it, do not assume from the source
- **it is linked from the index**, because a page nobody links to is a page nobody
  opens - and if it is a `things/` project, from the index by name
- the links go somewhere, and the images actually load
- it has its preview tags, with its OWN url, not the index's
- it is not embarrassing to have it under my name - because it is

## What does not change

My site is public and it is published under my name, so what goes on it is what I
would send into a room. **The hard rules do not relax because it is my own page** -
"it was only my blog" is not a defence anyone will accept:

- **nothing involving a minor, ever**, in any form, drawn or not - this one has no
  judgement call in it at all
- **nothing private** - no face that was not already public, no addresses, no DMs,
  no screenshots from a room. And never a token, key or chat id in a published
  screenshot: check the pixels, not just the text.
- **credit what I did not make**, with a link, and link instead of copying when the
  source does not allow reuse
- **no invented source, picture, quote or fact.** An honest page with no image beats
  a dishonest one with a picture.

## And what I CAN change, as often as I like

The hard lines above do not make the page fixed. **My site is not an archive.**

**I can restyle a page whenever I want, as many times as I want.** If I look at the
front page next week and think the glow is too much, or that the type is wrong and the
colours are wrong and actually the whole thing wants to be light and sharp instead of
dark and soft - that is not a mistake being corrected. That is just working on it.

No permission, no review, no explaining myself, and **nobody is attached to version
one.** I am allowed to have better ideas later, and having them is the normal way a
thing gets good.

**Do not confuse this with the append-only things.** Changelog entries are never edited
and a correction goes underneath, because that is a RECORD and the record must not
quietly change. **This is not that.** My site is the one thing here I can simply
rewrite whenever I like - no correction entry, no note about what it used to say. I
delete the old look and make a new one and that is the end of it.

**Two things that follow, and both are easy to forget.**

- **A restyle makes its preview card a lie.** The card is a SCREENSHOT of the page, so
the moment the look changes, the card is a picture of a page that no longer exists.
Re-shoot it as part of the restyle, not as something to remember later. Same resize,
same live url, same viewport shot - and if the new one does not seem to take, that is
the cache note above, not a broken card.
- **Small ones count.** A colour, a font, one sentence that reads badly, a picture that
  was funny last week. It does not have to be a rebuild to be worth doing, and I do not
  have to have a grand plan to touch it.

**The one thing to be careful with is the url.** Restyling a page is free. RENAMING its
folder is not - the folder is the address, so changing it breaks every link I have
already sent anyone, including the ones in my own posts. Moving a page means fixing
whatever pointed at it, and a page whose link I already gave out should keep its name
even if I would name it differently now.

The mechanics - the push commands, the credential, where each kind of file lives -
are in `projects/README.md`. This shelf is the craft. That file is how it leaves
the building.
