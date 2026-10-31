"""Textual themes ported from pbs-tui, with terminal-aware defaults.

The four theme definitions below mirror
``pbs-tui/src/pbs_tui/app.py`` exactly (same names, same hex values):
``pbs-dark`` / ``pbs-light`` are the branded pair, ``ansi-dark`` /
``ansi-light`` the muted 256-color tones that blend with the terminal
colorscheme.

Unlike pbs-tui (which defaults to ``pbs-dark``), the arcade defaults to
the ``ansi-*`` pair and picks light vs dark from the terminal background,
so the TUI matches the terminal out of the box. Detection order:
``COLORFGBG`` first (instant, when the terminal sets it), then a direct
OSC 11 query to the terminal (works almost everywhere ``COLORFGBG`` is
absent, e.g. Kitty/Ghostty/multiplexers with passthrough), then dark.
An explicit ``--theme`` flag or ``ARCADE_THEME`` env var overrides
detection; the command palette can still switch at runtime.
"""

from __future__ import annotations

import os
import re
import select

try:  # Textual < 0.47 does not expose the Theme helper
    from textual.theme import Theme as _TextualTheme
except Exception:  # pragma: no cover - defensive fallback for older installs
    _TextualTheme = None

HAS_THEME_SUPPORT = _TextualTheme is not None

THEME_NAMES = ("pbs-dark", "pbs-light", "ansi-dark", "ansi-light")

if HAS_THEME_SUPPORT:
    PBS_DARK_THEME = _TextualTheme(
        "pbs-dark",
        primary="#4DB2FF",
        secondary="#89DDFF",
        warning="#F9E2AF",
        error="#F38BA8",
        success="#94E2D5",
        accent="#F8BD96",
        foreground="#E6EEF8",
        background="#0B1220",
        surface="#141B2D",
        panel="#141B2D",
        boost="#CBA6F7",
        dark=True,
    )

    PBS_LIGHT_THEME = _TextualTheme(
        "pbs-light",
        primary="#1F5BA5",
        secondary="#0284C7",
        warning="#D97706",
        error="#B91C1C",
        success="#15803D",
        accent="#7C3AED",
        foreground="#172033",
        background="#F3F7FD",
        surface="#FFFFFF",
        panel="#FFFFFF",
        boost="#4338CA",
        dark=False,
    )

    # ANSI-inspired themes: fixed hex colors chosen to resemble a
    # terminal-style palette (same values as pbs-tui).
    ANSI_DARK_THEME = _TextualTheme(
        "ansi-dark",
        primary="#5F87AF",     # ANSI 67  — muted blue
        secondary="#5FAFAF",   # ANSI 73  — teal
        warning="#D7AF5F",     # ANSI 179 — amber
        error="#AF5F5F",       # ANSI 131 — muted red
        success="#5FAF5F",     # ANSI 71  — green
        accent="#AF87D7",      # ANSI 140 — lavender
        foreground="#C0C0C0",  # ANSI 7   — silver (light gray)
        background="#1C1C1C",  # ANSI 234 — near-black
        surface="#262626",     # ANSI 235 — dark gray
        panel="#262626",
        boost="#D787AF",       # ANSI 175 — pink
        dark=True,
    )

    ANSI_LIGHT_THEME = _TextualTheme(
        "ansi-light",
        primary="#005FAF",     # ANSI 25  — dark blue
        secondary="#008787",   # ANSI 30  — dark teal
        warning="#AF8700",     # ANSI 136 — dark amber
        error="#AF0000",       # ANSI 124 — dark red
        success="#008700",     # ANSI 28  — dark green
        accent="#5F00AF",      # ANSI 55  — purple
        foreground="#303030",  # ANSI 236 — dark gray
        background="#EEEEEE",  # ANSI 255 — near-white
        surface="#FFFFFF",     # white
        panel="#FFFFFF",
        boost="#870087",       # ANSI 90  — dark magenta
        dark=False,
    )

    ALL_THEMES = (
        PBS_DARK_THEME,
        PBS_LIGHT_THEME,
        ANSI_DARK_THEME,
        ANSI_LIGHT_THEME,
    )
