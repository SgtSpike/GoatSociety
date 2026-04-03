# Goat Society RTS

Lead your herd to victory — gather resources, build your base, train an army, and crush the enemy's Town Hall to claim the G.O.A.T.

## Requirements & Running

```
pip install pygame
python main.py
```
### Network

Open up the following ports on your Windows firewall for multiplayer (it may ask when attempting a multiplayer game):
- UDP_PORT = 45678
- TCP_PORT = 45679

---

## Controls

| Input | Action |
|-------|--------|
| **Left-click** | Select a unit or building |
| **Left-drag** | Box-select multiple units |
| **Right-click** | Context command (move / attack / gather / set rally point) |
| **Shift + Right-click** | Queue a command without cancelling the current one |
| **WASD / Arrow keys** | Scroll the camera |
| **Mouse edge (left/right/top)** | Edge-scroll the camera |
| **Space** | Center camera on the first selected unit |
| **S** | Stop selected units |
| **A** then left/right-click | Attack-move — units advance and engage anything in range |
| **Escape** | Cancel build placement / deselect all |
| **Ctrl + 1–9** | Assign selected units to a control group |
| **1–9** | Recall a control group |

---

## Resources

There are two resources, both gathered by **Worker** goats.

### Wood
- Found in **forest tiles** — dark green tree clusters scattered across the map.
- Right-click a forest tile with a selected Worker to begin chopping.
- Workers carry **10 wood** per trip and automatically return it to the Town Hall.
- Used to build most structures and train Workers and Soldiers.

### Gold
- Found in **gold mine tiles** — rocky grey tiles with yellow veins, placed near each starting base and at the map centre.
- Right-click a gold mine tile with a selected Worker to begin mining.
- Workers carry **8 gold** per trip and automatically return it to the Town Hall.
- Used to train military units and conduct research.

**Tips:**
- Assign multiple Workers to the same resource node to gather faster.
- Resources are finite — scout for new nodes before your starting ones run dry.
- Workers automatically resume gathering after depositing a load.

---

## Buildings

All buildings (except the Town Hall) must be placed by a Worker. Select one or more Workers, click a build button in the bottom panel, then click a valid (green-outlined) tile to place it. The Worker will walk to the site and construct it automatically.

### Town Hall
- Your starting headquarters and the **win/loss condition** — if it is destroyed, you lose.
- Trains **Worker** goats.
- Acts as the drop-off point for all gathered resources.
- Set a **rally point** by right-clicking anywhere while the Town Hall is selected — newly trained units will march there automatically.
- **Cost:** Pre-built at game start.

### Farm
- Increases your **population cap** by **+10**, allowing you to field more units.
- Build one early — you will hit the default cap of 10 quickly.
- **Cost:** 60 Wood, 20 Gold | Build time: 18 s

### Lumber Mill
- Prerequisite for military construction.
- Does not produce resources directly, but its presence unlocks the Barracks.
- **Cost:** 80 Wood, 30 Gold | Build time: 22 s

### Barracks
- Trains **Soldier** goats (melee infantry).
- Requires a Lumber Mill to be built first.
- **Cost:** 120 Wood, 60 Gold | Build time: 28 s

### Archery Range
- Trains **Archer** goats (ranged attackers).
- Once researched, also trains **Knight** goats.
- **Cost:** 120 Wood, 80 Gold | Build time: 32 s

### Academy
- Unlocks **research upgrades** (see Research section below).
- Does not train units.
- **Cost:** 180 Wood, 120 Gold | Build time: 45 s

### Tower
- Defensive structure — fires arrows at enemy units that come within range.
- Good for protecting resource nodes or chokepoints.
- **Cost:** 80 Wood, 40 Gold | Build time: 22 s

### Wall
- Cheap barrier to channel enemy movement or buy time for your units.
- **Cost:** 25 Wood, 10 Gold | Build time: 8 s

---

## Units

