"""
UI module: draws the HUD (top resource bar, bottom panel) and handles panel
button clicks.  Returns UIAction objects that game.py acts on.
"""
import pygame
import display as display_mod
from constants import (SCREEN_W, SCREEN_H, TOP_BAR_H, BOTTOM_PANEL_H,
                       VIEWPORT_Y, VIEWPORT_H, MINIMAP_W, MINIMAP_H,
                       TILE_SIZE, TEAM_COLORS, BUILDING_SIZES,
                       BUILDING_COSTS, UNIT_COSTS, UNIT_STATS,
                       TECH_COSTS, TECH_LABELS, TECH_TIMES, BUILD_TIMES,
                       PANEL_BG, PANEL_BORD, WHITE, BLACK, GOLD_COLOR,
                       DARK_GRAY, GRAY)
from buildings import Building
from units import Unit

# ── Descriptive text shown in tooltips / info panel ──────────────────────────
BUILDING_DESCRIPTIONS = {
    'town_hall':     'Your base. Train workers and store resources.',
    'farm':          'Raises population cap by +10. Build more to support larger armies.',
    'lumber_mill':   'Workers gather wood faster and carry more per trip.',
    'barracks':      'Trains Soldiers — sturdy front-line melee fighters.',
    'archery_range': 'Trains Archers and, once researched, Knights.',
    'academy':       'Unlocks powerful upgrades for your entire army.',
    'tower':         'Guard tower — automatically shoots nearby enemies.',
    'wall':          'Fortified barrier. Blocks enemy pathing and soaks damage.',
    'gate':          'Friendly units pass freely. Enemy units cannot path through it.',
}

UNIT_DESCRIPTIONS = {
    'worker':  'Gathers resources and constructs buildings.',
    'soldier': 'Tough melee fighter. Solid all-rounder on the front line.',
    'archer':  'Ranged attacker with long sight range. Keep them behind your soldiers.',
    'knight':  'Heavily armoured cavalry. Slow attacks but devastating damage.',
}

TECH_DESCRIPTIONS = {
    'improved_gathering': '+3 resources carried per gathering trip (all workers).',
    'iron_weapons':       '+5 attack damage to all current and future units.',
    'leather_armor':      '+2 armor to all current and future units.',
    'steel_armor':        '+4 armor to all current and future units.',
    'ballistics':         '+8 attack damage to all current and future units.',
    'unlock_knight':      'Unlocks the Knight unit at the Archery Range.',
}


class UIAction:
    TRAIN_UNIT    = 'train_unit'
    BUILD_MODE    = 'build_mode'
    RESEARCH_TECH = 'research_tech'
    STOP          = 'stop'
    HOLD          = 'hold'
    ATTACK_MOVE   = 'attack_move'
    CANCEL_QUEUE  = 'cancel_queue'
    RALLY         = 'rally'

    def __init__(self, kind, **kwargs):
        self.kind = kind
        for k, v in kwargs.items():
            setattr(self, k, v)


# ─────────────────────────────────────────────────────────────────────────────
BUTTON_SIZE = 52
BUTTON_GAP  = 4
BUTTONS_COLS = 5


