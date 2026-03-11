import math
from collections import deque
import pygame
from entities import Entity
from commands import Cmd, CmdData
from constants import (TILE_SIZE, BUILDING_SIZES, BUILDING_HP, BUILD_TIMES,
                       BUILDING_TRAINS, UNIT_COSTS, TRAIN_TIMES,
                       TECH_COSTS, TECH_TIMES, PLAYER_TEAM)
try:
    import sounds
except Exception:
    class sounds:  # type: ignore
        @staticmethod
        def play(*a, **kw): pass

TOWER_RANGE       = 7 * TILE_SIZE   # pixels
TOWER_DAMAGE      = 20
TOWER_ATTACK_SPD  = 0.8             # attacks per second


class Building(Entity):
    """
    Buildings store their position as top-left tile (_tx, _ty).
    x and y (world-pixel center) are properties derived from _tx/_ty.
    tx and ty properties override Entity's to return the stored top-left tile.
    """

    def __init__(self, btype, tile_x, tile_y, team):
        super().__init__(team)
        self.btype    = btype
        self._tx      = tile_x   # top-left tile x
        self._ty      = tile_y   # top-left tile y
        self.w_tiles, self.h_tiles = BUILDING_SIZES.get(btype, (2, 2))

        self.hp       = BUILDING_HP.get(btype, 300)
        self.max_hp   = self.hp
        self.armor    = 5

        self.is_constructed        = False
        self.construction_progress = 0.0
        self.build_time            = BUILD_TIMES.get(btype, 20)

        self.train_queue      = deque()
        self.train_progress   = 0.0
        self.research_queue   = deque()
        self.research_progress= 0.0
        self.rally_point      = None   # (world_px_x, world_px_y)
        self.atk_cd           = 0.0   # tower attack cooldown

    # --- Coordinate properties (override Entity's tx/ty/x/y) ---------------
    @property
    def tx(self):
        return self._tx

    @property
    def ty(self):
        return self._ty

    @property
    def x(self):
        return (self._tx + self.w_tiles / 2) * TILE_SIZE

    @property
    def y(self):
        return (self._ty + self.h_tiles / 2) * TILE_SIZE

    # ------------------------------------------------------------------------
    def get_rect(self):
        return pygame.Rect(self._tx * TILE_SIZE, self._ty * TILE_SIZE,
                           self.w_tiles * TILE_SIZE, self.h_tiles * TILE_SIZE)

    def get_tile_rect(self):
        return pygame.Rect(self._tx, self._ty, self.w_tiles, self.h_tiles)

    def tile_footprint(self):
        for dx in range(self.w_tiles):
            for dy in range(self.h_tiles):
                yield self._tx + dx, self._ty + dy

    # ----------------------------------------------------------- update
    def update(self, dt, game):
        if not self.is_constructed:
            return
        self._update_training(dt, game)
        self._update_research(dt, game)
        if self.btype == 'tower':
            self._update_tower(dt, game)

    def _update_tower(self, dt, game):
        if self.atk_cd > 0:
            self.atk_cd -= dt
            return
        # Find nearest enemy unit or building within range
        best, best_d = None, TOWER_RANGE
        for team_id, player in game.players.items():
            if team_id == self.team:
                continue
            for unit in player.units:
                if unit.alive:
                    d = math.hypot(unit.x - self.x, unit.y - self.y)
                    if d < best_d:
                        best_d, best = d, unit
        if best:
            game.spawn_projectile(self.x, self.y, best, TOWER_DAMAGE)
            self.atk_cd = 1.0 / TOWER_ATTACK_SPD
            if self.team == PLAYER_TEAM:
                sounds.play('tower_fire')

    def _update_training(self, dt, game):
        if not self.train_queue:
            return
        utype  = self.train_queue[0]
        train_t = TRAIN_TIMES.get(utype, 12)
        self.train_progress += dt / train_t
        if self.train_progress >= 1.0:
            self.train_progress = 0.0
            self.train_queue.popleft()
            spawn = self._spawn_point(game)
            if spawn:
                unit = game.spawn_unit(
                    utype,
                    spawn[0] * TILE_SIZE + TILE_SIZE // 2,
                    spawn[1] * TILE_SIZE + TILE_SIZE // 2,
                    self.team)
                if unit and self.rally_point:
                    unit.give_command(CmdData(Cmd.MOVE,
                                              wx=self.rally_point[0],
                                              wy=self.rally_point[1]))

    def _update_research(self, dt, game):
        if not self.research_queue:
            return
        tech   = self.research_queue[0]
        tech_t = TECH_TIMES.get(tech, 30)
        self.research_progress += dt / tech_t
        if self.research_progress >= 1.0:
            self.research_progress = 0.0
            self.research_queue.popleft()
            game.players[self.team].techs.add(tech)
            game.apply_tech(self.team, tech)
            if self.team == PLAYER_TEAM:
                sounds.play('research_complete')

    def _spawn_point(self, game):
        for r in range(1, 7):
            for dx in range(-r, self.w_tiles + r):
                for dy in range(-r, self.h_tiles + r):
                    if -r < dx < self.w_tiles + r - 1 and -r < dy < self.h_tiles + r - 1:
                        continue
                    ntx, nty = self._tx + dx, self._ty + dy
                    if game.game_map.is_passable(ntx, nty):
                        return (ntx, nty)
        return None

    # -------------------------------------------------------- completion
    def complete(self, game):
        self.is_constructed = True
        self.construction_progress = 1.0
        if self.team == PLAYER_TEAM:
            sounds.play('building_complete')
        footprint = set(self.tile_footprint())
        for ftx, fty in footprint:
            if self.btype == 'gate':
                # Gate stays passable for the owning team; enemies are blocked by team-aware A*
                game.game_map.gates[(ftx, fty)] = self.team
                game.game_map.set_buildable(ftx, fty, False)
                game.game_map.set_passable(ftx, fty, True)
            else:
                game.game_map.set_passable(ftx, fty, False)
                game.game_map.set_buildable(ftx, fty, False)

        # Eject any units standing on the building's footprint
        if self.btype != 'gate':
            import pathfinding as pf
            for player in game.players.values():
                for unit in player.units:
                    if (unit.tx, unit.ty) in footprint:
                        escape = pf.adjacent_passable(game.game_map, unit.tx, unit.ty)
                        if escape:
                            unit.x = escape[0] * TILE_SIZE + TILE_SIZE // 2
                            unit.y = escape[1] * TILE_SIZE + TILE_SIZE // 2
                            unit._path = []
                            unit._path_cd = 0.0

    # --------------------------------------------------------- training
    def trainable_units(self, player):
        if not self.is_constructed:
            return []
        units = list(BUILDING_TRAINS.get(self.btype, []))
        if 'knight' in units and 'unlock_knight' not in player.techs:
            units.remove('knight')
        return units

    def _worker_cost(self, player):
        """Flexible worker cost: 25+25 if possible, else 50 of any single resource."""
        if player.wood >= 25 and player.gold >= 25:
            return {'wood': 25, 'gold': 25, 'food': 1}
        if player.wood >= 50:
            return {'wood': 50, 'gold': 0, 'food': 1}
        if player.gold >= 50:
            return {'wood': 0, 'gold': 50, 'food': 1}
        return {'wood': 25, 'gold': 25, 'food': 1}  # will fail affordability check

    def can_train(self, utype, player):
        if len(self.train_queue) >= 5:
            return False, "Queue full"
        cost = self._worker_cost(player) if utype == 'worker' else UNIT_COSTS.get(utype, {})
        if player.food + cost.get('food', 0) > player.food_cap:
            return False, "Pop cap reached"
        if player.wood < cost.get('wood', 0):
            return False, "Need wood"
        if player.gold < cost.get('gold', 0):
            return False, "Need gold"
        return True, ""

    def train_unit(self, utype, player):
        ok, _ = self.can_train(utype, player)
        if not ok:
            return False
        if utype == 'worker':
            cost = self._worker_cost(player)
            player.wood -= cost['wood']
            player.gold -= cost['gold']
            self.train_queue.append(utype)
        else:
            player.pay_unit(utype)
            self.train_queue.append(utype)
        return True

    def cancel_last_in_queue(self, player):
        if self.train_queue:
            utype = self.train_queue.pop()
            player.refund_unit(utype)

    # --------------------------------------------------------- research
    def researchable_techs(self):
        if self.btype != 'academy' or not self.is_constructed:
            return []
        return list(TECH_COSTS.keys())

    def can_research(self, tech, player):
        if tech in player.techs:
            return False, "Already done"
        if tech in self.research_queue:
            return False, "Already queued"
        cost = TECH_COSTS.get(tech, {})
        if player.wood < cost.get('wood', 0):
            return False, "Need wood"
        if player.gold < cost.get('gold', 0):
            return False, "Need gold"
        return True, ""

    def start_research(self, tech, player):
        ok, _ = self.can_research(tech, player)
        if not ok:
            return False
        player.pay_tech(tech)
        self.research_queue.append(tech)
        return True
