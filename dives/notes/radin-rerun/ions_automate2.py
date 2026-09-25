"""
IONS Noetic Adventure — Multi-Pass Automation Script
=====================================================
Version: 2.9
Automates a specific gate of the IONS Noetic Adventure web experiment,
running it multiple times (passes) in sequence.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    export IONS_USERNAME="your-username"
    export IONS_PASSWORD="your-password"
    export IONS_GATE="1"
    export IONS_PASSNUMB="3"
    export IONS_RUN_ID="A"          # optional — distinguishes parallel runs
    python ions_automate2.py
"""

import argparse
import base64
import difflib
import io
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://www.noeticadventure.org/login"
SCREENSHOT_INTERVAL_SECONDS = 0.25
SCREENSHOTS_PER_EPOCH = 30
SCREEN_TIMEOUT_MS = 30_000
API_RETRY_COUNT = 1
FUZZY_THRESHOLD = 0.3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_env(name):
    value = os.environ.get(name)
    if not value:
        log.error("Environment variable %s is not set.", name)
        sys.exit(1)
    return value

def require_env_int(name, min_val=1):
    raw = require_env(name)
    try:
        val = int(raw)
        if val < min_val:
            raise ValueError(f"must be >= {min_val}")
        return val
    except ValueError as exc:
        log.error("Environment variable %s must be an integer >= %d (got %r): %s", name, min_val, raw, exc)
        sys.exit(1)

def screenshot_to_b64(screenshot_bytes):
    return base64.standard_b64encode(screenshot_bytes).decode("utf-8")

GATE_CROP_CONFIG = {
    1: {"flame_crop": {"left": 70, "top": 25, "right": 82, "bottom": 50},
        "word_crop":  {"left": 81, "top": 16, "right": 97, "bottom": 44}},
    2: {"flame_crop": {"left": 63, "top": 38, "right": 78, "bottom": 55},
        "word_crop":  {"left": 80, "top": 32, "right": 98, "bottom": 54}},
    3: {"flame_crop": {"left": 72, "top": 15, "right": 84, "bottom": 35},
        "word_crop":  {"left": 80, "top": 12, "right": 98, "bottom": 32}},
    4: {"flame_crop": {"left": 72, "top": 15, "right": 86, "bottom": 38},
        "word_crop":  {"left": 82, "top": 17, "right": 99, "bottom": 38}},
    5: {"flame_crop": {"left": 73, "top": 27, "right": 83, "bottom": 48},
        "word_crop":  {"left": 82, "top": 20, "right": 99, "bottom": 42}},
    6: {"flame_crop": {"left": 68, "top": 55, "right": 80, "bottom": 75},
        "word_crop":  {"left": 80, "top": 35, "right": 98, "bottom": 58}},
    7: {"flame_crop": {"left": 75, "top": 30, "right": 86, "bottom": 50},
        "word_crop":  {"left": 83, "top": 24, "right": 99, "bottom": 44}},
}

def crop_region(screenshot_bytes, coords):
    img = Image.open(io.BytesIO(screenshot_bytes))
    w, h = img.size
    left   = int(w * coords["left"]   / 100)
    top    = int(h * coords["top"]    / 100)
    right  = int(w * coords["right"]  / 100)
    bottom = int(h * coords["bottom"] / 100)
    cropped = img.crop((left, top, right, bottom))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()

def call_claude_vision(client, image_b64, prompt, max_tokens=64, model="claude-sonnet-4-6"):
    for attempt in range(API_RETRY_COUNT + 1):
        try:
            message = client.messages.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                    {"type": "text", "text": prompt},
                ]}],
            )
            return message.content[0].text.strip()
        except Exception as exc:
            if attempt < API_RETRY_COUNT:
                log.warning("Claude API call failed (attempt %d): %s — retrying…", attempt + 1, exc)
            else:
                log.error("Claude API call failed after %d attempt(s): %s", attempt + 1, exc)
                return "API ERROR"
    return "API ERROR"

