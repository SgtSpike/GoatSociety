import sys
import random
import socket as _socket_mod
import pygame
from pygame.locals import QUIT, KEYDOWN, K_ESCAPE, K_RETURN, K_BACKSPACE, K_F4, K_F11
import display as display_mod
from constants import (SCREEN_W, SCREEN_H, FPS, TITLE,
                       VIEWPORT_X, VIEWPORT_Y, VIEWPORT_W, VIEWPORT_H,
                       PANEL_BG, PANEL_BORD, WHITE, BLACK)
from game import Game
from renderer import Renderer
from ui import UI
from assets import Assets


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _make_font(size, bold=False):
    return pygame.font.SysFont("Arial", size, bold=bold)


def _draw_centered_text(surf, font, text, color, cy):
    ts = font.render(text, True, color)
    surf.blit(ts, (SCREEN_W // 2 - ts.get_width() // 2, cy))
    return ts.get_height()


def _draw_button(surf, font, text, rect, hovered, active=True):
    if not active:
        bg  = (35, 35, 45)
        col = (80, 80, 90)
    elif hovered:
        bg  = (70, 80, 110)
        col = WHITE
    else:
        bg  = (50, 55, 75)
        col = (200, 210, 230)
    pygame.draw.rect(surf, bg, rect, border_radius=6)
    pygame.draw.rect(surf, (90, 100, 130), rect, 2, border_radius=6)
    ts = font.render(text, True, col)
    surf.blit(ts, (rect.centerx - ts.get_width() // 2,
                   rect.centery - ts.get_height() // 2))


def _scale_to_screen(screen, game_surf):
    win_w, win_h = screen.get_size()
    sr = display_mod.calc_scale_rect(win_w, win_h)
    display_mod.set_scale_rect(sr)
    screen.fill((0, 0, 0))
    scaled = pygame.transform.scale(game_surf, (sr.width, sr.height))
    screen.blit(scaled, (sr.x, sr.y))
    pygame.display.flip()


def _transform_mouse_event(event):
    """Return a copy of a mouse event with pos/buttons transformed to game-space."""
    if hasattr(event, 'pos'):
        gpos = display_mod.game_pos(event.pos)
        d = {'pos': gpos}
        if hasattr(event, 'button'):
            d['button'] = event.button
        if hasattr(event, 'buttons'):
            d['buttons'] = event.buttons
        if hasattr(event, 'rel'):
            d['rel'] = event.rel
        return pygame.event.Event(event.type, d)
    return event


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def show_main_menu(screen, game_surf) -> str | None:
    """
    Draw a simple main menu. Returns 'singleplayer', 'host', 'join', or None (quit).
    """
    font_title  = _make_font(52, bold=True)
    font_btn    = _make_font(22, bold=True)

    btn_w, btn_h = 280, 52
    btn_x = SCREEN_W // 2 - btn_w // 2
    choices = [
        ('singleplayer', 'Singleplayer'),
        ('load',         'Load Game'),
        ('host',         'Host Game'),
        ('join',         'Join Game'),
        (None,           'Quit'),
    ]
    focused = 0

    while True:
        mx, my = display_mod.get_mouse_pos()

        # Layout buttons
        total_h = len(choices) * (btn_h + 14)
        start_y = SCREEN_H // 2 - total_h // 2 + 60
        rects = []
        for i, (key, label) in enumerate(choices):
            r = pygame.Rect(btn_x, start_y + i * (btn_h + 14), btn_w, btn_h)
            rects.append(r)

        # Draw
        game_surf.fill((18, 20, 28))

        # Title
        _draw_centered_text(game_surf, font_title, "GOAT SOCIETY",
                            (120, 200, 110), SCREEN_H // 2 - total_h // 2 - 20)

        for i, (key, label) in enumerate(choices):
            hovered = rects[i].collidepoint(mx, my) or focused == i
            _draw_button(game_surf, font_btn, label, rects[i], hovered)

        _scale_to_screen(screen, game_surf)

        # Events
        for event in pygame.event.get():
            if event.type == QUIT:
                return None
            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None
                elif event.key == K_RETURN:
                    return choices[focused][0]
                elif event.key == pygame.K_DOWN:
                    focused = (focused + 1) % len(choices)
                elif event.key == pygame.K_UP:
                    focused = (focused - 1) % len(choices)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gpos = display_mod.game_pos(event.pos)
                for i, (key, label) in enumerate(choices):
                    if rects[i].collidepoint(gpos):
                        return key
            elif event.type == pygame.MOUSEMOTION:
                gpos = display_mod.game_pos(event.pos)
                for i, r in enumerate(rects):
                    if r.collidepoint(gpos):
                        focused = i


# ---------------------------------------------------------------------------
# Game configuration screen
# ---------------------------------------------------------------------------

def show_game_config(screen, game_surf) -> dict | None:
    """
    Show game configuration screen.
    Returns dict with config options, or None on cancel.
    """
    font_title = _make_font(32, bold=True)
    font_label = _make_font(18, bold=True)
    font_btn   = _make_font(18, bold=True)
    font_small = _make_font(15)

    # Config state
    config = {
        'num_players': 2,
        'map_size': 'medium',
        'game_mode': 'standard',
        'ai_difficulty': 'normal',
    }

    map_sizes = ['small', 'medium', 'large']
    map_size_labels = {'small': 'Small (80x60)', 'medium': 'Medium (120x90)', 'large': 'Large (160x120)'}
    game_modes = ['standard', 'king_of_hill', 'survival']
    mode_labels = {'standard': 'Standard', 'king_of_hill': 'King of the Hill', 'survival': 'Survival'}
    mode_descs = {
        'standard': 'Destroy all enemy Town Halls to win.',
        'king_of_hill': 'Hold the center hill for 3 minutes to win.',
        'survival': 'Survive endless escalating waves of enemies.',
    }
    difficulties = ['easy', 'normal', 'hard']
    diff_labels = {'easy': 'Easy', 'normal': 'Normal', 'hard': 'Hard'}

    clock = pygame.time.Clock()
    start_rect = pygame.Rect(SCREEN_W // 2 - 130, SCREEN_H - 100, 260, 50)

    # Clickable rects stored each frame: [(rect, key, value), ...]
    click_rects = []

    while True:
        clock.tick(30)
        mx, my = display_mod.get_mouse_pos()
        click_rects = []

        game_surf.fill((18, 20, 28))

        cy = 40
        _draw_centered_text(game_surf, font_title, "GAME SETUP",
                            (120, 200, 110), cy)
        cy += 70

        def _option_row(label_text, options, labels_dict, config_key, btn_w, cy_ref):
            label = font_label.render(label_text, True, WHITE)
            game_surf.blit(label, (SCREEN_W // 2 - 200, cy_ref))
            gap = btn_w + 10
            for i, opt in enumerate(options):
                bx = SCREEN_W // 2 - 20 + i * gap
                rect = pygame.Rect(bx, cy_ref - 4, btn_w, 32)
                active = config[config_key] == opt
                hovered = rect.collidepoint(mx, my)
                bg = (80, 140, 80) if active else ((60, 65, 85) if hovered else (42, 45, 58))
                pygame.draw.rect(game_surf, bg, rect, border_radius=4)
                pygame.draw.rect(game_surf, (90, 100, 130), rect, 1, border_radius=4)
                text = labels_dict[opt] if isinstance(labels_dict, dict) else str(opt)
                ts = font_small.render(text, True, WHITE if active else (180, 180, 200))
                game_surf.blit(ts, (rect.centerx - ts.get_width() // 2,
                                    rect.centery - ts.get_height() // 2))
                click_rects.append((rect, config_key, opt))

        # Players
        player_labels = {n: str(n) for n in range(2, 7)}
        _option_row("Players:", list(range(2, 7)), player_labels, 'num_players', 44, cy)
        cy += 55

        # Map Size
        _option_row("Map Size:", map_sizes, map_size_labels, 'map_size', 130, cy)
        cy += 55

        # Game Mode
        _option_row("Game Mode:", game_modes, mode_labels, 'game_mode', 135, cy)
        cy += 40
        desc = mode_descs.get(config['game_mode'], '')
        desc_s = font_small.render(desc, True, (160, 160, 180))
        game_surf.blit(desc_s, (SCREEN_W // 2 - desc_s.get_width() // 2, cy))
        cy += 40

        # AI Difficulty
        _option_row("AI Difficulty:", difficulties, diff_labels, 'ai_difficulty', 90, cy)
        cy += 70

        # Start button
        hovered_start = start_rect.collidepoint(mx, my)
        _draw_button(game_surf, font_btn, "START GAME", start_rect, hovered_start)

        _draw_centered_text(game_surf, font_small, "ESC to go back",
                            (120, 120, 130), SCREEN_H - 40)

        _scale_to_screen(screen, game_surf)

        for event in pygame.event.get():
            if event.type == QUIT:
                return None
            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None
                elif event.key == K_RETURN:
                    return config
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gpos = display_mod.game_pos(event.pos)
                for rect, key, val in click_rects:
                    if rect.collidepoint(gpos):
                        config[key] = val
                if start_rect.collidepoint(gpos):
                    return config


# ---------------------------------------------------------------------------
# Load game screen
# ---------------------------------------------------------------------------

def show_load_screen(screen, game_surf) -> str | None:
    """Show save file browser. Returns filename to load, or None on cancel."""
    from savegame import list_saves
    import time as _time

    font_title = _make_font(32, bold=True)
    font_btn   = _make_font(18, bold=True)
    font_small = _make_font(15)

    clock = pygame.time.Clock()

    while True:
        clock.tick(30)
        saves = list_saves()
        mx, my = display_mod.get_mouse_pos()

        game_surf.fill((18, 20, 28))
        cy = 40
        _draw_centered_text(game_surf, font_title, "LOAD GAME",
                            (120, 200, 110), cy)
        cy += 70

        if not saves:
            _draw_centered_text(game_surf, font_small, "No save files found.",
                                (160, 160, 180), cy)
        else:
            row_rects = []
            for i, (filename, name, ts) in enumerate(saves[:8]):
                # Format timestamp
                if ts > 0:
                    lt = _time.localtime(ts)
                    date_str = _time.strftime('%Y-%m-%d %H:%M', lt)
                else:
                    date_str = '???'
                label = f"{name}   ({date_str})"
                rect = pygame.Rect(SCREEN_W // 2 - 220, cy, 440, 36)
                hovered = rect.collidepoint(mx, my)
                _draw_button(game_surf, font_small, label, rect, hovered)
                row_rects.append((rect, filename))
                cy += 44

        _draw_centered_text(game_surf, font_small, "ESC to go back",
                            (120, 120, 130), SCREEN_H - 40)

        _scale_to_screen(screen, game_surf)

        for event in pygame.event.get():
            if event.type == QUIT:
                return None
            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gpos = display_mod.game_pos(event.pos)
                if saves:
                    for rect, filename in row_rects:
                        if rect.collidepoint(gpos):
                            return filename


# ---------------------------------------------------------------------------
# Host lobby
# ---------------------------------------------------------------------------

def show_host_lobby(screen, game_surf, session) -> dict | None:
    """
    Show the host waiting lobby with game config and player list.
    Returns config dict on start, or None on cancel.
    """
    import network
    font_title = _make_font(32, bold=True)
    font_label = _make_font(18, bold=True)
    font_body  = _make_font(18)
    font_small = _make_font(15)
    font_btn   = _make_font(20, bold=True)

    local_ip = network.get_local_ip()
    clock = pygame.time.Clock()

    # Game config (host chooses settings)
    config = {
        'map_size': 'medium',
        'game_mode': 'standard',
        'ai_difficulty': 'normal',
    }

    map_sizes = ['small', 'medium', 'large']
    map_size_labels = {'small': 'Small', 'medium': 'Medium', 'large': 'Large'}
    game_modes = ['standard', 'king_of_hill', 'survival']
    mode_labels = {'standard': 'Standard', 'king_of_hill': 'King of the Hill',
                   'survival': 'Survival'}
    difficulties = ['easy', 'normal', 'hard']
    diff_labels = {'easy': 'Easy', 'normal': 'Normal', 'hard': 'Hard'}

    # Team colors for display
    team_colors = [
        (80, 180, 80),    # 0 = host (green)
        (80, 130, 230),   # 1 = blue
        (230, 80, 80),    # 2 = red
        (230, 200, 50),   # 3 = yellow
        (180, 80, 220),   # 4 = purple
        (230, 140, 50),   # 5 = orange
    ]

    btn_start = pygame.Rect(SCREEN_W // 2 - 130, SCREEN_H - 90, 260, 50)
    click_rects = []

    while True:
        clock.tick(30)
        mx, my = display_mod.get_mouse_pos()
        click_rects = []

        # Poll for new client connections
        session.try_accept()

        clients = session.clients_info
        has_clients = len(clients) > 0

        # Draw
        game_surf.fill((18, 20, 28))

        cy = 30
        _draw_centered_text(game_surf, font_title, "HOST GAME",
                            (120, 200, 110), cy)
        cy += 50

        _draw_centered_text(game_surf, font_body, f"Your IP: {local_ip}",
                            (200, 210, 230), cy)
        cy += 40

        # --- Player list ---
        _draw_centered_text(game_surf, font_label, "Players:",
                            WHITE, cy)
        cy += 28

        # Host (always player 1, team 0)
        host_txt = font_small.render("  1. You (Host)", True, team_colors[0])
        game_surf.blit(host_txt, (SCREEN_W // 2 - 120, cy))
        cy += 24

        if clients:
            for ci in clients:
                idx = ci['team'] + 1
                col = team_colors[ci['team']] if ci['team'] < len(team_colors) else WHITE
                status = "Ready" if ci['connected'] else "Disconnected"
                txt = font_small.render(f"  {idx}. {ci['name']} - {status}",
                                        True, col if ci['connected'] else (120, 120, 130))
                game_surf.blit(txt, (SCREEN_W // 2 - 120, cy))
                cy += 24
        else:
            txt = font_small.render("  Waiting for players...", True, (120, 120, 140))
            game_surf.blit(txt, (SCREEN_W // 2 - 120, cy))
            cy += 24

        # Show slots remaining
        max_c = session._max_clients
        slots = max_c - len(clients)
        if slots > 0:
            txt = font_small.render(f"  ({slots} slot{'s' if slots != 1 else ''} open)",
                                    True, (100, 100, 120))
            game_surf.blit(txt, (SCREEN_W // 2 - 120, cy))
        cy += 36

        # --- Config options ---
        def _option_row(label_text, options, labels_dict, config_key, btn_w, cy_ref):
            label = font_label.render(label_text, True, WHITE)
            game_surf.blit(label, (SCREEN_W // 2 - 200, cy_ref))
            gap = btn_w + 10
            for i, opt in enumerate(options):
                bx = SCREEN_W // 2 - 20 + i * gap
                rect = pygame.Rect(bx, cy_ref - 4, btn_w, 32)
                active = config[config_key] == opt
                hovered = rect.collidepoint(mx, my)
                bg = (80, 140, 80) if active else ((60, 65, 85) if hovered else (42, 45, 58))
                pygame.draw.rect(game_surf, bg, rect, border_radius=4)
                pygame.draw.rect(game_surf, (90, 100, 130), rect, 1, border_radius=4)
                text = labels_dict[opt] if isinstance(labels_dict, dict) else str(opt)
                ts = font_small.render(text, True, WHITE if active else (180, 180, 200))
                game_surf.blit(ts, (rect.centerx - ts.get_width() // 2,
                                    rect.centery - ts.get_height() // 2))
                click_rects.append((rect, config_key, opt))

        _option_row("Map Size:", map_sizes, map_size_labels, 'map_size', 100, cy)
        cy += 45
        _option_row("Game Mode:", game_modes, mode_labels, 'game_mode', 135, cy)
        cy += 45
        _option_row("AI Difficulty:", difficulties, diff_labels, 'ai_difficulty', 90, cy)
        cy += 50

        # Start button (enabled when at least one client connected)
        hovered_start = btn_start.collidepoint(mx, my) and has_clients
        _draw_button(game_surf, font_btn, "START GAME (Enter)",
                     btn_start, hovered_start, active=has_clients)

        _draw_centered_text(game_surf, font_small, "ESC to cancel",
                            (120, 120, 130), SCREEN_H - 35)

        _scale_to_screen(screen, game_surf)

        for event in pygame.event.get():
            if event.type == QUIT:
                return None
            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None
                elif event.key == K_RETURN and has_clients:
                    config['num_players'] = 1 + len(clients)  # host + clients
                    config['human_teams'] = [0] + [c['team'] for c in clients]
                    return config
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gpos = display_mod.game_pos(event.pos)
                for rect, key, val in click_rects:
                    if rect.collidepoint(gpos):
                        config[key] = val
                if btn_start.collidepoint(gpos) and has_clients:
                    config['num_players'] = 1 + len(clients)
                    config['human_teams'] = [0] + [c['team'] for c in clients]
                    return config


# ---------------------------------------------------------------------------
# Join screen
# ---------------------------------------------------------------------------

def show_join_screen(screen, game_surf) -> tuple | None:
    """
    Show a join screen. First scans for LAN hosts (2s), then lets user pick or
    type an IP manually. Returns (addr, seed, host_name) or None.
    """
    import network

    font_title  = _make_font(32, bold=True)
    font_body   = _make_font(18)
    font_small  = _make_font(15)
    font_btn    = _make_font(18, bold=True)

    # --- Phase 1: scanning ---
    game_surf.fill((18, 20, 28))
    _draw_centered_text(game_surf, font_title, "JOIN GAME", (120, 200, 110), SCREEN_H // 4)
    _draw_centered_text(game_surf, font_body, "Scanning for LAN games...",
                        (160, 160, 180), SCREEN_H // 2 - 20)
    _scale_to_screen(screen, game_surf)

    # Actually do the scan (blocks ~2s)
    hosts = network.discover_hosts(timeout=2.0)

    # --- Phase 2: show results + manual input ---
    manual_ip   = ''
    error_msg   = ''
    clock       = pygame.time.Clock()

    manual_rect = pygame.Rect(SCREEN_W // 2 - 160, SCREEN_H * 3 // 4 - 15, 240, 36)
    connect_rect= pygame.Rect(SCREEN_W // 2 + 90,  SCREEN_H * 3 // 4 - 15, 110, 36)

    while True:
        clock.tick(30)
        mx, my = display_mod.get_mouse_pos()

        game_surf.fill((18, 20, 28))
        cy = SCREEN_H // 4
        _draw_centered_text(game_surf, font_title, "JOIN GAME", (120, 200, 110), cy)
        cy += 56

        if hosts:
            _draw_centered_text(game_surf, font_small, "Found games:", (180, 180, 200), cy)
            cy += 24
            for i, host_info in enumerate(hosts):
                addr, seed, hname = host_info[0], host_info[1], host_info[2]
                n_players = host_info[3] if len(host_info) > 3 else 1
                max_players = host_info[4] if len(host_info) > 4 else 6
                row_rect = pygame.Rect(SCREEN_W // 2 - 220, cy, 340, 34)
                join_rect= pygame.Rect(SCREEN_W // 2 + 130, cy, 90, 34)
                hovered_row  = row_rect.collidepoint(mx, my)
                hovered_join = join_rect.collidepoint(mx, my)
                label = f"{hname}  [{addr}]  ({n_players}/{max_players})"
                _draw_button(game_surf, font_small, label, row_rect, hovered_row)
                _draw_button(game_surf, font_btn, "JOIN", join_rect, hovered_join)
                cy += 44
        else:
            _draw_centered_text(game_surf, font_small, "No games found on LAN.",
                                (140, 140, 150), cy)
            cy += 30

        cy = SCREEN_H * 3 // 4 - 50
        _draw_centered_text(game_surf, font_small, "Enter IP manually:", (180, 180, 200), cy)

        # Manual IP text box
        pygame.draw.rect(game_surf, (35, 38, 52), manual_rect, border_radius=4)
        pygame.draw.rect(game_surf, PANEL_BORD, manual_rect, 2, border_radius=4)
        ip_surf = font_body.render(manual_ip + '|', True, WHITE)
        game_surf.blit(ip_surf, (manual_rect.x + 6,
                                 manual_rect.centery - ip_surf.get_height() // 2))

        hovered_conn = connect_rect.collidepoint(mx, my)
        _draw_button(game_surf, font_btn, "CONNECT", connect_rect, hovered_conn)

        if error_msg:
            _draw_centered_text(game_surf, font_small, error_msg,
                                (230, 80, 80), SCREEN_H * 3 // 4 + 30)

        _draw_centered_text(game_surf, font_small, "ESC to go back",
                            (120, 120, 130), SCREEN_H - 60)

        _scale_to_screen(screen, game_surf)

        for event in pygame.event.get():
            if event.type == QUIT:
                return None
            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None
                elif event.key == K_BACKSPACE:
                    manual_ip = manual_ip[:-1]
                    error_msg = ''
                elif event.key == K_RETURN:
                    if manual_ip.strip():
                        addr = manual_ip.strip()
                        return (addr, 0, addr)
                else:
                    ch = event.unicode
                    if ch and (ch.isdigit() or ch == '.'):
                        manual_ip += ch
                        error_msg = ''

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gpos = display_mod.game_pos(event.pos)

                # Check host rows
                cy2 = SCREEN_H // 4 + 56
                if hosts:
                    cy2 += 24
                    for host_info in hosts:
                        addr, seed, hname = host_info[0], host_info[1], host_info[2]
                        row_rect2 = pygame.Rect(SCREEN_W // 2 - 220, cy2, 340, 34)
                        join_rect2= pygame.Rect(SCREEN_W // 2 + 130, cy2, 90, 34)
                        if row_rect2.collidepoint(gpos) or join_rect2.collidepoint(gpos):
                            return (addr, seed, hname)
                        cy2 += 44

                # Connect button
                if connect_rect.collidepoint(gpos) and manual_ip.strip():
                    addr = manual_ip.strip()
                    return (addr, 0, addr)


# ---------------------------------------------------------------------------
# Wait for start (client side)
# ---------------------------------------------------------------------------

def wait_for_start(screen, game_surf, session) -> dict | None:
    """
    Show a "waiting for host" screen. Polls session.start_info until set.
    Returns the start_info dict or None on disconnect/ESC.
    """
    font_title = _make_font(28, bold=True)
    font_body  = _make_font(18)
    font_small = _make_font(15)
    clock      = pygame.time.Clock()
    dots       = 0
    dot_timer  = 0.0

    while True:
        dt = clock.tick(30) / 1000.0
        dot_timer += dt
        if dot_timer >= 0.4:
            dot_timer = 0.0
            dots = (dots + 1) % 4

        if session.start_info is not None:
            return session.start_info

        if not session.is_connected():
            return None

        game_surf.fill((18, 20, 28))
        _draw_centered_text(game_surf, font_title,
                            "Connected!", (80, 230, 80), SCREEN_H // 2 - 60)
        _draw_centered_text(game_surf, font_body,
                            "Waiting for host to start" + '.' * dots,
                            (160, 160, 180), SCREEN_H // 2)
        _draw_centered_text(game_surf, font_small, "ESC to disconnect",
                            (120, 120, 130), SCREEN_H - 60)
        _scale_to_screen(screen, game_surf)

        for event in pygame.event.get():
            if event.type == QUIT:
                return None
            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None


# ---------------------------------------------------------------------------
# Unified game loop
# ---------------------------------------------------------------------------

def run_game_loop(screen, game_surf, clock, game, assets,
                  session=None, is_host=False):
    """
    Run the game until it ends (game_over) or the user quits.
    Works for singleplayer (session=None) and multiplayer.
    After game_over, keeps rendering for ~3 seconds before returning.
    """
    renderer  = Renderer(game_surf, assets)
    ui        = UI(assets)
    font_msg  = pygame.font.SysFont("Arial", 14, bold=True)
    font_end  = pygame.font.SysFont("Arial", 52, bold=True)
    is_fs     = False

    state_timer  = 0.0
    running      = True
    game_over_t  = 0.0   # seconds since game_over became True

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        # HOST: apply incoming commands from client
        if is_host and session:
            for cmd_data in session.poll_commands():
                game.apply_net_command(cmd_data)

        # CLIENT: apply latest state snapshot from host
        if not is_host and session:
            state = session.poll_state()
            if state:
                game.apply_net_state(state)
            if not session.is_connected() and not game.game_over:
                game._add_message("Connection lost!")
                game.game_over = True

        # --- Events ---
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                sr = display_mod.calc_scale_rect(event.w, event.h)
                display_mod.set_scale_rect(sr)

            elif event.type == KEYDOWN:
                if event.key == K_F4:
                    running = False
                elif event.key == K_F11:
                    is_fs = not is_fs
                    if is_fs:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode(
                            (SCREEN_W, SCREEN_H), pygame.RESIZABLE)
                    sr = display_mod.calc_scale_rect(*screen.get_size())
                    display_mod.set_scale_rect(sr)
                else:
                    game.handle_event(event, ui)

            elif event.type == pygame.MOUSEWHEEL:
                # Zoom in/out with scroll wheel
                factor = 1.1 if event.y > 0 else (1 / 1.1)
                game.zoom = max(0.4, min(3.0, game.zoom * factor))

            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                                 pygame.MOUSEMOTION):
                game.handle_event(_transform_mouse_event(event), ui)

            else:
                game.handle_event(event, ui)

        # --- Quick-load (F9) ---
        if getattr(game, '_request_load', False) and session is None:
            game._request_load = False
            from savegame import list_saves, load_game
            saves = list_saves()
            if saves:
                try:
                    game = load_game(saves[0][0])
                    renderer = Renderer(game_surf, assets)
                    ui = UI(assets)
                except Exception as e:
                    print(f"Quick-load failed: {e}")

        # --- Simulation ---
        if not game.game_over:
            game.update_camera(dt)
            # Only the host (or singleplayer) runs the simulation
            if not getattr(game, 'paused', False) and (session is None or is_host):
                game.update(dt)
        else:
            # Still allow camera panning during end screen
            game.update_camera(dt)
            game_over_t += dt
            if game_over_t >= 3.0:
                running = False

        # HOST: send state snapshot at ~20 Hz
        if is_host and session and session.is_connected():
            state_timer += dt
            if state_timer >= 0.05:
                state_timer = 0.0
                session.send_state(game.serialize_state())

        # --- Render ---
        renderer.draw(game, ui)

        # Status messages
        msgs = game.get_messages()
        for i, (t, msg) in enumerate(reversed(msgs[-4:])):
            alpha = min(255, int(t / 3.0 * 255))
            ms = font_msg.render(msg, True, (255, 220, 100))
            ms.set_alpha(alpha)
            game_surf.blit(ms, (SCREEN_W // 2 - ms.get_width() // 2,
                                VIEWPORT_Y + VIEWPORT_H - 30 - i * 20))

        # Pause overlay
        if getattr(game, 'paused', False):
            dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 120))
            game_surf.blit(dim, (0, 0))
            pause_txt = font_end.render("PAUSED", True, (220, 220, 230))
            game_surf.blit(pause_txt, (SCREEN_W // 2 - pause_txt.get_width() // 2,
                                       SCREEN_H // 2 - pause_txt.get_height() // 2))
            hint = font_msg.render("Press ESC to resume", True, (160, 160, 180))
            game_surf.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2,
                                  SCREEN_H // 2 + pause_txt.get_height() // 2 + 10))

        # Multiplayer end-game overlay
        if game.game_over and session is not None:
            my_team = game.net_my_team
            my_player = game.players.get(my_team)
            # Player wins if their town hall still stands
            won = my_player is not None and any(
                b.btype == 'town_hall' and b.alive
                for b in my_player.buildings)
            label = "VICTORY!" if won else "DEFEAT"
            col   = (80, 240, 80) if won else (240, 60, 60)
            big   = font_end.render(label, True, col)
            game_surf.blit(big, (SCREEN_W // 2 - big.get_width() // 2,
                                 SCREEN_H // 2 - big.get_height() // 2))

        # FPS counter
        fps_s = font_msg.render(f"{clock.get_fps():.0f}", True, (120, 120, 130))
        game_surf.blit(fps_s, (SCREEN_W - fps_s.get_width() - 6, 4))

        _scale_to_screen(screen, game_surf)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    pygame.init()
    import sounds as sounds_mod
    sounds_mod.init()
    pygame.display.set_caption(TITLE)
    screen   = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
    game_surf= pygame.Surface((SCREEN_W, SCREEN_H))
    clock    = pygame.time.Clock()

    sr = display_mod.calc_scale_rect(*screen.get_size())
    display_mod.set_scale_rect(sr)

    print("Loading assets...")
    assets = Assets()

    while True:
        choice = show_main_menu(screen, game_surf)

        if choice is None:
            break

        elif choice == 'singleplayer':
            cfg = show_game_config(screen, game_surf)
            if cfg is None:
                continue
            game = Game(config=cfg)
            run_game_loop(screen, game_surf, clock, game, assets)

        elif choice == 'load':
            filename = show_load_screen(screen, game_surf)
            if filename:
                from savegame import load_game
                try:
                    game = load_game(filename)
                    run_game_loop(screen, game_surf, clock, game, assets)
                except Exception as e:
                    print(f"Load failed: {e}")
                    import traceback; traceback.print_exc()

        elif choice == 'host':
            import network
            seed = random.randint(0, 99999)
            session = network.HostSession(seed, network.get_local_ip())
            lobby_result = show_host_lobby(screen, game_surf, session)
            if lobby_result:
                cfg = lobby_result
                human_teams = set(cfg.pop('human_teams', [0]))
                session.send_start(config=cfg | {'seed': seed})
                cfg['seed'] = seed
                game = Game(seed=seed, config=cfg)
                game.net_mode     = 'host'
                game.net_my_team  = 0
                game._net_session = session
                # Stop AI for all human-controlled teams and cancel auto-gather
                game.ai_controllers = [
                    ai for ai in game.ai_controllers
                    if ai.team not in human_teams
                ]
                for ht in human_teams:
                    if ht != 0 and ht in game.players:
                        for u in game.players[ht].units:
                            u.stop()
                run_game_loop(screen, game_surf, clock, game, assets,
                              session=session, is_host=True)
            session.close()

        elif choice == 'join':
            import network
            result = show_join_screen(screen, game_surf)
            if result:
                addr, seed, host_name = result
                session = network.ClientSession()
                try:
                    session.connect(addr)
                    session.send_ready(name=_socket_mod.gethostname())
                    start_info = wait_for_start(screen, game_surf, session)
                    if start_info:
                        seed        = start_info['seed']
                        client_team = start_info['client_team']
                        cfg         = start_info.get('config', {})
                        cfg['seed'] = seed
                        game = Game(seed=seed, config=cfg)
                        game.net_mode     = 'client'
                        game.net_my_team  = client_team
                        game._net_session = session
                        # Center camera on client team's starting base
                        for b in game.players[client_team].buildings:
                            if b.btype == 'town_hall':
                                from constants import VIEWPORT_W, VIEWPORT_H
                                game.cam_x = b.x - VIEWPORT_W / 2
                                game.cam_y = b.y - VIEWPORT_H / 2
                                game._clamp_camera()
                                break
                        run_game_loop(screen, game_surf, clock, game, assets,
                                      session=session, is_host=False)
                    session.close()
                except Exception as e:
                    print(f"Connection failed: {e}")
                    # Show brief error message
                    game_surf.fill((18, 20, 28))
                    font_err = pygame.font.SysFont("Arial", 20, bold=True)
                    err_s = font_err.render(f"Connection failed: {e}",
                                            True, (230, 80, 80))
                    game_surf.blit(err_s, (SCREEN_W // 2 - err_s.get_width() // 2,
                                           SCREEN_H // 2 - err_s.get_height() // 2))
                    _scale_to_screen(screen, game_surf)
                    pygame.time.wait(2000)

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
