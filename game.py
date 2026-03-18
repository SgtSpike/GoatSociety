"""
Central game state.  Owns the map, players, entities, and processes input.
"""
import pygame
import math
import random
from collections import deque
from constants import (TILE_SIZE, MAP_W, MAP_H, SCREEN_W, SCREEN_H,
                       VIEWPORT_X, VIEWPORT_Y, VIEWPORT_W, VIEWPORT_H,
                       TOP_BAR_H, BOTTOM_PANEL_H,
                       PLAYER_TEAM, AI_TEAM, NEUTRAL_TEAM, TEAM_COLORS,
                       CAMERA_SPEED, EDGE_SCROLL_MARGIN,
                       BUILDING_SIZES, BUILDING_COSTS,
                       UNIT_STATS, UNIT_COSTS)
from map import GameMap
from entities import Entity, Player, Projectile
from units import Unit, State
from buildings import Building
from commands import Cmd, CmdData
from ai import AIController
from ui import UIAction
import display as display_mod
try:
    import sounds
except Exception:
    class sounds:  # type: ignore
        @staticmethod
        def play(*a, **kw): pass


class Game:
    def __init__(self, seed=None, config=None):
        # Reset entity ID counter so host and client produce matching IDs
        Entity._id_ctr = 0

        # Net mode: None | 'host' | 'client'
        self.net_mode     = None
        self.net_my_team  = PLAYER_TEAM   # 0 for host/singleplayer, 1 for client
        self._net_session = None

        # Game configuration
        self.config = config or {}
        self.num_players = self.config.get('num_players', 2)
        self.game_mode = self.config.get('game_mode', 'standard')
        self.ai_difficulty = self.config.get('ai_difficulty', 'normal')

        # Map size from config
        map_size = self.config.get('map_size', 'medium')
        if map_size == 'small':
            self._map_w, self._map_h = 80, 60
        elif map_size == 'large':
            self._map_w, self._map_h = 160, 120
        else:
            self._map_w, self._map_h = MAP_W, MAP_H

        self.seed  = seed or random.randint(0, 99999)
        # Compute start positions for map clearing
        mw, mh = self._map_w, self._map_h
        _all_positions = [
            (6, 6), (mw - 10, mh - 9), (mw - 10, 6),
            (6, mh - 9), (mw // 2, 6), (mw // 2, mh - 9),
        ]
        self.game_map = GameMap(seed=self.seed,
                                width=mw, height=mh,
                                start_positions=_all_positions[:self.num_players])

        # Create players: team 0 is human, teams 1+ are AI
        self.players = {PLAYER_TEAM: Player(PLAYER_TEAM)}
        for t in range(1, self.num_players):
            self.players[t] = Player(t)
        self.players[NEUTRAL_TEAM] = Player(NEUTRAL_TEAM)

        # Neutral camps: [(cx_tile, cy_tile, captured_by_team_or_None)]
        self.neutral_camps = []
        self._camp_income_timer = 0.0

        self.projectiles   = []
        self.dead_effects  = []   # [(x, y, utype/btype, team, timer, is_unit)]
        self.particles     = []   # [(x, y, color, size, life, max_life, vx, vy)]
        self.selection     = []
        self.drag_start    = None  # screen coords (x, y) or None
        self.build_mode    = None  # building type string or None
        self.time_elapsed  = 0.0
        self.game_over     = False
        self.player_won    = False

        # Camera (top-left world pixel)
        self.cam_x = 0.0
        self.cam_y = 0.0

        # Message overlays {text, timer}
        self._messages = []

        # Control groups  {1-9: [entity, ...]}
        self._ctrl_groups = {}

        # Create AI controllers for all AI teams
        self.ai_controllers = []
        for t in range(1, self.num_players):
            ai = AIController(t)
            # Apply difficulty settings
            if self.ai_difficulty == 'easy':
                ai.attack_interval = 120.0
                ai.attack_delay = 1.5
            elif self.ai_difficulty == 'hard':
                ai.attack_interval = 50.0
                ai.attack_delay = 0.7
                # Give hard AI a resource bonus
                self.players[t].wood += 100
                self.players[t].gold += 100
            self.ai_controllers.append(ai)

        # Tech bonuses per team
        self._tech_bonuses = {0: {}, 1: {}}

        # King of the Hill state
        self._koth_control = {}  # {team_id: seconds_held}
        self._koth_winner = None
        self._koth_time_to_win = 180.0  # 3 minutes of control to win
        self._koth_cx = self._map_w // 2  # hill center tile
        self._koth_cy = self._map_h // 2
        self._koth_radius = 6  # tiles

        # Survival state
        self._survival_wave = 0
        self._survival_timer = 0.0
        # Base interval between waves depends on difficulty
        if self.ai_difficulty == 'easy':
            self._survival_interval = 300.0    # 5 minutes
        elif self.ai_difficulty == 'hard':
            self._survival_interval = 180.0    # 3 minutes
        else:
            self._survival_interval = 240.0    # 4 minutes (normal)

        self._pending_attack_move = False
        self._pending_patrol = False
        self.selected_resource = None   # ResourceNode clicked for inspection
        self._active_cmd_team = None    # team context for message tagging

        # Attack flash events: [(wx, wy, team_attacked, timer)]
        self.attack_events = []

        # Viewport zoom (1.0 = normal, >1 = zoom in, <1 = zoom out)
        self.zoom = 1.0

        # ↑ ↑ ↓ ↓ ← → ← → — you know what to do
        self._konami_buf  = []
        self._goat_mode_t = 0.0   # seconds remaining of SUPREME GOAT MODE
        self._last_delete_t = -99.0  # double-delete confirmation timer
        self._last_click_t  = -99.0  # double-click detection timer
        self._last_click_pos = (0, 0)
        self._request_load  = False  # set True by F9 to signal main loop
        self.paused         = False  # toggled by Escape

        self._setup_start()

    # ----------------------------------------------------------------- property
    @property
    def _my_team(self):
        return self.net_my_team

    # ================================================================= SETUP
    def _setup_start(self):
        """Place starting units and buildings for all players."""
        mw = self._map_w
        mh = self._map_h
        # Start positions for up to 6 players (spread around map edges)
        positions = [
            (6, 6),                    # top-left (player)
            (mw - 10, mh - 9),         # bottom-right
            (mw - 10, 6),              # top-right
            (6, mh - 9),               # bottom-left
            (mw // 2, 6),              # top-center
            (mw // 2, mh - 9),         # bottom-center
        ]
        for team_id in range(self.num_players):
            if team_id < len(positions):
                tx, ty = positions[team_id]
                self._place_start(team_id, tx, ty)

        # Neutral camps (placed in mid-map areas)
        self._place_neutral_camps()

        # Center camera on player start
        p_tx, p_ty = positions[0]
        self.cam_x = p_tx * TILE_SIZE - VIEWPORT_W // 2
        self.cam_y = p_ty * TILE_SIZE - VIEWPORT_H // 2
        self._clamp_camera()

    def _place_start(self, team, tx, ty):
        # Town hall
        th = self.place_building('town_hall', tx, ty, team, instant=True)
        if th:
            th.rally_point = (
                (tx + 6) * TILE_SIZE,
                (ty + 4) * TILE_SIZE)

        # Three worker goats
        offset_positions = [(tx + 5, ty + 1), (tx + 5, ty + 2), (tx + 5, ty + 3)]
        for otx, oty in offset_positions:
            while not self.game_map.is_passable(otx, oty):
                otx += 1
            self.spawn_unit('worker',
                            otx * TILE_SIZE + TILE_SIZE // 2,
                            oty * TILE_SIZE + TILE_SIZE // 2,
                            team)

        # Kick off AI workers gathering
        if team != PLAYER_TEAM and team != NEUTRAL_TEAM:
            for u in self.players[team].units:
                node = self.game_map.find_nearest_resource(u.tx, u.ty, 'gold')
                if node is None:
                    node = self.game_map.find_nearest_resource(u.tx, u.ty, 'wood')
                if node:
                    u.give_command(CmdData(Cmd.GATHER, resource=node))

    def _place_neutral_camps(self):
        """Place 4 neutral camps in mid-map areas with 2-3 wild goat defenders."""
        rng = random.Random(self.seed + 777)
        mw, mh = self._map_w, self._map_h
        camp_positions = [
            (mw // 4, mh // 4),
            (mw * 3 // 4, mh // 4),
            (mw // 4, mh * 3 // 4),
            (mw * 3 // 4, mh * 3 // 4),
        ]
        for cx, cy in camp_positions:
            cx += rng.randint(-6, 6)
            cy += rng.randint(-6, 6)
            cx = max(10, min(mw - 10, cx))
            cy = max(10, min(mh - 10, cy))

            self.neutral_camps.append([cx, cy, None])  # None = uncaptured

            # Spawn 2-3 neutral soldier goats
            count = rng.randint(2, 3)
            for i in range(count):
                ox = cx + rng.randint(-2, 2)
                oy = cy + rng.randint(-2, 2)
                while not self.game_map.is_passable(ox, oy):
                    ox += 1
                    if ox >= self._map_w - 1:
                        ox = cx
                        break
                self.spawn_unit('soldier',
                                ox * TILE_SIZE + TILE_SIZE // 2,
                                oy * TILE_SIZE + TILE_SIZE // 2,
                                NEUTRAL_TEAM)

    def _update_neutral_camps(self, dt):
        """Check if camps are captured and provide passive income."""
        self._camp_income_timer += dt

        for camp in self.neutral_camps:
            cx, cy, captured = camp[0], camp[1], camp[2]

            if captured is not None:
                continue  # Already captured

            # Check if all neutral units near the camp are dead
            camp_wx = cx * TILE_SIZE + TILE_SIZE // 2
            camp_wy = cy * TILE_SIZE + TILE_SIZE // 2
            radius = 6 * TILE_SIZE
            alive_neutrals = [u for u in self.players[NEUTRAL_TEAM].units
                              if u.alive and
                              math.hypot(u.x - camp_wx, u.y - camp_wy) < radius]

            if not alive_neutrals:
                # Find which team has units closest to claim it
                best_team = None
                best_dist = float('inf')
                for team_id in range(self.num_players):
                    for u in self.players[team_id].units:
                        if u.alive:
                            d = math.hypot(u.x - camp_wx, u.y - camp_wy)
                            if d < radius and d < best_dist:
                                best_dist = d
                                best_team = team_id
                if best_team is not None:
                    camp[2] = best_team
                    if best_team == self._my_team:
                        self._add_message("Neutral camp captured! +5 gold/min")

        # Passive income every 12 seconds (= 5 gold/min)
        if self._camp_income_timer >= 12.0:
            self._camp_income_timer = 0.0
            for camp in self.neutral_camps:
                if camp[2] is not None:
                    self.players[camp[2]].gold += 5

    # ================================================================= UPDATE
    def update(self, dt):
        if self.game_over or self.paused:
            return
        self.time_elapsed += dt

        # Tick SUPREME GOAT MODE down and remove bonus when it expires
        if self._goat_mode_t > 0:
            self._goat_mode_t -= dt
            if self._goat_mode_t <= 0:
                for p in self.players.values():
                    for u in p.units:
                        u.speed_bonus = max(0, u.speed_bonus - 120)
                self._add_message("Goat mode over. They're tired now.", duration=3.0)

        # Update food for all players
        for player in self.players.values():
            player.update_food_cap()
            player.recompute_food()

        # Update map visibility (player team only)
        p = self.players[PLAYER_TEAM]
        self.game_map.update_visibility(p.units, p.buildings)

        # Update units
        for team_id, player in self.players.items():
            for unit in list(player.units):
                if unit.alive:
                    unit.update(dt, self)
            for unit in player.units:
                if not unit.alive:
                    self.dead_effects.append([unit.x, unit.y, unit.utype,
                                              unit.team, 2.0, True])
            player.units = [u for u in player.units if u.alive]

        # Update buildings
        for team_id, player in self.players.items():
            for bld in list(player.buildings):
                if bld.alive:
                    bld.update(dt, self)
            # Restore passability for any building that just died
            for bld in player.buildings:
                if not bld.alive and bld.is_constructed:
                    self.dead_effects.append([bld.x, bld.y, bld.btype,
                                              bld.team, 4.0, False,
                                              bld._tx, bld._ty,
                                              bld.w_tiles, bld.h_tiles])
                    if bld.btype == 'gate':
                        for ftx, fty in bld.tile_footprint():
                            self.game_map.gates.pop((ftx, fty), None)
                    else:
                        for ftx, fty in bld.tile_footprint():
                            self.game_map.set_passable(ftx, fty, True)
                            self.game_map.set_buildable(ftx, fty, True)
            player.buildings = [b for b in player.buildings if b.alive]

        # Update projectiles
        for proj in self.projectiles:
            proj.update(dt, self)
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Neutral camps
        self._update_neutral_camps(dt)

        # Game mode updates
        if self.game_mode == 'king_of_hill':
            self._update_koth(dt)
        elif self.game_mode == 'survival':
            self._update_survival(dt)

        # AI: run on host and singleplayer (human teams' controllers already removed)
        if self.net_mode != 'client':
            for ai in self.ai_controllers:
                ai.update(dt, self)

        # Clean selection
        self.selection = [e for e in self.selection if e.alive]

        # Win/lose check
        self._check_game_over()

        # Message timers (stored as (duration, text, team) — team=None shows to all)
        self._messages = [(t - dt, msg, tm) for (t, msg, tm) in self._messages if t > 0]

        # Update particles
        for p in self.particles:
            p[0] += p[6] * dt   # x += vx * dt
            p[1] += p[7] * dt   # y += vy * dt
            p[7] += 80 * dt     # gravity
            p[4] -= dt           # life -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

        # Dead entity fade effects
        for de in self.dead_effects:
            de[4] -= dt
        self.dead_effects = [de for de in self.dead_effects if de[4] > 0]

        # Attack flash events
        for ev in self.attack_events:
            ev[3] -= dt
        self.attack_events = [ev for ev in self.attack_events if ev[3] > 0]

    # ================================================================= INPUT
    def handle_event(self, event, ui):
        """Process a pygame event.  ui is the UI instance."""
        if self.game_over:
            return

        if event.type == pygame.KEYDOWN:
            self._on_keydown(event, ui)
            if self.paused:
                return  # only allow keyboard (for unpause) while paused

        if self.paused:
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            if event.button == 1:  # Left click
                if ui.is_over_ui(pos):
                    action = ui.handle_click(pos, self)
                    if action:
                        self._handle_ui_action(action)
                else:
                    self._on_left_down(pos)

            elif event.button == 3:  # Right click
                if not ui.is_over_ui(pos):
                    self._on_right_click(pos, pygame.key.get_mods())

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self._on_left_up(event.pos, ui)

        elif event.type == pygame.MOUSEMOTION:
            pass   # no per-frame mouse-move logic needed

    def update_camera(self, dt):
        keys = pygame.key.get_pressed()
        mx, my = display_mod.get_mouse_pos()
        spd = CAMERA_SPEED * dt
        m  = EDGE_SCROLL_MARGIN

        # Edge-scroll only while mouse is inside the viewport (not over UI panels).
        in_vp = TOP_BAR_H <= my < SCREEN_H - BOTTOM_PANEL_H
        if keys[pygame.K_LEFT]  or keys[pygame.K_a] or (in_vp and mx < m):
            self.cam_x -= spd
        if keys[pygame.K_RIGHT] or keys[pygame.K_d] or (in_vp and mx > SCREEN_W - m):
            self.cam_x += spd
        if keys[pygame.K_UP]    or keys[pygame.K_w] or (in_vp and my < TOP_BAR_H + m):
            self.cam_y -= spd
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]:
            self.cam_y += spd

        self._clamp_camera()

    def _clamp_camera(self):
        max_x = self._map_w * TILE_SIZE - VIEWPORT_W
        max_y = self._map_h * TILE_SIZE - VIEWPORT_H
        self.cam_x = max(0, min(max_x, self.cam_x))
        self.cam_y = max(0, min(max_y, self.cam_y))

    # ---------------------------------------------------------------- keyboard
    def _on_keydown(self, event, ui):
        k = event.key
        mod = event.mod

        if k == pygame.K_ESCAPE:
            if self.build_mode:
                self.build_mode = None
            elif self.selection:
                for e in self.selection:
                    e.selected = False
                self.selection = []
            else:
                self.paused = not self.paused
        elif k == pygame.K_DELETE:
            t = self.time_elapsed
            if t - self._last_delete_t < 0.5 and self.selection:
                # Second press: delete selected own-team entities
                unit_ids     = [e.id for e in self.selection
                                if isinstance(e, Unit) and e.team == self._my_team]
                building_ids = [e.id for e in self.selection
                                if isinstance(e, Building) and e.team == self._my_team]
                if self.net_mode == 'client':
                    self._net_session.send_command({
                        't': 'cmd', 'cmd_type': 'delete',
                        'team': self._my_team,
                        'unit_ids': unit_ids, 'building_ids': building_ids,
                    })
                else:
                    for ent in list(self.selection):
                        if ent.team == self._my_team:
                            ent.alive = False
                self.selection = []
                self._last_delete_t = -99.0
            elif self.selection:
                self._last_delete_t = t
                self._add_message("Press Delete again to delete selection", duration=2.0)
        elif k == pygame.K_x and not mod:
            self._cmd_selection(CmdData(Cmd.STOP))
        elif k == pygame.K_a and not mod:
            self._pending_attack_move = True
        elif k == pygame.K_p and not mod:
            self._pending_patrol = True
        elif k == pygame.K_b and not mod:
            pass   # build menu shown in UI automatically when worker selected
        elif k == pygame.K_SPACE:
            # Center on first selected unit
            if self.selection:
                e = self.selection[0]
                self.cam_x = e.x - VIEWPORT_W / 2
                self.cam_y = e.y - VIEWPORT_H / 2
                self._clamp_camera()
        elif pygame.K_1 <= k <= pygame.K_9:
            n = k - pygame.K_1   # 0-8
            if mod & pygame.KMOD_CTRL:
                self._ctrl_groups[n] = list(self.selection)
            else:
                grp = self._ctrl_groups.get(n, [])
                self.selection = [e for e in grp if e.alive]

        elif k == pygame.K_F5:
            from savegame import save_game
            path = save_game(self)
            self._add_message("Game saved!", duration=2.0)
        elif k == pygame.K_F9:
            # Quick-load handled by main loop (sets a flag)
            self._request_load = True

        # Track Konami code: ↑ ↑ ↓ ↓ ← → ← →
        _KONAMI = [pygame.K_UP, pygame.K_UP, pygame.K_DOWN, pygame.K_DOWN,
                   pygame.K_LEFT, pygame.K_RIGHT, pygame.K_LEFT, pygame.K_RIGHT]
        if k in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            self._konami_buf.append(k)
            self._konami_buf = self._konami_buf[-8:]
            if self._konami_buf == _KONAMI:
                self._activate_goat_mode()

    def _activate_goat_mode(self):
        self._goat_mode_t = 15.0
        for p in self.players.values():
            for u in p.units:
                u.speed_bonus += 120
        self._add_message("BAAAAAA!!! SUPREME GOAT MODE ACTIVATED!!!", duration=15.0)
        print(r"""
          / \__
         (    @\___         SUPREME GOAT MODE
         /         O        ================
        /   (_____/         All goats are now
       /_____/   U          going VERY fast.
        """)

    # ---------------------------------------------------------------- mouse
    def _on_left_down(self, pos):
        if self.build_mode:
            return   # handled on mouse up for ghost
        self.drag_start = pos

    def _on_left_up(self, pos, ui):
        if self.build_mode:
            if not ui.is_over_ui(pos):
                mods = pygame.key.get_mods()
                self._try_place_building(pos, keep_mode=bool(mods & pygame.KMOD_SHIFT))
            return

        # Attack-move: left click also counts as target
        if self._pending_attack_move and not ui.is_over_ui(pos):
            self._pending_attack_move = False
            wx, wy = self._screen_to_world(pos)
            for ent in self.selection:
                if isinstance(ent, Unit) and ent.team == self._my_team:
                    self._issue_cmd(ent, CmdData(Cmd.ATTACK_MOVE, wx=wx, wy=wy))
            self.drag_start = None
            return

        # Patrol: left click sets patrol destination
        if self._pending_patrol and not ui.is_over_ui(pos):
            self._pending_patrol = False
            wx, wy = self._screen_to_world(pos)
            for ent in self.selection:
                if isinstance(ent, Unit) and ent.team == self._my_team:
                    self._issue_cmd(ent, CmdData(Cmd.PATROL, wx=wx, wy=wy))
            self.drag_start = None
            return

        if self.drag_start is None:
            return

        dx = abs(pos[0] - self.drag_start[0])
        dy = abs(pos[1] - self.drag_start[1])

        if dx < 5 and dy < 5:
            self._click_select(pos, pygame.key.get_mods())
        else:
            self._drag_select(self.drag_start, pos, pygame.key.get_mods())

        self.drag_start = None

    def _screen_to_world(self, pos):
        """Convert game-space screen position to world pixel coordinates."""
        return ((pos[0] - VIEWPORT_X) / self.zoom + self.cam_x,
                (pos[1] - VIEWPORT_Y) / self.zoom + self.cam_y)

    def _click_select(self, pos, mods):
        wx, wy = self._screen_to_world(pos)
        tx = int(wx // TILE_SIZE)
        ty = int(wy // TILE_SIZE)

        # Double-click detection
        now = self.time_elapsed
        is_double = (now - self._last_click_t < 0.35 and
                     abs(pos[0] - self._last_click_pos[0]) < 8 and
                     abs(pos[1] - self._last_click_pos[1]) < 8)
        self._last_click_t = now
        self._last_click_pos = pos

        # Try own team first, then anything
        hit = self._entity_at(wx, wy, team=self._my_team)
        if hit is None:
            hit = self._entity_at(wx, wy, team=None)

        if not (mods & pygame.KMOD_CTRL):
            for e in self.selection:
                e.selected = False
            self.selection = []

        if hit and hit.team == self._my_team:
            self.selected_resource = None
            # Double-click: select all visible units of same type on screen
            if is_double and isinstance(hit, Unit):
                utype = hit.utype
                z = self.zoom
                vw = VIEWPORT_W / z
                vh = VIEWPORT_H / z
                for u in self.players[self._my_team].units:
                    if (u.alive and u.utype == utype and
                            self.cam_x <= u.x <= self.cam_x + vw and
                            self.cam_y <= u.y <= self.cam_y + vh and
                            u not in self.selection):
                        u.selected = True
                        self.selection.append(u)
                sounds.play('unit_select')
            elif hit not in self.selection:
                hit.selected = True
                self.selection.append(hit)
                sounds.play('unit_select')
        elif hit is None:
            node = self.game_map.get_resource(tx, ty)
            if node and not node.depleted and self.game_map.is_explored(tx, ty):
                self.selected_resource = node
            else:
                self.selected_resource = None

    def _drag_select(self, start, end, mods):
        self.selected_resource = None
        if not (mods & pygame.KMOD_CTRL):
            for e in self.selection:
                e.selected = False
            self.selection = []

        # Convert screen rect to world space (zoom-aware)
        wx1, wy1 = self._screen_to_world((min(start[0], end[0]), min(start[1], end[1])))
        wx2, wy2 = self._screen_to_world((max(start[0], end[0]), max(start[1], end[1])))

        for unit in self.players[self._my_team].units:
            if unit.alive and wx1 <= unit.x <= wx2 and wy1 <= unit.y <= wy2:
                if unit not in self.selection:
                    unit.selected = True
                    self.selection.append(unit)

        # If no units selected, allow building selection
        if not self.selection:
            for bld in self.players[self._my_team].buildings:
                if not bld.alive:
                    continue
                br = bld.get_rect()
                if (wx1 <= br.right and wx2 >= br.left and
                        wy1 <= br.bottom and wy2 >= br.top):
                    if bld not in self.selection:
                        bld.selected = True
                        self.selection.append(bld)

    def _on_right_click(self, pos, mods):
        if self.build_mode:
            self.build_mode = None
            return

        wx, wy = self._screen_to_world(pos)
        tx = int(wx // TILE_SIZE)
        ty = int(wy // TILE_SIZE)

        queue = bool(mods & pygame.KMOD_SHIFT)

        # Attack-move mode
        if self._pending_attack_move:
            self._pending_attack_move = False
            for ent in self.selection:
                if isinstance(ent, Unit) and ent.team == self._my_team:
                    self._issue_cmd(ent, CmdData(Cmd.ATTACK_MOVE, wx=wx, wy=wy), queue)
            return

        # What's at the click?  Target is any entity NOT on our team.
        target_any = self._entity_at(wx, wy)
        target = target_any if (target_any and target_any.team != self._my_team) else None
        resource = self.game_map.get_resource(tx, ty)

        # Resume construction: right-click own building under construction
        own_bld = self._entity_at(wx, wy, team=self._my_team)
        if isinstance(own_bld, Building) and not own_bld.is_constructed:
            workers = [e for e in self.selection
                       if isinstance(e, Unit) and e.team == self._my_team and e.utype == 'worker']
            for w in workers:
                self._issue_cmd(w, CmdData(Cmd.BUILD, building=own_bld), queue)
            return

        for ent in self.selection:
            if not isinstance(ent, Unit) or ent.team != self._my_team:
                # Building: set rally point
                if isinstance(ent, Building) and ent.team == self._my_team:
                    if self.net_mode == 'client':
                        self._net_session.send_command({
                            't': 'cmd',
                            'cmd_type': 'set_rally',
                            'building_id': ent.id,
                            'wx': wx,
                            'wy': wy,
                            'unit_ids': [],
                            'team': self._my_team,
                        })
                    else:
                        ent.rally_point = (wx, wy)
                continue

            if target and target.team != self._my_team:
                self._issue_cmd(ent, CmdData(Cmd.ATTACK, target=target), queue)
            elif resource and not resource.depleted and ent.utype == 'worker':
                self._issue_cmd(ent, CmdData(Cmd.GATHER, resource=resource), queue)
            else:
                self._issue_cmd(ent, CmdData(Cmd.MOVE, wx=wx, wy=wy), queue)
                sounds.play('unit_move')

    # ---------------------------------------------------------------- UI actions
    def _handle_ui_action(self, action):
        sel = self.selection

        if action.kind == UIAction.STOP:
            self._cmd_selection(CmdData(Cmd.STOP))

        elif action.kind == UIAction.HOLD:
            self._cmd_selection(CmdData(Cmd.STOP))

        elif action.kind == UIAction.ATTACK_MOVE:
            self._pending_attack_move = True

        elif action.kind == UIAction.PATROL:
            self._pending_patrol = True

        elif action.kind == UIAction.BUILD_MODE:
            if hasattr(action, 'btype'):
                workers = [e for e in sel
                           if isinstance(e, Unit) and e.team == self._my_team and e.utype == 'worker']
                if workers:
                    self.build_mode = action.btype

        elif action.kind == UIAction.TRAIN_UNIT:
            bld = getattr(action, 'building', None)
            if bld:
                if self.net_mode == 'client':
                    self._net_session.send_command({
                        't': 'cmd',
                        'cmd_type': 'train',
                        'building_id': bld.id,
                        'utype': action.utype,
                        'unit_ids': [],
                        'team': self._my_team,
                    })
                else:
                    ok, reason = bld.can_train(action.utype, self.players[self._my_team])
                    if ok:
                        bld.train_unit(action.utype, self.players[self._my_team])
                    else:
                        self._add_message(reason)
                        sounds.play('error')

        elif action.kind == UIAction.RESEARCH_TECH:
            bld = getattr(action, 'building', None)
            if bld:
                if self.net_mode == 'client':
                    self._net_session.send_command({
                        't': 'cmd',
                        'cmd_type': 'research',
                        'building_id': bld.id,
                        'tech': action.tech,
                        'unit_ids': [],
                        'team': self._my_team,
                    })
                else:
                    ok, reason = bld.can_research(action.tech, self.players[self._my_team])
                    if ok:
                        bld.start_research(action.tech, self.players[self._my_team])
                    else:
                        self._add_message(reason)
                        sounds.play('error')

        elif action.kind == UIAction.CANCEL_QUEUE:
            bld = getattr(action, 'building', None)
            if bld:
                if self.net_mode == 'client':
                    self._net_session.send_command({
                        't': 'cmd',
                        'cmd_type': 'cancel_queue',
                        'building_id': bld.id,
                        'unit_ids': [],
                        'team': self._my_team,
                    })
                else:
                    bld.cancel_last_in_queue(self.players[self._my_team])

    def _cmd_selection(self, cmd):
        units = [e for e in self.selection
                 if isinstance(e, Unit) and e.team == self._my_team]
        if self.net_mode == 'client' and units:
            self._net_session.send_command(
                self._serialize_cmd([u.id for u in units], cmd))
        else:
            for u in units:
                u.give_command(cmd)

    def _issue_cmd(self, unit, cmd, queue=False):
        """Issue a command to a unit, routing through network if we're a client."""
        if self.net_mode == 'client':
            self._net_session.send_command(
                self._serialize_cmd([unit.id], cmd, queue=queue))
        else:
            unit.give_command(cmd, queue=queue)

    def _serialize_cmd(self, unit_ids, cmd, queue=False) -> dict:
        """Serialize a CmdData to a network-friendly dict."""
        d = {
            't': 'cmd',
            'team': self._my_team,
            'unit_ids': unit_ids,
            'cmd_type': cmd.type,
            'queue': queue,
        }
        if hasattr(cmd, 'wx'):
            d['wx'] = cmd.wx
        if hasattr(cmd, 'wy'):
            d['wy'] = cmd.wy
        if hasattr(cmd, 'target') and cmd.target:
            d['target_id'] = cmd.target.id
        if hasattr(cmd, 'resource') and cmd.resource:
            d['rtx'] = cmd.resource.tx
            d['rty'] = cmd.resource.ty
        if hasattr(cmd, 'building') and cmd.building:
            d['building_id'] = cmd.building.id
        return d

    # ---------------------------------------------------------------- build placement
    def _try_place_building(self, pos, keep_mode=False):
        wx, wy = self._screen_to_world(pos)
        snap_tx = int(wx // TILE_SIZE)
        snap_ty = int(wy // TILE_SIZE)

        if self.net_mode == 'client':
            # Send placement request to host; host validates and executes
            workers = [e for e in self.selection
                       if isinstance(e, Unit) and e.team == self._my_team and e.utype == 'worker']
            self._net_session.send_command({
                't': 'cmd',
                'cmd_type': 'place_building',
                'btype': self.build_mode,
                'tx': snap_tx,
                'ty': snap_ty,
                'worker_ids': [w.id for w in workers],
                'unit_ids': [],
                'team': self._my_team,
            })
            if not keep_mode:
                self.build_mode = None
            return

        player = self.players[self._my_team]
        if not player.can_afford_building(self.build_mode):
            self._add_message("Not enough resources!")
            sounds.play('error')
            return

        if not self.can_place_building(self.build_mode, snap_tx, snap_ty):
            self._add_message("Cannot build here!")
            sounds.play('error')
            return

        player.pay_building(self.build_mode)
        bld = self.place_building(self.build_mode, snap_tx, snap_ty, self._my_team)
        if bld:
            workers = [e for e in self.selection
                       if isinstance(e, Unit) and e.team == self._my_team and e.utype == 'worker']
            if workers:
                workers[0].give_command(CmdData(Cmd.BUILD, building=bld))
            self._add_message(f"Building {self.build_mode.replace('_',' ').title()}...")
            sounds.play('building_start')

        if not keep_mode:
            self.build_mode = None

    # ================================================================= SPAWNING
    def spawn_unit(self, utype, wx, wy, team):
        unit = Unit(utype, wx, wy, team)
        bonuses = self._tech_bonuses.get(team, {})
        unit.dmg_bonus    = bonuses.get('dmg', 0)
        unit.armor_bonus  = bonuses.get('armor', 0)
        unit.gather_bonus = bonuses.get('gather', 0)
        unit.speed_bonus  = bonuses.get('speed', 0)
        self.players[team].units.append(unit)
        return unit

    def place_building(self, btype, tx, ty, team, instant=False):
        bld = Building(btype, tx, ty, team)
        self.players[team].buildings.append(bld)
        if instant:
            bld.complete(self)
        return bld

    def spawn_projectile(self, x, y, target, damage):
        self.projectiles.append(Projectile(x, y, target, damage))

    def add_attack_event(self, wx, wy, team_attacked):
        """Record a hit position for the screen-flash and minimap dot effect."""
        self.attack_events.append([wx, wy, team_attacked, 1.5])
        # Spawn hit particles
        for _ in range(4):
            vx = random.uniform(-40, 40)
            vy = random.uniform(-60, -10)
            col = random.choice([(220, 50, 30), (255, 160, 40), (200, 80, 60)])
            self.particles.append([wx, wy, col, random.uniform(2, 4),
                                   0.4, 0.4, vx, vy])

    def spawn_gather_particles(self, x, y, rtype):
        """Spawn sparkle particles at a gathering site."""
        if rtype == 'wood':
            colors = [(160, 120, 50), (120, 90, 30), (180, 150, 80)]
        else:
            colors = [(240, 200, 40), (255, 230, 80), (200, 170, 30)]
        for _ in range(3):
            vx = random.uniform(-30, 30)
            vy = random.uniform(-50, -15)
            self.particles.append([x, y, random.choice(colors),
                                   random.uniform(1.5, 3), 0.5, 0.5, vx, vy])

    # ================================================================= QUERIES
    def all_units(self):
        """Iterate every living unit across all teams."""
        for player in self.players.values():
            for unit in player.units:
                if unit.alive:
                    yield unit

    def idle_workers(self, team):
        """Return list of idle workers for the given team."""
        return [u for u in self.players[team].units
                if u.alive and u.utype == 'worker' and u.state == 'idle']

    def gatherer_counts(self, team):
        """Return (wood_gatherers, gold_gatherers) for the given team."""
        wood = sum(1 for u in self.players[team].units
                   if u.alive and u.utype == 'worker'
                   and u.state in ('gathering', 'returning')
                   and u.last_node and u.last_node.type == 'wood')
        gold = sum(1 for u in self.players[team].units
                   if u.alive and u.utype == 'worker'
                   and u.state in ('gathering', 'returning')
                   and u.last_node and u.last_node.type == 'gold')
        return wood, gold

    def can_place_building(self, btype, tx, ty):
        w, h = BUILDING_SIZES.get(btype, (2, 2))
        for dx in range(w):
            for dy in range(h):
                if not self.game_map.is_buildable(tx + dx, ty + dy):
                    return False
                if not self.game_map.is_passable(tx + dx, ty + dy):
                    return False
                for team_id, p in self.players.items():
                    for b in p.buildings:
                        for ftx, fty in b.tile_footprint():
                            if ftx == tx + dx and fty == ty + dy:
                                return False
        return True

    def _entity_at(self, wx, wy, team=None):
        """Return entity whose visual rect contains (wx, wy), or None."""
        for team_id, player in self.players.items():
            if team is not None and team_id != team:
                continue
            for unit in player.units:
                if not unit.alive:
                    continue
                if abs(unit.x - wx) < TILE_SIZE // 2 and abs(unit.y - wy) < TILE_SIZE // 2:
                    return unit

        for team_id, player in self.players.items():
            if team is not None and team_id != team:
                continue
            for bld in player.buildings:
                if not bld.alive:
                    continue
                r = bld.get_rect()
                if r.collidepoint(wx, wy):
                    return bld
        return None

    def _entity_by_id(self, eid):
        """Return the first living entity with the given id, across all teams."""
        for player in self.players.values():
            for unit in player.units:
                if unit.id == eid and unit.alive:
                    return unit
            for bld in player.buildings:
                if bld.id == eid and bld.alive:
                    return bld
        return None

    def nearest_storage(self, tx, ty, team, rtype=None):
        """Find nearest storage building for the given team.
        rtype='wood' also checks lumber_mill; rtype='gold' also checks mine."""
        storage_btypes = {'town_hall'}
        if rtype == 'wood':
            storage_btypes.add('lumber_mill')
        elif rtype == 'gold':
            storage_btypes.add('mine')
        best, best_d = None, float('inf')
        for bld in self.players[team].buildings:
            if bld.btype in storage_btypes and bld.alive and bld.is_constructed:
                d = math.hypot(bld.tx - tx, bld.ty - ty)
                if d < best_d:
                    best_d, best = d, bld
        return best

    # ================================================================= TECH
    def apply_tech(self, team, tech):
        bonuses = self._tech_bonuses.setdefault(team, {})
        if tech == 'improved_gathering':
            bonuses['gather'] = bonuses.get('gather', 0) + 3
        elif tech == 'iron_weapons':
            bonuses['dmg'] = bonuses.get('dmg', 0) + 5
        elif tech == 'leather_armor':
            bonuses['armor'] = bonuses.get('armor', 0) + 2
        elif tech == 'steel_armor':
            bonuses['armor'] = bonuses.get('armor', 0) + 4
        elif tech == 'ballistics':
            bonuses['dmg'] = bonuses.get('dmg', 0) + 8
        for unit in self.players[team].units:
            unit.dmg_bonus    = bonuses.get('dmg', 0)
            unit.armor_bonus  = bonuses.get('armor', 0)
            unit.gather_bonus = bonuses.get('gather', 0)

    # ================================================================= GAME MODES
    def _update_koth(self, dt):
        """King of the Hill: control the center for 3 minutes to win."""
        cx = self._koth_cx * TILE_SIZE + TILE_SIZE // 2
        cy = self._koth_cy * TILE_SIZE + TILE_SIZE // 2
        radius = self._koth_radius * TILE_SIZE

        # Count military units in the hill zone per team
        counts = {}
        for team_id in range(self.num_players):
            counts[team_id] = sum(
                1 for u in self.players[team_id].units
                if u.alive and u.utype != 'worker'
                and math.hypot(u.x - cx, u.y - cy) < radius)

        # Determine controlling team (must have exclusive presence)
        controlling = None
        for team_id, cnt in counts.items():
            if cnt > 0:
                if controlling is None:
                    controlling = team_id
                else:
                    controlling = None  # contested
                    break

        if controlling is not None:
            self._koth_control[controlling] = self._koth_control.get(controlling, 0.0) + dt
            if self._koth_control[controlling] >= self._koth_time_to_win:
                self.game_over = True
                self.player_won = (controlling == self._my_team)
                self._koth_winner = controlling
                sounds.play('victory' if self.player_won else 'defeat')

    def _update_survival(self, dt):
        """Survival mode: escalating waves of enemies from map edges."""
        self._survival_timer += dt
        interval = max(30.0, self._survival_interval - self._survival_wave * 10)
        if self._survival_timer < interval:
            return
        self._survival_timer = 0.0
        self._survival_wave += 1

        # Spawn enemies at random map edges
        rng = random.Random()
        wave_size = min(4 + self._survival_wave * 2, 20)
        mw, mh = self._map_w, self._map_h

        for _ in range(wave_size):
            edge = rng.choice(['top', 'bottom', 'left', 'right'])
            if edge == 'top':
                tx, ty = rng.randint(5, mw - 5), 1
            elif edge == 'bottom':
                tx, ty = rng.randint(5, mw - 5), mh - 2
            elif edge == 'left':
                tx, ty = 1, rng.randint(5, mh - 5)
            else:
                tx, ty = mw - 2, rng.randint(5, mh - 5)

            # Escalate unit types with wave number
            if self._survival_wave >= 6:
                utype = rng.choice(['soldier', 'archer', 'knight'])
            elif self._survival_wave >= 3:
                utype = rng.choice(['soldier', 'archer'])
            else:
                utype = 'soldier'

            # Spawn for the highest AI team (dedicated survival enemy)
            enemy_team = self.num_players - 1
            if enemy_team < 1:
                enemy_team = 1
            u = self.spawn_unit(utype,
                                tx * TILE_SIZE + TILE_SIZE // 2,
                                ty * TILE_SIZE + TILE_SIZE // 2,
                                enemy_team)
            if u:
                # Attack-move toward player base
                p_th = next((b for b in self.players[PLAYER_TEAM].buildings
                             if b.btype == 'town_hall' and b.alive), None)
                if p_th:
                    u.give_command(CmdData(Cmd.ATTACK, target=p_th))

        self._add_message(f"Wave {self._survival_wave}!", duration=3.0)

    # ================================================================= WIN/LOSE
    def _check_game_over(self):
        if self.game_over:
            return

        p_alive = any(b.btype == 'town_hall' and b.alive
                      for b in self.players[PLAYER_TEAM].buildings)

        if not p_alive:
            self.game_over = True
            self.player_won = False
            sounds.play('defeat')
            return

        # Check if all AI opponents' town halls are destroyed
        all_ai_dead = True
        for t in range(1, self.num_players):
            if t in self.players:
                if any(b.btype == 'town_hall' and b.alive
                       for b in self.players[t].buildings):
                    all_ai_dead = False
                    break

        if all_ai_dead:
            self.game_over = True
            self.player_won = True
            sounds.play('victory')

    # ================================================================= MESSAGES
    def _add_message(self, text, duration=3.0):
        # Tag each message with the active command team so players only see
        # messages triggered by their own actions. None = show to all players.
        team = self._active_cmd_team if self._active_cmd_team is not None else self._my_team
        self._messages.append((duration, text, team))

    def get_messages(self):
        return [(t, msg) for (t, msg, tm) in self._messages
                if t > 0 and (tm is None or tm == self._my_team)]

    # ================================================================= NETWORK: SERIALISE
    def serialize_state(self) -> dict:
        """
        Produce a complete snapshot of the game state for transmission to the client.
        """
        units_data = []
        for team_id, player in self.players.items():
            for u in player.units:
                units_data.append({
                    'id':           u.id,
                    'team':         u.team,
                    'utype':        u.utype,
                    'x':            round(u.x, 1),
                    'y':            round(u.y, 1),
                    'hp':           u.hp,
                    'max_hp':       u.max_hp,
                    'state':        u.state,
                    'flip_h':       u.flip_h,
                    'anim_t':       round(u.anim_t, 2),
                    'carry_wood':   u.carry_wood,
                    'carry_gold':   u.carry_gold,
                    'gather_prog':  round(u.gather_prog, 3),
                    'alive':        u.alive,
                })

        buildings_data = []
        for team_id, player in self.players.items():
            for b in player.buildings:
                buildings_data.append({
                    'id':                    b.id,
                    'team':                  b.team,
                    'btype':                 b.btype,
                    'tx':                    b._tx,
                    'ty':                    b._ty,
                    'hp':                    b.hp,
                    'max_hp':                b.max_hp,
                    'is_constructed':        b.is_constructed,
                    'construction_progress': round(b.construction_progress, 3),
                    'train_queue':           list(b.train_queue),
                    'train_progress':        round(b.train_progress, 3),
                    'research_queue':        list(b.research_queue),
                    'research_progress':     round(b.research_progress, 3),
                    'alive':                 b.alive,
                    'rally_point':           list(b.rally_point) if b.rally_point else None,
                })

        # Only send changed/depleted resource nodes to save bandwidth
        resources_data = []
        for (tx, ty), node in self.game_map.resources.items():
            if node.depleted or node.amount != node.max_amount:
                resources_data.append({
                    'tx':       tx,
                    'ty':       ty,
                    'amount':   node.amount,
                    'depleted': node.depleted,
                })

        players_data = []
        for team_id, player in self.players.items():
            players_data.append({
                'team':      player.team,
                'wood':      player.wood,
                'gold':      player.gold,
                'food':      player.food,
                'food_cap':  player.food_cap,
                'techs':     list(player.techs),
            })

        projectiles_data = [
            {'x': round(p.x, 1), 'y': round(p.y, 1),
             'tx': round(p.target.x, 1) if p.target else round(p.x + 1, 1),
             'ty': round(p.target.y, 1) if p.target else round(p.y, 1)}
            for p in self.projectiles if p.alive
        ]

        return {
            't':           'state',
            'units':       units_data,
            'buildings':   buildings_data,
            'resources':   resources_data,
            'players':     players_data,
            'projectiles': projectiles_data,
            'game_over':   self.game_over,
            'player_won':  self.player_won,
            'messages':    list(self._messages),
            'time':        round(self.time_elapsed, 2),
        }

    # ================================================================= NETWORK: APPLY STATE (CLIENT)
    def apply_net_state(self, state: dict):
        """
        Update local game state from a host-sent snapshot.
        Called on the client every time a new state arrives.
        """
        # Build lookup tables for existing entities
        existing_units = {}
        for player in self.players.values():
            for u in player.units:
                existing_units[u.id] = u

        existing_blds = {}
        for player in self.players.values():
            for b in player.buildings:
                existing_blds[b.id] = b

        seen_uids = set()
        seen_bids = set()

        # --- Units ---
        for ud in state.get('units', []):
            eid   = ud['id']
            team  = ud['team']
            utype = ud['utype']
            seen_uids.add(eid)

            if eid in existing_units:
                u = existing_units[eid]
            else:
                # Create new unit; bypass spawn_unit to control ID
                u = Unit(utype, ud['x'], ud['y'], team)
                u.id = eid
                self.players[team].units.append(u)
                existing_units[eid] = u

            u.x           = ud['x']
            u.y           = ud['y']
            u.hp          = ud['hp']
            u.max_hp      = ud['max_hp']
            u.state       = ud['state']
            u.flip_h      = ud['flip_h']
            u.anim_t      = ud['anim_t']
            u.carry_wood  = ud['carry_wood']
            u.carry_gold  = ud['carry_gold']
            u.gather_prog = ud['gather_prog']
            u.alive       = ud['alive']

        # --- Buildings ---
        for bd in state.get('buildings', []):
            eid   = bd['id']
            team  = bd['team']
            btype = bd['btype']
            seen_bids.add(eid)

            was_constructed = False
            if eid in existing_blds:
                b = existing_blds[eid]
                was_constructed = b.is_constructed
            else:
                b = Building(btype, bd['tx'], bd['ty'], team)
                b.id = eid
                self.players[team].buildings.append(b)
                existing_blds[eid] = b
                was_constructed = False

            b.hp                    = bd['hp']
            b.max_hp                = bd['max_hp']
            b.is_constructed        = bd['is_constructed']
            b.construction_progress = bd['construction_progress']
            b.train_queue           = deque(bd['train_queue'])
            b.train_progress        = bd['train_progress']
            b.research_queue        = deque(bd['research_queue'])
            b.research_progress     = bd['research_progress']
            b.alive                 = bd['alive']
            rp = bd.get('rally_point')
            b.rally_point = tuple(rp) if rp else None

            # If just completed construction (or brand new + already complete): update map
            newly_complete = (b.is_constructed and not was_constructed) or \
                             (b.is_constructed and eid not in existing_blds)
            if newly_complete:
                for ftx, fty in b.tile_footprint():
                    if btype == 'gate':
                        self.game_map.gates[(ftx, fty)] = team
                        self.game_map.set_buildable(ftx, fty, False)
                        self.game_map.set_passable(ftx, fty, True)
                    else:
                        self.game_map.set_passable(ftx, fty, False)
                        self.game_map.set_buildable(ftx, fty, False)

        # --- Remove entities no longer in the snapshot ---
        # Cleanup gate tiles for gates disappearing from the snapshot
        for player in self.players.values():
            for b in player.buildings:
                if b.id not in seen_bids and b.btype == 'gate' and b.is_constructed:
                    for ftx, fty in b.tile_footprint():
                        self.game_map.gates.pop((ftx, fty), None)
            player.units     = [u for u in player.units     if u.id in seen_uids]
            player.buildings = [b for b in player.buildings if b.id in seen_bids]

        # --- Resources ---
        for rd in state.get('resources', []):
            node = self.game_map.get_resource(rd['tx'], rd['ty'])
            if node:
                node.amount = rd['amount']
                if rd['depleted']:
                    node.amount = 0

        # --- Players ---
        for pd in state.get('players', []):
            team   = pd['team']
            player = self.players.get(team)
            if player:
                player.wood     = pd['wood']
                player.gold     = pd['gold']
                player.food     = pd['food']
                player.food_cap = pd['food_cap']
                player.techs    = set(pd['techs'])

        # --- Clean selection: keep only alive entities we still know about ---
        valid_ids = seen_uids | seen_bids
        self.selection = [
            e for e in self.selection
            if e.alive and e.id in valid_ids
        ]

        # --- Projectiles (lightweight render-only objects) ---
        from types import SimpleNamespace
        self.projectiles = [
            SimpleNamespace(
                x=pd['x'], y=pd['y'], alive=True,
                target=SimpleNamespace(x=pd['tx'], y=pd['ty'], alive=True)
            )
            for pd in state.get('projectiles', [])
        ]

        # --- Update fog of war from our team's perspective ---
        my_player = self.players[self.net_my_team]
        self.game_map.update_visibility(my_player.units, my_player.buildings)

        # --- Game state ---
        self.game_over    = state.get('game_over', False)
        self.player_won   = state.get('player_won', False)
        # Only import messages that belong to this player's team (or global ones)
        raw = state.get('messages', [])
        self._messages = [
            (t, msg, tm) for t, msg, tm in
            (item if len(item) == 3 else (*item, None) for item in raw)
            if tm is None or tm == self.net_my_team
        ]
        self.time_elapsed = state.get('time', self.time_elapsed)

    # ================================================================= NETWORK: APPLY COMMAND (HOST)
    def apply_net_command(self, data: dict):
        """
        Apply a command sent by the client.  Called on the host every frame.
        """
        cmd_type  = data.get('cmd_type', '')
        team      = data.get('team', AI_TEAM)
        unit_ids  = set(data.get('unit_ids', []))
        queue_cmd = data.get('queue', False)
        player    = self.players.get(team)

        if player is None:
            return

        # Tag any messages generated here with the client's team so they route
        # back to the correct player and not to the host.
        prev_cmd_team = self._active_cmd_team
        self._active_cmd_team = team

        units = [u for u in player.units if u.id in unit_ids]

        if cmd_type == 'move':
            wx, wy = data['wx'], data['wy']
            for u in units:
                u.give_command(CmdData(Cmd.MOVE, wx=wx, wy=wy), queue=queue_cmd)

        elif cmd_type == 'attack':
            target = self._entity_by_id(data.get('target_id'))
            if target:
                for u in units:
                    u.give_command(CmdData(Cmd.ATTACK, target=target), queue=queue_cmd)

        elif cmd_type == 'attack_move':
            wx, wy = data['wx'], data['wy']
            for u in units:
                u.give_command(CmdData(Cmd.ATTACK_MOVE, wx=wx, wy=wy), queue=queue_cmd)

        elif cmd_type == 'gather':
            node = self.game_map.get_resource(data.get('rtx', 0), data.get('rty', 0))
            if node:
                for u in units:
                    u.give_command(CmdData(Cmd.GATHER, resource=node), queue=queue_cmd)

        elif cmd_type == 'build':
            bld = self._entity_by_id(data.get('building_id'))
            if bld:
                for u in units:
                    u.give_command(CmdData(Cmd.BUILD, building=bld), queue=queue_cmd)

        elif cmd_type == 'patrol':
            wx, wy = data['wx'], data['wy']
            for u in units:
                u.give_command(CmdData(Cmd.PATROL, wx=wx, wy=wy), queue=queue_cmd)

        elif cmd_type == 'stop':
            for u in units:
                u.give_command(CmdData(Cmd.STOP))

        elif cmd_type == 'train':
            bld = self._entity_by_id(data.get('building_id'))
            if bld:
                bld.train_unit(data.get('utype', ''), player)

        elif cmd_type == 'research':
            bld = self._entity_by_id(data.get('building_id'))
            if bld:
                bld.start_research(data.get('tech', ''), player)

        elif cmd_type == 'cancel_queue':
            bld = self._entity_by_id(data.get('building_id'))
            if bld:
                bld.cancel_last_in_queue(player)

        elif cmd_type == 'place_building':
            btype = data.get('btype', '')
            tx    = data.get('tx', 0)
            ty    = data.get('ty', 0)
            if player.can_afford_building(btype) and self.can_place_building(btype, tx, ty):
                player.pay_building(btype)
                bld = self.place_building(btype, tx, ty, team)
                worker_ids = set(data.get('worker_ids', []))
                workers    = [u for u in player.units if u.id in worker_ids]
                if bld and workers:
                    workers[0].give_command(CmdData(Cmd.BUILD, building=bld))
            else:
                self._add_message("Cannot build there!")

        elif cmd_type == 'set_rally':
            bld = self._entity_by_id(data.get('building_id'))
            if bld:
                bld.rally_point = (data.get('wx', bld.x), data.get('wy', bld.y))

        elif cmd_type == 'delete':
            unit_ids     = set(data.get('unit_ids', []))
            building_ids = set(data.get('building_ids', []))
            for u in player.units:
                if u.id in unit_ids:
                    u.alive = False
            for b in player.buildings:
                if b.id in building_ids:
                    if b.btype == 'gate' and b.is_constructed:
                        for ftx, fty in b.tile_footprint():
                            self.game_map.gates.pop((ftx, fty), None)
                    b.alive = False

        self._active_cmd_team = prev_cmd_team
