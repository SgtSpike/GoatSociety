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

        # Minimap surface (1 px per tile)
        self.mm_surf = pygame.Surface((MAP_W, MAP_H))

        self._mm_dirty = True   # rebuild minimap next frame

    # ================================================================ PUBLIC
    def draw(self, game, ui):
        self.vp_surf.fill((20, 20, 20))

        self._draw_tiles(game)
        self._draw_resources(game)
        self._draw_buildings(game)
        self._draw_units(game)
        self._draw_projectiles(game)
        self._draw_selection_indicators(game)
        self._draw_health_bars(game)
        self._draw_fog(game)
        self._draw_build_ghost(game)
        self._draw_drag_rect(game)

        self.screen.blit(self.vp_surf, (VIEWPORT_X, VIEWPORT_Y))

        ui.draw(self.screen, game, self)

    # ================================================================ TILES
    def _draw_tiles(self, game):
        cam_x, cam_y = game.cam_x, game.cam_y
        start_tx = max(0, int(cam_x // TILE_SIZE))
        start_ty = max(0, int(cam_y // TILE_SIZE))
        end_tx   = min(MAP_W, start_tx + VIEWPORT_W // TILE_SIZE + 2)
        end_ty   = min(MAP_H, start_ty + VIEWPORT_H // TILE_SIZE + 2)

        for tx in range(start_tx, end_tx):
            for ty in range(start_ty, end_ty):
                if not game.game_map.is_explored(tx, ty):
                    continue  # will be covered by fog later
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                tile_surf = self.assets.get_tile(game.game_map.tiles[tx][ty])
                self.vp_surf.blit(tile_surf, (sx, sy))

    # ============================================================== RESOURCES
    def _draw_resources(self, game):
        # Resources are embedded in tile graphics; depletion shown as dirt
        cam_x, cam_y = game.cam_x, game.cam_y
        for (tx, ty), node in game.game_map.resources.items():
            if not game.game_map.is_visible(tx, ty):
                continue
            if node.depleted:
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                if -TILE_SIZE < sx < VIEWPORT_W and -TILE_SIZE < sy < VIEWPORT_H:
                    self.vp_surf.blit(self.assets.get_tile(TILE_DIRT), (sx, sy))
            elif node.type == 'wood' and node.amount < node.max_amount * 0.5:
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                if -TILE_SIZE < sx < VIEWPORT_W and -TILE_SIZE < sy < VIEWPORT_H:
                    # Draw depleted forest (dimmer)
                    ts = self.assets.get_tile(TILE_FOREST).copy()
                    ts.set_alpha(180)
                    self.vp_surf.blit(ts, (sx, sy))

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

                if sx + pw < 0 or sx > VIEWPORT_W or sy + ph < 0 or sy > VIEWPORT_H:
                    continue

                if bld.is_constructed:
                    surf = self.assets.get_building(bld.btype, bld.team)
                else:
                    surf = self.assets.get_building(bld.btype, bld.team, construction=True)
                    # Construction progress bar on top
                    if surf:
                        self.vp_surf.blit(surf, (sx, sy))
                    self._draw_construction_bar(bld, sx, sy, pw)
                    if bld.selected:
                        self._draw_selection_rect(sx, sy, pw, ph)
                    continue

                if surf:
                    if not visible:
                        dim = surf.copy()
                        dim.set_alpha(100)
                        self.vp_surf.blit(dim, (sx, sy))
                    else:
                        self.vp_surf.blit(surf, (sx, sy))

                if bld.selected:
                    self._draw_selection_rect(sx, sy, pw, ph)

                # Rally point flag
                if bld.selected and bld.rally_point:
                    rpx = int(bld.rally_point[0]) - int(cam_x)
                    rpy = int(bld.rally_point[1]) - int(cam_y)
                    pygame.draw.line(self.vp_surf, (255, 255, 0),
                                     (sx + pw // 2, sy + ph // 2), (rpx, rpy), 1)
                    pygame.draw.circle(self.vp_surf, (255, 255, 0), (rpx, rpy), 4, 1)

    def _draw_construction_bar(self, bld, sx, sy, pw):
        bh = 6
        by = sy - 10
        pygame.draw.rect(self.vp_surf, (60, 60, 60), (sx, by, pw, bh))
        filled = int(pw * bld.construction_progress)
        pygame.draw.rect(self.vp_surf, (255, 180, 0), (sx, by, filled, bh))
        pygame.draw.rect(self.vp_surf, (100, 100, 100), (sx, by, pw, bh), 1)

    def _draw_selection_rect(self, sx, sy, pw, ph):
        pygame.draw.rect(self.vp_surf, SEL_GREEN, (sx - 1, sy - 1, pw + 2, ph + 2), 2)

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

                if sx + TILE_SIZE < 0 or sx > VIEWPORT_W or sy + TILE_SIZE < 0 or sy > VIEWPORT_H:
                    continue

                surf = self.assets.get_unit(unit.utype, unit.team)
                if surf:
                    if unit.flip_h:
                        surf = pygame.transform.flip(surf, True, False)

                    # Gathering / building bob animation
                    draw_sy = sy
                    if unit.utype == 'worker' and unit.state in ('gathering', 'building'):
                        draw_sy += -int(abs(math.sin(unit.anim_t * 5.5)) * 3)

                    self.vp_surf.blit(surf, (sx, draw_sy))

                    # Sparkle at the axe tip on the "down-stroke" peak
                    if unit.utype == 'worker' and unit.state == 'gathering':
                        phase = math.sin(unit.anim_t * 5.5)
                        if phase < -0.8:          # bottom of swing = impact
                            # axe tip offset from sprite top-left (matches _draw_goat)
                            flip = unit.flip_h
                            tip_x = sx + (TILE_SIZE - 8 if flip else 8)
                            tip_y = draw_sy + TILE_SIZE // 2 - 5
                            pygame.draw.circle(self.vp_surf, (255, 235, 100), (tip_x, tip_y), 3)
                            pygame.draw.circle(self.vp_surf, (255, 200,  40), (tip_x, tip_y), 1)
                            # two tiny chips offset from tip
                            for cx2, cy2 in [(tip_x - 4, tip_y - 3), (tip_x + 2, tip_y - 5)]:
                                pygame.draw.circle(self.vp_surf, (190, 140, 60), (cx2, cy2), 1)

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
                self.vp_surf.blit(rot, (sx - rot.get_width() // 2,
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
                pygame.draw.ellipse(self.vp_surf, SEL_GREEN,
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
        pygame.draw.rect(self.vp_surf, (40, 40, 40), (x, y, w, h))
        pygame.draw.rect(self.vp_surf, col, (x, y, int(w * ratio), h))
        pygame.draw.rect(self.vp_surf, (0, 0, 0), (x, y, w, h), 1)

    # ================================================================== FOG
    def _draw_fog(self, game):
        if not FOG_OF_WAR:
            return
        cam_x, cam_y = game.cam_x, game.cam_y
        start_tx = max(0, int(cam_x // TILE_SIZE))
        start_ty = max(0, int(cam_y // TILE_SIZE))
        end_tx   = min(MAP_W, start_tx + VIEWPORT_W // TILE_SIZE + 2)
        end_ty   = min(MAP_H, start_ty + VIEWPORT_H // TILE_SIZE + 2)

        for tx in range(start_tx, end_tx):
            for ty in range(start_ty, end_ty):
                sx = tx * TILE_SIZE - int(cam_x)
                sy = ty * TILE_SIZE - int(cam_y)
                if game.game_map.is_visible(tx, ty):
                    pass   # fully visible
                elif game.game_map.is_explored(tx, ty):
                    self.vp_surf.blit(_DIM_SURF, (sx, sy))
                else:
                    self.vp_surf.blit(_FOG_SURF, (sx, sy))

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
        wx   = (mx - VIEWPORT_X) + int(game.cam_x)
        wy   = (my - VIEWPORT_Y) + int(game.cam_y)
        snap_tx = int(wx // TILE_SIZE)
        snap_ty = int(wy // TILE_SIZE)

        valid = game.can_place_building(game.build_mode, snap_tx, snap_ty)
        ghost = self.assets.get_ghost(game.build_mode, valid)
        if ghost:
            sx = snap_tx * TILE_SIZE - int(game.cam_x)
            sy = snap_ty * TILE_SIZE - int(game.cam_y)
            self.vp_surf.blit(ghost, (sx, sy))
            # Outline
            col = (0, 220, 0) if valid else (220, 0, 0)
            pygame.draw.rect(self.vp_surf, col,
                             (sx, sy, w * TILE_SIZE, h * TILE_SIZE), 2)

    # ============================================================= DRAG RECT
    def _draw_drag_rect(self, game):
        if game.drag_start is None:
            return
        mx, my = display_mod.get_mouse_pos()
        x0, y0 = game.drag_start
        if abs(mx - x0) < 4 and abs(my - y0) < 4:
            return
        rx = min(x0, mx) - VIEWPORT_X
        ry = min(y0, my) - VIEWPORT_Y
        rw = abs(mx - x0)
        rh = abs(my - y0)
        pygame.draw.rect(self.vp_surf, SEL_GREEN, (rx, ry, rw, rh), 1)
        drag_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
        drag_surf.fill((0, 255, 0, 25))
        self.vp_surf.blit(drag_surf, (rx, ry))

    # ============================================================ MINIMAP
    def draw_minimap(self, screen, game, mm_rect):
        """Draw minimap into mm_rect on screen."""
        mm_surf = pygame.Surface((MAP_W, MAP_H))

        # Tiles
        for tx in range(MAP_W):
            for ty in range(MAP_H):
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
            tc = TEAM_COLORS[team_id]
            for bld in player.buildings:
                if not bld.alive:
                    continue
                if any(game.game_map.is_explored(ftx, fty)
                       for ftx, fty in bld.tile_footprint()):
                    for ftx, fty in bld.tile_footprint():
                        if 0 <= ftx < MAP_W and 0 <= fty < MAP_H:
                            mm_surf.set_at((ftx, fty), tc)

        # Units
        for team_id, player in game.players.items():
            tc = TEAM_COLORS[team_id]
            for unit in player.units:
                if unit.alive and game.game_map.is_visible(unit.tx, unit.ty):
                    ux, uy = unit.tx, unit.ty
                    if 0 <= ux < MAP_W and 0 <= uy < MAP_H:
                        mm_surf.set_at((ux, uy), tc)

        # Scale to mm_rect
        scaled = pygame.transform.scale(mm_surf, (mm_rect.width, mm_rect.height))
        screen.blit(scaled, mm_rect.topleft)

        # Viewport box
        vx = int((game.cam_x / TILE_SIZE) / MAP_W * mm_rect.width)
        vy = int((game.cam_y / TILE_SIZE) / MAP_H * mm_rect.height)
        vw = int((VIEWPORT_W / TILE_SIZE) / MAP_W * mm_rect.width)
        vh = int((VIEWPORT_H / TILE_SIZE) / MAP_H * mm_rect.height)
        pygame.draw.rect(screen, (255, 255, 255),
                         (mm_rect.x + vx, mm_rect.y + vy, vw, vh), 1)

        # Border
        pygame.draw.rect(screen, PANEL_BORD, mm_rect, 2)