else:  # pragma: no cover - legacy Textual without Theme helper
    PBS_DARK_THEME = None
    PBS_LIGHT_THEME = None
    ANSI_DARK_THEME = None
    ANSI_LIGHT_THEME = None
    ALL_THEMES = ()


def _colorfgbg_is_light() -> bool | None:
    """Tri-state ``COLORFGBG`` read: True/False, or None when absent/broken."""
    raw = os.environ.get("COLORFGBG", "").strip()
    if not raw:
        return None
    try:
        background = int(raw.split(";")[-1])
    except ValueError:
        return None
    return background in (7, 15) or 231 <= background <= 255


_OSC11_REPLY = re.compile(r"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)")


def parse_osc11_background(raw: bytes) -> tuple[int, int, int] | None:
    """Pull an ``(r, g, b)`` triple out of an OSC 11 terminal reply.

    Terminals answer ``OSC 11 ; rgb:RRRR/GGGG/BBBB ST`` with 1-4 hex
    digits per channel; scale down to 8 bits per channel.
    """
    match = _OSC11_REPLY.search(raw.decode("ascii", "replace"))
    if not match:
        return None
    channels = []
    for part in match.groups():
        scale = len(part)
        channels.append(round(int(part, 16) / (16**scale - 1) * 255))
    red, green, blue = channels
    return red, green, blue


def _luminance(red: int, green: int, blue: int) -> float:
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def query_terminal_background(timeout: float = 0.2) -> tuple[int, int, int] | None:
    """Ask the terminal for its background colour (OSC 11).

    Opens ``/dev/tty`` directly so it works even when stdin/stdout are
    redirected, restores the termios state afterwards, and never blocks
    longer than ``timeout``. Returns None when there is no tty, the
    terminal stays silent (no passthrough), or anything else goes wrong —
    silence is normal, never an error.
    """
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None
    try:
        try:
            import termios
            import tty

            saved = termios.tcgetattr(fd)
            tty.setraw(fd)
        except Exception:
            termios = None
        try:
            os.write(fd, b"\x1b]11;?\x1b\\")
            reply = b""
            while len(reply) < 64 and b"\x1b\\" not in reply and b"\x07" not in reply:
                ready, _, _ = select.select([fd], [], [], timeout)
                if not ready:
                    break
                try:
                    chunk = os.read(fd, 64)
                except OSError:
                    break
                if not chunk:
                    break
                reply += chunk
        finally:
            if termios is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, saved)
                except Exception:
                    pass
        return parse_osc11_background(reply)
    except Exception:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def detect_ansi_theme() -> str:
    """Return ``ansi-light`` on a light terminal, else ``ansi-dark``.

    ``COLORFGBG`` (``fg;bg`` with 256-color indices) wins when present.
    Otherwise the terminal itself is asked via OSC 11 and its background
    luminance decides (threshold 0.5). Anything silent or unparseable
    falls back to dark, preserving the TUI's historical dark look.
    """
    colorfgbg = _colorfgbg_is_light()
    if colorfgbg is not None:
        return "ansi-light" if colorfgbg else "ansi-dark"
    probed = query_terminal_background()
    if probed is not None and _luminance(*probed) > 0.5:
        return "ansi-light"
    return "ansi-dark"


def resolve_theme(explicit: str | None = None) -> str:
    """Pick the startup theme: explicit flag > ``ARCADE_THEME`` > detect."""
    for candidate in (explicit, os.environ.get("ARCADE_THEME")):
        if candidate and candidate in THEME_NAMES:
            return candidate
    return detect_ansi_theme()


__all__ = [
    "ALL_THEMES",
    "ANSI_DARK_THEME",
    "ANSI_LIGHT_THEME",
    "HAS_THEME_SUPPORT",
    "PBS_DARK_THEME",
    "PBS_LIGHT_THEME",
    "THEME_NAMES",
    "detect_ansi_theme",
    "parse_osc11_background",
    "query_terminal_background",
    "resolve_theme",
]
