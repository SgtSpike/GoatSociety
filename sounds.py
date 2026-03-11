"""
Procedural sound effects for Goat Society RTS.
All audio is synthesised from PCM math — no audio files required.

Usage:
    import sounds
    sounds.init()       # call once, after pygame.init()
    sounds.play('chop') # play a named effect
"""
import array
import math
import random
import time
import pygame

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_RATE    = 22050   # samples/sec
_AMP     = 26000   # peak amplitude (below 32767 to avoid clipping on mix)
_sounds  = {}      # name → pygame.Sound
_enabled = True

# Rate-limit: minimum seconds between plays of the same sound
_MIN_INTERVAL = {
    'attack_melee': 0.08,
    'arrow_fire':   0.08,
    'tower_fire':   0.10,
    'chop':         0.25,
    'clink':        0.30,
    'unit_select':  0.05,
    'unit_move':    0.08,
    'error':        0.4,
    'unit_death':   0.12,
}
_last_played: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init():
    """Initialise the mixer and pre-bake all sound effects."""
    global _enabled
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=_RATE, size=-16, channels=2, buffer=512)
        _bake_all()
    except Exception as e:
        print(f"[sounds] Audio unavailable: {e}")
        _enabled = False


def play(name: str, volume: float = 1.0):
    """Play a named sound effect, with optional rate-limiting."""
    if not _enabled:
        return
    s = _sounds.get(name)
    if s is None:
        return
    now = time.monotonic()
    min_iv = _MIN_INTERVAL.get(name, 0.0)
    if now - _last_played.get(name, 0.0) < min_iv:
        return
    _last_played[name] = now
    s.set_volume(max(0.0, min(1.0, volume)))
    s.play()


# ---------------------------------------------------------------------------
# PCM helpers
# ---------------------------------------------------------------------------

def _make_sound(samples: list[float]) -> pygame.mixer.Sound:
    """Pack a list of normalised floats into a stereo 16-bit pygame.Sound."""
    buf = array.array('h', [0] * len(samples) * 2)
    for i, v in enumerate(samples):
        val = int(max(-1.0, min(1.0, v)) * _AMP)
        buf[i * 2]     = val
        buf[i * 2 + 1] = val
    return pygame.mixer.Sound(buffer=buf)


def _sine(freq: float, dur: float, vol: float = 0.5,
          attack: float = 0.005, decay: float = 0.0) -> list[float]:
    """Sine wave with linear attack + exponential decay tail."""
    n  = int(_RATE * dur)
    tw = int(_RATE * attack)
    out = []
    for i in range(n):
        t   = i / _RATE
        osc = math.sin(2 * math.pi * freq * t)
        if i < tw:
            env = i / max(1, tw)
        else:
            progress = (i - tw) / max(1, n - tw)
            env = math.exp(-decay * progress * 6) if decay > 0 else (1 - progress)
        out.append(osc * env * vol)
    return out


def _square(freq: float, dur: float, vol: float = 0.35,
            duty: float = 0.5) -> list[float]:
    """Square / pulse wave, linearly faded out."""
    n = int(_RATE * dur)
    out = []
    for i in range(n):
        t     = i / _RATE
        phase = (freq * t) % 1.0
        s     = vol if phase < duty else -vol
        out.append(s * (1.0 - i / n))
    return out


def _noise(dur: float, vol: float = 0.4, seed: int = 0) -> list[float]:
    """White noise with linear fade-out."""
    rng = random.Random(seed)
    n   = int(_RATE * dur)
    return [rng.uniform(-vol, vol) * (1.0 - i / n) for i in range(n)]


def _sweep(f0: float, f1: float, dur: float, vol: float = 0.4) -> list[float]:
    """Sine sweep from f0 to f1 with fade-out."""
    n   = int(_RATE * dur)
    out = []
    for i in range(n):
        t    = i / _RATE
        frac = i / n
        freq = f0 + (f1 - f0) * frac
        osc  = math.sin(2 * math.pi * freq * t)
        out.append(osc * vol * (1.0 - frac))
    return out


def _mix(*tracks: list[float]) -> list[float]:
    """Sum tracks together (clipped to ±1)."""
    n = max(len(t) for t in tracks)
    result = []
    for i in range(n):
        v = sum(t[i] for t in tracks if i < len(t))
        result.append(max(-1.0, min(1.0, v)))
    return result


def _concat(*tracks: list[float]) -> list[float]:
    """Concatenate tracks sequentially."""
    out = []
    for t in tracks:
        out.extend(t)
    return out