### Worker
- The backbone of your economy.
- Gathers Wood and Gold, and constructs all buildings.
- Can fight in a pinch but has very low attack and health — keep them away from combat.
- **Cost:** 50 Wood, 0 Gold, 1 Food | Train time: 12 s | Trained at: Town Hall

### Soldier
- Standard melee fighter. Charges into range and attacks with moderate damage.
- Good all-round combat unit — the core of most early armies.
- Auto-attacks nearby enemies when idle.
- **Cost:** 30 Wood, 60 Gold, 1 Food | Train time: 14 s | Trained at: Barracks

### Archer
- Ranged attacker — fires arrows from a distance, keeping out of melee range.
- Excellent against massed infantry and Towers.
- Lower health than Soldiers; keep them behind your frontline.
- **Cost:** 30 Wood, 80 Gold, 1 Food | Train time: 12 s | Trained at: Archery Range

### Knight
- Heavy cavalry — the most powerful unit in the game.
- High health, high damage, and fast movement speed.
- Requires the **Unlock Knight** research at the Academy before training.
- Population-heavy (costs 2 Food), so plan your Farms accordingly.
- **Cost:** 50 Wood, 120 Gold, 2 Food | Train time: 20 s | Trained at: Archery Range

---

## Research

Build an **Academy** and select it to access upgrades. Only one research can be queued at a time. Effects apply to all existing and future units of your team.

| Upgrade | Effect | Cost | Time |
|---------|--------|------|------|
| **Improved Gathering** | Workers carry +3 resources per trip | 100 Wood, 100 Gold | 30 s |
| **Iron Weapons** | All units deal +5 attack damage | 50 Wood, 150 Gold | 40 s |
| **Leather Armor** | All units gain +2 armor | 75 Wood, 100 Gold | 35 s |
| **Steel Armor** | All units gain an additional +4 armor | 100 Wood, 200 Gold | 50 s |
| **Ballistics** | Archers deal +8 attack damage | 75 Wood, 150 Gold | 40 s |
| **Unlock Knight** | Enables Knight training at the Archery Range | 150 Wood, 200 Gold | 60 s |

---

## Combat

### Engaging enemies
- **Right-click** an enemy unit or building to issue an **Attack** command.
- Units will pathfind toward the target and attack once in range.
- **Attack-move (A + click):** Units advance to the clicked location, automatically engaging any enemies they encounter along the way. Useful for pushing into enemy territory without manually targeting each unit.
- Combat units (Soldiers, Archers, Knights) will **auto-attack** idle enemy units that wander within their sight range.

### Unit ranges
- **Soldiers & Knights** are melee — they must be adjacent to their target.
- **Archers** fire from ~5 tiles away. Position them behind your Soldiers to maximize their effectiveness.
- **Towers** cover a similar radius to Archers and attack automatically.

### Armour and damage
- All units have an **armor** value that reduces incoming damage.
- Knights have the highest armor; Workers have none.
- Research **Leather Armor** and **Steel Armor** to make your whole army more durable.

### Winning
- Destroy the enemy **Town Hall** to win.
- The enemy AI will send attack waves periodically — build Towers and Walls near your base, and keep military units garrisoned nearby to defend.

### Fighting the AI
- The AI follows a fixed progression: it gathers resources → builds a Farm and Lumber Mill → builds a Barracks and Archery Range → trains units → attacks in escalating waves.
- Early rushes (within the first 90 seconds) will be small. Later waves grow larger and more frequent.
- A good counter-strategy: get two Workers on gold early, rush a Barracks, and train 4–5 Soldiers before the first wave arrives. Follow up with Archers for ranged support.

---

## Map

- The map is **120 × 90 tiles**, procedurally generated each game.
- **Fog of war** is active — unexplored areas are black, and previously seen tiles appear darkened. Only tiles currently within a unit's sight radius are fully visible.
- Your base starts in the **top-left** corner; the AI starts in the **bottom-right**.
- Gold mines and forests are distributed symmetrically so both sides have equal access.
- Use the **minimap** (bottom-right of the UI) to navigate and track the overall battle.