def safe_wait_for(page, selector, timeout_ms=SCREEN_TIMEOUT_MS):
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        log.error("Timeout waiting for element: %s", selector)
        return False


# ---------------------------------------------------------------------------
# Session guard
# ---------------------------------------------------------------------------

def check_session(page, username, password):
    url = page.url
    login_form_visible = False
    try:
        page.wait_for_selector("input[type='password']", state="visible", timeout=500)
        login_form_visible = True
    except PlaywrightTimeoutError:
        pass
    if "login" in url.lower() or login_form_visible:
        log.warning("Session expired — re-logging in…")
        login(page, username, password)
        return True
    return False


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login(page, username, password):
    log.info("Step 1 — Navigating to home screen…")
    page.goto(BASE_URL)
    if not safe_wait_for(page, "text=Get Started"):
        raise RuntimeError("Home screen did not load.")
    page.click("text=Get Started")

    log.info("Step 2 — Dismissing Informed Consent modal…")
    if not safe_wait_for(page, "text=Informed Consent"):
        raise RuntimeError("Informed Consent modal did not appear.")
    try:
        page.get_by_role("button", name="Yes").click(timeout=5_000)
    except Exception:
        modal_buttons = page.locator("button").all()
        if modal_buttons:
            modal_buttons[-1].click()
        else:
            raise RuntimeError("Could not find Yes button.")
    try:
        page.wait_for_selector("text=Informed Consent", state="hidden", timeout=10_000)
    except PlaywrightTimeoutError:
        pass

    log.info("Step 3 — Clicking Login link…")
    if not safe_wait_for(page, "a:has-text('Login'), button:has-text('Login')", timeout_ms=10_000):
        raise RuntimeError("Sign Up screen did not appear.")
    page.click("a:has-text('Login')")
    try:
        page.wait_for_selector("button:has-text('Sign Up')", state="hidden", timeout=10_000)
    except PlaywrightTimeoutError:
        pass

    log.info("Step 4 — Entering credentials…")
    if not safe_wait_for(page, "input[type='password']"):
        raise RuntimeError("Login form did not appear.")
    page.fill("input[placeholder='Username'], input[name='username']", username)
    page.fill("input[type='password']", password)
    submitted = False
    for sel in ["button[type='submit']", "input[type='submit']", "button:has-text('Login →')", "button:has-text('Login')"]:
        try:
            page.click(sel, timeout=3_000)
            submitted = True
            log.info("Step 4 — Submitted login with selector: %s", sel)
            break
        except Exception:
            continue
    if not submitted:
        raise RuntimeError("Could not find login submit button.")

    log.info("Step 5 — Waiting for Leaderboard…")
    if not safe_wait_for(page, "button:has-text('Play'), button:has-text('Resume'), a:has-text('Play'), button:has-text('Play Next')"):
        raise RuntimeError("Leaderboard did not appear.")
    log.info("Login complete — now on Leaderboard screen.")


# ---------------------------------------------------------------------------
# Gate navigation
# ---------------------------------------------------------------------------

