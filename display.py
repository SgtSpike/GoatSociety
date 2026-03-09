"""
Thin module that tracks the letterbox rect so any module can convert
window-space mouse coordinates into game-space coordinates without
creating circular imports.
"""
from constants import SCREEN_W, SCREEN_H

_scale_rect = None   # pygame.Rect of the game image within the real window


def set_scale_rect(rect):
    global _scale_rect
    _scale_rect = rect


def game_pos(window_pos):
    """Map a window-space (x, y) to game-space (1280×768) coordinates."""
    if _scale_rect is None or _scale_rect.width == 0 or _scale_rect.height == 0:
        return window_pos
    gx = int((window_pos[0] - _scale_rect.x) * SCREEN_W / _scale_rect.width)
    gy = int((window_pos[1] - _scale_rect.y) * SCREEN_H / _scale_rect.height)
    return (gx, gy)


def get_mouse_pos():
    """Return current mouse position in game-space."""
    import pygame
    return game_pos(pygame.mouse.get_pos())


def calc_scale_rect(window_w, window_h):
    """
    Return the pygame.Rect inside the window where the game image should be
    drawn, maintaining the game aspect ratio (letterbox / pillarbox).
    """
    import pygame
    aspect = SCREEN_W / SCREEN_H
    win_aspect = window_w / window_h
    if win_aspect > aspect:
        # Window is wider → pillarbox (black bars on sides)
        h = window_h
        w = int(h * aspect)
        x = (window_w - w) // 2
        y = 0
    else:
        # Window is taller → letterbox (black bars top/bottom)
        w = window_w
        h = int(w / aspect)
        x = 0
        y = (window_h - h) // 2
    return pygame.Rect(x, y, w, h)
