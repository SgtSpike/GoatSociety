# Goat Society RTS - Constants

SCREEN_W = 1280
SCREEN_H = 768
FPS = 60
TITLE = "Goat Society RTS"

TILE_SIZE = 32
MAP_W = 120   # tiles wide
MAP_H = 90    # tiles tall

# UI Layout
TOP_BAR_H = 44
BOTTOM_PANEL_H = 196
MINIMAP_W = 192
MINIMAP_H = 144

VIEWPORT_X = 0
VIEWPORT_Y = TOP_BAR_H
VIEWPORT_W = SCREEN_W
VIEWPORT_H = SCREEN_H - TOP_BAR_H - BOTTOM_PANEL_H

# Camera
CAMERA_SPEED = 420   # pixels/sec
EDGE_SCROLL_MARGIN = 18

# Teams
PLAYER_TEAM = 0
AI_TEAM = 1
NEUTRAL_TEAM = 99
TEAM_COLORS = {
    0: (80, 140, 230),    # blue (player)
    1: (210, 70, 70),     # red
    2: (60, 190, 60),     # green
    3: (200, 160, 40),    # yellow
    4: (170, 70, 200),    # purple
    5: (220, 130, 50),    # orange
    NEUTRAL_TEAM: (160, 160, 100),   # neutral / wild goats
}

# Tile types
TILE_GRASS  = 0
TILE_WATER  = 1
TILE_FOREST = 2
TILE_GOLD   = 3
TILE_ROCK   = 4
TILE_DIRT   = 5

# Colors
BLACK       = (0,   0,   0)
WHITE       = (255, 255, 255)
GREEN       = (34,  139, 34)
RED         = (200, 50,  50)
BLUE        = (50,  100, 200)
GRAY        = (128, 128, 128)
DARK_GRAY   = (40,  40,  40)
GOLD_COLOR  = (255, 200, 30)
BROWN       = (101, 67,  33)
DARK_GREEN  = (0,   80,  0)
PANEL_BG    = (28,  28,  35)
PANEL_BORD  = (55,  55,  70)
SEL_GREEN   = (0,   255, 0)
HP_RED      = (200, 30,  30)
HP_GREEN    = (30,  200, 30)
HP_YELLOW   = (220, 200, 0)

# Starting resources
STARTING_WOOD = 200
STARTING_GOLD = 150
BASE_FOOD_CAP = 10

# Gather
WOOD_PER_TRIP = 10
GOLD_PER_TRIP = 8
GATHER_TIME   = 2.5   # seconds per trip

# Building sizes (w_tiles, h_tiles)
BUILDING_SIZES = {
    'town_hall':     (4, 3),
    'farm':          (3, 2),
    'lumber_mill':   (2, 2),
    'mine':          (2, 2),
    'barracks':      (3, 2),
    'archery_range': (3, 2),
    'academy':       (3, 3),
    'tower':         (1, 1),
    'wall':          (1, 1),
    'gate':          (1, 1),
}

# Build costs {wood, gold}
BUILDING_COSTS = {
    'farm':          {'wood': 20,  'gold': 10},
    'lumber_mill':   {'wood': 80,  'gold': 30},
    'mine':          {'wood': 60,  'gold': 0},
    'barracks':      {'wood': 120, 'gold': 60},
    'archery_range': {'wood': 120, 'gold': 80},
    'academy':       {'wood': 180, 'gold': 120},
    'tower':         {'wood': 80,  'gold': 40},
    'wall':          {'wood': 4,   'gold': 1},
    'gate':          {'wood': 20,  'gold': 5},
}

# Build times (seconds)
BUILD_TIMES = {
    'town_hall':     0,   # pre-built at game start
    'farm':          18,
    'lumber_mill':   22,
    'mine':          20,
    'barracks':      28,
    'archery_range': 32,
    'academy':       45,
    'tower':         22,
    'wall':          2,
    'gate':          6,
}

# Building HP
BUILDING_HP = {
    'town_hall':     900,
    'farm':          200,
    'lumber_mill':   280,
    'mine':          300,
    'barracks':      450,
    'archery_range': 380,
    'academy':       500,
    'tower':         350,
    'wall':          600,
    'gate':          500,
}

# Units that each building can train
BUILDING_TRAINS = {
    'town_hall':     ['worker'],
    'barracks':      ['soldier'],
    'archery_range': ['archer', 'knight'],
    'academy':       [],
}

# Unit costs {wood, gold, food}
UNIT_COSTS = {
    'worker':  {'wood': 50,  'gold': 0,   'food': 1},
    'soldier': {'wood': 30,  'gold': 60,  'food': 1},
    'archer':  {'wood': 30,  'gold': 80,  'food': 1},
    'knight':  {'wood': 50,  'gold': 120, 'food': 2},
}

# Unit train times (seconds)
TRAIN_TIMES = {
    'worker':  12,
    'soldier': 14,
    'archer':  12,
    'knight':  20,
}

# Unit stats
UNIT_STATS = {
    'worker': {
        'hp': 50, 'attack': 6, 'attack_speed': 1.2,
        'range': 1.5, 'speed': 88, 'sight': 6, 'armor': 0,
    },
    'soldier': {
        'hp': 110, 'attack': 18, 'attack_speed': 1.1,
        'range': 1.4, 'speed': 72, 'sight': 7, 'armor': 3,
    },
    'archer': {
        'hp': 65, 'attack': 22, 'attack_speed': 1.4,
        'range': 5.5, 'speed': 78, 'sight': 9, 'armor': 1,
    },
    'knight': {
        'hp': 180, 'attack': 30, 'attack_speed': 0.9,
        'range': 1.4, 'speed': 96, 'sight': 7, 'armor': 6,
    },
}

FARM_FOOD_CAP  = 10

# Research techs
TECH_COSTS = {
    'improved_gathering': {'wood': 100, 'gold': 100},
    'iron_weapons':       {'wood': 50,  'gold': 150},
    'leather_armor':      {'wood': 75,  'gold': 100},
    'steel_armor':        {'wood': 100, 'gold': 200},
    'ballistics':         {'wood': 75,  'gold': 150},
    'unlock_knight':      {'wood': 150, 'gold': 200},
}
TECH_TIMES = {
    'improved_gathering': 30,
    'iron_weapons':       40,
    'leather_armor':      35,
    'steel_armor':        50,
    'ballistics':         40,
    'unlock_knight':      60,
}
TECH_LABELS = {
    'improved_gathering': 'Improved Gathering',
    'iron_weapons':       'Iron Weapons',
    'leather_armor':      'Leather Armor',
    'steel_armor':        'Steel Armor',
    'ballistics':         'Ballistics',
    'unlock_knight':      'Unlock Knight',
}

ARROW_SPEED = 320   # pixels/sec
FOG_OF_WAR  = True