def select_gate_from_dropdown(page, target_gate):
    gate_label = f"Gate {target_gate:02d}"
    log.info("Looking for navigation buttons on Leaderboard…")

    # Wait for any clickable button to appear on the Leaderboard
    any_button_sel = "button:has-text('Play'), button:has-text('Resume'), a:has-text('Play'), a:has-text('Resume')"
    if not safe_wait_for(page, any_button_sel, timeout_ms=10_000):
        raise RuntimeError("No navigation buttons found on Leaderboard.")

    # The Leaderboard loads in stages: initially shows "Play" while data loads,
    # then switches to "Resume" + "Play Again" once the user's progress is known.
    # Wait for the page to finish loading before deciding which button to use.
    log.info("Waiting for Leaderboard to finish loading…")
    time.sleep(3.0)

    # Use JS to figure out exactly which buttons are present
    buttons = page.evaluate("""() => {
        const result = [];
        for (const el of document.querySelectorAll('button, a')) {
            const t = (el.innerText || el.textContent || '').trim();
            if (t === 'Play Again') result.push('Play Again');
            else if (t === 'Resume') result.push('Resume');
            else if (t === 'Play') result.push('Play');
        }
        return [...new Set(result)];
    }""")
    log.info("Leaderboard buttons found: %s", buttons)

    if 'Play Again' in buttons:
        log.info("Using 'Play Again' dropdown to select '%s'…", gate_label)
        page.click("button:has-text('Play Again'), a:has-text('Play Again')")
        time.sleep(1.5)  # allow dropdown to fully render
    elif 'Play' in buttons:
        log.info("Found bare 'Play' button — clicking to start Gate 1 directly.")
        page.click("button:text-is('Play'), a:text-is('Play')")
        return
    elif 'Resume' in buttons:
        log.info("Clicking 'Resume' (will go to current gate).")
        page.click("button:has-text('Resume'), a:has-text('Resume')")
        return
    else:
        raise RuntimeError("No 'Play Again', 'Play', or 'Resume' button found on Leaderboard.")
    if not safe_wait_for(page, f"text={gate_label}", timeout_ms=10_000):
        raise RuntimeError(f"Dropdown item '{gate_label}' did not appear.")
    page.click(f"text={gate_label}")
    log.info("Clicked dropdown item '%s'.", gate_label)

    # Door screen
    try:
        page.wait_for_url("**/door/**", timeout=10_000)
        log.info("Door screen confirmed for Gate %d.", target_gate)
        loc = page.locator("text=Play Again").first
        loc.wait_for(state="visible", timeout=8_000)
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            log.info("Clicked door button for Gate %d.", target_gate)
        else:
            log.warning("Door button bounding_box() returned None.")
    except PlaywrightTimeoutError:
        log.warning("Door screen not detected for Gate %d.", target_gate)

    if not safe_wait_for(page, "text=Enter Gate, text=What is the secret word?, [class*='countdown'], [class*='timer']", timeout_ms=3_000):
        log.warning("No recognised gate screen appeared after door; proceeding.")
    else:
        log.info("Gate screen confirmed after door.")

def navigate_to_gate(page, target_gate):
    log.info("Navigating to Gate %d from Leaderboard…", target_gate)
    select_gate_from_dropdown(page, target_gate)
    log.info("Gate navigation complete.")

def return_to_leaderboard(page):
    log.info("Verifying Leaderboard position…")
    leaderboard_sel = "button:text-is('Play'), a:text-is('Play'), button:has-text('Play Again'), a:has-text('Play Again'), button:has-text('Resume'), a:has-text('Resume')"
    try:
        page.wait_for_selector(leaderboard_sel, state="visible", timeout=5_000)
        log.info("Already on Leaderboard.")
        return
    except PlaywrightTimeoutError:
        pass
    log.warning("Not on Leaderboard; navigating to BASE_URL.")
    page.goto(BASE_URL)
    try:
        page.wait_for_selector(leaderboard_sel, state="visible", timeout=20_000)
        log.info("Leaderboard reached.")
    except PlaywrightTimeoutError:
        log.error("Could not reach Leaderboard.")


# ---------------------------------------------------------------------------
# Gate screens
# ---------------------------------------------------------------------------

def enter_gate(page):
    log.info("Screen 1 — Waiting for Gate Entry screen…")
    if not safe_wait_for(page, "text=Enter Gate", timeout_ms=5_000):
        log.warning("Gate Entry screen not found — proceeding with gate 1 default.")
        return 1
    gate_number = 1
    try:
        text = page.locator("button:has-text('Enter Gate'), a:has-text('Enter Gate')").first.inner_text()
        parts = text.split()
        for i, part in enumerate(parts):
            if part.lower() == "gate" and i + 1 < len(parts):
                gate_number = int(parts[i + 1])
                break
    except Exception:
        pass
    log.info("Entering Gate %d…", gate_number)
    for sel in ("button:has-text('Enter Gate')", "a:has-text('Enter Gate')", "text=Enter Gate"):
        try:
            page.click(sel, timeout=3_000)
            log.info("Clicked 'Enter Gate'.")
            return gate_number
        except Exception:
            continue
    raise RuntimeError("Could not click 'Enter Gate' button.")

