// the same-document flavour of the same api:
// flips this page's colours in place with a view transition when supported,
// falls back to flipping instantly everywhere else.
// firefox has shipped THIS half since v144 (october 2025),
// so the button works there even though cross-page fades do not.
const btn = document.getElementById('flip');

function flip() {
    document.body.classList.toggle('alt');
}

if (btn) btn.addEventListener('click', () => {
    if (document.startViewTransition) document.startViewTransition(flip);
    else flip();
});
