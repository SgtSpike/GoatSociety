import random
import math
from constants import *


class ResourceNode:
    def __init__(self, tx, ty, rtype, amount):
        self.tx     = tx
        self.ty     = ty
        self.type   = rtype   # 'wood' or 'gold'
        self.amount = amount
        self.max_amount = amount
        self.gatherers = []   # Unit refs currently at this node

    @property
    def depleted(self):
        return self.amount <= 0

    def gather(self, amount, game_map=None):
        taken = min(self.amount, amount)
        self.amount -= taken
        if self.depleted and game_map is not None:
            game_map.set_passable(self.tx, self.ty, True)
            game_map.set_buildable(self.tx, self.ty, True)
        return taken


class GameMap:
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)

        self.width    = MAP_W
        self.height   = MAP_H
        self.tiles    = [[TILE_GRASS] * MAP_H for _ in range(MAP_W)]
        self.passable = [[True]       * MAP_H for _ in range(MAP_W)]
        self.buildable= [[True]       * MAP_H for _ in range(MAP_W)]
        self.resources= {}          # (tx, ty) -> ResourceNode
        self.gates    = {}          # (tx, ty) -> owner_team  (passable for owner, blocked for enemies)
        self.explored = set()       # tiles ever seen by player
        self.visible  = set()       # tiles visible THIS frame

        self._generate()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def _generate(self):
        self._place_water()
        self._place_rocks()
        self._place_forests()
        # Clear start areas BEFORE placing gold so near-base mines are not wiped
        self._clear_area(5,  5,  10)
        self._clear_area(MAP_W - 6, MAP_H - 6, 10)
        self._place_gold()
        self._update_passability()

    def _place_water(self):
        for _ in range(4):
            cx = random.randint(20, MAP_W - 20)
            cy = random.randint(20, MAP_H - 20)
            r  = random.randint(3, 6)
            for x in range(cx - r - 1, cx + r + 2):
                for y in range(cy - r - 1, cy + r + 2):
                    if 0 <= x < MAP_W and 0 <= y < MAP_H:
                        if math.hypot(x - cx, y - cy) < r + random.uniform(-1, 1.2):
                            self.tiles[x][y] = TILE_WATER

    def _place_rocks(self):
        for _ in range(6):
            cx = random.randint(8, MAP_W - 8)
            cy = random.randint(8, MAP_H - 8)
            for _ in range(random.randint(2, 6)):
                x = cx + random.randint(-2, 2)
                y = cy + random.randint(-2, 2)
                if 0 <= x < MAP_W and 0 <= y < MAP_H:
                    self.tiles[x][y] = TILE_ROCK

    def _place_forests(self):
        for _ in range(26):   # more forest clusters
            cx = random.randint(4, MAP_W - 4)
            cy = random.randint(4, MAP_H - 4)
            r  = random.randint(2, 6)   # slightly larger max radius
            for x in range(cx - r - 1, cx + r + 2):
                for y in range(cy - r - 1, cy + r + 2):
                    if 0 <= x < MAP_W and 0 <= y < MAP_H:
                        if self.tiles[x][y] == TILE_GRASS:
                            if math.hypot(x - cx, y - cy) < r * 0.85 + random.uniform(-0.8, 0.8):
                                self.tiles[x][y] = TILE_FOREST
                                self.resources[(x, y)] = ResourceNode(
                                    x, y, 'wood', random.randint(100, 200))

    def _place_gold(self):
        # Fixed near-base deposits (guaranteed for both teams)
        # Randomised slightly so they aren't always in exactly the same spot
        def near(base_x, base_y, spread=4):
            return (base_x + random.randint(-spread, spread),
                    base_y + random.randint(-spread, spread))

        spots = [
            near(17, 6),  near(6, 17),                               # player base
            near(MAP_W - 18, MAP_H - 7), near(MAP_W - 7, MAP_H - 18),  # AI base
        ]

        # Two extra random mid-map deposits
        for _ in range(2):
            spots.append((
                random.randint(MAP_W // 4, MAP_W * 3 // 4),
                random.randint(MAP_H // 4, MAP_H * 3 // 4),
            ))

        for (gx, gy) in spots:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    x, y = gx + dx, gy + dy
                    if 0 <= x < MAP_W and 0 <= y < MAP_H:
                        if self.tiles[x][y] == TILE_GRASS:
                            self.tiles[x][y] = TILE_GOLD
                            self.resources[(x, y)] = ResourceNode(
                                x, y, 'gold', random.randint(300, 500))

    def _clear_area(self, cx, cy, radius):
        for x in range(max(0, cx - radius), min(MAP_W, cx + radius + 1)):
            for y in range(max(0, cy - radius), min(MAP_H, cy + radius + 1)):
                if math.hypot(x - cx, y - cy) <= radius:
                    self.tiles[x][y] = TILE_GRASS
                    self.resources.pop((x, y), None)

    def _update_passability(self):
        for x in range(MAP_W):
            for y in range(MAP_H):
                t = self.tiles[x][y]
                ok = t not in (TILE_WATER, TILE_FOREST, TILE_GOLD, TILE_ROCK)
                self.passable[x][y]  = ok
                self.buildable[x][y] = ok

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def is_passable(self, tx, ty):
        if tx < 0 or tx >= MAP_W or ty < 0 or ty >= MAP_H:
            return False
        return self.passable[tx][ty]

    def is_passable_for(self, tx, ty, team):
        """Like is_passable, but also blocks enemy gate tiles."""
        if not self.is_passable(tx, ty):
            return False
        gate_team = self.gates.get((tx, ty))
        if gate_team is not None and gate_team != team:
            return False
        return True

    def is_buildable(self, tx, ty):
        if tx < 0 or tx >= MAP_W or ty < 0 or ty >= MAP_H:
            return False
        return self.buildable[tx][ty]

    def set_passable(self, tx, ty, val):
        if 0 <= tx < MAP_W and 0 <= ty < MAP_H:
            self.passable[tx][ty] = val

    def set_buildable(self, tx, ty, val):
        if 0 <= tx < MAP_W and 0 <= ty < MAP_H:
            self.buildable[tx][ty] = val

    def get_resource(self, tx, ty):
        return self.resources.get((tx, ty))

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------
    def update_visibility(self, player_units, player_buildings):
        """Rebuild visible set from current player unit/building positions."""
        self.visible = set()
        for u in player_units:
            self._reveal_circle(u.tx, u.ty, u.sight)
        for b in player_buildings:
            if b.is_constructed:
                self._reveal_circle(b.tx + b.w_tiles // 2,
                                    b.ty + b.h_tiles // 2, 4)

    def _reveal_circle(self, cx, cy, radius):
        r2 = radius * radius
        for x in range(int(cx - radius) - 1, int(cx + radius) + 2):
            for y in range(int(cy - radius) - 1, int(cy + radius) + 2):
                if 0 <= x < MAP_W and 0 <= y < MAP_H:
                    if (x - cx)**2 + (y - cy)**2 <= r2:
                        self.visible.add((x, y))
                        self.explored.add((x, y))

    def is_visible(self, tx, ty):
        if not FOG_OF_WAR:
            return True
        return (tx, ty) in self.visible

    def is_explored(self, tx, ty):
        if not FOG_OF_WAR:
            return True
        return (tx, ty) in self.explored

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def world_to_tile(self, wx, wy):
        return int(wx // TILE_SIZE), int(wy // TILE_SIZE)

    def tile_center(self, tx, ty):
        return tx * TILE_SIZE + TILE_SIZE // 2, ty * TILE_SIZE + TILE_SIZE // 2

    def find_nearest_resource(self, tx, ty, rtype, max_radius=30):
        best, best_d = None, float('inf')
        for (rx, ry), node in self.resources.items():
            if node.type == rtype and not node.depleted:
                d = math.hypot(rx - tx, ry - ty)
                if d < best_d:
                    best_d, best = d, node
        return best
