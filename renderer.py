import pygame
import math
import display as display_mod
from constants import (TILE_SIZE, MAP_W, MAP_H, SCREEN_W, SCREEN_H,
                       VIEWPORT_X, VIEWPORT_Y, VIEWPORT_W, VIEWPORT_H,
                       TOP_BAR_H, BOTTOM_PANEL_H, MINIMAP_W, MINIMAP_H,
                       TEAM_COLORS, TILE_GRASS, TILE_WATER, TILE_FOREST,
                       TILE_GOLD, TILE_ROCK, TILE_DIRT,
                       HP_RED, HP_GREEN, HP_YELLOW, SEL_GREEN,
                       PANEL_BG, PANEL_BORD, DARK_GRAY, WHITE, BLACK, GOLD_COLOR,
                       FOG_OF_WAR)
from buildings import Building
from units import Unit


# Pre-baked fog/dim overlays
_FOG_SURF  = pygame.Surface((TILE_SIZE, TILE_SIZE))
_FOG_SURF.fill((0, 0, 0))

_DIM_SURF  = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
_DIM_SURF.fill((0, 0, 0, 160))


class Renderer:
    def __init__(self, screen, assets):
        self.screen = screen
        self.assets = assets
        self.font_sm = pygame.font.SysFont("Arial", 11)
        self.font_md = pygame.font.SysFont("Arial", 13, bold=True)
        self.font_lg = pygame.font.SysFont("Arial", 16, bold=True)

        # Off-screen surface for viewport
        self.vp_surf = pygame.Surface((VIEWPORT_W, VIEWPORT_H))
        self._scene  = self.vp_surf   # will be overridden each frame by draw()

        # Minimap surface (1 px per tile)
        self.mm_surf = pygame.Surface((MAP_W, MAP_H))

        self._mm_dirty = True   # rebuild minimap next frame

    # ================================================================ PUBLIC
    def draw(self, game, ui):
        zoom = max(0.1, game.zoom)
        # Render to a zoom-adjusted scene surface, then scale to vp_surf
        scene_w = max(1, int(VIEWPORT_W / zoom))
        scene_h = max(1, int(VIEWPORT_H / zoom))
        if not hasattr(self, '_scene_surf') or self._scene_surf.get_size() != (scene_w, scene_h):
            self._scene_surf = pygame.Surface((scene_w, scene_h))
        scene = self._scene_surf
        scene.fill((20, 20, 20))

        self._scene = scene   # shared by all draw helpers

        self._draw_tiles(game)
        self._draw_resources(game)
        self._draw_dead_effects(game)
        self._draw_buildings(game)
        self._draw_units(game)
        self._draw_projectiles(game)
        self._draw_particles(game)
        self._draw_selection_indicators(game)
        self._draw_health_bars(game)
        self._draw_fog(game)
        self._draw_neutral_camps(game)
        if game.game_mode == 'king_of_hill':
            self._draw_koth_zone(game)
        self._draw_build_ghost(game)
        self._draw_drag_rect(game)

        if zoom == 1.0:
            self.vp_surf.blit(scene, (0, 0))
        else:
            pygame.transform.scale(scene, (VIEWPORT_W, VIEWPORT_H), self.vp_surf)

        self.screen.blit(self.vp_surf, (VIEWPORT_X, VIEWPORT_Y))

        # Red vignette when the player's team is under attack
        self._draw_attack_vignette(game)

        ui.draw(self.screen, game, self)

    # ================================================================ TILES
    def _draw_tiles(self, game):
        s = self._scene
        sw, sh = s.get_size()
        cam_x, cam_y = game.cam_x, game.cam_y
        start_tx = max(0, int(cam_x // TILE_SIZE))
        start_ty = max(0, int(cam_y // TILE_SIZE))
        end_tx   = min(game.game_map.width, start_tx + sw // TILE_SIZE + 2)
        end_ty   = min(game.game_map.height, start_ty + sh // TILE_SIZE + 2)

        for tx in range(start_tx, end_tx):
            for ty in range(start_ty, end_ty):
                if not game.game_map.is_explored(tx, ty):
                    continue  # will be covered by fog later
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                tile_surf = self.assets.get_tile(game.game_map.tiles[tx][ty],
                                                game.time_elapsed)
                s.blit(tile_surf, (sx, sy))

    # ============================================================== RESOURCES
    def _draw_resources(self, game):
        # Resources are embedded in tile graphics; depletion shown as dirt
        s = self._scene
        sw, sh = s.get_size()
        cam_x, cam_y = game.cam_x, game.cam_y
        for (tx, ty), node in game.game_map.resources.items():
            if not game.game_map.is_visible(tx, ty):
                continue
            if node.depleted:
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                if -TILE_SIZE < sx < sw and -TILE_SIZE < sy < sh:
                    s.blit(self.assets.get_tile(TILE_DIRT), (sx, sy))
            elif node.type == 'wood' and node.amount < node.max_amount * 0.5:
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                if -TILE_SIZE < sx < sw and -TILE_SIZE < sy < sh:
                    # Draw depleted forest (dimmer)
                    ts = self.assets.get_tile(TILE_FOREST).copy()
                    ts.set_alpha(180)
                    s.blit(ts, (sx, sy))

    # ============================================================= BUILDINGS
    def _draw_buildings(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for team_id, player in game.players.items():
            for bld in player.buildings:
                if not bld.alive:
                    continue
                # Check if any tile in footprint is visible/explored
                visible = any(game.game_map.is_visible(ftx, fty)
                              for ftx, fty in bld.tile_footprint())
                explored = any(game.game_map.is_explored(ftx, fty)
                               for ftx, fty in bld.tile_footprint())
                if not explored:
                    continue

                sx = bld._tx * TILE_SIZE - int(cam_x)
                sy = bld._ty * TILE_SIZE - int(cam_y)
                pw = bld.w_tiles * TILE_SIZE
                ph = bld.h_tiles * TILE_SIZE

                sw2, sh2 = self._scene.get_size()
                if sx + pw < 0 or sx > sw2 or sy + ph < 0 or sy > sh2:
                    continue

                if bld.is_constructed:
                    # Use vertical wall sprite when wall has vertical neighbours
                    draw_btype = bld.btype
                    if bld.btype == 'wall':
                        ftx, fty = bld._tx, bld._ty
                        has_v = any(
                            any(b.btype == 'wall' and b.alive and b._tx == ftx and b._ty == fty + dy
                                for player2 in game.players.values()
                                for b in player2.buildings
                                if b.team == bld.team)
                            for dy in (-1, 1)
                        )
                        if has_v:
                            draw_btype = 'wall_v'
                    surf = self.assets.get_building(draw_btype, bld.team)
                else:
                    surf = self.assets.get_building(bld.btype, bld.team, construction=True)
                    # Construction progress bar on top
                    if surf:
                        self._scene.blit(surf, (sx, sy))
                    self._draw_construction_bar(bld, sx, sy, pw)
                    if bld.selected:
                        self._draw_selection_rect(sx, sy, pw, ph)
                    continue

                if surf:
                    if not visible:
                        dim = surf.copy()
                        dim.set_alpha(100)
                        self._scene.blit(dim, (sx, sy))
                    else:
                        self._scene.blit(surf, (sx, sy))

                # Damage overlay (cracks when < 50% HP, fire when < 25% HP)
                if visible and bld.hp < bld.max_hp:
                    hp_ratio = bld.hp / bld.max_hp
                    dmg_surf = self.assets.get_damage_overlay(
                        bld.btype if bld.btype != 'wall_v' else 'wall', hp_ratio)
                    if dmg_surf:
                        # Animate fire flicker
                        if hp_ratio < 0.25:
                            import math as _m
                            flicker = _m.sin(game.time_elapsed * 8) * 0.15 + 0.85
                            copy = dmg_surf.copy()
                            copy.set_alpha(int(255 * flicker))
                            self._scene.blit(copy, (sx, sy))
                        else:
                            self._scene.blit(dmg_surf, (sx, sy))

                if bld.selected:
                    self._draw_selection_rect(sx, sy, pw, ph)

                # Rally point flag
                if bld.selected and bld.rally_point:
                    rpx = int(bld.rally_point[0]) - int(cam_x)
                    rpy = int(bld.rally_point[1]) - int(cam_y)
                    pygame.draw.line(self._scene, (255, 255, 0),
                                     (sx + pw // 2, sy + ph // 2), (rpx, rpy), 1)
                    pygame.draw.circle(self._scene, (255, 255, 0), (rpx, rpy), 4, 1)

    def _draw_construction_bar(self, bld, sx, sy, pw):
        bh = 6
        by = sy - 10
        pygame.draw.rect(self._scene, (60, 60, 60), (sx, by, pw, bh))
        filled = int(pw * bld.construction_progress)
        pygame.draw.rect(self._scene, (255, 180, 0), (sx, by, filled, bh))
        pygame.draw.rect(self._scene, (100, 100, 100), (sx, by, pw, bh), 1)

    def _draw_selection_rect(self, sx, sy, pw, ph):
        pygame.draw.rect(self._scene, SEL_GREEN, (sx - 1, sy - 1, pw + 2, ph + 2), 2)

    # ================================================================= UNITS
    def _draw_units(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for team_id, player in game.players.items():
            for unit in player.units:
                if not unit.alive:
                    continue
                if not game.game_map.is_visible(unit.tx, unit.ty):
                    continue
                sx = int(unit.x) - int(cam_x) - TILE_SIZE // 2
                sy = int(unit.y) - int(cam_y) - TILE_SIZE // 2

                sw3, sh3 = self._scene.get_size()
                if sx + TILE_SIZE < 0 or sx > sw3 or sy + TILE_SIZE < 0 or sy > sh3:
                    continue

                surf = self.assets.get_unit(unit.utype, unit.team)
                if surf:
                    if unit.flip_h:
                        surf = pygame.transform.flip(surf, True, False)

                    # Gathering / building bob animation
                    draw_sy = sy
                    if unit.utype == 'worker' and unit.state in ('gathering', 'building'):
                        draw_sy += -int(abs(math.sin(unit.anim_t * 5.5)) * 3)

                    self._scene.blit(surf, (sx, draw_sy))

                    # Sparkle at the axe tip on the "down-stroke" peak
                    if unit.utype == 'worker' and unit.state == 'gathering':
                        phase = math.sin(unit.anim_t * 5.5)
                        if phase < -0.8:          # bottom of swing = impact
                            # axe tip offset from sprite top-left (matches _draw_goat)
                            flip = unit.flip_h
                            tip_x = sx + (TILE_SIZE - 8 if flip else 8)
                            tip_y = draw_sy + TILE_SIZE // 2 - 5
                            pygame.draw.circle(self._scene, (255, 235, 100), (tip_x, tip_y), 3)
                            pygame.draw.circle(self._scene, (255, 200,  40), (tip_x, tip_y), 1)
                            # two tiny chips offset from tip
                            for cx2, cy2 in [(tip_x - 4, tip_y - 3), (tip_x + 2, tip_y - 5)]:
                                pygame.draw.circle(self._scene, (190, 140, 60), (cx2, cy2), 1)

    # ============================================================ PROJECTILES
    def _draw_projectiles(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        arrow = self.assets.projectiles.get('arrow')
        if not arrow:
            return
        for proj in game.projectiles:
            if not proj.alive:
                continue
            if game.game_map.is_visible(int(proj.x // TILE_SIZE),
                                         int(proj.y // TILE_SIZE)):
                sx = int(proj.x) - int(cam_x)
                sy = int(proj.y) - int(cam_y)
                dx = proj.target.x - proj.x if proj.target else 1
                dy = proj.target.y - proj.y if proj.target else 0
                angle = -math.degrees(math.atan2(dy, dx))
                rot = pygame.transform.rotate(arrow, angle)
                self._scene.blit(rot, (sx - rot.get_width() // 2,
                                        sy - rot.get_height() // 2))

    # =========================================================== SELECTION
    def _draw_selection_indicators(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for ent in game.selection:
            if not ent.alive:
                continue
            if isinstance(ent, Unit):
                if not game.game_map.is_visible(ent.tx, ent.ty):
                    continue
                sx = int(ent.x) - int(cam_x)
                sy = int(ent.y) - int(cam_y)
                pygame.draw.ellipse(self._scene, SEL_GREEN,
                                    (sx - 12, sy + TILE_SIZE // 2 - 5, 24, 10), 2)

    # ============================================================= HEALTH BARS
    def _draw_health_bars(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for team_id, player in game.players.items():
            for unit in player.units:
                if not unit.alive or unit.hp >= unit.max_hp:
                    continue
                if not game.game_map.is_visible(unit.tx, unit.ty):
                    continue
                sx = int(unit.x) - int(cam_x)
                sy = int(unit.y) - int(cam_y) - TILE_SIZE // 2 - 6
                self._draw_hp_bar(sx - 12, sy, 24, 4, unit.hp, unit.max_hp)

            for bld in player.buildings:
                if not bld.alive or not bld.is_constructed or bld.hp >= bld.max_hp:
                    continue
                if not any(game.game_map.is_visible(ftx, fty)
                           for ftx, fty in bld.tile_footprint()):
                    continue
                sx = bld._tx * TILE_SIZE - int(cam_x)
                sy = bld._ty * TILE_SIZE - int(cam_y) - 8
                pw = bld.w_tiles * TILE_SIZE
                self._draw_hp_bar(sx, sy, pw, 5, bld.hp, bld.max_hp)

    def _draw_hp_bar(self, x, y, w, h, hp, max_hp):
        ratio = hp / max_hp
        if ratio > 0.5:
            col = HP_GREEN
        elif ratio > 0.25:
            col = HP_YELLOW
        else:
            col = HP_RED
        pygame.draw.rect(self._scene, (40, 40, 40), (x, y, w, h))
        pygame.draw.rect(self._scene, col, (x, y, int(w * ratio), h))
        pygame.draw.rect(self._scene, (0, 0, 0), (x, y, w, h), 1)

    # ================================================================== FOG
    def _draw_fog(self, game):
        if not FOG_OF_WAR:
            return
        cam_x, cam_y = game.cam_x, game.cam_y
        start_tx = max(0, int(cam_x // TILE_SIZE))
        start_ty = max(0, int(cam_y // TILE_SIZE))
        sw_f, sh_f = self._scene.get_size()
        end_tx   = min(game.game_map.width, start_tx + sw_f // TILE_SIZE + 2)
        end_ty   = min(game.game_map.height, start_ty + sh_f // TILE_SIZE + 2)

        for tx in range(start_tx, end_tx):
            for ty in range(start_ty, end_ty):
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                if game.game_map.is_visible(tx, ty):
                    pass   # fully visible
                elif game.game_map.is_explored(tx, ty):
                    self._scene.blit(_DIM_SURF, (sx, sy))
                else:
                    self._scene.blit(_FOG_SURF, (sx, sy))

    # ============================================================ BUILD GHOST
    def _draw_build_ghost(self, game):
        if game.build_mode is None:
            return
        mx, my = display_mod.get_mouse_pos()
        if not (VIEWPORT_X <= mx < VIEWPORT_X + VIEWPORT_W and
                VIEWPORT_Y <= my < VIEWPORT_Y + VIEWPORT_H):
            return
        from constants import BUILDING_SIZES
        w, h = BUILDING_SIZES.get(game.build_mode, (2, 2))
        wx   = (mx - VIEWPORT_X) / game.zoom + game.cam_x
        wy   = (my - VIEWPORT_Y) / game.zoom + game.cam_y
        snap_tx = int(wx // TILE_SIZE)
        snap_ty = int(wy // TILE_SIZE)

        valid = game.can_place_building(game.build_mode, snap_tx, snap_ty)
        ghost = self.assets.get_ghost(game.build_mode, valid)
        if ghost:
            sx = snap_tx * TILE_SIZE - int(game.cam_x)
            sy = snap_ty * TILE_SIZE - int(game.cam_y)
            self._scene.blit(ghost, (sx, sy))
            # Outline
            col = (0, 220, 0) if valid else (220, 0, 0)
            pygame.draw.rect(self._scene, col,
                             (sx, sy, w * TILE_SIZE, h * TILE_SIZE), 2)

    # ============================================================= DRAG RECT
    def _draw_drag_rect(self, game):
        if game.drag_start is None:
            return
        mx, my = display_mod.get_mouse_pos()
        x0, y0 = game.drag_start
        if abs(mx - x0) < 4 and abs(my - y0) < 4:
            return
        # Convert game-space coords to scene-space
        z = game.zoom
        rx = int((min(x0, mx) - VIEWPORT_X) / z)
        ry = int((min(y0, my) - VIEWPORT_Y) / z)
        rw = max(1, int(abs(mx - x0) / z))
        rh = max(1, int(abs(my - y0) / z))
        pygame.draw.rect(self._scene, SEL_GREEN, (rx, ry, rw, rh), 1)
        drag_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
        drag_surf.fill((0, 255, 0, 25))
        self._scene.blit(drag_surf, (rx, ry))

    # ========================================================= NEUTRAL CAMPS
    def _draw_neutral_camps(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for camp in game.neutral_camps:
            cx, cy, captured = camp[0], camp[1], camp[2]
            sx = cx * TILE_SIZE - int(cam_x)
            sy = cy * TILE_SIZE - int(cam_y)
            sw, sh = self._scene.get_size()
            if sx < -50 or sx > sw + 50 or sy < -50 or sy > sh + 50:
                continue
            if not game.game_map.is_explored(cx, cy):
                continue

            # Draw camp marker (small flag/banner)
            if captured is not None:
                col = TEAM_COLORS.get(captured, (160, 160, 100))
            else:
                col = (160, 160, 100)  # neutral color

            # Flag pole
            pygame.draw.line(self._scene, (140, 140, 140),
                             (sx, sy + 10), (sx, sy - 14), 2)
            # Pennant
            pygame.draw.polygon(self._scene, col,
                                [(sx, sy - 14), (sx + 14, sy - 8), (sx, sy - 2)])
            # Camp circle indicator
            camp_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(camp_surf, (*col, 40), (20, 20), 20)
            pygame.draw.circle(camp_surf, (*col, 120), (20, 20), 20, 2)
            self._scene.blit(camp_surf, (sx - 20, sy - 20))

    # ========================================================= KING OF THE HILL
    def _draw_koth_zone(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        cx = game._koth_cx * TILE_SIZE + TILE_SIZE // 2 - int(cam_x)
        cy = game._koth_cy * TILE_SIZE + TILE_SIZE // 2 - int(cam_y)
        r = game._koth_radius * TILE_SIZE

        # Translucent circle
        size = r * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        # Determine color by controlling team
        best_team = None
        best_time = 0
        for t, secs in game._koth_control.items():
            if secs > best_time:
                best_time = secs
                best_team = t
        col = TEAM_COLORS.get(best_team, (200, 200, 100)) if best_team is not None else (200, 200, 100)
        pygame.draw.circle(surf, (*col, 30), (size // 2, size // 2), r)
        pygame.draw.circle(surf, (*col, 140), (size // 2, size // 2), r, 2)
        self._scene.blit(surf, (cx - size // 2, cy - size // 2))

        # Progress text
        if best_team is not None and best_time > 0:
            pct = int(100 * best_time / game._koth_time_to_win)
            txt = self.font_sm.render(f"Hill: {pct}%", True, col)
            self._scene.blit(txt, (cx - txt.get_width() // 2, cy - r - 16))

    # =========================================================== DEAD EFFECTS
    def _draw_dead_effects(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for de in game.dead_effects:
            is_unit = de[5]
            timer = de[4]
            if is_unit:
                x, y, utype, team = de[0], de[1], de[2], de[3]
                max_t = 2.0
                alpha = int(255 * (timer / max_t))
                surf = self.assets.get_dead_unit(utype, team)
                if surf:
                    sx = int(x) - int(cam_x) - TILE_SIZE // 2
                    sy = int(y) - int(cam_y) - TILE_SIZE // 2
                    sw, sh = self._scene.get_size()
                    if sx + TILE_SIZE < 0 or sx > sw or sy + TILE_SIZE < 0 or sy > sh:
                        continue
                    copy = surf.copy()
                    copy.set_alpha(alpha)
                    self._scene.blit(copy, (sx, sy))
            else:
                # Destroyed building rubble
                x, y, btype, team = de[0], de[1], de[2], de[3]
                btx, bty = de[6], de[7]
                w_tiles, h_tiles = de[8], de[9]
                max_t = 4.0
                alpha = int(255 * (timer / max_t))
                rubble = self.assets.get_rubble(btype)
                if rubble:
                    sx = btx * TILE_SIZE - int(cam_x)
                    sy = bty * TILE_SIZE - int(cam_y)
                    copy = rubble.copy()
                    copy.set_alpha(alpha)
                    self._scene.blit(copy, (sx, sy))

    # =========================================================== PARTICLES
    def _draw_particles(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        for p in getattr(game, 'particles', []):
            sx = int(p[0]) - int(cam_x)
            sy = int(p[1]) - int(cam_y)
            alpha = int(255 * (p[4] / p[5]))
            col = (*p[2][:3], alpha) if len(p[2]) >= 3 else (255, 255, 255, alpha)
            size = max(1, int(p[3] * (p[4] / p[5])))
            ps = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, col, (size, size), size)
            self._scene.blit(ps, (sx - size, sy - size))

    # ======================================================= ATTACK VIGNETTE
    def _draw_attack_vignette(self, game):
        """Flash red border on screen when the player's team is attacked."""
        player_team = game._my_team
        player_events = [ev for ev in game.attack_events if ev[2] == player_team]
        if not player_events:
            return
        # Use the brightest (most recent) event for alpha
        max_t = max(ev[3] for ev in player_events)
        alpha = int(min(180, max_t / 1.5 * 180))
        thickness = 18
        vignette = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        # Four edge bars
        for rect in [
            (0, 0, SCREEN_W, thickness),
            (0, SCREEN_H - thickness, SCREEN_W, thickness),
            (0, 0, thickness, SCREEN_H),
            (SCREEN_W - thickness, 0, thickness, SCREEN_H),
        ]:
            pygame.draw.rect(vignette, (220, 30, 30, alpha), rect)
        self.screen.blit(vignette, (0, 0))

    # ============================================================ MINIMAP
    def draw_minimap(self, screen, game, mm_rect):
        """Draw minimap into mm_rect on screen."""
        mw, mh = game.game_map.width, game.game_map.height
        mm_surf = pygame.Surface((mw, mh))

        # Tiles
        for tx in range(mw):
            for ty in range(mh):
                if not game.game_map.is_explored(tx, ty):
                    col = (5, 5, 5)
                else:
                    t = game.game_map.tiles[tx][ty]
                    if t == TILE_GRASS:   col = (60, 110, 42)
                    elif t == TILE_WATER: col = (35, 75, 140)
                    elif t == TILE_FOREST:col = (25, 70, 18)
                    elif t == TILE_GOLD:  col = (160, 130, 20)
                    elif t == TILE_ROCK:  col = (90, 90, 95)
                    else:                 col = (100, 80, 55)
                mm_surf.set_at((tx, ty), col)

        # Buildings
        for team_id, player in game.players.items():
            tc = TEAM_COLORS.get(team_id, (100, 100, 100))
            for bld in player.buildings:
                if not bld.alive:
                    continue
                if any(game.game_map.is_explored(ftx, fty)
                       for ftx, fty in bld.tile_footprint()):
                    for ftx, fty in bld.tile_footprint():
                        if 0 <= ftx < mw and 0 <= fty < mh:
                            mm_surf.set_at((ftx, fty), tc)

        # Units
        for team_id, player in game.players.items():
            tc = TEAM_COLORS.get(team_id, (100, 100, 100))
            for unit in player.units:
                if unit.alive and game.game_map.is_visible(unit.tx, unit.ty):
                    ux, uy = unit.tx, unit.ty
                    if 0 <= ux < mw and 0 <= uy < mh:
                        mm_surf.set_at((ux, uy), tc)

        # Attack event dots (shown before scaling so they're sharp)
        for ev in game.attack_events:
            wx, wy, _team, timer = ev
            dot_tx = int(wx // TILE_SIZE)
            dot_ty = int(wy // TILE_SIZE)
            if 0 <= dot_tx < mw and 0 <= dot_ty < mh:
                mm_surf.set_at((dot_tx, dot_ty), (255, 60, 60))
                for ndx, ndy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx2, ny2 = dot_tx + ndx, dot_ty + ndy
                    if 0 <= nx2 < mw and 0 <= ny2 < mh:
                        mm_surf.set_at((nx2, ny2), (220, 40, 40))

        # Neutral camp markers
        for camp in game.neutral_camps:
            cx, cy, captured = camp[0], camp[1], camp[2]
            if game.game_map.is_explored(cx, cy):
                cc = TEAM_COLORS.get(captured, (160, 160, 100)) if captured is not None else (160, 160, 100)
                for ndx in range(-1, 2):
                    for ndy in range(-1, 2):
                        nx2, ny2 = cx + ndx, cy + ndy
                        if 0 <= nx2 < mw and 0 <= ny2 < mh:
                            mm_surf.set_at((nx2, ny2), cc)

        # Scale to mm_rect
        scaled = pygame.transform.scale(mm_surf, (mm_rect.width, mm_rect.height))
        screen.blit(scaled, mm_rect.topleft)

        # Viewport box (zoom-aware: more tiles visible when zoomed out)
        z = max(0.1, game.zoom)
        vx = int((game.cam_x / TILE_SIZE) / mw * mm_rect.width)
        vy = int((game.cam_y / TILE_SIZE) / mh * mm_rect.height)
        vw = int((VIEWPORT_W / z / TILE_SIZE) / mw * mm_rect.width)
        vh = int((VIEWPORT_H / z / TILE_SIZE) / mh * mm_rect.height)
        pygame.draw.rect(screen, (255, 255, 255),
                         (mm_rect.x + vx, mm_rect.y + vy, vw, vh), 1)

        # Border
        pygame.draw.rect(screen, PANEL_BORD, mm_rect, 2)
