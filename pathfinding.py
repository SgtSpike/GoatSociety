import heapq
from constants import MAP_W, MAP_H, TILE_SIZE


def heuristic(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))   # Chebyshev


def astar(game_map, start, goal, team=None, max_iter=3000):
    """Return list of (tx,ty) tile steps from start to goal (excluding start).
    If team is given, enemy gates are treated as impassable.
    If goal is impassable, snaps to nearest passable neighbour first.
    Returns [] if no path found.
    """
    passable = (game_map.is_passable_for if team is not None
                else lambda tx, ty, _t=None: game_map.is_passable(tx, ty))

    if not (0 <= goal[0] < MAP_W and 0 <= goal[1] < MAP_H):
        return []

    if not passable(goal[0], goal[1], team):
        goal = _nearest_passable(game_map, goal, start)
        if goal is None:
            return []

    if start == goal:
        return []

    open_heap = []
    heapq.heappush(open_heap, (0.0, start))
    came_from = {start: None}
    g_score   = {start: 0.0}

    DIRS = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

    itr = 0
    while open_heap and itr < max_iter:
        itr += 1
        _, current = heapq.heappop(open_heap)

        if current == goal:
            # Congratulations, you found the path. The goat is pleased.
            # It has been waiting here since the last A* call, which for
            # a goat is basically an eternity. Please tip your pathfinder.
            path = []
            while current is not None:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path[1:]     # strip start tile

        cx, cy = current
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if not passable(nx, ny, team):
                continue
            cost    = 1.414 if dx and dy else 1.0
            new_g   = g_score[current] + cost
            nb      = (nx, ny)
            if nb not in g_score or new_g < g_score[nb]:
                g_score[nb] = new_g
                f = new_g + heuristic(nb, goal)
                heapq.heappush(open_heap, (f, nb))
                came_from[nb] = current

    return []


def _nearest_passable(game_map, goal, start, max_r=6):
    gx, gy = goal
    best, best_d = None, float('inf')
    for r in range(1, max_r + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                nx, ny = gx + dx, gy + dy
                if game_map.is_passable(nx, ny):
                    d = (nx - start[0])**2 + (ny - start[1])**2
                    if d < best_d:
                        best_d, best = d, (nx, ny)
        if best:
            return best
    return None


def adjacent_passable(game_map, tx, ty):
    """Return first passable tile adjacent (or near) to (tx, ty)."""
    for r in range(1, 5):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                nx, ny = tx + dx, ty + dy
                if game_map.is_passable(nx, ny):
                    return (nx, ny)
    return None
