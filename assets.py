import pygame
import math
import random
from constants import (TILE_SIZE, TILE_GRASS, TILE_WATER, TILE_FOREST,
                       TILE_GOLD, TILE_ROCK, TILE_DIRT, TEAM_COLORS,
                       BUILDING_SIZES)


class Assets:
    def __init__(self):
        self.tiles       = {}
        self.units       = {}
        self.buildings   = {}
        self.projectiles = {}
        self.ui_icons    = {}
        self._font_small = pygame.font.SysFont("Arial", 11, bold=True)
        self._font_med   = pygame.font.SysFont("Arial", 13, bold=True)
        self._make_tiles()
        self._make_units()
        self._make_buildings()
        self._make_projectiles()
        self._make_ui_icons()

    # ------------------------------------------------------------------ tiles
    def _make_tiles(self):
        ts = TILE_SIZE

        # --- Grass ---
        s = pygame.Surface((ts, ts))
        s.fill((78, 128, 52))
        rng = random.Random(1)
        for _ in range(25):
            x, y = rng.randint(0, ts - 1), rng.randint(0, ts - 1)
            c = (rng.randint(60, 100), rng.randint(110, 155), rng.randint(40, 65))
            pygame.draw.circle(s, c, (x, y), rng.randint(1, 2))
        self.tiles[TILE_GRASS] = s

        # --- Water ---
        s = pygame.Surface((ts, ts))
        s.fill((42, 90, 155))
        for i in range(0, ts, 6):
            pygame.draw.line(s, (55, 108, 175), (0, i), (ts, (i + 3) % ts), 1)
        self.tiles[TILE_WATER] = s

        # --- Forest ---
        s = pygame.Surface((ts, ts))
        s.fill((45, 95, 35))
        pygame.draw.circle(s, (25, 72, 15), (ts // 2, ts // 2 + 2), 13)
        pygame.draw.circle(s, (35, 88, 22), (ts // 2, ts // 2 - 2), 11)
        pygame.draw.circle(s, (50, 108, 30), (ts // 2 + 1, ts // 2 - 5), 8)
        pygame.draw.rect(s, (90, 58, 22), (ts // 2 - 3, ts // 2 + 5, 6, 8))
        self.tiles[TILE_FOREST] = s

        # --- Gold Mine ---
        s = pygame.Surface((ts, ts))
        s.fill((78, 78, 85))
        pygame.draw.ellipse(s, (95, 95, 102), (2, 7, ts - 4, ts - 12))
        rng2 = random.Random(7)
        for _ in range(6):
            x, y = rng2.randint(4, ts - 8), rng2.randint(9, ts - 8)
            pygame.draw.ellipse(s, (225, 185, 30), (x, y, rng2.randint(4, 7), 3))
        self.tiles[TILE_GOLD] = s

        # --- Rock ---
        s = pygame.Surface((ts, ts))
        s.fill((78, 128, 52))
        pygame.draw.ellipse(s, (110, 110, 118), (3, 7, ts - 6, ts - 10))
        pygame.draw.ellipse(s, (140, 140, 148), (6, 10, ts - 12, ts - 16))
        pygame.draw.line(s, (85, 85, 92), (8, 14), (ts - 8, 18), 1)
        self.tiles[TILE_ROCK] = s

        # --- Dirt ---
        s = pygame.Surface((ts, ts))
        s.fill((130, 100, 68))
        self.tiles[TILE_DIRT] = s

    # ------------------------------------------------------------------ units
    def _draw_goat(self, surf, body_col, team_col, variant):
        ts = TILE_SIZE
        cx, cy = ts // 2, ts // 2 + 2

        shade = tuple(max(0, c - 35) for c in body_col)

        # body
        pygame.draw.ellipse(surf, body_col, (cx - 11, cy - 4, 22, 13))
        # head
        pygame.draw.circle(surf, body_col, (cx + 8, cy - 6), 8)
        # ears
        pygame.draw.ellipse(surf, body_col, (cx + 5, cy - 14, 4, 5))
        pygame.draw.ellipse(surf, body_col, (cx + 11, cy - 14, 4, 5))
        # horns
        horn = (200, 188, 140)
        pygame.draw.line(surf, horn, (cx + 6, cy - 13), (cx + 4, cy - 18), 2)
        pygame.draw.line(surf, horn, (cx + 12, cy - 13), (cx + 15, cy - 17), 2)
        # eye
        pygame.draw.circle(surf, (15, 10, 5), (cx + 12, cy - 7), 2)
        pygame.draw.circle(surf, (255, 255, 200), (cx + 13, cy - 8), 1)
        # snout
        pygame.draw.ellipse(surf, shade, (cx + 13, cy - 4, 6, 4))
        # legs
        for lx in [cx - 8, cx - 3, cx + 2, cx + 7]:
            pygame.draw.rect(surf, shade, (lx, cy + 8, 3, 7))
        # tail
        pygame.draw.circle(surf, (235, 235, 235), (cx - 12, cy - 1), 4)
        # team scarf
        pygame.draw.rect(surf, team_col, (cx + 2, cy - 10, 8, 3))

        if variant == 'worker':
            pygame.draw.line(surf, (140, 90, 30), (cx - 14, cy + 1), (cx - 9, cy - 5), 2)
            pygame.draw.line(surf, (190, 170, 50), (cx - 9, cy - 5), (cx - 6, cy - 7), 2)
        elif variant == 'soldier':
            pygame.draw.ellipse(surf, (110, 110, 135), (cx + 3, cy - 14, 12, 8))
            pygame.draw.rect(surf, (70, 70, 120), (cx - 16, cy - 4, 5, 9))
        elif variant == 'archer':
            pygame.draw.rect(surf, (120, 78, 28), (cx - 15, cy - 6, 4, 11))
            pygame.draw.arc(surf, (120, 78, 28),
                            pygame.Rect(cx - 17, cy - 9, 9, 15), 0.4, 2.6, 2)
        elif variant == 'knight':
            pygame.draw.ellipse(surf, (95, 95, 125), (cx - 13, cy - 5, 26, 15))
            pygame.draw.ellipse(surf, (115, 115, 145), (cx + 2, cy - 15, 14, 10))

    def _make_units(self):
        ts = TILE_SIZE
        colors = {
            'worker':  (210, 200, 175),
            'soldier': (175, 175, 195),
            'archer':  (185, 155, 110),
            'knight':  (155, 155, 180),
        }
        for utype, col in colors.items():
            for team in [0, 1]:
                s = pygame.Surface((ts, ts), pygame.SRCALPHA)
                self._draw_goat(s, col, TEAM_COLORS[team], utype)
                self.units[f'{utype}_{team}'] = s

    # -------------------------------------------------------------- buildings
    def _draw_building(self, btype, w_tiles, h_tiles, team):
        pw = w_tiles * TILE_SIZE
        ph = h_tiles * TILE_SIZE
        s  = pygame.Surface((pw, ph), pygame.SRCALPHA)
        tc = TEAM_COLORS[team]

        if btype == 'town_hall':
            pygame.draw.rect(s, (95, 92, 105), (4, ph // 3, pw - 8, ph - ph // 3 - 4))
            pygame.draw.polygon(s, (72, 68, 80),
                                [(0, ph // 3 + 2), (pw // 2, 6), (pw, ph // 3 + 2)])
            for wx in [20, pw - 32]:
                pygame.draw.rect(s, (160, 195, 215), (wx, ph // 3 + 10, 12, 18))
            door_x = pw // 2 - 8
            pygame.draw.rect(s, (55, 38, 18), (door_x, ph - 28, 16, 24))
            pygame.draw.rect(s, tc, (4, ph // 3, pw - 8, 5))
            # flag pole + pennant
            pygame.draw.line(s, (180, 180, 180), (pw // 2, 6), (pw // 2, -14), 2)
            pygame.draw.polygon(s, tc, [(pw // 2, -14), (pw // 2 + 16, -8), (pw // 2, -2)])

        elif btype == 'farm':
            pygame.draw.rect(s, (125, 98, 60), (0, 0, pw, ph))
            for row in range(4):
                for col in range(pw // 8):
                    pygame.draw.rect(s, (65, 138, 48),
                                     (col * 8 + 2, row * (ph // 4) + 4, 5, ph // 4 - 6))
            pygame.draw.rect(s, (155, 65, 35), (4, 4, 30, 36))
            pygame.draw.polygon(s, (110, 44, 22), [(4, 5), (19, -4), (34, 5)])
            pygame.draw.rect(s, (70, 35, 15), (11, 22, 12, 18))
            pygame.draw.rect(s, tc, (4, 4, 30, 4))

        elif btype == 'lumber_mill':
            pygame.draw.rect(s, (112, 72, 32), (3, ph // 3, pw - 6, ph - ph // 3 - 3))
            pygame.draw.polygon(s, (82, 52, 18),
                                [(0, ph // 3 + 2), (pw // 2, 4), (pw, ph // 3 + 2)])
            # saw blade
            bx, by = pw - 18, ph // 2 + 4
            pygame.draw.circle(s, (185, 185, 185), (bx, by), 12)
            pygame.draw.circle(s, (155, 155, 155), (bx, by), 8)
            for i in range(8):
                a = i * math.pi / 4
                pygame.draw.line(s, (185, 185, 185),
                                 (bx, by), (int(bx + 12 * math.cos(a)), int(by + 12 * math.sin(a))), 2)
            pygame.draw.rect(s, tc, (3, ph // 3, pw - 6, 4))

        elif btype == 'mine':
            # Stone building with mine shaft entrance
            pygame.draw.rect(s, (88, 84, 95), (3, ph // 3, pw - 6, ph - ph // 3 - 3))
            pygame.draw.polygon(s, (65, 62, 72),
                                [(0, ph // 3 + 2), (pw // 2, 4), (pw, ph // 3 + 2)])
            # shaft entrance arch
            ex, ey = pw // 2 - 8, ph // 2
            pygame.draw.rect(s, (22, 18, 12), (ex, ey, 16, ph - ey - 2))
            pygame.draw.ellipse(s, (22, 18, 12), (ex, ey - 8, 16, 16))
            # timber supports
            pygame.draw.line(s, (100, 65, 22), (ex, ey), (ex, ey + 14), 2)
            pygame.draw.line(s, (100, 65, 22), (ex + 16, ey), (ex + 16, ey + 14), 2)
            pygame.draw.line(s, (100, 65, 22), (ex, ey), (ex + 16, ey), 2)
            # gold nugget glint
            pygame.draw.ellipse(s, (220, 185, 30), (pw // 2 - 14, ph // 2 - 6, 6, 4))
            pygame.draw.ellipse(s, (220, 185, 30), (pw // 2 - 5,  ph // 2 - 10, 5, 3))
            pygame.draw.rect(s, tc, (3, ph // 3, pw - 6, 4))

        elif btype == 'barracks':
            pygame.draw.rect(s, (82, 82, 95), (2, ph // 3, pw - 4, ph - ph // 3 - 3))
            pygame.draw.polygon(s, (60, 60, 72),
                                [(0, ph // 3 + 2), (pw // 2, 4), (pw, ph // 3 + 2)])
            for fx in [10, pw - 20]:
                pygame.draw.line(s, (160, 160, 165), (fx, 4), (fx, ph // 3), 2)
                pygame.draw.polygon(s, tc, [(fx, 4), (fx + 14, 8), (fx, 12)])
            pygame.draw.rect(s, (50, 33, 14), (pw // 2 - 9, ph - 30, 18, 26))
            pygame.draw.rect(s, tc, (2, ph // 3, pw - 4, 4))

        elif btype == 'archery_range':
            pygame.draw.rect(s, (92, 72, 42), (2, ph // 3, pw - 4, ph - ph // 3 - 3))
            pygame.draw.polygon(s, (68, 50, 25),
                                [(0, ph // 3 + 2), (pw // 2, 4), (pw, ph // 3 + 2)])
            # target
            tx2, ty2 = pw - 22, ph // 2 + 6
            for r, col in [(11, (195, 45, 45)), (8, (255, 255, 255)), (4, (195, 45, 45))]:
                pygame.draw.circle(s, col, (tx2, ty2), r)
            pygame.draw.line(s, (90, 55, 15), (pw - 44, ty2), (pw - 10, ty2), 2)
            pygame.draw.polygon(s, (90, 55, 15),
                                [(pw - 10, ty2), (pw - 16, ty2 - 4), (pw - 16, ty2 + 4)])
            pygame.draw.rect(s, tc, (2, ph // 3, pw - 4, 4))

        elif btype == 'academy':
            pygame.draw.rect(s, (105, 95, 72), (4, ph // 3, pw - 8, ph - ph // 3 - 3))
            pygame.draw.polygon(s, (78, 70, 50),
                                [(0, ph // 3 + 2), (pw // 2, 5), (pw, ph // 3 + 2)])
            for col_x in [12, pw // 2 - 4, pw - 16]:
                pygame.draw.rect(s, (145, 132, 108), (col_x, ph // 3, 8, ph - ph // 3 - 3))
            # arcane star
            scx, scy = pw // 2, ph // 2 + 8
            pygame.draw.circle(s, (168, 135, 215), (scx, scy), 10, 1)
            for i in range(6):
                a = i * math.pi / 3
                pygame.draw.line(s, (168, 135, 215),
                                 (scx, scy), (int(scx + 10 * math.cos(a)), int(scy + 10 * math.sin(a))), 1)
            pygame.draw.rect(s, tc, (4, ph // 3, pw - 8, 4))

        elif btype == 'tower':
            pygame.draw.rect(s, (98, 95, 108), (4, 0, pw - 8, ph))
            for i in range(3):
                pygame.draw.rect(s, (118, 115, 128), (4 + i * 9, 0, 7, 8))
            pygame.draw.rect(s, (38, 35, 45), (pw // 2 - 4, 12, 8, 14))
            pygame.draw.line(s, (175, 175, 178), (pw // 2, 0), (pw // 2, -12), 2)
            pygame.draw.polygon(s, tc, [(pw // 2, -12), (pw // 2 + 14, -6), (pw // 2, 0)])

        elif btype == 'wall':
            # Horizontal wall (default)
            pygame.draw.rect(s, (105, 105, 115), (1, ph // 3, pw - 2, ph - ph // 3 - 1))
            pygame.draw.rect(s, (85, 85, 95), (0, ph // 3, pw, 4))
            pygame.draw.rect(s, tc, (1, ph // 3, pw - 2, 3))

        elif btype == 'wall_v':
            # Vertical wall variant
            pygame.draw.rect(s, (105, 105, 115), (pw // 3, 1, pw - pw // 3 - 1, ph - 2))
            pygame.draw.rect(s, (85, 85, 95), (pw // 3, 0, 4, ph))
            pygame.draw.rect(s, tc, (pw // 3, 1, 3, ph - 2))

        elif btype == 'gate':
            # Stone pillars on each side
            pillar_col = (100, 95, 108)
            bar_col    = (70, 52, 28)
            pygame.draw.rect(s, pillar_col, (0, 0, 7, ph))
            pygame.draw.rect(s, pillar_col, (pw - 7, 0, 7, ph))
            # Horizontal wooden bars
            for by2 in range(3, ph - 1, 7):
                pygame.draw.rect(s, bar_col, (7, by2, pw - 14, 4))
            # Team-colour cap on each pillar
            pygame.draw.rect(s, tc, (0, 0, 7, 4))
            pygame.draw.rect(s, tc, (pw - 7, 0, 7, 4))

        return s

    _BUILDING_SIZE_OVERRIDES = {'wall_v': (1, 1)}

    def _make_buildings(self):
        btypes = list(BUILDING_SIZES.keys()) + ['wall_v']
        for btype in btypes:
            w, h = self._BUILDING_SIZE_OVERRIDES.get(btype, BUILDING_SIZES.get(btype, (2, 2)))
            for team in [0, 1]:
                self.buildings[f'{btype}_{team}'] = self._draw_building(btype, w, h, team)

            # Ghost (build preview) - valid
            ghost = self._draw_building(btype, w, h, 0).copy()
            ghost.set_alpha(160)
            self.buildings[f'{btype}_ghost_ok'] = ghost

            # Ghost - invalid (red tint)
            ghost_bad = ghost.copy()
            red_overlay = pygame.Surface(ghost_bad.get_size(), pygame.SRCALPHA)
            red_overlay.fill((180, 0, 0, 80))
            ghost_bad.blit(red_overlay, (0, 0))
            self.buildings[f'{btype}_ghost_bad'] = ghost_bad

            # Construction site
            pw, ph = w * TILE_SIZE, h * TILE_SIZE
            con = pygame.Surface((pw, ph), pygame.SRCALPHA)
            pygame.draw.rect(con, (120, 95, 60), (0, 0, pw, ph))
            for i in range(0, pw, 14):
                pygame.draw.line(con, (90, 55, 18), (i, 0), (i, ph), 1)
            for j in range(0, ph, 14):
                pygame.draw.line(con, (90, 55, 18), (0, j), (pw, j), 1)
            pygame.draw.rect(con, (90, 55, 18), (0, 0, pw, ph), 2)
            self.buildings[f'{btype}_construction'] = con

    # ------------------------------------------------------------ projectiles
    def _make_projectiles(self):
        s = pygame.Surface((14, 4), pygame.SRCALPHA)
        pygame.draw.line(s, (95, 58, 18), (0, 2), (10, 2), 2)
        pygame.draw.polygon(s, (95, 58, 18), [(10, 0), (14, 2), (10, 4)])
        self.projectiles['arrow'] = s

    # --------------------------------------------------------------- ui icons
    def _make_ui_icons(self):
        """Small 44x44 icons for the command panel buttons."""
        size = 44

        def base(color=(55, 55, 68)):
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(s, color, (0, 0, size, size), border_radius=4)
            pygame.draw.rect(s, (80, 80, 95), (0, 0, size, size), 2, border_radius=4)
            return s

        def label(s, text, color=(230, 230, 230)):
            surf = self._font_small.render(text, True, color)
            s.blit(surf, (size // 2 - surf.get_width() // 2,
                          size // 2 - surf.get_height() // 2))

        for btype in BUILDING_SIZES:
            s = base()
            w, h = BUILDING_SIZES[btype]
            small = self._draw_building(btype, w, h, 0)
            scaled = pygame.transform.smoothscale(small, (size - 8, size - 8))
            s.blit(scaled, (4, 4))
            self.ui_icons[f'build_{btype}'] = s

        for utype in ['worker', 'soldier', 'archer', 'knight']:
            s = base()
            unit_surf = self.units.get(f'{utype}_0')
            if unit_surf:
                scaled = pygame.transform.smoothscale(unit_surf, (size - 6, size - 6))
                s.blit(scaled, (3, 3))
            self.ui_icons[f'train_{utype}'] = s

        for tech in ['improved_gathering', 'iron_weapons', 'leather_armor',
                     'steel_armor', 'ballistics', 'unlock_knight']:
            s = base((40, 38, 58))
            short = {
                'improved_gathering': 'GathR',
                'iron_weapons':       'IronW',
                'leather_armor':      'LeathA',
                'steel_armor':        'SteelA',
                'ballistics':         'Ballis',
                'unlock_knight':      'Knight',
            }[tech]
            label(s, short, (200, 180, 240))
            self.ui_icons[f'tech_{tech}'] = s

        for cmd_name, text, col in [
            ('stop', 'S', (220, 60, 60)),
            ('hold', 'H', (60, 120, 220)),
            ('attack_move', 'A', (220, 180, 50)),
        ]:
            s = base()
            surf = self._font_med.render(text, True, col)
            s.blit(surf, (size // 2 - surf.get_width() // 2,
                          size // 2 - surf.get_height() // 2))
            self.ui_icons[f'cmd_{cmd_name}'] = s

    # ---------------------------------------------------------------- getters
    def get_tile(self, tile_type):
        return self.tiles.get(tile_type, self.tiles[TILE_GRASS])

    def get_unit(self, utype, team):
        return self.units.get(f'{utype}_{team}')

    def get_building(self, btype, team, construction=False):
        if construction:
            return self.buildings.get(f'{btype}_construction')
        return self.buildings.get(f'{btype}_{team}')

    def get_ghost(self, btype, valid):
        suffix = 'ok' if valid else 'bad'
        return self.buildings.get(f'{btype}_ghost_{suffix}')

    def get_icon(self, key):
        return self.ui_icons.get(key)
