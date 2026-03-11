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
# Host lobby
# ---------------------------------------------------------------------------

def show_host_lobby(screen, game_surf, session) -> str | None:
    """
    Show the host waiting lobby. Returns client name on success, None on cancel.
    """
    import network
    font_title = _make_font(32, bold=True)
    font_body  = _make_font(18)
    font_small = _make_font(15)

    btn_start = pygame.Rect(SCREEN_W // 2 - 130, SCREEN_H // 2 + 80, 260, 50)
    font_btn  = _make_font(20, bold=True)

    local_ip = network.get_local_ip()
    clock = pygame.time.Clock()

    while True:
        clock.tick(30)
        mx, my = display_mod.get_mouse_pos()

        # Poll for new client connection each frame
        session.try_accept()

        connected = session.is_connected()
        client_nm = session.client_name

        # Draw
        game_surf.fill((18, 20, 28))

        cy = SCREEN_H // 4
        _draw_centered_text(game_surf, font_title, "HOST GAME",
                            (120, 200, 110), cy)
        cy += 60

        _draw_centered_text(game_surf, font_body, f"Your IP: {local_ip}",
                            (200, 210, 230), cy)
        cy += 36

        if connected:
            _draw_centered_text(game_surf, font_body,
                                f"Player 2: {client_nm} - Ready!",
                                (80, 230, 80), cy)
        else:
            _draw_centered_text(game_surf, font_body,
                                "Waiting for player to connect...",
                                (160, 160, 180), cy)
        cy += 50

        # Start button (only when client is ready)
        hovered_start = btn_start.collidepoint(mx, my) and connected
        _draw_button(game_surf, font_btn, "Press ENTER to start",
                     btn_start, hovered_start, active=connected)

        _draw_centered_text(game_surf, font_small, "ESC to cancel",
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
                elif event.key == K_RETURN and connected:
                    return client_nm
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gpos = display_mod.game_pos(event.pos)
                if btn_start.collidepoint(gpos) and connected:
                    return client_nm


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
            for i, (addr, seed, hname) in enumerate(hosts):
                row_rect = pygame.Rect(SCREEN_W // 2 - 220, cy, 340, 34)
                join_rect= pygame.Rect(SCREEN_W // 2 + 130, cy, 90, 34)
                hovered_row  = row_rect.collidepoint(mx, my)
                hovered_join = join_rect.collidepoint(mx, my)
                _draw_button(game_surf, font_small, f"{hname}  [{addr}]",
                             row_rect, hovered_row)
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
                    for addr, seed, hname in hosts:
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

        # --- Simulation ---
        if not game.game_over:
            game.update_camera(dt)
            # Only the host (or singleplayer) runs the simulation
            if session is None or is_host:
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

        # Multiplayer end-game overlay (client perspective)
        if game.game_over and session is not None:
            # Host: player_won=True means team 0 wins
            # Client is team 1, so if player_won=True they lose
            if is_host:
                won = game.player_won
            else:
                won = not game.player_won   # team 1 wins when team 0 loses
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
            game = Game()
            run_game_loop(screen, game_surf, clock, game, assets)

        elif choice == 'host':
            import network
            seed = random.randint(0, 99999)
            session = network.HostSession(seed, network.get_local_ip())
            client_name = show_host_lobby(screen, game_surf, session)
            if client_name:
                session.send_start(client_team=1)
                game = Game(seed=seed)
                game.net_mode     = 'host'
                game.net_my_team  = 0
                game._net_session = session
                # Team 1 is human-controlled — cancel the AI's auto-assigned gather
                from constants import AI_TEAM
                for u in game.players[AI_TEAM].units:
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
                        game = Game(seed=seed)
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
