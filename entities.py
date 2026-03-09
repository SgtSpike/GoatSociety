import math
from constants import STARTING_WOOD, STARTING_GOLD, BASE_FOOD_CAP, FARM_FOOD_CAP, TILE_SIZE


class Entity:
    _id_ctr = 0

    def __init__(self, team):
        self.id       = Entity._id_ctr
        Entity._id_ctr += 1
        self.team     = team
        self.hp       = 1
        self.max_hp   = 1
        self.alive    = True
        self.selected = False
        self.armor    = 0

    @property
    def tx(self):
        return int(self.x // TILE_SIZE)

    @property
    def ty(self):
        return int(self.y // TILE_SIZE)

    def take_damage(self, amount):
        actual = max(0, amount - self.armor)
        self.hp = max(0, self.hp - actual)
        if self.hp <= 0:
            self.alive = False

    def distance_to(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        return math.sqrt(dx * dx + dy * dy)

    def distance_to_pos(self, wx, wy):
        return math.hypot(self.x - wx, self.y - wy)


class Player:
    def __init__(self, team):
        self.team      = team
        self.wood      = STARTING_WOOD
        self.gold      = STARTING_GOLD
        self.food      = 0          # food currently consumed
        self.food_cap  = BASE_FOOD_CAP
        self.units     = []
        self.buildings = []
        self.techs     = set()      # researched tech IDs
        self.defeated  = False

    def update_food_cap(self):
        cap = BASE_FOOD_CAP
        for b in self.buildings:
            if b.is_constructed and b.btype == 'farm':
                cap += FARM_FOOD_CAP
        self.food_cap = cap

    def recompute_food(self):
        """Derive current food use from living units + training queues."""
        from constants import UNIT_COSTS
        food = sum(UNIT_COSTS.get(u.utype, {}).get('food', 0)
                   for u in self.units if u.alive)
        for b in self.buildings:
            for utype in b.train_queue:
                food += UNIT_COSTS.get(utype, {}).get('food', 0)
        self.food = food

    def can_afford_unit(self, utype):
        from constants import UNIT_COSTS
        cost = UNIT_COSTS.get(utype, {})
        return (self.wood >= cost.get('wood', 0) and
                self.gold >= cost.get('gold', 0) and
                self.food + cost.get('food', 0) <= self.food_cap)

    def pay_unit(self, utype):
        from constants import UNIT_COSTS
        cost = UNIT_COSTS[utype]
        self.wood -= cost.get('wood', 0)
        self.gold -= cost.get('gold', 0)

    def refund_unit(self, utype):
        from constants import UNIT_COSTS
        cost = UNIT_COSTS[utype]
        self.wood += cost.get('wood', 0)
        self.gold += cost.get('gold', 0)

    def can_afford_building(self, btype):
        from constants import BUILDING_COSTS
        cost = BUILDING_COSTS.get(btype, {})
        return (self.wood >= cost.get('wood', 0) and
                self.gold >= cost.get('gold', 0))

    def pay_building(self, btype):
        from constants import BUILDING_COSTS
        cost = BUILDING_COSTS[btype]
        self.wood -= cost.get('wood', 0)
        self.gold -= cost.get('gold', 0)

    def can_afford_tech(self, tech):
        from constants import TECH_COSTS
        cost = TECH_COSTS.get(tech, {})
        return (self.wood >= cost.get('wood', 0) and
                self.gold >= cost.get('gold', 0))

    def pay_tech(self, tech):
        from constants import TECH_COSTS
        cost = TECH_COSTS[tech]
        self.wood -= cost.get('wood', 0)
        self.gold -= cost.get('gold', 0)


class Projectile:
    def __init__(self, x, y, target, damage, speed=320):
        self.x      = float(x)
        self.y      = float(y)
        self.target = target
        self.damage = damage
        self.speed  = speed
        self.alive  = True

    def update(self, dt):
        if not self.target or not self.target.alive:
            self.alive = False
            return
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.hypot(dx, dy)
        if dist < 6:
            self.target.take_damage(self.damage)
            self.alive = False
        else:
            move = min(self.speed * dt, dist)
            self.x += dx / dist * move
            self.y += dy / dist * move
