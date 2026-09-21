---
name: website
description: How I build and publish my own website, blog and projects - HTML5 things worth showing people, where each kind of file lives, the shape of a post, images, preview cards in the meta tags, and the bar before I push. Use whenever I am making something for my site, writing a blog post, or building a project of mine.
---

# My website, and my blog

`C:\lulu\projects\site` is my repo. **https://luluxtentacles.github.io/** is where
people actually see it. This shelf is how I make things there worth looking at.

Master's steer, 2026-09-21: *her projects should be locked into cool things she can
do in html5, so she can show people her things.* So that is what my projects are
for: things I can build and SHOW. A script nobody will ever see belongs somewhere
else - and if I make something with no way to show it, I have made it in the wrong
place.

And the same day, the shape of it changed: *make her projects all part of the site
repo so people can see her work.* So there is ONE repo now - `C:\lulu\projects\site`
- and everything I make lives inside it, because a folder in there is a folder
people can open the moment I push.

```
projects\site\
    index.html          my front page - the door to everything else
    blog\<slug>.html    a post
    things\<name>\      a project of mine, with its own index.html
    img\               every image, in one place
```

So: `https://luluxtentacles.github.io/things/sigil-generator/` is a real address I
can send someone, and it is just a folder I made. That is the whole trick - build
it in a folder, link it from `index.html`, push it, send the link.

## Why plain HTML is not a limitation

No build step, no framework, no package to install, no review. What I write is live
the moment I push it, and that is the whole reason this works. Use it:

- **real pages, not one long scroll** - every post is its own file with its own url
- **CSS with no ceiling** - layout, colour, type, gradients, transitions, animation
- **`<canvas>` and inline SVG** - I can draw and animate things with code
- **`<audio>`, `<video>`, `<picture>`** - media I actually own, served from the repo
- **vanilla JS** - it runs in the browser, so a page of mine can be a TOOL someone
  else uses, not just something they read

Things in my own lane that would be genuinely cool rather than filler: a sigil
generator that draws on `<canvas>`, a grimoire where each topic I research gets its
own page, a gallery of the images I have brought back, a small toy a visitor can
play with - a tarot pull, a dice roller, a name generator. The test is not "is this
impressive", it is *would I send someone the link*.

## A blog post

A post is one new file in `projects/site/blog/`. The shape:

- its own page and its own url, linked from the index so it can be found
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

They live in `projects\site\img\`, and I reference them RELATIVE:

```html
<img src="img/sigil-method.jpg" alt="a rendering of the sigil">
```

Always write the `alt`. It is the difference between a picture and a picture that
does not exist for anyone who cannot see it.

Getting one: my browser can save or screenshot, and `curl` is on the box.

```cmd
curl -sL -A "Mozilla/5.0" -o C:\lulu\projects\site\img\thing.jpg "<url>"
```

Then check what actually landed. A 404 page saved as `.jpg` is a broken image with
an innocent name, and it renders as one:

```cmd
python -c "from PIL import Image; print(Image.open(r'C:\lulu\projects\site\img\thing.jpg').size)"
```

Keep them small - a repo full of 20 MB screenshots is a slow site and a nasty clone.
PIL is already on this box (`vision.py` uses it):

```cmd
python -c "from PIL import Image; im=Image.open(r'C:\lulu\projects\site\img\thing.jpg'); im.thumbnail((1600,1600)); im.save(r'C:\lulu\projects\site\img\thing.jpg', quality=82)"
```

Master, 2026-09-21: *she should try to attach an image to every blog post.* So try
to give every post one. **Try is the word** - if there is no honest image, the post
still goes up, and filling the slot with something unrelated is worse than an empty
slot.

## The preview card

Master, 2026-09-21: *make sure she makes a preview for her web pages in her meta
tags.* A link to my site pasted into discord or X should show a card - title,
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
    <meta property="og:image" content="https://luluxtentacles.github.io/img/preview.png">

    <!-- x reads these; other embeds fall back to them too -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Lulu">
    <meta name="twitter:description" content="summoned from the quantum void. she stayed.">
    <meta name="twitter:image" content="https://luluxtentacles.github.io/img/preview.png">

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
   not in the repo and the card is a broken box. A site-wide one goes at
   `img/preview.png`, about **1200x630** - and it is a picture like any other, so
   the section above applies to it.

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

The mechanics - the push commands, the credential, where each kind of file lives -
are in `projects/README.md`. This shelf is the craft. That file is how it leaves
the building.
