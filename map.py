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
            game_map.tiles[self.tx][self.ty] = TILE_DIRT
        return taken


class GameMap:
    def __init__(self, seed=None, width=None, height=None, start_positions=None):
        if seed is not None:
            random.seed(seed)

        self.width    = width or MAP_W
        self.height   = height or MAP_H
        self._start_positions = start_positions or []
        self.tiles    = [[TILE_GRASS] * self.height for _ in range(self.width)]
        self.passable = [[True]       * self.height for _ in range(self.width)]
        self.buildable= [[True]       * self.height for _ in range(self.width)]
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
        if self._start_positions:
            for sx, sy in self._start_positions:
                self._clear_area(sx + 2, sy + 2, 10)
        else:
            self._clear_area(5,  5,  10)
            self._clear_area(self.width - 6, self.height - 6, 10)
        self._place_gold()
        self._update_passability()

    def _place_water(self):
        for _ in range(max(2, self.width * self.height // 2700)):
            cx = random.randint(20, self.width - 20)
            cy = random.randint(20, self.height - 20)
            r  = random.randint(3, 6)
            for x in range(cx - r - 1, cx + r + 2):
                for y in range(cy - r - 1, cy + r + 2):
                    if 0 <= x < self.width and 0 <= y < self.height:
                        if math.hypot(x - cx, y - cy) < r + random.uniform(-1, 1.2):
                            self.tiles[x][y] = TILE_WATER

    def _place_rocks(self):
        for _ in range(max(4, self.width * self.height // 1800)):
            cx = random.randint(8, self.width - 8)
            cy = random.randint(8, self.height - 8)
            for _ in range(random.randint(2, 6)):
                x = cx + random.randint(-2, 2)
                y = cy + random.randint(-2, 2)
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.tiles[x][y] = TILE_ROCK

    def _place_forests(self):
        count = max(15, self.width * self.height // 415)
        for _ in range(count):
            cx = random.randint(4, self.width - 4)
            cy = random.randint(4, self.height - 4)
            r  = random.randint(2, 6)
            for x in range(cx - r - 1, cx + r + 2):
                for y in range(cy - r - 1, cy + r + 2):
                    if 0 <= x < self.width and 0 <= y < self.height:
                        if self.tiles[x][y] == TILE_GRASS:
                            if math.hypot(x - cx, y - cy) < r * 0.85 + random.uniform(-0.8, 0.8):
                                self.tiles[x][y] = TILE_FOREST
                                self.resources[(x, y)] = ResourceNode(
                                    x, y, 'wood', random.randint(100, 200))

    def _place_gold(self):
        def near(base_x, base_y, spread=4):
            return (base_x + random.randint(-spread, spread),
                    base_y + random.randint(-spread, spread))

        spots = [
            near(17, 6),  near(6, 17),
            near(self.width - 18, self.height - 7),
            near(self.width - 7, self.height - 18),
        ]

        for _ in range(max(2, self.width * self.height // 5400)):
            spots.append((
                random.randint(self.width // 4, self.width * 3 // 4),
                random.randint(self.height // 4, self.height * 3 // 4),
            ))

        for (gx, gy) in spots:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    x, y = gx + dx, gy + dy
                    if 0 <= x < self.width and 0 <= y < self.height:
                        if self.tiles[x][y] == TILE_GRASS:
                            self.tiles[x][y] = TILE_GOLD
                            self.resources[(x, y)] = ResourceNode(
                                x, y, 'gold', random.randint(300, 500))

    def _clear_area(self, cx, cy, radius):
        for x in range(max(0, cx - radius), min(self.width, cx + radius + 1)):
            for y in range(max(0, cy - radius), min(self.height, cy + radius + 1)):
                if math.hypot(x - cx, y - cy) <= radius:
                    self.tiles[x][y] = TILE_GRASS
                    self.resources.pop((x, y), None)

    def _update_passability(self):
        for x in range(self.width):
            for y in range(self.height):
                t = self.tiles[x][y]
                ok = t not in (TILE_WATER, TILE_FOREST, TILE_GOLD, TILE_ROCK)
                self.passable[x][y]  = ok
                self.buildable[x][y] = ok

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def is_passable(self, tx, ty):
        if tx < 0 or tx >= self.width or ty < 0 or ty >= self.height:
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
        if tx < 0 or tx >= self.width or ty < 0 or ty >= self.height:
            return False
        return self.buildable[tx][ty]

    def set_passable(self, tx, ty, val):
        if 0 <= tx < self.width and 0 <= ty < self.height:
            self.passable[tx][ty] = val

    def set_buildable(self, tx, ty, val):
        if 0 <= tx < self.width and 0 <= ty < self.height:
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
                if 0 <= x < self.width and 0 <= y < self.height:
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