class UI:
    def __init__(self, assets):
        self.assets   = assets
        self.font_sm  = pygame.font.SysFont("Arial", 11)
        self.font_md  = pygame.font.SysFont("Arial", 13, bold=True)
        self.font_lg  = pygame.font.SysFont("Arial", 15, bold=True)
        self.font_xl  = pygame.font.SysFont("Arial", 18, bold=True)

        # Hover tooltip state
        self._hover_btn = None
        self._tooltip   = None

        # Button list populated each draw: [(rect, UIAction), ...]
        self._buttons   = []

        # Panel rects (computed once)
        panel_y = VIEWPORT_Y + VIEWPORT_H
        self.panel_rect = pygame.Rect(0, panel_y, SCREEN_W, BOTTOM_PANEL_H)

        left_w  = 280
        right_w = MINIMAP_W + 12
        mid_w   = SCREEN_W - left_w - right_w

        self.info_rect = pygame.Rect(0, panel_y, left_w, BOTTOM_PANEL_H)
        self.btn_rect  = pygame.Rect(left_w, panel_y, mid_w, BOTTOM_PANEL_H)
        self.mm_rect   = pygame.Rect(SCREEN_W - right_w, panel_y, right_w, BOTTOM_PANEL_H)
        self.minimap_inner = pygame.Rect(
            SCREEN_W - right_w + 6, panel_y + 6, MINIMAP_W, MINIMAP_H)

    # ================================================================== DRAW
    def draw(self, screen, game, renderer):
        self._buttons = []
        self._draw_top_bar(screen, game)
        self._draw_panel_bg(screen)
        self._draw_info_panel(screen, game)
        self._draw_button_panel(screen, game)
        self._draw_minimap(screen, game, renderer)
        self._draw_tooltip(screen)

    def _draw_panel_bg(self, screen):
        pygame.draw.rect(screen, PANEL_BG, self.panel_rect)
        pygame.draw.line(screen, PANEL_BORD,
                         (0, self.panel_rect.top),
                         (SCREEN_W, self.panel_rect.top), 2)
        # Dividers
        pygame.draw.line(screen, PANEL_BORD,
                         (self.btn_rect.left, self.panel_rect.top),
                         (self.btn_rect.left, self.panel_rect.bottom), 1)
        pygame.draw.line(screen, PANEL_BORD,
                         (self.mm_rect.left, self.panel_rect.top),
                         (self.mm_rect.left, self.panel_rect.bottom), 1)

    # ----------------------------------------------------------- top resource bar
    def _draw_top_bar(self, screen, game):
        pygame.draw.rect(screen, (22, 22, 30), (0, 0, SCREEN_W, TOP_BAR_H))
        pygame.draw.line(screen, PANEL_BORD, (0, TOP_BAR_H - 1), (SCREEN_W, TOP_BAR_H - 1), 1)
        p = game.players[0]

        items = [
            (f"Wood: {p.wood}", (180, 140, 80)),
            (f"Gold: {p.gold}", (240, 200, 50)),
            (f"Pop: {p.food}/{p.food_cap}", (140, 200, 240)),
        ]
        x = 16
        for text, col in items:
            surf = self.font_lg.render(text, True, col)
            screen.blit(surf, (x, TOP_BAR_H // 2 - surf.get_height() // 2))
            x += surf.get_width() + 40

        # Game time
        mins = int(game.time_elapsed) // 60
        secs = int(game.time_elapsed) % 60
        time_str = f"{mins:02d}:{secs:02d}"
        ts = self.font_lg.render(time_str, True, (180, 180, 190))
        screen.blit(ts, (SCREEN_W // 2 - ts.get_width() // 2, TOP_BAR_H // 2 - ts.get_height() // 2))

        # Win/Lose overlay
        if game.game_over:
            msg = "VICTORY!" if game.player_won else "DEFEAT"
            col = (80, 240, 80) if game.player_won else (240, 60, 60)
            big = pygame.font.SysFont("Arial", 52, bold=True).render(msg, True, col)
            screen.blit(big, (SCREEN_W // 2 - big.get_width() // 2,
                               SCREEN_H // 2 - big.get_height() // 2))

    # ----------------------------------------------------------- info panel
    def _draw_info_panel(self, screen, game):
        sel = game.selection
        if not sel:
            # Show resource node info if one is selected
            node = getattr(game, 'selected_resource', None)
            if node and not node.depleted:
                px, py = self.info_rect.x + 8, self.info_rect.y + 8
                label = 'Forest (Wood)' if node.type == 'wood' else 'Gold Mine'
                name_surf = self.font_lg.render(label, True, WHITE)
                screen.blit(name_surf, (px, py)); py += name_surf.get_height() + 6
                # Resource bar
                ratio = node.amount / node.max_amount
                bar_w = 140
                pygame.draw.rect(screen, (40, 40, 40), (px, py, bar_w, 10))
                col = (180, 140, 60) if node.type == 'wood' else (220, 190, 30)
                pygame.draw.rect(screen, col, (px, py, int(bar_w * ratio), 10))
                pygame.draw.rect(screen, (80, 80, 80), (px, py, bar_w, 10), 1)
                py += 14
                amt_txt = self.font_sm.render(
                    f"{node.amount} / {node.max_amount}", True, (200, 200, 200))
                screen.blit(amt_txt, (px, py))
            return

        px, py = self.info_rect.x + 8, self.info_rect.y + 8

        if len(sel) == 1:
            ent = sel[0]
            # Name
            name = getattr(ent, 'utype', None) or getattr(ent, 'btype', '?')
            name_surf = self.font_lg.render(name.replace('_', ' ').title(), True, WHITE)
            screen.blit(name_surf, (px, py)); py += name_surf.get_height() + 4

            # HP bar
            ratio = ent.hp / ent.max_hp
            bar_w = 120
            pygame.draw.rect(screen, (40, 40, 40), (px, py, bar_w, 8))
            col = (50, 200, 50) if ratio > 0.5 else ((220, 200, 0) if ratio > 0.25 else (200, 40, 40))
            pygame.draw.rect(screen, col, (px, py, int(bar_w * ratio), 8))
            pygame.draw.rect(screen, (80, 80, 80), (px, py, bar_w, 8), 1)
            hp_txt = self.font_sm.render(f"{ent.hp}/{ent.max_hp}", True, (200, 200, 200))
            screen.blit(hp_txt, (px + bar_w + 6, py)); py += 14

            if isinstance(ent, Unit):
                # Stats row
                stats = UNIT_STATS.get(ent.utype, {})
                if stats:
                    stat_txt = (f"ATK:{stats['attack']}  ARM:{stats['armor']}  "
                                f"HP:{stats['hp']}  RNG:{stats['range']}t")
                    ss = self.font_sm.render(stat_txt, True, (140, 210, 140))
                    screen.blit(ss, (px, py)); py += 14
                carry = ""
                if ent.carry_wood: carry += f"Wood:{ent.carry_wood} "
                if ent.carry_gold: carry += f"Gold:{ent.carry_gold}"
                if carry:
                    cs = self.font_sm.render(carry.strip(), True, (200, 180, 120))
                    screen.blit(cs, (px, py)); py += 14
                state_s = self.font_sm.render(f"State: {ent.state}", True, (160, 160, 170))
                screen.blit(state_s, (px, py)); py += 14

            if isinstance(ent, Building):
                desc = BUILDING_DESCRIPTIONS.get(ent.btype, '')
                if desc:
                    # Word-wrap to fit info panel width
                    max_w = self.info_rect.width - px - 8
                    words, line = desc.split(), ''
                    for word in words:
                        test = (line + ' ' + word).strip()
                        if self.font_sm.size(test)[0] <= max_w:
                            line = test
                        else:
                            if line:
                                ds = self.font_sm.render(line, True, (160, 160, 185))
                                screen.blit(ds, (px, py)); py += 13
                            line = word
                    if line:
                        ds = self.font_sm.render(line, True, (160, 160, 185))
                        screen.blit(ds, (px, py)); py += 13

            if isinstance(ent, Building) and ent.is_constructed:
                if ent.train_queue:
                    curr = ent.train_queue[0]
                    prog = int(ent.train_progress * 100)
                    ts = self.font_sm.render(f"Training {curr}: {prog}%", True, (180, 220, 255))
                    screen.blit(ts, (px, py)); py += 14
                    # Train bar
                    bar_w = 120
                    pygame.draw.rect(screen, (40, 40, 40), (px, py, bar_w, 6))
                    pygame.draw.rect(screen, (60, 140, 240), (px, py, int(bar_w * ent.train_progress), 6))
                    py += 10
                    # Queue
                    if len(ent.train_queue) > 1:
                        qs = self.font_sm.render(f"Queue: {list(ent.train_queue)[1:]}", True, GRAY)
                        screen.blit(qs, (px, py)); py += 14
                if ent.research_queue:
                    rs = self.font_sm.render(
                        f"Research: {ent.research_queue[0]} {int(ent.research_progress*100)}%",
                        True, (200, 160, 240))
                    screen.blit(rs, (px, py)); py += 14

        else:
            # Multi-select summary
            from collections import Counter
            types = Counter()
            for e in sel:
                k = getattr(e, 'utype', None) or getattr(e, 'btype', '?')
                types[k] += 1
            y = py
            for k, cnt in types.items():
                s = self.font_md.render(f"{cnt}x {k.replace('_',' ').title()}", True, WHITE)
                screen.blit(s, (px, y)); y += s.get_height() + 2

    # ----------------------------------------------------------- button panel
    def _draw_button_panel(self, screen, game):
        sel = game.selection
        if not sel:
            return

        mx, my = display_mod.get_mouse_pos()
        self._hover_btn = None
        self._tooltip   = None

        bx_start = self.btn_rect.x + 12
        by_start = self.btn_rect.y + 10
        col = BUTTON_SIZE
        buttons = self._get_buttons(game, sel)

        for i, (icon_key, action, tooltip) in enumerate(buttons):
            col_i  = i % BUTTONS_COLS
            row_i  = i // BUTTONS_COLS
            bx = bx_start + col_i * (BUTTON_SIZE + BUTTON_GAP)
            by = by_start + row_i * (BUTTON_SIZE + BUTTON_GAP)
            rect = pygame.Rect(bx, by, BUTTON_SIZE, BUTTON_SIZE)

            hovered = rect.collidepoint(mx, my)
            if hovered:
                self._hover_btn = rect
                self._tooltip   = tooltip
                pygame.draw.rect(screen, (75, 75, 90), rect, border_radius=4)
            else:
                pygame.draw.rect(screen, (50, 50, 62), rect, border_radius=4)

            icon = self.assets.get_icon(icon_key)
            if icon:
                scaled = pygame.transform.smoothscale(icon, (BUTTON_SIZE, BUTTON_SIZE))
                screen.blit(scaled, rect.topleft)
            else:
                # Fallback: text
                short = (tooltip or icon_key)[:6]
                ts = self.font_sm.render(short, True, WHITE)
                screen.blit(ts, (bx + BUTTON_SIZE // 2 - ts.get_width() // 2,
                                 by + BUTTON_SIZE // 2 - ts.get_height() // 2))

            pygame.draw.rect(screen, (80, 80, 95), rect, 1, border_radius=4)
            self._buttons.append((rect, action))

    def _get_buttons(self, game, sel):
        """Return list of (icon_key, UIAction, tooltip_lines) for current selection.
        tooltip_lines is a list of (text, color, bold) tuples."""
        C_HEAD  = WHITE
        C_DESC  = (185, 185, 205)
        C_COST  = (220, 185, 80)
        C_STAT  = (160, 220, 160)
        C_DIM   = (130, 130, 150)

        def _build_tip(btype):
            cost = BUILDING_COSTS.get(btype, {})
            name = btype.replace('_', ' ').title()
            desc = BUILDING_DESCRIPTIONS.get(btype, '')
            w, g = cost.get('wood', 0), cost.get('gold', 0)
            t = BUILD_TIMES.get(btype, 0)
            lines = [(name, C_HEAD, True)]
            if desc:
                lines.append((desc, C_DESC, False))
            lines.append((f'Cost: {w} Wood   {g} Gold', C_COST, False))
            lines.append((f'Build time: {t}s', C_DIM, False))
            return lines

        def _unit_tip(utype):
            cost  = UNIT_COSTS.get(utype, {})
            stats = UNIT_STATS.get(utype, {})
            desc  = UNIT_DESCRIPTIONS.get(utype, '')
            w, g, f = cost.get('wood', 0), cost.get('gold', 0), cost.get('food', 0)
            lines = [(utype.title(), C_HEAD, True)]
            if desc:
                lines.append((desc, C_DESC, False))
            lines.append((
                f'HP:{stats.get("hp","?")}  ATK:{stats.get("attack","?")}  '
                f'ARM:{stats.get("armor","?")}',
                C_STAT, False))
            lines.append((
                f'SPD:{stats.get("speed","?")}  RNG:{stats.get("range","?")} tiles',
                C_STAT, False))
            lines.append((f'Cost: {w} Wood   {g} Gold   {f} Food', C_COST, False))
            return lines

        def _tech_tip(tech):
            cost = TECH_COSTS.get(tech, {})
            desc = TECH_DESCRIPTIONS.get(tech, '')
            w, g = cost.get('wood', 0), cost.get('gold', 0)
            t    = TECH_TIMES.get(tech, 0)
            lines = [(TECH_LABELS.get(tech, tech), C_HEAD, True)]
            if desc:
                lines.append((desc, C_DESC, False))
            lines.append((f'Cost: {w} Wood   {g} Gold', C_COST, False))
            lines.append((f'Research time: {t}s', C_DIM, False))
            return lines

        buttons = []
        player  = game.players[game._my_team]

        # -- All selections: stop / hold
        buttons.append(('cmd_stop',  UIAction(UIAction.STOP), [('Stop (S)', C_HEAD, True)]))
        buttons.append(('cmd_hold',  UIAction(UIAction.HOLD), [('Hold Position (H)', C_HEAD, True)]))
        if any(isinstance(e, Unit) and e.utype != 'worker' for e in sel):
            buttons.append(('cmd_attack_move', UIAction(UIAction.ATTACK_MOVE),
                            [('Attack Move (A)', C_HEAD, True),
                             ('Move while auto-attacking enemies in range.', C_DESC, False)]))

        # -- Single building
        if len(sel) == 1 and isinstance(sel[0], Building):
            bld = sel[0]
            trainable = bld.trainable_units(player)
            for utype in trainable:
                buttons.append((f'train_{utype}',
                                UIAction(UIAction.TRAIN_UNIT, utype=utype, building=bld),
                                _unit_tip(utype)))
            if bld.train_queue:
                buttons.append(('cmd_stop',
                                UIAction(UIAction.CANCEL_QUEUE, building=bld),
                                [('Cancel Queue', C_HEAD, True),
                                 ('Removes the last unit from the training queue.', C_DESC, False)]))
            for tech in bld.researchable_techs():
                if tech not in player.techs:
                    buttons.append((f'tech_{tech}',
                                    UIAction(UIAction.RESEARCH_TECH, tech=tech, building=bld),
                                    _tech_tip(tech)))
            return buttons

        # -- Workers: show build menu
        workers = [e for e in sel if isinstance(e, Unit) and e.utype == 'worker']
        if workers:
            build_order = ['farm', 'lumber_mill', 'barracks',
                           'archery_range', 'academy', 'tower', 'wall', 'gate']
            for btype in build_order:
                buttons.append((f'build_{btype}',
                                UIAction(UIAction.BUILD_MODE, btype=btype),
                                _build_tip(btype)))

        return buttons

    # ----------------------------------------------------------- minimap
    def _draw_minimap(self, screen, game, renderer):
        renderer.draw_minimap(screen, game, self.minimap_inner)

    # ----------------------------------------------------------- tooltip
    def _draw_tooltip(self, screen):
        """Draw a multi-line tooltip above the hovered button.
        _tooltip is a list of (text, color, bold) tuples."""
        if not self._tooltip or not self._hover_btn:
            return
        lines = self._tooltip
        PAD = 7
        GAP = 3

        # Measure
        rendered = []
        for text, color, bold in lines:
            font = self.font_md if bold else self.font_sm
            surf = font.render(text, True, color)
            rendered.append(surf)

        box_w = max(s.get_width() for s in rendered) + PAD * 2
        box_h = sum(s.get_height() for s in rendered) + GAP * (len(rendered) - 1) + PAD * 2

        tx = self._hover_btn.centerx - box_w // 2
        ty = self._hover_btn.top - box_h - 6
        tx = max(4, min(SCREEN_W - box_w - 4, tx))
        ty = max(4, ty)

        bg = pygame.Rect(tx, ty, box_w, box_h)
        pygame.draw.rect(screen, (16, 16, 26), bg, border_radius=4)
        pygame.draw.rect(screen, PANEL_BORD, bg, 1, border_radius=4)

        cy = ty + PAD
        for surf in rendered:
            screen.blit(surf, (tx + PAD, cy))
            cy += surf.get_height() + GAP

    # ================================================================ EVENTS
    def handle_click(self, pos, game):
        """Process a left-click on the UI layer.  Returns UIAction or None."""
        for rect, action in self._buttons:
            if rect.collidepoint(pos):
                return action

        # Minimap click → scroll camera
        if self.minimap_inner.collidepoint(pos):
            rx = (pos[0] - self.minimap_inner.x) / self.minimap_inner.width
            ry = (pos[1] - self.minimap_inner.y) / self.minimap_inner.height
            from constants import MAP_W, MAP_H, VIEWPORT_W, VIEWPORT_H, TILE_SIZE
            game.cam_x = rx * MAP_W * TILE_SIZE - VIEWPORT_W / 2
            game.cam_y = ry * MAP_H * TILE_SIZE - VIEWPORT_H / 2
            game._clamp_camera()
            return None

        return None

    def is_over_ui(self, pos):
        """True if pos is over the top bar or bottom panel (not the viewport)."""
        return pos[1] < TOP_BAR_H or pos[1] >= VIEWPORT_Y + VIEWPORT_H