def _note(semitones: float, dur: float, vol: float = 0.45,
          wave: str = 'sine', decay: float = 0.8) -> list[float]:
    """Musical note relative to A4 (440 Hz)."""
    freq = 440.0 * (2 ** (semitones / 12.0))
    if wave == 'sine':
        return _sine(freq, dur, vol, attack=0.01, decay=decay)
    return _square(freq, dur, vol)


def _chord(semitone_list: list[float], dur: float, vol: float = 0.3) -> list[float]:
    return _mix(*[_note(s, dur, vol) for s in semitone_list])


# ---------------------------------------------------------------------------
# Sound definitions
# ---------------------------------------------------------------------------

def _bake_all():
    # --- UI / selection ---
    _sounds['unit_select'] = _make_sound(_mix(
        _square(900, 0.03, 0.25),
        _noise(0.03, 0.08, seed=1),
    ))

    _sounds['unit_move'] = _make_sound(_mix(
        _sine(520, 0.07, 0.25, attack=0.005, decay=1.0),
        _sine(390, 0.05, 0.15, attack=0.005, decay=1.0),
    ))

    _sounds['error'] = _make_sound(_mix(
        _square(180, 0.18, 0.28, duty=0.6),
        _square(175, 0.18, 0.22, duty=0.4),
    ))

    # --- Combat ---
    _sounds['attack_melee'] = _make_sound(_mix(
        _noise(0.10, 0.45, seed=2),
        _sine(120, 0.10, 0.25, attack=0.002, decay=0.8),
        _sweep(300, 80, 0.10, 0.15),
    ))

    _sounds['arrow_fire'] = _make_sound(_mix(
        _noise(0.06, 0.20, seed=3),
        _sweep(800, 200, 0.08, 0.25),
    ))

    _sounds['tower_fire'] = _make_sound(_mix(
        _noise(0.07, 0.22, seed=4),
        _sweep(600, 150, 0.10, 0.28),
    ))

    _sounds['unit_death'] = _make_sound(_mix(
        _noise(0.22, 0.35, seed=5),
        _sine(90, 0.22, 0.28, attack=0.005, decay=0.6),
    ))

    # --- Gathering ---
    _sounds['chop'] = _make_sound(_mix(
        _noise(0.07, 0.50, seed=6),
        _sine(160, 0.07, 0.22, attack=0.003, decay=0.9),
        _square(80, 0.04, 0.15),
    ))

    _sounds['clink'] = _make_sound(_mix(
        _sine(1400, 0.10, 0.35, attack=0.002, decay=0.9),
        _sine(1800, 0.06, 0.18, attack=0.002, decay=1.0),
        _noise(0.04, 0.08, seed=7),
    ))

    # --- Construction / research ---
    _sounds['building_start'] = _make_sound(_mix(
        _note(-5, 0.12, 0.30),
        _note(0,  0.10, 0.25),
    ))

    _sounds['building_complete'] = _make_sound(_concat(
        _note(0,   0.10, 0.40),   # A4
        _note(4,   0.10, 0.40),   # C#5
        _note(7,   0.10, 0.40),   # E5
        _note(12,  0.20, 0.50),   # A5
    ))

    _sounds['research_complete'] = _make_sound(_concat(
        _chord([0, 7],    0.10, 0.28),
        _chord([4, 9],    0.10, 0.28),
        _chord([7, 12],   0.10, 0.28),
        _chord([12, 16, 19], 0.30, 0.32),
    ))

    # --- Resource depleted ---
    _sounds['resource_depleted'] = _make_sound(_mix(
        _noise(0.18, 0.30, seed=8),
        _sine(100, 0.18, 0.25, attack=0.01, decay=0.5),
    ))

    # --- End game ---
    # Victory: bright ascending fanfare
    _sounds['victory'] = _make_sound(_concat(
        _note(0,  0.12, 0.50),
        _note(4,  0.12, 0.50),
        _note(7,  0.12, 0.50),
        _note(12, 0.12, 0.50),
        _chord([0, 4, 7, 12], 0.45, 0.45),
        _note(16, 0.55, 0.55),
    ))

    # Defeat: sad descending phrase
    _sounds['defeat'] = _make_sound(_concat(
        _note(7,  0.22, 0.38),
        _note(5,  0.22, 0.38),
        _note(2,  0.22, 0.38),
        _chord([-1, 2], 0.55, 0.35),
    ))