def observe_flame(page, client, epoch, gate_number):
    log.info("Epoch %d — Screen 2: Waiting for Flame Observation screen…", epoch)
    safe_wait_for(page, "[class*='countdown'], [class*='timer'], :text('Gate')")
    gate_crops = GATE_CROP_CONFIG.get(gate_number, GATE_CROP_CONFIG[1])
    flame_coords = gate_crops["flame_crop"]
    word_coords  = gate_crops["word_crop"]
    log.info("Epoch %d — Using Gate %d crop config: flame=%s  word=%s", epoch, gate_number, flame_coords, word_coords)

    brightness_futures = []
    word_futures = []
    candidate_votes = {}

    BRIGHTNESS_PROMPT = (
        "Rate the brightness of the candle flame in this image on a scale of 0 to 10, "
        "where 0 is completely dark and 10 is maximum brightness. Reply with only a single number."
    )
    WORD_PROMPT = (
        "In this image there is a candle flame. To the right of the flame, small text "
        "words appear briefly in and out of focus. Large letters such as 'NS' are NOT "
        "the word — ignore them. Focus only on the small-font word near the flame. "
        "What is that word? Do not explain. Do not describe. Reply with ONE word only. "
        "If you cannot determine the word, reply with the single word UNKNOWN."
    )

    log.info("Epoch %d — Capturing up to %d screenshots…", epoch, SCREENSHOTS_PER_EPOCH)
    with ThreadPoolExecutor(max_workers=16) as pool:
        for i in range(SCREENSHOTS_PER_EPOCH):
            try:
                page.wait_for_selector("text=What is the secret word?", state="visible", timeout=100)
                log.info("Epoch %d — MC screen detected after %d frames; stopping capture early.", epoch, i)
                break
            except PlaywrightTimeoutError:
                pass

            raw = page.screenshot()
            flame_crop = crop_region(raw, flame_coords)
            word_crop  = crop_region(raw, word_coords)

            if i in (9, 14, 19, 24, 29):
                brightness_futures.append((i+1, pool.submit(call_claude_vision, client, screenshot_to_b64(flame_crop), BRIGHTNESS_PROMPT, 8, "claude-haiku-4-5-20251001")))

            top_non_unknown = max((v for k, v in candidate_votes.items() if k != "unknown"), default=0)
            if top_non_unknown < 3:
                word_futures.append((i, pool.submit(call_claude_vision, client, screenshot_to_b64(word_crop), WORD_PROMPT, 8)))

            log.info("  Screenshot %2d/%d captured", i + 1, SCREENSHOTS_PER_EPOCH)
            if i < SCREENSHOTS_PER_EPOCH - 1:
                time.sleep(SCREENSHOT_INTERVAL_SECONDS)

        for idx, fut in word_futures:
            word = fut.result()
            if word and word.upper() != "API ERROR":
                word = word.split()[0] if word.split() else word
                key = word.lower().strip()
                candidate_votes[key] = candidate_votes.get(key, 0) + 1
                log.info("  Frame %2d word candidate: %s", idx, word)

        brightness_scores = []
        for _, fut in brightness_futures:
            try:
                brightness_scores.append(float(fut.result()))
            except Exception:
                brightness_scores.append(0.0)

    mean_brightness = sum(brightness_scores) / len(brightness_scores) if brightness_scores else 0.0
    log.info("Epoch %d — Mean brightness: %.2f", epoch, mean_brightness)

    non_unknown = {k: v for k, v in candidate_votes.items() if k != "unknown"}
    if non_unknown:
        identified_word = max(non_unknown, key=lambda k: non_unknown[k])
        log.info("Epoch %d — Word votes: %s  →  '%s'", epoch, candidate_votes, identified_word)
    else:
        identified_word = "UNKNOWN"
        log.warning("Epoch %d — %s", epoch, "Only 'unknown' votes found." if candidate_votes else "No word candidates found.")
    log.info("Epoch %d — Identified word: %s", epoch, identified_word)
    return mean_brightness, identified_word

