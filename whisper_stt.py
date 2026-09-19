"""whisper_stt.py

Her ears: turn a Discord voice message into text.

ffmpeg decodes the attachment to 16 kHz mono PCM (Discord voice messages are
Opus inside an Ogg container; whisper wants raw wav), then whisper-cli.exe
transcribes that wav. The transcript is handed back to stand in for the
message's content, so everything after it - the addressing gate, the prompt,
memory, the journal - sees a typed message and nothing has to special-case
voice.

Ported from Nyan's whisper_stt.py in C:/Python/DiscordBotN5, with every path
routed through paths.py: the binary, the model and the scratch wavs must all
resolve inside this folder, or the call is refused instead of run.

Config keys read by lulu_bot.py (config.json):
    stt           false   master switch; off means is_ready() is never true
    stt_folder    "whisper.cpp"
    stt_exe       "<stt_folder>/build/bin/Release/whisper-cli.exe"
    stt_model     "<stt_folder>/ggml-small-q5_1.bin"
    stt_language  "auto"  whisper's -l; "auto" detects the language per clip
    stt_timeout   180     seconds per helper process

Cost, measured on this box 2026-09-19 with ggml-small-q5_1.bin: 19.4s of wall
clock for 11.0s of audio, of which 17.2s is the single encode pass - about 1.7x
realtime. That is why the timeout is minutes and not the 60s Nyan used: 60s
starts cutting off anything past ~35s of speech.

Usage:
    from whisper_stt import WhisperSTT, audio_suffix, is_audio_attachment

    stt = WhisperSTT(enabled=True)
    if stt.is_ready():
        text = await stt.transcribe_bytes(blob, suffix=".ogg")
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

import paths

LOG = logging.getLogger("lulu.stt")

# What ffmpeg will be handed. Discord's native voice messages arrive as
# audio/ogg; the rest is the same set Nyan accepts, kept identical so the two
# bots agree on what counts as audio.
SUFFIXES = ("ogg", "mp3", "wav", "m4a", "flac", "webm")
_DOTTED = tuple(f".{s}" for s in SUFFIXES)
MIME_SUFFIX = {
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/flac": "flac",
    "audio/webm": "webm",
}


class WhisperSTT:
    # Where ffmpeg is looked for when config says nothing. Folder-relative on
    # purpose: run-bot.cmd sets NO PATH at all, so a bare `ffmpeg` is not
    # findable on this box however it is installed - a binary sitting in my own
    # folder was invisible, which is exactly what master watched happen.
    DEFAULT_FFMPEG = "ffmpeg/ffmpeg.exe"

    def __init__(self, enabled: bool = False, base_dir: str = "whisper.cpp",
                 exe_path: str | None = None, model_path: str | None = None,
                 ffmpeg_path: str | None = None, language: str = "auto",
                 timeout: int = 180):
        self.enabled = enabled
        # Folder-relative, all of it. resolve() is what turns these into real
        # paths, and it refuses anything that lands outside the folder.
        self.base_rel = base_dir
        self.exe_rel = exe_path or f"{base_dir}/build/bin/Release/whisper-cli.exe"
        self.model_rel = model_path or f"{base_dir}/ggml-small-q5_1.bin"
        self.work_rel = f"{base_dir}/stt_tmp"
        # None means "look in the folder first" - see ffmpeg(). A bare name still
        # means a PATH lookup, so an explicit config value keeps working.
        self.ffmpeg_path = ffmpeg_path
        self.language = language
        self.timeout = timeout

    def ffmpeg(self) -> str | None:
        """The ffmpeg to run: folder-relative first, then PATH. None if neither.

        Folder-first applies to EVERY name, not only ones containing a separator.
        A binary beside me is the normal case here, because run-bot.cmd sets no
        PATH at all - so both `ffmpeg` and `ffmpeg/ffmpeg.exe` mean "the one in my
        folder, if it is there" before falling back to a PATH lookup. My own
        probe caught the stricter version failing on a folder-local file that
        happened to have no separator in its name.

        The folder path goes through paths.resolve(), so an escape is refused
        rather than run - same rule as every other configured path here.

        Returning None rather than raising is deliberate: the caller logs it in
        plain words instead of failing later with a confusing exec error.
        """
        candidate = self.ffmpeg_path or self.DEFAULT_FFMPEG
        try:
            full = paths.resolve(candidate)
        except paths.SandboxError as exc:
            LOG.warning("stt: ffmpeg path is outside the folder (%s)", exc)
            return None
        if full.is_file():
            return str(full)
        # Nothing beside me: PATH is where a bare name is normally looked for.
        return shutil.which(candidate)

    # -- readiness --------------------------------------------------------
    def is_ready(self) -> bool:
        """STT is on and the binary, the model and ffmpeg are all here.

        Logged rather than raised: this runs at startup, and a bot that refuses
        to boot because it cannot hear is worse than one that carries on deaf.
        """
        if not self.enabled:
            return False
        try:
            exe = paths.resolve(self.exe_rel)
            model = paths.resolve(self.model_rel)
        except paths.SandboxError as exc:
            LOG.warning("stt: configured paths are outside the folder (%s)", exc)
            return False
        missing = [str(p) for p in (exe, model) if not p.exists()]
        if missing:
            LOG.warning("stt: missing %s", ", ".join(missing))
            return False
        if self.ffmpeg() is None:
            LOG.warning("stt: no ffmpeg - looked in the folder at %r and on PATH",
                        self.DEFAULT_FFMPEG)
            return False
        return True

    # -- the two helpers --------------------------------------------------
    async def _spawn(self, cmd: list[str], cwd: str | None = None):
        """Run a helper; return (stdout, stderr), or (None, None) on any failure.

        The kill on timeout is the point of routing both helpers through here.
        wait_for() cancels the *wait*, not the process: Nyan's version left
        whisper-cli running at full tilt on a clip it had already given up on,
        holding ~100 MB and every core for as long as the audio was long.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except Exception as exc:
            LOG.warning("stt: could not start %s (%s)", cmd[0], exc)
            return None, None
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(),
                                                    timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            LOG.warning("stt: %s timed out after %ss", Path(cmd[0]).name, self.timeout)
            return None, None
        if proc.returncode != 0:
            LOG.warning("stt: %s exited %s: %s", Path(cmd[0]).name, proc.returncode,
                        (stderr or b"").decode(errors="ignore").strip()[:400])
            return None, None
        return stdout, stderr

    async def _transcribe(self, source: Path, stamp: str) -> str | None:
        """ffmpeg -> wav, whisper -> text. The wav never outlives the call."""
        try:
            base = paths.resolve(self.base_rel)
            work = paths.resolve(self.work_rel)
            exe = paths.resolve(self.exe_rel)
            model = paths.resolve(self.model_rel)
        except paths.SandboxError as exc:
            LOG.warning("stt: paths are outside the folder (%s)", exc)
            return None

        work.mkdir(parents=True, exist_ok=True)
        wav = work / f"out_{stamp}.wav"
        ffmpeg = self.ffmpeg()
        if ffmpeg is None:
            LOG.warning("stt: no ffmpeg to convert with, so I cannot decode this")
            return None
        try:
            converted, _ = await self._spawn([
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(source),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(wav),
            ])
            if converted is None or not wav.exists():
                return None
            stdout, _ = await self._spawn([
                str(exe),
                "-m", str(model),
                "-f", str(wav),
                "-nt",              # no timestamps: the words are the message
                "-l", self.language,
            ], cwd=str(base))
            text = (stdout or b"").decode(errors="ignore").strip()
            return text or None
        finally:
            wav.unlink(missing_ok=True)

    # -- public -----------------------------------------------------------
    async def transcribe_bytes(self, data: bytes, suffix: str = ".ogg") -> str | None:
        """Transcribe raw attachment bytes - what the bot actually holds.

        Discord hands the audio over the gateway as bytes, so there is no file
        to point ffmpeg at, and no reason for one to survive the call.
        """
        if not self.enabled:
            return None
        if suffix.lower() not in _DOTTED:
            suffix = ".ogg"
        try:
            work = paths.resolve(self.work_rel)
        except paths.SandboxError as exc:
            LOG.warning("stt: scratch folder is outside the folder (%s)", exc)
            return None

        work.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        source = work / f"in_{stamp}{suffix}"
        try:
            source.write_bytes(data)
            return await self._transcribe(source, stamp)
        finally:
            source.unlink(missing_ok=True)

    async def transcribe_file(self, name: str) -> str | None:
        """Transcribe a file inside the folder, named relative to it.

        Unused by the bot - Discord never gives us a file - but it is how the
        ears get tested without a live server, and how master can check a model
        without waiting for someone to send a voice note.
        """
        if not self.enabled:
            return None
        try:
            source = paths.resolve(name, must_exist=True)
        except paths.SandboxError as exc:
            LOG.warning("stt: %s", exc)
            return None
        return await self._transcribe(source, datetime.now().strftime("%Y%m%d_%H%M%S_%f"))


# ------------------------------------------------------------------ helpers

def is_audio_attachment(attachment) -> bool:
    """Is this attachment something ffmpeg can decode?

    content_type is checked first and on its own because a stand-in attachment
    restored from a cache may carry no filename at all, while a real one always
    has both.
    """
    content_type = (getattr(attachment, "content_type", "") or "").lower()
    if content_type.startswith("audio/"):
        return True
    filename = (getattr(attachment, "filename", "") or "").lower()
    return filename.endswith(_DOTTED)


def audio_suffix(attachment) -> str:
    """The extension to write the bytes under, for ffmpeg's benefit.

    ffmpeg sniffs the container itself, so this is only a hint - but a wrong
    hint costs a confusing error, and a Discord voice message often arrives
    with the content type as the better evidence.
    """
    mime = (getattr(attachment, "content_type", "") or "").lower()
    if mime in MIME_SUFFIX:
        return f".{MIME_SUFFIX[mime]}"
    filename = (getattr(attachment, "filename", "") or "").lower()
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1]
        if f".{ext}" in _DOTTED:
            return f".{ext}"
    return ".ogg"
