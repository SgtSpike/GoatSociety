"""
AI controller for team 1.
Phases: Gather → Economy → Military → Attack
Improvements: balanced wood/gold gathering, mine/lumber_mill usage,
academy + research, tower defence, smarter attack targeting, reactive defence.
"""
import random
import math
from commands import Cmd, CmdData
from constants import (TILE_SIZE, MAP_W, MAP_H, AI_TEAM, PLAYER_TEAM, NEUTRAL_TEAM,
                       BUILDING_COSTS, UNIT_COSTS, TECH_COSTS)
from buildings import Building
from units import Unit, State


class AIPhase:
    GATHER   = 'gather'
    ECONOMY  = 'economy'
    MILITARY = 'military'
    ATTACK   = 'attack'


class AIController:
    def __init__(self, team=AI_TEAM):
        self.team            = team
        self.phase           = AIPhase.GATHER
        self.timer           = 0.0
        self.attack_timer    = 0.0
        self.attack_interval = 80.0
        self.wave_num        = 0
        self._build_cd       = 0.0
        self._research_cd    = 0.0
        self._defend_cd      = 0.0
        # Difficulty multipliers (set by game after creation)
        self.resource_mult   = 1.0   # bonus resources per gather
        self.train_mult      = 1.0   # training speed multiplier
        self.attack_delay    = 1.0   # attack interval multiplier

    def update(self, dt, game):
        self.timer        += dt
        self.attack_timer += dt
        self._build_cd    -= dt
        self._research_cd -= dt
        self._defend_cd   -= dt

        player = game.players[self.team]
        if player.defeated:
            return

        self._update_workers(game, player)
        self._update_training(game, player)
        if self._build_cd <= 0:
            self._maybe_build(game, player)
            self._build_cd = 3.0
        if self._research_cd <= 0:
            self._maybe_research(game, player)
            self._research_cd = 5.0
        if self._defend_cd <= 0:
            self._maybe_defend(game, player)
            self._defend_cd = 4.0
        self._maybe_attack(game, player)
        self._update_phase(player)

    # ---------------------------------------------------------------- workers
    def _update_workers(self, game, player):
        workers = [u for u in player.units if u.utype == 'worker' and u.alive]
        n = len(workers)
        if n == 0:
            return

        # Split workers: ~60% gold, ~40% wood (adjust if resources very lopsided)
        gold_target = max(1, int(n * 0.6))
        wood_target = max(1, n - gold_target)

        gold_workers = [w for w in workers
                        if w.last_node and w.last_node.type == 'gold'
                        and w.state in (State.GATHERING, State.RETURNING)]
        wood_workers = [w for w in workers
                        if w.last_node and w.last_node.type == 'wood'
                        and w.state in (State.GATHERING, State.RETURNING)]

        for unit in workers:
            if unit.state not in (State.IDLE,) and unit.gather_node:
                continue  # already assigned
            if unit.state == State.IDLE:
                # Decide: gold or wood?
                if len(gold_workers) < gold_target:
                    self._send_gather(unit, game, 'gold')
                    gold_workers.append(unit)
                elif len(wood_workers) < wood_target:
                    self._send_gather(unit, game, 'wood')
                    wood_workers.append(unit)
                else:
                    self._send_gather(unit, game, 'gold')
                    gold_workers.append(unit)

    def _send_gather(self, unit, game, preferred='gold'):
        fallback = 'wood' if preferred == 'gold' else 'gold'
        node = game.game_map.find_nearest_resource(unit.tx, unit.ty, preferred)
        if node is None or node.depleted:
            node = game.game_map.find_nearest_resource(unit.tx, unit.ty, fallback)
        if node:
            unit.give_command(CmdData(Cmd.GATHER, resource=node))

    # ---------------------------------------------------------------- training
    def _update_training(self, game, player):
        n_workers  = sum(1 for u in player.units if u.utype == 'worker' and u.alive)
        n_military = sum(1 for u in player.units
                         if u.utype in ('soldier', 'archer', 'knight') and u.alive)

        for bld in player.buildings:
            if not bld.is_constructed or not bld.alive:
                continue
            if len(bld.train_queue) >= 3:
                continue
            trainable = bld.trainable_units(player)
            if not trainable:
                continue

            if bld.btype == 'town_hall':
                # Keep up to 8 workers; more when economy is low
                want_workers = 8 if n_military > 4 else 10
                if n_workers < want_workers:
                    bld.train_unit('worker', player)

            elif bld.btype == 'barracks':
                # Mix soldiers and keep training
                bld.train_unit('soldier', player)

            elif bld.btype == 'archery_range':
                # Prefer archers early; knights when unlocked and wave >= 3
                if 'unlock_knight' in player.techs and self.wave_num >= 3:
                    if not bld.train_unit('knight', player):
                        bld.train_unit('archer', player)
                else:
                    bld.train_unit('archer', player)

    # ---------------------------------------------------------------- building
    def _maybe_build(self, game, player):
        # Any worker that is idle or gathering can be recruited
        worker = next((u for u in player.units
                       if u.utype == 'worker' and u.alive
                       and u.state in (State.IDLE, State.GATHERING, State.RETURNING)), None)
        if worker is None:
            return

        n_farm     = self._count_buildings(player, 'farm')
        n_lumber   = self._count_buildings(player, 'lumber_mill')
        n_mine     = self._count_buildings(player, 'mine')
        n_barracks = self._count_buildings(player, 'barracks')
        n_archery  = self._count_buildings(player, 'archery_range')
        n_academy  = self._count_buildings(player, 'academy')
        n_tower    = self._count_buildings(player, 'tower')
        n_military = sum(1 for u in player.units
                         if u.utype in ('soldier', 'archer', 'knight') and u.alive)

        # Priority build order
        want = None
        if n_farm == 0 and player.can_afford_building('farm'):
            want = 'farm'
        elif n_lumber == 0 and player.can_afford_building('lumber_mill'):
            want = 'lumber_mill'
        elif n_mine == 0 and player.can_afford_building('mine'):
            want = 'mine'
        elif n_barracks == 0 and player.can_afford_building('barracks'):
            want = 'barracks'
        elif n_archery == 0 and n_barracks > 0 and player.can_afford_building('archery_range'):
            want = 'archery_range'
        elif n_academy == 0 and n_military >= 4 and player.can_afford_building('academy'):
            want = 'academy'
        elif n_tower < 2 and n_barracks > 0 and player.can_afford_building('tower'):
            want = 'tower'
        elif n_farm < 3 and player.can_afford_building('farm'):
            want = 'farm'
        elif n_barracks < 2 and player.can_afford_building('barracks'):
            want = 'barracks'

        if want:
            spot = self._find_build_spot(game, player, want)
            if spot:
                bld = game.place_building(want, spot[0], spot[1], self.team)
                if bld:
                    worker.give_command(CmdData(Cmd.BUILD, building=bld))

    def _count_buildings(self, player, btype):
        return sum(1 for b in player.buildings if b.btype == btype and b.alive)

    def _find_build_spot(self, game, player, btype):
        from constants import BUILDING_SIZES
        th = next((b for b in player.buildings if b.btype == 'town_hall' and b.is_constructed),
                  next((b for b in player.buildings if b.btype == 'town_hall'), None))
        if th is None:
            return None
        cx, cy = th.tx + th.w_tiles // 2, th.ty + th.h_tiles // 2

        # Towers go close to base; other buildings a bit further
        r_min = 3 if btype == 'tower' else 5
        r_max = 8 if btype == 'tower' else 14

        for _ in range(100):
            r = random.randint(r_min, r_max)
            a = random.uniform(0, 2 * math.pi)
            tx = cx + int(r * math.cos(a))
            ty = cy + int(r * math.sin(a))
            if game.can_place_building(btype, tx, ty):
                return (tx, ty)
        return None

    # ---------------------------------------------------------------- research
    def _maybe_research(self, game, player):
        academy = next((b for b in player.buildings
                        if b.btype == 'academy' and b.is_constructed and b.alive), None)
        if academy is None:
            return
        # Research priority
        priority = ['iron_weapons', 'leather_armor', 'unlock_knight',
                    'ballistics', 'steel_armor', 'improved_gathering']
        for tech in priority:
            if tech not in player.techs and tech not in academy.research_queue:
                ok, _ = academy.can_research(tech, player)
                if ok:
                    academy.start_research(tech, player)
                    break

    # ---------------------------------------------------------------- defence
    def _maybe_defend(self, game, player):
        """If the AI base is under attack, rally nearby fighters to defend."""
        th = next((b for b in player.buildings if b.btype == 'town_hall' and b.alive), None)
        if th is None:
            return

        # Check for enemy units near our base (from any enemy team)
        base_cx, base_cy = th.x, th.y
        DEFEND_RADIUS = 12 * TILE_SIZE
        threats = []
        for tid, p in game.players.items():
            if tid == self.team or tid == NEUTRAL_TEAM:
                continue
            threats.extend(u for u in p.units
                           if u.alive and math.hypot(u.x - base_cx, u.y - base_cy) < DEFEND_RADIUS)
        if not threats:
            return

        # Rally any idle fighters toward the closest threat
        closest = min(threats, key=lambda u: math.hypot(u.x - base_cx, u.y - base_cy))
        defenders = [u for u in player.units
                     if u.alive and u.utype in ('soldier', 'archer', 'knight')
                     and u.state == State.IDLE]
        for d in defenders:
            d.give_command(CmdData(Cmd.ATTACK, target=closest))

    # ---------------------------------------------------------------- attack
    def _maybe_attack(self, game, player):
        # In KotH mode, use hill-focused strategy
        if getattr(game, 'game_mode', 'standard') == 'king_of_hill':
            self._maybe_attack_koth(game, player)
            return

        interval = max(40.0, self.attack_interval - self.wave_num * 6) * self.attack_delay
        if self.attack_timer < interval:
            return
        self.attack_timer = 0.0
        self.wave_num    += 1

        fighters = [u for u in player.units
                    if u.alive and u.utype in ('soldier', 'archer', 'knight')
                    and u.state == State.IDLE]

        min_needed = max(3, self.wave_num * 2)
        if len(fighters) < min_needed:
            return

        # Target the closest enemy building to our fighters' centroid
        if not fighters:
            return
        cx = sum(u.x for u in fighters) / len(fighters)
        cy = sum(u.y for u in fighters) / len(fighters)
        # Gather targets from all enemy teams
        targets = []
        for tid, p in game.players.items():
            if tid == self.team or tid == NEUTRAL_TEAM:
                continue
            targets.extend(b for b in p.buildings if b.alive and b.is_constructed)
        if not targets:
            for tid, p in game.players.items():
                if tid == self.team or tid == NEUTRAL_TEAM:
                    continue
                targets.extend(b for b in p.buildings if b.alive)
        if not targets:
            return
        target_bld = min(targets, key=lambda b: math.hypot(b.x - cx, b.y - cy))

        for unit in fighters:
            unit.give_command(CmdData(Cmd.ATTACK, target=target_bld))

    def _maybe_attack_koth(self, game, player):
        """KotH AI: prioritise holding the hill; attack enemies on it."""
        hill_wx = game._koth_cx * TILE_SIZE + TILE_SIZE // 2
        hill_wy = game._koth_cy * TILE_SIZE + TILE_SIZE // 2
        hill_r  = game._koth_radius * TILE_SIZE

        fighters = [u for u in player.units
                    if u.alive and u.utype in ('soldier', 'archer', 'knight')]

        # Count our troops already on the hill
        on_hill = [u for u in fighters
                   if math.hypot(u.x - hill_wx, u.y - hill_wy) < hill_r]
        idle    = [u for u in fighters if u.state == State.IDLE]

        # Check if an enemy is contesting the hill
        enemy_on_hill = []
        for tid, p in game.players.items():
            if tid == self.team or tid == NEUTRAL_TEAM:
                continue
            enemy_on_hill.extend(
                u for u in p.units
                if u.alive and u.utype != 'worker'
                and math.hypot(u.x - hill_wx, u.y - hill_wy) < hill_r)

        # Urgent: enemy holds the hill — send everyone available
        if enemy_on_hill and idle:
            target = min(enemy_on_hill,
                         key=lambda u: math.hypot(u.x - hill_wx, u.y - hill_wy))
            for u in idle:
                u.give_command(CmdData(Cmd.ATTACK, target=target))
            return

        # If we have fewer than 3 troops on the hill, send idle fighters there
        if len(on_hill) < 3 and idle:
            for u in idle:
                u.give_command(CmdData(Cmd.ATTACK_MOVE,
                                       wx=hill_wx, wy=hill_wy))
            return

        # Otherwise, with the hill held, use excess idle fighters to harass
        interval = max(40.0, self.attack_interval - self.wave_num * 6) * self.attack_delay
        if self.attack_timer < interval:
            return
        self.attack_timer = 0.0
        self.wave_num += 1

        excess = [u for u in idle if u not in on_hill]
        if len(excess) < 3:
            return

        # Attack-move toward enemy buildings
        targets = []
        for tid, p in game.players.items():
            if tid == self.team or tid == NEUTRAL_TEAM:
                continue
            targets.extend(b for b in p.buildings if b.alive and b.is_constructed)
        if not targets:
            return
        cx = sum(u.x for u in excess) / len(excess)
        cy = sum(u.y for u in excess) / len(excess)
        target_bld = min(targets, key=lambda b: math.hypot(b.x - cx, b.y - cy))
        for u in excess:
            u.give_command(CmdData(Cmd.ATTACK, target=target_bld))

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