def wait_for_next_epoch(page, epoch):
    log.info("Epoch %d — Screen 4: Checking for Wait screen…", epoch)
    try:
        page.wait_for_selector("text=Wait for next intention period", state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        log.info("Epoch %d — No wait screen detected.", epoch)
        return False
    log.info("Epoch %d — Wait screen visible; waiting for it to disappear…", epoch)
    try:
        page.wait_for_selector("text=Wait for next intention period", state="hidden", timeout=60_000)
        log.info("Epoch %d — Wait screen gone.", epoch)
        return True
    except PlaywrightTimeoutError:
        log.error("Epoch %d — Timed out on Wait screen.", epoch)
        return False


# ---------------------------------------------------------------------------
# Gate complete detection
# ---------------------------------------------------------------------------

def detect_gate_complete(page):
    for sel in ("text=Last gate", "text=End of gate", "text=Gates completed"):
        try:
            page.wait_for_selector(sel, state="visible", timeout=1000)
            log.info("Gate complete detected via selector: %s", sel)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


# ---------------------------------------------------------------------------
# Exit gate and re-enter
# ---------------------------------------------------------------------------

def exit_gate_and_reenter(page, target_gate):
    """Clicks Play again on the Last gate overlay then clicks through the door screen."""
    log.info("Screen 5 — Last gate overlay: clicking play button via JS search…")

    for attempt in range(3):
        box = page.evaluate("""() => {
            const kw = ['Play again', 'Play the gate again'];
            const els = [...document.querySelectorAll('button, a, span, div')];
            // Sort by fewest children first so we pick the most specific (leaf) element
            els.sort((a, b) => a.children.length - b.children.length);
            const el = els.find(e => {
                const t = (e.innerText || e.textContent || '').trim();
                // Exact match or starts-with, but reject elements whose text contains newlines
                // (those are parent containers holding multiple buttons)
                if (t.includes('\\n')) return false;
                return kw.some(k => t === k || t.startsWith(k));
            });
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) return null;
            return {x: r.left + r.width/2, y: r.top + r.height/2,
                    text: (el.innerText || el.textContent).trim()};
        }""")

        if box:
            log.info("Attempt %d: JS found '%s' at (%.0f, %.0f); clicking.",
                     attempt + 1, box['text'], box['x'], box['y'])
            page.mouse.click(box['x'], box['y'])
            time.sleep(0.8)
            try:
                page.wait_for_selector("text=Last gate, text=End of gate", state="hidden", timeout=3_000)
                log.info("Last gate overlay dismissed successfully.")
                break
            except PlaywrightTimeoutError:
                log.warning("Overlay still visible after attempt %d; retrying.", attempt + 1)
        else:
            log.warning("Attempt %d: JS could not find play button.", attempt + 1)
            time.sleep(0.5)
    else:
        log.error("Could not dismiss Last gate overlay after 3 attempts.")
        return

    # Door screen
    log.info("Waiting for door screen…")
    try:
        page.wait_for_url("**/door/**", timeout=10_000)
        log.info("Door screen confirmed (URL: %s).", page.url)
        loc = page.locator("text=Play Again").first
        loc.wait_for(state="visible", timeout=8_000)
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            log.info("Clicked through door screen for Gate %d.", target_gate)
        else:
            log.warning("Door button bounding_box() returned None.")
    except PlaywrightTimeoutError:
        log.warning("Door screen did not appear after Play again; proceeding.")


# ---------------------------------------------------------------------------
# Bbox click helper
# ---------------------------------------------------------------------------

def click_via_bbox(page, locator, label):
    try:
        locator.scroll_into_view_if_needed()
        time.sleep(0.2)
        box = locator.bounding_box()
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            log.info("bbox-clicking '%s' at (%.0f, %.0f).", label, cx, cy)
            page.mouse.click(cx, cy)
            return True
        log.warning("bbox_click: bounding_box() returned None for '%s'.", label)
        return False
    except Exception as exc:
        log.warning("bbox_click failed for '%s': %s", label, exc)
        return False


# ---------------------------------------------------------------------------
# Answer question
# ---------------------------------------------------------------------------

def answer_question(page, identified_word, epoch):
    log.info("Epoch %d — Screen 3: Waiting for Multiple Choice screen…", epoch)

    if detect_gate_complete(page):
        log.info("Epoch %d — Gate complete overlay detected before MC.", epoch)
        return "GATE COMPLETE"

    if not safe_wait_for(page, "text=What is the secret word?"):
        log.error("Epoch %d — Multiple Choice screen did not appear.", epoch)
        return "SCREEN ERROR"

    if detect_gate_complete(page):
        log.info("Epoch %d — Gate complete overlay detected after MC wait.", epoch)
        return "GATE COMPLETE"

    option_data = page.evaluate("""
        () => Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]')).map((el, i) => {
            let text = '';
            if (el.id) { const lbl = document.querySelector('label[for="' + el.id + '"]'); if (lbl) text = lbl.textContent.trim(); }
            if (!text) { const lbl = el.closest('label'); if (lbl) text = lbl.textContent.trim(); }
            if (!text && el.parentElement) text = el.parentElement.textContent.trim();
            if (!text) { let s = el.nextSibling; while (s) { const t = s.textContent ? s.textContent.trim() : ''; if (t) { text = t; break; } s = s.nextSibling; } }
            return { index: i, text: text };
        })
    """)
    log.info("Epoch %d — Found %d inputs, texts: %s", epoch, len(option_data), [d['text'] for d in option_data])

    matched_idx = None
    matched_word = None
    best_score = 0.0
    for d in option_data:
        if not d['text']:
            continue
        opt = d['text'].lower().strip()
        iw  = identified_word.lower().strip()
        score = max(
            difflib.SequenceMatcher(None, iw, opt).ratio(),
            difflib.SequenceMatcher(None, opt, iw).ratio(),
            1.0 if (iw in opt or opt in iw) else 0.0,
        )
        log.info("  Fuzzy match '%s' vs '%s': %.2f", iw, opt, score)
        if score > best_score:
            best_score = score
            if score >= FUZZY_THRESHOLD:
                matched_idx = d['index']
                matched_word = d['text']

    if matched_word:
        log.info("Epoch %d — Fuzzy matched '%s' → '%s' (score %.2f).", epoch, identified_word, matched_word, best_score)
    else:
        log.warning("Epoch %d — No fuzzy match for '%s' (best %.2f); selecting first as fallback.", epoch, identified_word, best_score)
        matched_idx = option_data[0]['index'] if option_data else None
        matched_word = option_data[0]['text'] if option_data else identified_word

    if matched_idx is not None:
        target = page.locator("input[type='radio'], input[type='checkbox']").nth(matched_idx)
        try:
            if not click_via_bbox(page, target, matched_word):
                target.click(force=True, timeout=3_000)
            log.info("Epoch %d — Clicked checkbox %d for '%s'.", epoch, matched_idx, matched_word)
        except Exception as exc:
            log.error("Epoch %d — Could not click checkbox: %s", epoch, exc)
            if detect_gate_complete(page):
                return "GATE COMPLETE"
    else:
        log.error("Epoch %d — No checkbox found.", epoch)

    time.sleep(0.5)
    if safe_wait_for(page, "text=Submit", timeout_ms=5000):
        submit_loc = page.locator("text=Submit").first
        if not click_via_bbox(page, submit_loc, "Submit"):
            page.click("text=Submit", force=True)
    else:
        log.error("Epoch %d — Submit button did not appear; treating as gate complete.", epoch)
        return "GATE COMPLETE"

    return matched_word


# ---------------------------------------------------------------------------
# Single-gate pass
# ---------------------------------------------------------------------------

def run_gate_pass(page, client, username, password, target_gate, pass_number, already_in_gate=False):
    log.info("=" * 60)
    log.info("PASS %d — Gate %d", pass_number, target_gate)
    log.info("=" * 60)

    epoch_results = []
    ended_with_reenter = False

    if check_session(page, username, password):
        already_in_gate = False

    if not already_in_gate:
        navigate_to_gate(page, target_gate)

    gate_number = enter_gate(page)

    epoch = 1
    while True:
        if detect_gate_complete(page):
            log.info("Pass %d — Gate complete detected before epoch %d.", pass_number, epoch)
            break

        if check_session(page, username, password):
            gate_number = enter_gate(page)

        mean_brightness, identified_word = observe_flame(page, client, epoch, gate_number)

        if detect_gate_complete(page):
            log.info("Pass %d — Gate complete after observation in epoch %d.", pass_number, epoch)
            epoch_results.append({"epoch": epoch, "mean_brightness": mean_brightness,
                                   "identified_word": identified_word, "selected_word": "N/A (gate ended)", "no_match": False})
            break

        if check_session(page, username, password):
            gate_number = enter_gate(page)
            continue

        selected_word = answer_question(page, identified_word, epoch)
        if selected_word == "GATE COMPLETE":
            log.info("Pass %d — Gate complete during answer phase of epoch %d.", pass_number, epoch)
            break

        no_match = identified_word != "API ERROR" and selected_word.lower() != identified_word.lower()
        epoch_results.append({"epoch": epoch, "mean_brightness": mean_brightness,
                               "identified_word": identified_word, "selected_word": selected_word, "no_match": no_match})

        if detect_gate_complete(page):
            log.info("Pass %d — Gate complete after submission in epoch %d.", pass_number, epoch)
            break

        if check_session(page, username, password):
            gate_number = enter_gate(page)
            epoch += 1
            continue

        had_wait = wait_for_next_epoch(page, epoch)
        epoch += 1
        if not had_wait and detect_gate_complete(page):
            break

    exit_gate_and_reenter(page, target_gate)
    ended_with_reenter = True
    return gate_number, epoch_results, ended_with_reenter


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_results(target_gate, total_passes, start_time, all_pass_results, output_dir, run_id=""):
    tag = f"_{run_id}" if run_id else ""
    filename = output_dir / f"ions_gate_{target_gate}{tag}_multipass_results.txt"
    lines = [
        "IONS Noetic Adventure — Multi-Pass Automated Run",
        f"Target Gate: {target_gate}",
        f"Run ID: {run_id}" if run_id else "",
        f"Requested Passes: {total_passes}   Completed Passes: {len(all_pass_results)}",
        f"Date/Time Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", "",
    ]
    # Remove blank line if no run_id line was added
    lines = [l for l in lines if l is not None]
    all_no_match = []
    for pi, (actual_gate, epoch_results) in enumerate(all_pass_results, 1):
        lines.append(f"--- Pass {pi} (Gate {actual_gate}) ---")
        no_match_epochs = []
        for r in epoch_results:
            flag = "  *** NO MATCH — FALLBACK USED ***" if r.get("no_match") else ""
            lines.append(f"  Epoch {r['epoch']}: Brightness={r['mean_brightness']:.1f}  "
                         f"Identified={r['identified_word']}  Selected={r['selected_word']}{flag}")
            if r.get("no_match"):
                no_match_epochs.append(r['epoch'])
        lines.append(f"  Total epochs this pass: {len(epoch_results)}")
        if no_match_epochs:
            lines.append(f"  WARNING — Fallback epochs: {no_match_epochs}")
            all_no_match.append(f"Pass {pi}: {no_match_epochs}")
        lines.append("")
    lines.append(f"Run complete.  Total passes: {len(all_pass_results)}")
    if all_no_match:
        lines.append("Overall fallback summary: " + " | ".join(all_no_match))
    text = "\n".join(lines) + "\n"
    filename.write_text(text, encoding="utf-8")
    log.info("Results written to %s", filename)
    print("\n" + text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    username     = require_env("IONS_USERNAME")
    password     = require_env("IONS_PASSWORD")
    api_key      = require_env("ANTHROPIC_API_KEY")
    target_gate  = require_env_int("IONS_GATE", min_val=1)
    total_passes = require_env_int("IONS_PASSNUMB", min_val=1)
    run_id       = os.environ.get("IONS_RUN_ID", "")

    if target_gate > 7:
        log.error("IONS_GATE must be 1-7.")
        sys.exit(1)

    run_label = f" (Run ID: {run_id})" if run_id else ""
    log.info("Multi-pass run: Gate %d, %d pass(es) requested.%s", target_gate, total_passes, run_label)
    client = anthropic.Anthropic(api_key=api_key)
    start_time = datetime.now()
    output_dir = Path(__file__).parent
    all_pass_results = []

    tag = f"_{run_id}" if run_id else ""

    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=False, firefox_user_prefs={"browser.privatebrowsing.autostart": True})
        page = browser.new_context().new_page()
        try:
            login(page, username, password)
            already_in_gate = False

            for pass_number in range(1, total_passes + 1):
                try:
                    actual_gate, epoch_results, ended_with_reenter = run_gate_pass(
                        page, client, username, password, target_gate, pass_number, already_in_gate)
                    already_in_gate = ended_with_reenter and (pass_number < total_passes)
                    all_pass_results.append((actual_gate, epoch_results))
                    log.info("Pass %d complete (%d epochs).", pass_number, len(epoch_results))
                    write_results(target_gate, total_passes, start_time, all_pass_results, output_dir, run_id)

                    # Per-pass file
                    single = output_dir / f"ions_gate_{target_gate}{tag}_results.txt"
                    if epoch_results:
                        lines = ["IONS Noetic Adventure — Automated Run",
                                 f"Gate: {actual_gate} of 7", f"Pass: {pass_number} of {total_passes}",
                                 f"Run ID: {run_id}" if run_id else "",
                                 f"Date/Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
                        lines = [l for l in lines if l is not None]
                        for r in epoch_results:
                            flag = "  *** NO MATCH ***" if r.get("no_match") else ""
                            lines.append(f"Epoch {r['epoch']}: Mean Brightness = {r['mean_brightness']:.1f}, "
                                         f"Word Identified = {r['identified_word']}, Word Selected = {r['selected_word']}{flag}")
                        lines += ["", f"Pass complete. Total epochs: {len(epoch_results)}"]
                        single.write_text("\n".join(lines) + "\n", encoding="utf-8")
                        log.info("Per-pass results written to %s", single)

                except Exception as exc:
                    log.error("Pass %d failed: %s", pass_number, exc, exc_info=True)
                    already_in_gate = False
                    try:
                        login(page, username, password)
                    except Exception as e2:
                        log.error("Recovery login failed: %s — aborting.", e2)
                        break
                    continue

                if pass_number < total_passes and not already_in_gate:
                    try:
                        return_to_leaderboard(page)
                    except Exception as exc:
                        log.error("Could not reach Leaderboard: %s", exc)
                        try:
                            login(page, username, password)
                        except Exception:
                            log.error("Recovery login failed — aborting.")
                            break

        except Exception as exc:
            log.error("Unexpected error: %s", exc, exc_info=True)
        finally:
            if all_pass_results:
                write_results(target_gate, total_passes, start_time, all_pass_results, output_dir, run_id)
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=None)
    parser.parse_args()
    run()