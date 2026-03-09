"""
Simple scripted AI for team 1.
Phase 1: Gather resources with workers
Phase 2: Build economy buildings
Phase 3: Build military buildings, train troops
Phase 4: Attack in waves
"""
import random
import math
from commands import Cmd, CmdData
from constants import (TILE_SIZE, MAP_W, MAP_H, AI_TEAM, PLAYER_TEAM,
                       BUILDING_COSTS, UNIT_COSTS)
from buildings import Building
from units import Unit, State


class AIPhase:
    GATHER   = 'gather'
    ECONOMY  = 'economy'
    MILITARY = 'military'
    ATTACK   = 'attack'


class AIController:
    def __init__(self, team=AI_TEAM):
        self.team       = team
        self.phase      = AIPhase.GATHER
        self.timer      = 0.0
        self.attack_timer    = 0.0
        self.attack_interval = 90.0   # seconds between waves (first wave sooner)
        self.wave_num   = 0
        self._gather_assigned = False
        self._build_cd = 0.0

    def update(self, dt, game):
        self.timer        += dt
        self.attack_timer += dt
        self._build_cd    -= dt

        player = game.players[self.team]
        if player.defeated:
            return

        self._update_workers(game, player)
        self._update_training(game, player)
        if self._build_cd <= 0:
            self._maybe_build(game, player)
            self._build_cd = 3.0   # check every 3 seconds
        self._maybe_attack(game, player)
        self._update_phase(player)

    # ---------------------------------------------------------------- workers
    def _update_workers(self, game, player):
        for unit in player.units:
            if unit.utype != 'worker' or not unit.alive:
                continue
            if unit.state in (State.IDLE,) and not unit.gather_node:
                self._send_gather(unit, game)

    def _send_gather(self, unit, game):
        # Prefer gold first, fall back to wood
        node = game.game_map.find_nearest_resource(unit.tx, unit.ty, 'gold')
        if node is None or node.depleted:
            node = game.game_map.find_nearest_resource(unit.tx, unit.ty, 'wood')
        if node:
            unit.give_command(CmdData(Cmd.GATHER, resource=node))

    # ---------------------------------------------------------------- training
    def _update_training(self, game, player):
        for bld in player.buildings:
            if not bld.is_constructed or not bld.alive:
                continue
            trainable = bld.trainable_units(player)
            if not trainable:
                continue
            if len(bld.train_queue) >= 3:
                continue
            # Choose what to train
            if bld.btype == 'town_hall':
                n_workers = sum(1 for u in player.units if u.utype == 'worker' and u.alive)
                if n_workers < 6:
                    bld.train_unit('worker', player)
            elif bld.btype == 'barracks':
                bld.train_unit('soldier', player)
            elif bld.btype == 'archery_range':
                bld.train_unit('archer', player)

    # ---------------------------------------------------------------- building
    def _maybe_build(self, game, player):
        # Find an idle worker
        worker = next((u for u in player.units
                       if u.utype == 'worker' and u.alive and u.state == State.IDLE), None)
        if worker is None:
            return

        has_farm     = self._count_buildings(player, 'farm') > 0
        has_lumber   = self._count_buildings(player, 'lumber_mill') > 0
        has_barracks = self._count_buildings(player, 'barracks') > 0
        has_archery  = self._count_buildings(player, 'archery_range') > 0

        want = None
        if not has_farm and player.can_afford_building('farm'):
            want = 'farm'
        elif not has_lumber and player.can_afford_building('lumber_mill'):
            want = 'lumber_mill'
        elif has_lumber and not has_barracks and player.can_afford_building('barracks'):
            want = 'barracks'
        elif has_barracks and not has_archery and player.can_afford_building('archery_range'):
            want = 'archery_range'
        elif self._count_buildings(player, 'farm') < 3 and player.can_afford_building('farm'):
            want = 'farm'
        elif (self._count_buildings(player, 'barracks') < 2 and
              player.can_afford_building('barracks')):
            want = 'barracks'

        if want:
            spot = self._find_build_spot(game, player, want)
            if spot:
                bld = game.place_building(want, spot[0], spot[1], self.team)
                if bld:
                    worker.give_command(CmdData(Cmd.BUILD, building=bld))

    def _count_buildings(self, player, btype):
        return sum(1 for b in player.buildings
                   if b.btype == btype and b.alive)

    def _find_build_spot(self, game, player, btype):
        from constants import BUILDING_SIZES
        w, h = BUILDING_SIZES.get(btype, (2, 2))

        # Start near the AI town hall
        th = next((b for b in player.buildings if b.btype == 'town_hall' and b.is_constructed), None)
        if th is None:
            th = next((b for b in player.buildings if b.btype == 'town_hall'), None)
        if th is None:
            return None

        cx, cy = th.tx + th.w_tiles // 2, th.ty + th.h_tiles // 2
        for attempt in range(80):
            r  = random.randint(5, 14)
            a  = random.uniform(0, 2 * math.pi)
            tx = cx + int(r * math.cos(a))
            ty = cy + int(r * math.sin(a))
            if game.can_place_building(btype, tx, ty):
                return (tx, ty)
        return None

    # ---------------------------------------------------------------- attack
    def _maybe_attack(self, game, player):
        # Scale attack interval down over time
        interval = max(45.0, self.attack_interval - self.wave_num * 8)
        if self.attack_timer < interval:
            return
        self.attack_timer = 0.0
        self.wave_num    += 1

        # Gather idle military units
        fighters = [u for u in player.units
                    if u.alive and u.utype in ('soldier', 'archer', 'knight')
                    and u.state == State.IDLE]

        min_needed = max(3, self.wave_num * 2)
        if len(fighters) < min_needed:
            return

        # Find player's town hall to attack
        enemy_player = game.players[PLAYER_TEAM]
        target_bld   = next((b for b in enemy_player.buildings
                             if b.btype == 'town_hall' and b.alive), None)
        if target_bld is None:
            target_bld = next((b for b in enemy_player.buildings if b.alive), None)

        if target_bld is None:
            return

        # Send fighters
        for unit in fighters:
            unit.give_command(CmdData(Cmd.ATTACK, target=target_bld))

    # ---------------------------------------------------------------- phase
    def _update_phase(self, player):
        n_buildings = len([b for b in player.buildings if b.is_constructed and b.alive])
        n_military  = sum(1 for u in player.units
                          if u.utype in ('soldier', 'archer', 'knight') and u.alive)

        if n_buildings >= 3 and n_military == 0:
            self.phase = AIPhase.MILITARY
        elif n_military >= 4:
            self.phase = AIPhase.ATTACK
        elif n_buildings < 2:
            self.phase = AIPhase.ECONOMY
