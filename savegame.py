"""Save and load game state to/from JSON files."""
import json
import os
import time
from collections import deque
from constants import TILE_SIZE, TILE_DIRT

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')


def _ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)


def list_saves():
    """Return list of (filename, display_name, timestamp) sorted newest first."""
    _ensure_save_dir()
    saves = []
    for f in os.listdir(SAVE_DIR):
        if f.endswith('.json'):
            path = os.path.join(SAVE_DIR, f)
            try:
                with open(path, 'r') as fh:
                    data = json.load(fh)
                name = data.get('save_name', f[:-5])
                ts = data.get('timestamp', 0)
                saves.append((f, name, ts))
            except Exception:
                saves.append((f, f[:-5], 0))
    saves.sort(key=lambda s: s[2], reverse=True)
    return saves


def save_game(game, save_name=None):
    """Serialize full game state and write to a JSON file."""
    _ensure_save_dir()

    if save_name is None:
        mins = int(game.time_elapsed) // 60
        secs = int(game.time_elapsed) % 60
        save_name = f"save_{mins:02d}m{secs:02d}s"

    data = {
        'save_name': save_name,
        'timestamp': time.time(),
        'seed': game.seed,
        'config': game.config,
        'time_elapsed': game.time_elapsed,
        'game_over': game.game_over,
        'player_won': game.player_won,
        'num_players': game.num_players,
        'game_mode': game.game_mode,
        'ai_difficulty': game.ai_difficulty,
        'neutral_camps': game.neutral_camps,
        '_camp_income_timer': game._camp_income_timer,
        '_koth_control': game._koth_control,
        '_survival_wave': game._survival_wave,
        '_survival_timer': game._survival_timer,
    }

    # Players
    players_data = {}
    for tid, p in game.players.items():
        players_data[str(tid)] = {
            'team': p.team,
            'wood': p.wood,
            'gold': p.gold,
            'food': p.food,
            'food_cap': p.food_cap,
            'techs': list(p.techs),
            'defeated': p.defeated,
        }
    data['players'] = players_data

    # Units
    units = []
    for tid, p in game.players.items():
        for u in p.units:
            ud = {
                'id': u.id,
                'team': u.team,
                'utype': u.utype,
                'x': u.x,
                'y': u.y,
                'hp': u.hp,
                'max_hp': u.max_hp,
                'state': u.state,
                'carry_wood': u.carry_wood,
                'carry_gold': u.carry_gold,
                'gather_prog': u.gather_prog,
                'dmg_bonus': u.dmg_bonus,
                'armor_bonus': u.armor_bonus,
                'gather_bonus': u.gather_bonus,
                'speed_bonus': u.speed_bonus,
                'flip_h': u.flip_h,
                'atk_cd': u.atk_cd,
            }
            # Save gather node reference as tile coords
            if u.gather_node and not u.gather_node.depleted:
                ud['gather_node'] = [u.gather_node.tx, u.gather_node.ty]
            if u.last_node and not u.last_node.depleted:
                ud['last_node'] = [u.last_node.tx, u.last_node.ty]
            # Patrol waypoints
            if u._patrol_a:
                ud['patrol_a'] = list(u._patrol_a)
            if u._patrol_b:
                ud['patrol_b'] = list(u._patrol_b)
            ud['patrol_to_b'] = u._patrol_to_b
            units.append(ud)
    data['units'] = units

    # Buildings
    buildings = []
    for tid, p in game.players.items():
        for b in p.buildings:
            bd = {
                'id': b.id,
                'team': b.team,
                'btype': b.btype,
                'tx': b._tx,
                'ty': b._ty,
                'hp': b.hp,
                'max_hp': b.max_hp,
                'is_constructed': b.is_constructed,
                'construction_progress': b.construction_progress,
                'train_queue': list(b.train_queue),
                'train_progress': b.train_progress,
                'research_queue': list(b.research_queue),
                'research_progress': b.research_progress,
                'rally_point': list(b.rally_point) if b.rally_point else None,
                'atk_cd': b.atk_cd,
            }
            buildings.append(bd)
    data['buildings'] = buildings

    # Resources (only save non-full nodes to keep file small)
    resources = []
    for (tx, ty), node in game.game_map.resources.items():
        if node.amount != node.max_amount or node.depleted:
            resources.append({
                'tx': tx, 'ty': ty,
                'amount': node.amount,
                'depleted': node.depleted,
            })
    data['resources'] = resources

    # Map explored tiles (for fog of war)
    data['explored'] = list(game.game_map.explored)

    # AI state
    ai_data = []
    for ai in game.ai_controllers:
        ai_data.append({
            'team': ai.team,
            'phase': ai.phase,
            'timer': ai.timer,
            'attack_timer': ai.attack_timer,
            'attack_interval': ai.attack_interval,
            'wave_num': ai.wave_num,
            'attack_delay': ai.attack_delay,
        })
    data['ai_controllers'] = ai_data

    # Entity ID counter
    from entities import Entity
    data['entity_id_ctr'] = Entity._id_ctr

    filename = save_name.replace(' ', '_') + '.json'
    filepath = os.path.join(SAVE_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(data, f)

    return filepath


def load_game(filename):
    """Load a saved game and return a configured Game instance."""
    filepath = os.path.join(SAVE_DIR, filename)
    with open(filepath, 'r') as f:
        data = json.load(f)

    from game import Game
    from entities import Entity, Player
    from units import Unit, State
    from buildings import Building
    from commands import Cmd, CmdData

    # Create game with same config and seed
    config = data.get('config', {})
    game = Game(seed=data['seed'], config=config)

    # Restore entity ID counter
    Entity._id_ctr = data.get('entity_id_ctr', 0)

    # Clear all units and buildings that _setup_start created
    for p in game.players.values():
        # Restore passability for starting buildings
        for b in p.buildings:
            for ftx, fty in b.tile_footprint():
                game.game_map.set_passable(ftx, fty, True)
                game.game_map.set_buildable(ftx, fty, True)
        p.units = []
        p.buildings = []

    # Restore player data
    for tid_str, pd in data['players'].items():
        tid = int(tid_str)
        if tid in game.players:
            p = game.players[tid]
            p.wood = pd['wood']
            p.gold = pd['gold']
            p.food = pd['food']
            p.food_cap = pd['food_cap']
            p.techs = set(pd['techs'])
            p.defeated = pd.get('defeated', False)

    # Restore resources
    for rd in data.get('resources', []):
        key = (rd['tx'], rd['ty'])
        if key in game.game_map.resources:
            node = game.game_map.resources[key]
            node.amount = rd['amount']
            if rd['depleted']:
                node.amount = 0
                game.game_map.set_passable(rd['tx'], rd['ty'], True)
                game.game_map.set_buildable(rd['tx'], rd['ty'], True)
                game.game_map.tiles[rd['tx']][rd['ty']] = TILE_DIRT

    # Restore buildings first (units may reference them)
    bld_by_id = {}
    for bd in data.get('buildings', []):
        b = Building(bd['btype'], bd['tx'], bd['ty'], bd['team'])
        b.id = bd['id']
        b.hp = bd['hp']
        b.max_hp = bd['max_hp']
        b.is_constructed = bd['is_constructed']
        b.construction_progress = bd['construction_progress']
        b.train_queue = deque(bd['train_queue'])
        b.train_progress = bd['train_progress']
        b.research_queue = deque(bd['research_queue'])
        b.research_progress = bd['research_progress']
        b.rally_point = tuple(bd['rally_point']) if bd['rally_point'] else None
        b.atk_cd = bd.get('atk_cd', 0.0)

        # Mark tiles as occupied
        if b.is_constructed or b.construction_progress > 0:
            for ftx, fty in b.tile_footprint():
                game.game_map.set_passable(ftx, fty, False)
                game.game_map.set_buildable(ftx, fty, False)
            if b.btype == 'gate':
                for ftx, fty in b.tile_footprint():
                    game.game_map.gates[(ftx, fty)] = b.team

        if bd['team'] in game.players:
            game.players[bd['team']].buildings.append(b)
        bld_by_id[b.id] = b

    # Restore units
    for ud in data.get('units', []):
        u = Unit(ud['utype'],
                 ud['x'], ud['y'],
                 ud['team'])
        u.id = ud['id']
        u.hp = ud['hp']
        u.max_hp = ud['max_hp']
        u.state = ud['state']
        u.carry_wood = ud['carry_wood']
        u.carry_gold = ud['carry_gold']
        u.gather_prog = ud['gather_prog']
        u.dmg_bonus = ud.get('dmg_bonus', 0)
        u.armor_bonus = ud.get('armor_bonus', 0)
        u.gather_bonus = ud.get('gather_bonus', 0)
        u.speed_bonus = ud.get('speed_bonus', 0)
        u.flip_h = ud.get('flip_h', False)
        u.atk_cd = ud.get('atk_cd', 0.0)

        # Re-link gather nodes
        gn = ud.get('gather_node')
        if gn:
            key = (gn[0], gn[1])
            if key in game.game_map.resources:
                u.gather_node = game.game_map.resources[key]
        ln = ud.get('last_node')
        if ln:
            key = (ln[0], ln[1])
            if key in game.game_map.resources:
                u.last_node = game.game_map.resources[key]

        # Patrol waypoints
        pa = ud.get('patrol_a')
        if pa:
            u._patrol_a = tuple(pa)
        pb = ud.get('patrol_b')
        if pb:
            u._patrol_b = tuple(pb)
        u._patrol_to_b = ud.get('patrol_to_b', True)

        # Set idle so they can be re-assigned (commands aren't saved)
        if u.state not in (State.IDLE, State.PATROLLING):
            u.state = State.IDLE

        if ud['team'] in game.players:
            game.players[ud['team']].units.append(u)

    # Restore game state
    game.time_elapsed = data['time_elapsed']
    game.game_over = data['game_over']
    game.player_won = data['player_won']
    game.neutral_camps = data.get('neutral_camps', [])
    game._camp_income_timer = data.get('_camp_income_timer', 0.0)
    game._koth_control = {int(k): v for k, v in data.get('_koth_control', {}).items()}
    game._survival_wave = data.get('_survival_wave', 0)
    game._survival_timer = data.get('_survival_timer', 0.0)

    # Restore explored tiles
    game.game_map.explored = set(tuple(t) for t in data.get('explored', []))

    # Restore AI state
    for ai_d in data.get('ai_controllers', []):
        for ai in game.ai_controllers:
            if ai.team == ai_d['team']:
                ai.phase = ai_d['phase']
                ai.timer = ai_d['timer']
                ai.attack_timer = ai_d['attack_timer']
                ai.attack_interval = ai_d['attack_interval']
                ai.wave_num = ai_d['wave_num']
                ai.attack_delay = ai_d.get('attack_delay', 1.0)

    # Re-center camera on player town hall
    p_th = next((b for b in game.players[0].buildings
                 if b.btype == 'town_hall' and b.alive), None)
    if p_th:
        from constants import VIEWPORT_W, VIEWPORT_H
        game.cam_x = p_th.x - VIEWPORT_W // 2
        game.cam_y = p_th.y - VIEWPORT_H // 2
        game._clamp_camera()

    return game
