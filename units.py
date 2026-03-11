import math
import random
from collections import deque
import pygame
from entities import Entity
from commands import Cmd, CmdData
from constants import (TILE_SIZE, UNIT_STATS, WOOD_PER_TRIP, GOLD_PER_TRIP,
                       GATHER_TIME, MAP_W, MAP_H, PLAYER_TEAM)
import pathfinding as pf
try:
    import sounds
except Exception:
    class sounds:  # type: ignore
        @staticmethod
        def play(*a, **kw): pass


class State:
    IDLE      = 'idle'
    MOVING    = 'moving'
    ATTACKING = 'attacking'
    GATHERING = 'gathering'
    RETURNING = 'returning'
    BUILDING  = 'building'


class Unit(Entity):
    def __init__(self, utype, wx, wy, team):
        super().__init__(team)
        self.utype   = utype
        stats        = UNIT_STATS[utype]
        self.hp      = stats['hp']
        self.max_hp  = stats['hp']
        self.attack_dmg   = stats['attack']
        self.attack_speed = stats['attack_speed']
        self.attack_range = stats['range'] * TILE_SIZE
        self.speed        = stats['speed']   # pixels/sec
        self.sight        = stats['sight']   # tiles
        self.armor        = stats['armor']

        # position (world pixels, center)
        self.x = float(wx)
        self.y = float(wy)

        self.state       = State.IDLE
        self.cmd_queue   = deque()
        self.cur_cmd     = None

        # movement
        self._path       = []
        self._path_idx   = 0
        self._needs_path = False
        self._path_goal  = None

        # combat
        self.atk_cd       = 0.0
        self.atk_target   = None   # Entity ref
        self._path_cd     = 0.0   # cooldown before next path recompute

        # gathering
        self.gather_node  = None
        self.gather_prog  = 0.0
        self.carry_wood   = 0
        self.carry_gold   = 0
        self.last_node    = None

        # building
        self.build_target = None

        # tech bonuses (applied externally)
        self.dmg_bonus    = 0
        self.armor_bonus  = 0
        self.gather_bonus = 0
        self.speed_bonus  = 0

        # visuals
        self.anim_t = 0.0
        self.flip_h = False

        # stuck / yield state
        self._stuck_t  = 0.0
        self._wait_t   = 0.0   # > 0 while yielding to let other units pass
        self._prev_x   = float(wx)
        self._prev_y   = float(wy)

    # tx/ty inherited from Entity use self.x, self.y — correct for units

    def get_rect(self):
        r = TILE_SIZE // 2 - 3
        return pygame.Rect(self.x - r, self.y - r, r * 2, r * 2)

    # ---------------------------------------------------------------- commands
    def give_command(self, cmd, queue=False):
        if not queue:
            self.cmd_queue.clear()
            self.cur_cmd = None
            self._path   = []
            self.atk_target = None
        self.cmd_queue.append(cmd)
        if not queue or self.cur_cmd is None:
            self._next_command()

    def _next_command(self):
        if self.cmd_queue:
            self.cur_cmd = self.cmd_queue.popleft()
            self._exec(self.cur_cmd)
        else:
            self.cur_cmd = None
            self.state = State.IDLE

    def _exec(self, cmd):
        if cmd.type == Cmd.MOVE:
            self._start_move(cmd.wx, cmd.wy)
        elif cmd.type == Cmd.ATTACK:
            self.atk_target = cmd.target
            self.state = State.ATTACKING
        elif cmd.type == Cmd.ATTACK_MOVE:
            self._start_move(cmd.wx, cmd.wy)
            self.state = State.MOVING   # will auto-attack while moving
        elif cmd.type == Cmd.GATHER:
            self.gather_node = cmd.resource
            self.last_node   = cmd.resource
            self.state = State.GATHERING
        elif cmd.type == Cmd.BUILD:
            self.build_target = cmd.building
            self.state = State.BUILDING
        elif cmd.type == Cmd.STOP:
            self.state = State.IDLE
            self._path = []
            self.atk_target = None

    def _start_move(self, wx, wy):
        self._path_goal  = (int(wx // TILE_SIZE), int(wy // TILE_SIZE))
        self._needs_path = True
        self.state = State.MOVING

    def stop(self):
        self.cmd_queue.clear()
        self.cur_cmd = None
        self._path = []
        self.atk_target = None
        self.state = State.IDLE

    # ----------------------------------------------------------------- update
    def update(self, dt, game):
        self.anim_t += dt

        if self.atk_cd > 0:
            self.atk_cd -= dt
        if self._path_cd > 0:
            self._path_cd -= dt

        if self.state == State.IDLE:
            self._idle_ai(game)
        elif self.state == State.MOVING:
            self._update_move(dt, game)
        elif self.state == State.ATTACKING:
            self._update_attack(dt, game)
        elif self.state == State.GATHERING:
            self._update_gather(dt, game)
        elif self.state == State.RETURNING:
            self._update_return(dt, game)
        elif self.state == State.BUILDING:
            self._update_build(dt, game)

        self._apply_separation(dt, game)

    def _apply_separation(self, dt, game):
        """Gently push this unit away from overlapping units and break deadlocks."""
        SEP = TILE_SIZE * 0.80
        for other in game.all_units():
            if other is self:
                continue
            dx = self.x - other.x
            dy = self.y - other.y
            dist_sq = dx * dx + dy * dy
            if 0 < dist_sq < SEP * SEP:
                dist = math.sqrt(dist_sq)
                push = (SEP - dist) * 0.40
                # Radial push away from other unit
                nx = self.x + (dx / dist) * push
                ny = self.y + (dy / dist) * push
                # Add a small perpendicular nudge so head-on units slide past
                # instead of just pushing each other straight back.  The sign
                # is consistent per pair (based on id) so the two units nudge
                # in opposite perpendicular directions.
                sign = 1 if id(self) > id(other) else -1
                nx += (-dy / dist) * push * 0.4 * sign
                ny += ( dx / dist) * push * 0.4 * sign
                ntx, nty = int(nx // TILE_SIZE), int(ny // TILE_SIZE)
                if game.game_map.is_passable_for(ntx, nty, self.team):
                    self.x, self.y = nx, ny

        # Stuck detection: if actively moving but making no progress,
        # sidestep one tile perpendicular to the path so the other unit can
        # pass, then recompute.
        if self.state in (State.MOVING, State.GATHERING, State.RETURNING) and self._wait_t <= 0:
            moved = math.hypot(self.x - self._prev_x, self.y - self._prev_y)
            if moved < 1.0:
                self._stuck_t += dt
            else:
                self._stuck_t = 0.0
            if self._stuck_t >= 0.35:
                self._stuck_t = 0.0
                self._wait_t = random.uniform(0.2, 0.5)
                self._try_sidestep(game)

        self._prev_x, self._prev_y = self.x, self.y

    def _try_sidestep(self, game):
        """Step one tile perpendicular to the current path to clear the way."""
        if not self._path or self._path_idx >= len(self._path):
            return
        goal_tile = self._path[self._path_idx]
        dir_x = goal_tile[0] - self.tx
        dir_y = goal_tile[1] - self.ty
        if dir_x == 0 and dir_y == 0:
            return
        # Two perpendicular directions; try in random order
        perps = [(-dir_y, dir_x), (dir_y, -dir_x)]
        random.shuffle(perps)
        for pdx, pdy in perps:
            mx = (1 if pdx > 0 else -1) if pdx != 0 else 0
            my = (1 if pdy > 0 else -1) if pdy != 0 else 0
            ntx, nty = self.tx + mx, self.ty + my
            if game.game_map.is_passable_for(ntx, nty, self.team):
                self.x = ntx * TILE_SIZE + TILE_SIZE // 2
                self.y = nty * TILE_SIZE + TILE_SIZE // 2
                self._path = []   # force recompute after sidestep
                self._path_cd = 0.0
                return

    def _idle_ai(self, game):
        if self.utype != 'worker':
            en = self._nearest_enemy(game)
            # _nearest_enemy already filters to sight range; if any enemy is visible,
            # switch to attacking — _update_attack will chase if not yet in range.
            if en:
                self.atk_target = en
                self.state = State.ATTACKING

    # ---------------------------------------------------------------- movement
    def _update_move(self, dt, game):
        # Yield: pause briefly to let blocking units pass, then recompute path
        if self._wait_t > 0:
            self._wait_t -= dt
            if self._wait_t <= 0:
                self._needs_path = True   # recompute from current position
            return

        if self._needs_path:
            self._needs_path = False
            start = (self.tx, self.ty)
            self._path     = pf.astar(game.game_map, start, self._path_goal, self.team)
            self._path_idx = 0

        if not self._path or self._path_idx >= len(self._path):
            self.state = State.IDLE
            self._next_command()
            return

        # auto-attack while moving (attack-move behavior for combat units)
        if self.utype != 'worker' and self.cur_cmd and self.cur_cmd.type == Cmd.ATTACK_MOVE:
            en = self._nearest_enemy(game)
            if en and self.distance_to(en) <= self.attack_range + TILE_SIZE:
                self.atk_target = en
                self.state = State.ATTACKING
                return

        self._step_path(dt)

    def _step_path(self, dt):
        if not self._path or self._path_idx >= len(self._path):
            return False
        goal_tile = self._path[self._path_idx]
        gx = goal_tile[0] * TILE_SIZE + TILE_SIZE // 2
        gy = goal_tile[1] * TILE_SIZE + TILE_SIZE // 2
        dx, dy = gx - self.x, gy - self.y
        dist = math.hypot(dx, dy)
        if dist < 2.0:
            self.x, self.y = gx, gy
            self._path_idx += 1
        else:
            spd = (self.speed + self.speed_bonus) * dt
            move = min(spd, dist)
            self.x += dx / dist * move
            self.y += dy / dist * move
            self.flip_h = dx < 0
        return True

    # ----------------------------------------------------------------- combat
    def _update_attack(self, dt, game):
        t = self.atk_target
        if t is None or not t.alive:
            self.atk_target = None
            self.state = State.IDLE
            self._next_command()
            return

        dist = self.distance_to(t)
        threshold = self.attack_range + TILE_SIZE

        if dist > threshold:
            # Chase - throttle path recompute to reduce CPU cost
            goal = (t.tx, t.ty)
            path_stale = (not self._path or self._path_idx >= len(self._path))
            goal_moved = (self._path_goal is not None and
                          self._path_goal != goal and
                          math.hypot(self._path_goal[0]-goal[0],
                                     self._path_goal[1]-goal[1]) > 2)
            if (path_stale or goal_moved) and self._path_cd <= 0:
                self._path_goal  = goal
                self._path = pf.astar(game.game_map, (self.tx, self.ty), goal, self.team)
                self._path_idx = 0
                self._path_cd = 0.5   # wait 0.5s before recomputing again
            self._step_path(dt)
        else:
            self._path = []
            if self.atk_cd <= 0:
                self._do_attack(t, game)
                self.atk_cd = 1.0 / self.attack_speed

    def _do_attack(self, target, game):
        dmg = self.attack_dmg + self.dmg_bonus
        if self.utype == 'archer':
            game.spawn_projectile(self.x, self.y, target, dmg)
            if self.team == PLAYER_TEAM:
                sounds.play('arrow_fire')
        else:
            was_alive = target.alive
            target.take_damage(dmg)
            game.add_attack_event(target.x, target.y, target.team)
            if self.team == PLAYER_TEAM:
                sounds.play('attack_melee')
            if was_alive and not target.alive:
                sounds.play('unit_death')

    # --------------------------------------------------------------- gathering
    def _update_gather(self, dt, game):
        node = self.gather_node
        if node is None or node.depleted:
            alt = game.game_map.find_nearest_resource(
                self.tx, self.ty,
                node.type if node else 'wood')
            if alt:
                self.gather_node = alt
                self.last_node   = alt
                # Reset path so the unit heads toward the new node immediately
                self._path    = []
                self._path_cd = 0.0
                node = alt
            else:
                self.state = State.IDLE
                return

        # Move adjacent to resource tile
        rtx, rty = node.tx, node.ty
        adj_cx = rtx * TILE_SIZE + TILE_SIZE // 2
        adj_cy = rty * TILE_SIZE + TILE_SIZE // 2
        dist = math.hypot(self.x - adj_cx, self.y - adj_cy)

        # "at goal" = worker arrived at the adjacent tile it was heading for
        at_goal = (self._path_goal is not None and
                   (self.tx, self.ty) == self._path_goal)
        need_move = dist > TILE_SIZE * 1.6 and not at_goal

        if need_move:
            if self._wait_t > 0:
                self._wait_t -= dt
                if self._wait_t <= 0:
                    self._path = []
                    self._path_cd = 0.0
                return
            goal = pf.adjacent_passable(game.game_map, rtx, rty)
            if goal is None:
                self.state = State.IDLE
                return
            if ((not self._path or self._path_idx >= len(self._path) or
                    self._path_goal != goal) and self._path_cd <= 0):
                self._path_goal = goal
                self._path = pf.astar(game.game_map, (self.tx, self.ty), goal, self.team)
                self._path_idx = 0
                self._path_cd = 0.3
            self._step_path(dt)
        else:
            self._path = []
            rate = GATHER_TIME
            self.gather_prog += dt / rate
            if self.gather_prog >= 1.0:
                self.gather_prog = 0.0
                amount = WOOD_PER_TRIP + self.gather_bonus \
                    if node.type == 'wood' else GOLD_PER_TRIP + self.gather_bonus
                taken = node.gather(amount, game.game_map)
                if node.type == 'wood':
                    self.carry_wood += taken
                    if self.team == PLAYER_TEAM:
                        sounds.play('chop')
                else:
                    self.carry_gold += taken
                    if self.team == PLAYER_TEAM:
                        sounds.play('clink')
                if node.depleted:
                    sounds.play('resource_depleted')
                self.state = State.RETURNING

    def _update_return(self, dt, game):
        rtype = 'wood' if self.carry_wood else 'gold'
        storage = game.nearest_storage(self.tx, self.ty, self.team, rtype=rtype)
        if storage is None:
            self.state = State.IDLE
            return

        # Distance to nearest edge of the building rect (not just its center)
        br = storage.get_rect()
        cx = max(br.left, min(br.right,  self.x))
        cy = max(br.top,  min(br.bottom, self.y))
        dist = math.hypot(self.x - cx, self.y - cy)

        if dist > TILE_SIZE * 1.5:
            if self._wait_t > 0:
                self._wait_t -= dt
                if self._wait_t <= 0:
                    self._path = []
                    self._path_cd = 0.0
                return
            goal = self._nearest_storage_tile(game, storage)
            if goal and (not self._path or self._path_idx >= len(self._path) or
                         self._path_goal != goal) and self._path_cd <= 0:
                self._path_goal = goal
                self._path = pf.astar(game.game_map, (self.tx, self.ty), goal, self.team)
                self._path_idx = 0
                self._path_cd = 0.3
            self._step_path(dt)
        else:
            self._path = []
            p = game.players[self.team]
            p.wood += self.carry_wood
            p.gold += self.carry_gold
            self.carry_wood = 0
            self.carry_gold = 0
            # Return to last node, or find a nearby alternative if it's depleted
            if self.last_node and not self.last_node.depleted:
                self.gather_node = self.last_node
                self.state = State.GATHERING
            else:
                rtype = self.last_node.type if self.last_node else 'wood'
                alt = game.game_map.find_nearest_resource(self.tx, self.ty, rtype)
                if alt is None and rtype == 'wood':
                    alt = game.game_map.find_nearest_resource(self.tx, self.ty, 'gold')
                elif alt is None and rtype == 'gold':
                    alt = game.game_map.find_nearest_resource(self.tx, self.ty, 'wood')
                if alt:
                    self.gather_node = alt
                    self.last_node   = alt
                    self._path    = []
                    self._path_cd = 0.0
                    self.state = State.GATHERING
                else:
                    self.state = State.IDLE

    def _nearest_unfinished_building(self, game):
        """Return the nearest unfinished friendly building, or None."""
        best, best_d = None, float('inf')
        for bld in game.players[self.team].buildings:
            if not bld.alive or bld.is_constructed:
                continue
            d = math.hypot(bld.tx - self.tx, bld.ty - self.ty)
            if d < best_d:
                best_d, best = d, bld
        return best

    def _nearest_storage_tile(self, game, storage):
        """Return the passable tile adjacent to the storage building nearest to this unit."""
        DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1,-1), (-1,1), (1,-1), (1,1)]
        best, best_d = None, float('inf')
        for ftx, fty in storage.tile_footprint():
            for dx, dy in DIRS:
                ntx, nty = ftx + dx, fty + dy
                if game.game_map.is_passable(ntx, nty):
                    d = (ntx - self.tx) ** 2 + (nty - self.ty) ** 2
                    if d < best_d:
                        best_d, best = d, (ntx, nty)
        return best

    # --------------------------------------------------------------- building
    def _update_build(self, dt, game):
        bld = self.build_target
        if bld is None or bld.is_constructed:
            self.build_target = None
            next_bld = self._nearest_unfinished_building(game)
            if next_bld:
                self.build_target = next_bld
            else:
                self.state = State.IDLE
                self._next_command()
            return

        # Move near building
        bx = (bld.tx + bld.w_tiles / 2) * TILE_SIZE
        by = (bld.ty + bld.h_tiles / 2) * TILE_SIZE
        reach = TILE_SIZE * (max(bld.w_tiles, bld.h_tiles) / 2 + 1.5)
        dist = math.hypot(self.x - bx, self.y - by)

        if dist > reach:
            goal = pf.adjacent_passable(game.game_map, bld.tx, bld.ty)
            if goal and (not self._path or self._path_idx >= len(self._path)):
                self._path_goal = goal
                self._path = pf.astar(game.game_map, (self.tx, self.ty), goal, self.team)
                self._path_idx = 0
            self._step_path(dt)
        else:
            self._path = []
            bld.construction_progress += dt / bld.build_time
            if bld.construction_progress >= 1.0:
                bld.construction_progress = 1.0
                bld.complete(game)
                self.build_target = None
                # Look for another unfinished building on the same team
                next_bld = self._nearest_unfinished_building(game)
                if next_bld:
                    self.build_target = next_bld
                    # Stay in BUILDING state; loop will handle movement
                else:
                    self.state = State.IDLE
                    self._next_command()

    # --------------------------------------------------------------- helpers
    def _nearest_enemy(self, game):
        best, best_d = None, self.sight * TILE_SIZE * 1.1
        for team, p in game.players.items():
            if team == self.team:
                continue
            for u in p.units:
                if u.alive:
                    d = self.distance_to(u)
                    if d < best_d:
                        best_d, best = d, u
            for b in p.buildings:
                if b.alive and b.is_constructed:
                    d = self.distance_to(b)
                    if d < best_d:
                        best_d, best = d, b
        return best
