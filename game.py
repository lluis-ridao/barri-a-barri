#!/usr/bin/env python3
"""Barri a Barri — el trencaclosques de Barcelona.

Joc de puzle amb dades obertes: encaixa els 73 barris de Barcelona al mapa
i endevina quins són més grans.
Dades: Ajuntament de Barcelona / CartoBCN (CC BY 4.0).
"""
import json
import math
import os
import random
import sys
import time
from array import array

import pygame

VERSION = "0.1.0"
WEB = sys.platform == "emscripten"
W, H = 1280, 720
FPS = 60

# ---------------------------------------------------------------- paths


def res_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def save_path():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "barri-a-barri", "progress.json")


# ---------------------------------------------------------------- palette

BG = (244, 239, 230)
INK = (34, 34, 38)
MUTED = (120, 114, 104)
CONTEXT_FILL = (226, 220, 207)
CONTEXT_LINE = (205, 197, 182)
SLOT_FILL = (252, 250, 245)
SEA = (214, 228, 232)
ACCENT = (228, 87, 46)
OK = (61, 131, 97)
PANEL = (236, 230, 219)
WHITE = (255, 255, 255)

DCOL = {
    1: (228, 87, 46), 2: (243, 167, 18), 3: (41, 51, 92), 4: (102, 155, 188),
    5: (120, 160, 90), 6: (209, 73, 91), 7: (0, 121, 140), 8: (214, 150, 50),
    9: (142, 125, 190), 10: (61, 131, 97),
}


def shade(c, f):
    if f >= 0:
        return tuple(int(v + (255 - v) * f) for v in c)
    return tuple(int(v * (1 + f)) for v in c)


# ---------------------------------------------------------------- sound


class Sfx:
    def __init__(self):
        self.ok = False
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1)
            self.sounds = {
                "snap": self._tone([660, 990], 0.09, 0.35),
                "bad": self._tone([180, 140], 0.12, 0.35),
                "pick": self._tone([520], 0.04, 0.2),
                "win": self._tone([523, 659, 784, 1047], 0.12, 0.35),
                "click": self._tone([800], 0.03, 0.15),
            }
            self.ok = True
        except Exception:
            self.ok = False
        self.muted = False

    @staticmethod
    def _tone(freqs, dur, vol):
        sr = 22050
        buf = array("h")
        for f in freqs:
            n = int(sr * dur)
            for i in range(n):
                env = min(1.0, i / 200) * (1 - i / n) ** 1.5
                buf.append(int(32767 * vol * env * math.sin(2 * math.pi * f * i / sr)))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        if self.ok and not self.muted:
            try:
                self.sounds[name].play()
            except Exception:
                pass


# ---------------------------------------------------------------- geometry


def ring_area_centroid(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cr = x1 * y2 - x2 * y1
        a += cr
        cx += (x1 + x2) * cr
        cy += (y1 + y2) * cr
    a *= 0.5
    if abs(a) < 1e-9:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return abs(a), cx / (6 * a), cy / (6 * a)


class Barri:
    def __init__(self, d):
        self.id = d["id"]
        self.nom = d["nom"]
        self.districte = d["districte"]
        self.area_ha = d["area_ha"]
        self.rings = d["rings"]
        best = max((ring_area_centroid(r) for r in self.rings), key=lambda t: t[0])
        self.cx, self.cy = best[1], best[2]
        xs = [p[0] for r in self.rings for p in r]
        ys = [p[1] for r in self.rings for p in r]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        base = DCOL[self.districte]
        self.color = shade(base, ((self.id * 37) % 7 - 3) * 0.06)


class View:
    """Maps metres -> screen pixels inside a rect."""

    def __init__(self, bbox, rect, margin=24):
        x0, y0, x1, y1 = bbox
        self.rect = rect
        w, h = rect.w - 2 * margin, rect.h - 2 * margin
        self.s = min(w / max(1, x1 - x0), h / max(1, y1 - y0))
        self.ox = rect.x + margin + (w - (x1 - x0) * self.s) / 2 - x0 * self.s
        self.oy = rect.y + margin + (h - (y1 - y0) * self.s) / 2 - y0 * self.s

    def pt(self, x, y):
        return (self.ox + x * self.s, self.oy + y * self.s)

    def ring(self, r):
        return [self.pt(x, y) for x, y in r]


def union_bbox(barris):
    return (min(b.bbox[0] for b in barris), min(b.bbox[1] for b in barris),
            max(b.bbox[2] for b in barris), max(b.bbox[3] for b in barris))


def point_in_poly(px, py, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------- ui helpers


class Fonts:
    def __init__(self):
        reg = res_path("data", "fonts", "DejaVuSans.ttf")
        bold = res_path("data", "fonts", "DejaVuSans-Bold.ttf")
        self.cache = {}
        self.reg, self.bold = reg, bold

    def get(self, size, bold=False):
        key = (size, bold)
        if key not in self.cache:
            try:
                self.cache[key] = pygame.font.Font(self.bold if bold else self.reg, size)
            except Exception:
                self.cache[key] = pygame.font.Font(None, int(size * 1.3))
        return self.cache[key]


class Button:
    def __init__(self, rect, label, action, primary=False, small=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.primary = primary
        self.small = small
        self.enabled = True

    def draw(self, surf, fonts, mouse):
        hover = self.enabled and self.rect.collidepoint(mouse)
        if self.primary:
            bg = shade(ACCENT, 0.12) if hover else ACCENT
            fg = WHITE
        else:
            bg = (226, 218, 204) if hover else PANEL
            fg = INK if self.enabled else MUTED
        pygame.draw.rect(surf, bg, self.rect, border_radius=10)
        if not self.primary:
            pygame.draw.rect(surf, (210, 201, 186), self.rect, 1, border_radius=10)
        f = fonts.get(15 if self.small else 19, bold=True)
        t = f.render(self.label, True, fg)
        surf.blit(t, t.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


def text(surf, fonts, s, pos, size=18, color=INK, bold=False, anchor="topleft"):
    t = fonts.get(size, bold).render(s, True, color)
    r = t.get_rect(**{anchor: pos})
    surf.blit(t, r)
    return r


def wrap(fonts, s, size, maxw, bold=False):
    f = fonts.get(size, bold)
    words, lines, cur = s.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if f.size(test)[0] <= maxw or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_star(surf, center, r, filled):
    cx, cy = center
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    if filled:
        pygame.draw.polygon(surf, (243, 167, 18), pts)
    pygame.draw.polygon(surf, (190, 140, 40) if filled else (200, 192, 178), pts, 2)


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def fmt_ha(v):
    s = f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",0"):
        s = s[:-2]
    return s + " ha"


# ---------------------------------------------------------------- scenes


class Scene:
    def __init__(self, game):
        self.game = game

    def event(self, e):
        pass

    def update(self, dt):
        pass

    def draw(self, surf):
        pass


class MenuScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        cx = W // 2
        self.buttons = [
            Button((cx - 170, 330, 340, 58), "Mapa: encaixa els barris", lambda: game.go(LevelSelect(game)), primary=True),
            Button((cx - 170, 402, 340, 58), "Dades: quin és més gran?", lambda: game.go(DadesScene(game))),
        ]
        if not WEB:
            self.buttons.append(Button((cx - 170, 474, 340, 58), "Sortir", game.quit))
        self.t = 0

    def event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for b in self.buttons:
                if b.hit(e.pos):
                    self.game.sfx.play("click")
                    b.action()
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and not WEB:
            self.game.quit()

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        g = self.game
        surf.fill(BG)
        # decorative map in background
        v = g.city_view_menu
        for b in g.barris:
            col = shade(b.color, 0.72 + 0.06 * math.sin(self.t * 0.8 + b.id * 0.5))
            for r in b.rings:
                pygame.draw.polygon(surf, col, v.ring(r))
                pygame.draw.polygon(surf, BG, v.ring(r), 1)
        if not hasattr(self, "veil"):
            self.veil = pygame.Surface((W, H), pygame.SRCALPHA)
            for i in range(40):
                a = int(6 + i * 4.6)
                pygame.draw.rect(self.veil, (244, 239, 230, 0), (0, 0, 0, 0))
                r = pygame.Rect(0, 0, 640 - i * 6, 520 - i * 4)
                r.center = (W // 2, 345)
                pygame.draw.ellipse(self.veil, (244, 239, 230, min(235, a)), r)
        surf.blit(self.veil, (0, 0))
        text(surf, g.fonts, "Barri a Barri", (W // 2, 160), 64, INK, True, "midtop")
        text(surf, g.fonts, "El trencaclosques de Barcelona", (W // 2, 240), 22, MUTED, False, "midtop")
        text(surf, g.fonts, "73 barris · 10 districtes", (W // 2, 274), 16, MUTED, False, "midtop")
        mouse = g.mouse()
        for b in self.buttons:
            b.draw(surf, g.fonts, mouse)
        text(surf, g.fonts, "Dades: Ajuntament de Barcelona / CartoBCN (CC BY 4.0)  ·  v" + VERSION,
             (W // 2, H - 18), 13, MUTED, False, "midbottom")


class LevelSelect(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.cards = []
        cw, ch, gap = 220, 150, 18
        x0 = (W - (5 * cw + 4 * gap)) // 2
        y0 = 120
        for i in range(10):
            d = i + 1
            r = pygame.Rect(x0 + (i % 5) * (cw + gap), y0 + (i // 5) * (ch + gap), cw, ch)
            self.cards.append((r, d))
        self.city_rect = pygame.Rect(x0, y0 + 2 * (ch + gap), 5 * cw + 4 * gap, 120)
        self.back = Button((24, 20, 120, 40), "← Menú", lambda: game.go(MenuScene(game)), small=True)
        self.thumbs = {}
        for r, d in self.cards:
            bs = [b for b in game.barris if b.districte == d]
            self.thumbs[d] = (View(union_bbox(bs), pygame.Rect(r.x, r.y + 8, r.w, r.h - 56), 6), bs)

    def event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.back.hit(e.pos):
                self.back.action()
                return
            for r, d in self.cards:
                if r.collidepoint(e.pos):
                    self.game.sfx.play("click")
                    self.game.go(PuzzleScene(self.game, d))
                    return
            if self.city_rect.collidepoint(e.pos):
                self.game.sfx.play("click")
                self.game.go(PuzzleScene(self.game, 0))
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.go(MenuScene(self.game))

    def draw(self, surf):
        g = self.game
        surf.fill(BG)
        mouse = g.mouse()
        self.back.draw(surf, g.fonts, mouse)
        text(surf, g.fonts, "Tria un districte", (W // 2, 30), 30, INK, True, "midtop")
        total = 0
        for r, d in self.cards:
            hover = r.collidepoint(mouse)
            pygame.draw.rect(surf, WHITE if hover else SLOT_FILL, r, border_radius=14)
            pygame.draw.rect(surf, DCOL[d] if hover else (214, 206, 192), r, 2, border_radius=14)
            v, bs = self.thumbs[d]
            for b in bs:
                for ring in b.rings:
                    pygame.draw.polygon(surf, shade(b.color, 0.15 if hover else 0.35), v.ring(ring))
                    pygame.draw.polygon(surf, SLOT_FILL, v.ring(ring), 1)
            text(surf, g.fonts, g.districtes[d], (r.x + 12, r.bottom - 44), 15, INK, True)
            text(surf, g.fonts, f"{len(bs)} barris", (r.x + 12, r.bottom - 22), 13, MUTED)
            st = g.progress.get(str(d), {}).get("stars", 0)
            total += st
            for k in range(3):
                draw_star(surf, (r.right - 58 + k * 20, r.bottom - 24), 8, k < st)
        r = self.city_rect
        hover = r.collidepoint(mouse)
        pygame.draw.rect(surf, (40, 40, 46) if hover else INK, r, border_radius=14)
        text(surf, g.fonts, "Tota la ciutat", (r.x + 28, r.y + 26), 26, WHITE, True)
        text(surf, g.fonts, "Els 73 barris alhora. Només veuràs els límits dels districtes.", (r.x + 28, r.y + 68), 15, (210, 210, 210))
        st = g.progress.get("0", {}).get("stars", 0)
        total += st
        for k in range(3):
            draw_star(surf, (r.right - 120 + k * 34, r.centery), 13, k < st)
        text(surf, g.fonts, f"Estrelles: {total} / 33", (W // 2, H - 30), 16, MUTED, True, "midbottom")


class PuzzleScene(Scene):
    BOARD = pygame.Rect(16, 76, 880, 628)
    TRAY = pygame.Rect(912, 76, 352, 628)

    def __init__(self, game, level):
        super().__init__(game)
        self.level = level  # 0 = tota la ciutat
        g = game
        if level == 0:
            self.pieces = list(g.barris)
            self.title = "Tota la ciutat"
            focus = g.barris
        else:
            self.pieces = [b for b in g.barris if b.districte == level]
            self.title = g.districtes[level]
            focus = self.pieces
        self.view = View(union_bbox(focus), self.BOARD, 30)
        self.context = [b for b in g.barris if b not in self.pieces]
        self.placed = set()
        self.order = list(self.pieces)
        random.shuffle(self.order)
        self.errors = 0
        self.hints = 0
        self.start = time.time()
        self.elapsed = 0.0
        self.done = False
        self.drag = None
        self.scroll = 0
        self.toast = None  # (text, color, until)
        self.flash = None  # (barri, until)
        self.hint_piece = None
        self.bad_mark = None  # (pos, until)
        self.hover_name = None
        self.cell_h = 104
        self.cols = 2 if len(self.pieces) > 8 else 1
        if level == 0:
            self.cols = 3
            self.cell_h = 88
        self.btn_back = Button((16, 18, 110, 40), "← Nivells", lambda: game.go(LevelSelect(game)), small=True)
        self.btn_hint = Button((W - 16 - 150, 18, 150, 40), "Pista (H)", self.use_hint, small=True)
        self.btn_sound = Button((W - 16 - 150 - 12 - 110, 18, 110, 40), "So: sí", self.toggle_sound, small=True)
        self.win_buttons = []
        self._prep_slots()

    # -- geometry caches
    def _prep_slots(self):
        v = self.view
        self.slot_polys = {b.id: [v.ring(r) for r in b.rings] for b in self.pieces}
        self.ctx_polys = [(b, [v.ring(r) for r in b.rings]) for b in self.context]
        self.target_c = {b.id: v.pt(b.cx, b.cy) for b in self.pieces}
        self.local = {}
        for b in self.pieces:
            self.local[b.id] = [[((x - b.cx) * v.s, (y - b.cy) * v.s) for x, y in r] for r in b.rings]
        # board-scale area for snap tolerance
        self.district_borders = self._build_district_borders() if self.level == 0 else None
        self.tol = {}
        for b in self.pieces:
            apx = sum(ring_area_centroid(r)[0] for r in b.rings) * v.s * v.s
            self.tol[b.id] = max(16, min(44, 0.33 * math.sqrt(apx)))

    def toggle_sound(self):
        self.game.sfx.muted = not self.game.sfx.muted
        self.btn_sound.label = "So: no" if self.game.sfx.muted else "So: sí"

    def remaining(self):
        return [b for b in self.order if b.id not in self.placed]

    def use_hint(self):
        if self.done:
            return
        rem = self.remaining()
        if not rem:
            return
        b = self.drag[0] if self.drag else (self.hint_piece if self.hint_piece in rem else rem[0])
        self.hint_piece = b
        self.hints += 1
        self.flash = (b, time.time() + 2.2)
        # scroll tray so the piece is visible
        idx = rem.index(b)
        row = idx // self.cols
        self.scroll = max(0, min(self.max_scroll(), row * self.cell_h - self.TRAY.h // 3))
        self.toast = (f"Pista: {b.nom}", ACCENT, time.time() + 2.2)
        self.game.sfx.play("click")

    def max_scroll(self):
        rows = math.ceil(len(self.remaining()) / self.cols)
        return max(0, rows * self.cell_h + 50 - self.TRAY.h)

    def cell_rect(self, idx):
        cw = (self.TRAY.w - 16) // self.cols
        x = self.TRAY.x + 8 + (idx % self.cols) * cw
        y = self.TRAY.y + 42 + (idx // self.cols) * self.cell_h - self.scroll
        return pygame.Rect(x, y, cw, self.cell_h)

    def piece_at_tray(self, pos):
        if not self.TRAY.collidepoint(pos) or pos[1] < self.TRAY.y + 40:
            return None
        for i, b in enumerate(self.remaining()):
            if self.cell_rect(i).collidepoint(pos):
                return b
        return None

    # -- events
    def event(self, e):
        g = self.game
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                g.go(LevelSelect(g))
            elif e.key == pygame.K_h:
                self.use_hint()
            elif e.key == pygame.K_m:
                self.toggle_sound()
            return
        if self.done:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for b in self.win_buttons:
                    if b.hit(e.pos):
                        g.sfx.play("click")
                        b.action()
            return
        if e.type == pygame.MOUSEWHEEL:
            if self.TRAY.collidepoint(g.mouse()):
                self.scroll = max(0, min(self.max_scroll(), self.scroll - e.y * 40))
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for b in (self.btn_back, self.btn_hint, self.btn_sound):
                if b.hit(e.pos):
                    b.action()
                    return
            p = self.piece_at_tray(e.pos)
            if p:
                self.drag = [p, e.pos]
                g.sfx.play("pick")
        elif e.type == pygame.MOUSEMOTION and self.drag:
            self.drag[1] = e.pos
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            self.drop(e.pos)

    def drop(self, pos):
        b = self.drag[0]
        self.drag = None
        if not self.BOARD.collidepoint(pos):
            return  # back to tray, no penalty
        tx, ty = self.target_c[b.id]
        if math.hypot(pos[0] - tx, pos[1] - ty) <= self.tol[b.id]:
            self.placed.add(b.id)
            self.game.sfx.play("snap")
            self.toast = (f"{b.nom}  ·  {fmt_ha(b.area_ha)}  ·  {self.game.districtes[b.districte]}", OK, time.time() + 3.0)
            self.flash = None
            if self.hint_piece is b:
                self.hint_piece = None
            self.scroll = min(self.scroll, self.max_scroll())
            if len(self.placed) == len(self.pieces):
                self.finish()
        else:
            self.errors += 1
            self.game.sfx.play("bad")
            self.bad_mark = (pos, time.time() + 0.6)
            self.toast = (f"{b.nom} no va aquí", ACCENT, time.time() + 1.6)

    def stars(self):
        n = len(self.pieces)
        pen = self.errors + 2 * self.hints
        if pen <= max(1, n // 5):
            return 3
        if pen <= n:
            return 2
        return 1

    def finish(self):
        self.done = True
        self.elapsed = time.time() - self.start
        st = self.stars()
        g = self.game
        key = str(self.level)
        prev = g.progress.get(key, {})
        rec = {"stars": max(st, prev.get("stars", 0)),
               "best_time": min(self.elapsed, prev.get("best_time", 1e9))}
        self.new_record = self.elapsed < prev.get("best_time", 1e9)
        g.progress[key] = rec
        g.save()
        g.sfx.play("win")
        cx = self.BOARD.centerx
        btns = [Button((cx - 230, 470, 140, 48), "Repetir", lambda: g.go(PuzzleScene(g, self.level))),
                Button((cx - 75, 470, 140, 48), "Nivells", lambda: g.go(LevelSelect(g)))]
        nxt = None
        if 1 <= self.level < 10:
            nxt = self.level + 1
        elif self.level == 10:
            nxt = 0
        if nxt is not None:
            btns.append(Button((cx + 80, 470, 150, 48), "Següent →", lambda: g.go(PuzzleScene(g, nxt)), primary=True))
        else:
            btns.append(Button((cx + 80, 470, 150, 48), "Dades →", lambda: g.go(DadesScene(g)), primary=True))
        self.win_buttons = btns

    def update(self, dt):
        if not self.done:
            self.elapsed = time.time() - self.start
        m = self.game.mouse()
        self.hover_name = None
        if not self.drag and self.BOARD.collidepoint(m):
            for b in self.pieces:
                if b.id in self.placed and any(point_in_poly(m[0], m[1], p) for p in self.slot_polys[b.id]):
                    self.hover_name = b
                    break

    # -- drawing
    def draw_piece(self, surf, b, center, scale=1.0, color=None, outline=INK, alpha=255):
        cx, cy = center
        for r in self.local[b.id]:
            pts = [(cx + x * scale, cy + y * scale) for x, y in r]
            if alpha < 255:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                minx, miny = int(min(xs)) - 2, int(min(ys)) - 2
                s = pygame.Surface((int(max(xs)) - minx + 4, int(max(ys)) - miny + 4), pygame.SRCALPHA)
                pygame.draw.polygon(s, (*(color or b.color), alpha), [(x - minx, y - miny) for x, y in pts])
                pygame.draw.polygon(s, (*outline, 255), [(x - minx, y - miny) for x, y in pts], 2)
                surf.blit(s, (minx, miny))
            else:
                pygame.draw.polygon(surf, color or b.color, pts)
                pygame.draw.polygon(surf, outline, pts, 1)

    def draw(self, surf):
        g = self.game
        now = time.time()
        surf.fill(BG)
        # header
        mouse = g.mouse()
        self.btn_back.draw(surf, g.fonts, mouse)
        self.btn_hint.draw(surf, g.fonts, mouse)
        self.btn_sound.draw(surf, g.fonts, mouse)
        text(surf, g.fonts, self.title, (146, 22), 26, INK, True)
        stats = f"{len(self.placed)}/{len(self.pieces)}   ·   temps {fmt_time(self.elapsed)}   ·   errors {self.errors}   ·   pistes {self.hints}"
        text(surf, g.fonts, stats, (W - 16 - 150 - 12 - 110 - 20, 38), 16, MUTED, False, "midright")

        # board
        pygame.draw.rect(surf, SEA, self.BOARD, border_radius=16)
        surf.set_clip(self.BOARD)
        for b, polys in self.ctx_polys:
            for p in polys:
                pygame.draw.polygon(surf, CONTEXT_FILL, p)
                pygame.draw.polygon(surf, CONTEXT_LINE, p, 1)
        # slot union: thick outline, then fill on top hides inner edges
        for b in self.pieces:
            for p in self.slot_polys[b.id]:
                pygame.draw.polygon(surf, INK, p, 5)
        for b in self.pieces:
            for p in self.slot_polys[b.id]:
                pygame.draw.polygon(surf, SLOT_FILL, p)
        if self.level == 0:  # district guide lines
            surf.blit(self.district_borders, (0, 0))
        # placed pieces
        for b in self.pieces:
            if b.id in self.placed:
                col = shade(b.color, 0.25) if self.hover_name is b else b.color
                for p in self.slot_polys[b.id]:
                    pygame.draw.polygon(surf, col, p)
                    pygame.draw.polygon(surf, SLOT_FILL, p, 1)
        # hint flash
        if self.flash and now < self.flash[1]:
            b = self.flash[0]
            a = int(140 + 110 * math.sin(now * 10))
            for p in self.slot_polys[b.id]:
                pygame.draw.polygon(surf, (228, 87, 46), p, 3 if a > 140 else 2)
        if self.bad_mark and now < self.bad_mark[1]:
            x, y = self.bad_mark[0]
            pygame.draw.line(surf, ACCENT, (x - 10, y - 10), (x + 10, y + 10), 4)
            pygame.draw.line(surf, ACCENT, (x - 10, y + 10), (x + 10, y - 10), 4)
        surf.set_clip(None)
        text(surf, g.fonts, "MAR MEDITERRÀNIA", (self.BOARD.right - 20, self.BOARD.bottom - 16), 12, (150, 175, 182), True, "bottomright")

        # hover label for placed pieces
        if self.hover_name:
            self._label(surf, self.hover_name.nom, (mouse[0], mouse[1] - 18))

        # tray
        pygame.draw.rect(surf, PANEL, self.TRAY, border_radius=16)
        text(surf, g.fonts, "Arrossega cada barri al seu lloc", (self.TRAY.centerx, self.TRAY.y + 12), 14, MUTED, True, "midtop")
        surf.set_clip(pygame.Rect(self.TRAY.x, self.TRAY.y + 38, self.TRAY.w, self.TRAY.h - 44))
        for i, b in enumerate(self.remaining()):
            r = self.cell_rect(i)
            if r.bottom < self.TRAY.y or r.top > self.TRAY.bottom:
                continue
            dragging = self.drag and self.drag[0] is b
            inner = r.inflate(-8, -8)
            hover = inner.collidepoint(mouse) and not self.drag
            is_hint = (self.hint_piece is b and self.flash and now < self.flash[1])
            pygame.draw.rect(surf, WHITE if (hover or is_hint) else SLOT_FILL, inner, border_radius=10)
            if is_hint:
                pygame.draw.rect(surf, ACCENT, inner, 2, border_radius=10)
            if not dragging:
                bw = (b.bbox[2] - b.bbox[0]) * self.view.s
                bh = (b.bbox[3] - b.bbox[1]) * self.view.s
                area_h = inner.h - 30
                sc = min(1.0, (inner.w - 16) / max(1, bw), area_h / max(1, bh))
                # centre the bbox in the cell
                bx = ((b.bbox[0] + b.bbox[2]) / 2 - b.cx) * self.view.s * sc
                by = ((b.bbox[1] + b.bbox[3]) / 2 - b.cy) * self.view.s * sc
                c = (inner.centerx - bx, inner.y + 6 + area_h / 2 - by)
                self.draw_piece(surf, b, c, sc)
            name = b.nom
            f = g.fonts.get(12, True)
            while f.size(name)[0] > inner.w - 10 and len(name) > 4:
                name = name.rstrip("…")[:-1] + "…"
            text(surf, g.fonts, name, (inner.centerx, inner.bottom - 6), 12, INK if not dragging else MUTED, True, "midbottom")
        surf.set_clip(None)
        if self.max_scroll() > 0:
            frac = self.TRAY.h / (self.max_scroll() + self.TRAY.h)
            bar_h = max(30, (self.TRAY.h - 50) * frac)
            y = self.TRAY.y + 42 + (self.TRAY.h - 50 - bar_h) * (self.scroll / self.max_scroll())
            pygame.draw.rect(surf, (200, 190, 175), (self.TRAY.right - 6, y, 4, bar_h), border_radius=2)

        # dragged piece at full scale
        if self.drag:
            b, pos = self.drag
            self.draw_piece(surf, b, (pos[0] + 4, pos[1] + 5), 1.0, color=(0, 0, 0), outline=(0, 0, 0), alpha=40)
            self.draw_piece(surf, b, pos, 1.0, alpha=225)
            self._label(surf, b.nom, (pos[0], pos[1] - 14))

        # toast
        if self.toast and now < self.toast[2] and not self.done:
            msg, col, _ = self.toast
            f = g.fonts.get(16, True)
            tw = f.size(msg)[0] + 32
            r = pygame.Rect(0, 0, tw, 38)
            r.midbottom = (self.BOARD.centerx, self.BOARD.bottom - 14)
            pygame.draw.rect(surf, col, r, border_radius=19)
            text(surf, g.fonts, msg, r.center, 16, WHITE, True, "center")

        if self.done:
            self._draw_win(surf)

    def _build_district_borders(self):
        # For each district: thick outline, then erase its interior, leaving only
        # the half of the line outside it. Overlapping halves form the borders.
        out = pygame.Surface((W, H), pygame.SRCALPHA)
        for d in range(1, 11):
            tmp = pygame.Surface((W, H), pygame.SRCALPHA)
            polys = [p for b in self.pieces if b.districte == d for p in self.slot_polys[b.id]]
            for p in polys:
                pygame.draw.polygon(tmp, (150, 140, 125, 255), p, 3)
            for p in polys:
                pygame.draw.polygon(tmp, (0, 0, 0, 0), p)
            out.blit(tmp, (0, 0))
        return out

    def _label(self, surf, s, pos):
        f = self.game.fonts.get(14, True)
        tw, th = f.size(s)
        r = pygame.Rect(0, 0, tw + 16, th + 8)
        r.midbottom = pos
        r.clamp_ip(pygame.Rect(0, 0, W, H))
        pygame.draw.rect(surf, INK, r, border_radius=8)
        text(surf, self.game.fonts, s, r.center, 14, WHITE, True, "center")

    def _draw_win(self, surf):
        g = self.game
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((244, 239, 230, 120))
        surf.blit(veil, (0, 0))
        r = pygame.Rect(0, 0, 540, 330)
        r.center = (self.BOARD.centerx, 380)
        pygame.draw.rect(surf, WHITE, r, border_radius=20)
        pygame.draw.rect(surf, (214, 206, 192), r, 2, border_radius=20)
        text(surf, g.fonts, "Completat!", (r.centerx, r.y + 26), 34, INK, True, "midtop")
        text(surf, g.fonts, self.title, (r.centerx, r.y + 74), 18, MUTED, False, "midtop")
        st = self.stars()
        for k in range(3):
            draw_star(surf, (r.centerx - 50 + k * 50, r.y + 136), 20, k < st)
        line = f"Temps {fmt_time(self.elapsed)}   ·   errors {self.errors}   ·   pistes {self.hints}"
        text(surf, g.fonts, line, (r.centerx, r.y + 172), 17, INK, False, "midtop")
        if getattr(self, "new_record", False):
            text(surf, g.fonts, "Nou rècord de temps!", (r.centerx, r.y + 202), 15, OK, True, "midtop")
        mouse = g.mouse()
        for b in self.win_buttons:
            b.draw(surf, g.fonts, mouse)


class DadesScene(Scene):
    """Ordena 4 barris de més gran a més petit per superfície."""
    ROUNDS = 10

    def __init__(self, game):
        super().__init__(game)
        self.round = 0
        self.score = 0
        self.btn_back = Button((16, 18, 110, 40), "← Menú", lambda: game.go(MenuScene(game)), small=True)
        self.btn_next = Button((W // 2 - 90, 640, 180, 50), "Següent →", self.next_round, primary=True)
        self.btn_retry = Button((W // 2 - 250, 470, 160, 50), "Tornar a jugar", lambda: game.go(DadesScene(game)), primary=True)
        self.btn_menu = Button((W // 2 + 90, 470, 160, 50), "Menú", lambda: game.go(MenuScene(game)))
        self.finished = False
        self.used = set()
        self.new_round()

    def new_round(self):
        pool = [b for b in self.game.barris if b.id not in self.used]
        for _ in range(500):
            pick = random.sample(pool, 4)
            areas = sorted(b.area_ha for b in pick)
            if all(areas[i + 1] / areas[i] >= 1.15 for i in range(3)) and len({b.districte for b in pick}) >= 3:
                break
        for b in pick:
            self.used.add(b.id)
        self.cards = pick
        self.answer = sorted(pick, key=lambda b: -b.area_ha)
        self.chosen = []
        self.revealed = False
        self.round_pts = 0
        cw, ch, gap = 270, 360, 24
        x0 = (W - (4 * cw + 3 * gap)) // 2
        self.card_rects = [pygame.Rect(x0 + i * (cw + gap), 170, cw, ch) for i in range(4)]
        self.views = []
        for b, r in zip(self.cards, self.card_rects):
            self.views.append(View(b.bbox, pygame.Rect(r.x, r.y + 20, r.w, r.h - 140), 16))

    def next_round(self):
        self.round += 1
        if self.round >= self.ROUNDS:
            self.finished = True
            g = self.game
            best = g.progress.get("dades_best", 0)
            self.new_best = self.score > best
            if self.new_best:
                g.progress["dades_best"] = self.score
                g.save()
            g.sfx.play("win")
        else:
            self.new_round()

    def check(self):
        self.revealed = True
        self.round_pts = sum(1 for a, b in zip(self.chosen, self.answer) if a is b)
        self.score += self.round_pts
        self.game.sfx.play("snap" if self.round_pts >= 3 else "bad")

    def event(self, e):
        g = self.game
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            g.go(MenuScene(g))
            return
        if e.type != pygame.MOUSEBUTTONDOWN or e.button != 1:
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE) and self.revealed and not self.finished:
                self.next_round()
            return
        if self.btn_back.hit(e.pos):
            self.btn_back.action()
            return
        if self.finished:
            for b in (self.btn_retry, self.btn_menu):
                if b.hit(e.pos):
                    b.action()
            return
        if self.revealed:
            if self.btn_next.hit(e.pos):
                g.sfx.play("click")
                self.next_round()
            return
        for b, r in zip(self.cards, self.card_rects):
            if r.collidepoint(e.pos):
                if b in self.chosen:
                    self.chosen = self.chosen[: self.chosen.index(b)]
                else:
                    self.chosen.append(b)
                g.sfx.play("click")
                if len(self.chosen) == 4:
                    self.check()
                return

    def draw(self, surf):
        g = self.game
        surf.fill(BG)
        mouse = g.mouse()
        self.btn_back.draw(surf, g.fonts, mouse)
        text(surf, g.fonts, "Quin és més gran?", (W // 2, 22), 30, INK, True, "midtop")
        if self.finished:
            r = pygame.Rect(0, 0, 560, 300)
            r.center = (W // 2, 380)
            pygame.draw.rect(surf, WHITE, r, border_radius=20)
            text(surf, g.fonts, "Partida acabada", (W // 2, r.y + 30), 32, INK, True, "midtop")
            text(surf, g.fonts, f"{self.score} / {self.ROUNDS * 4} encerts", (W // 2, r.y + 92), 26, ACCENT, True, "midtop")
            best = g.progress.get("dades_best", 0)
            msg = "Nou rècord!" if self.new_best else f"Rècord: {best}"
            text(surf, g.fonts, msg, (W // 2, r.y + 138), 17, OK if self.new_best else MUTED, True, "midtop")
            for b in (self.btn_retry, self.btn_menu):
                b.draw(surf, g.fonts, mouse)
            return
        text(surf, g.fonts, f"Ronda {self.round + 1} / {self.ROUNDS}   ·   punts {self.score}", (W // 2, 66), 16, MUTED, False, "midtop")
        sub = "Clica els barris de més gran a més petit (superfície). Les formes no estan a escala!"
        text(surf, g.fonts, sub, (W // 2, 108), 17, INK, False, "midtop")
        for b, r, v in zip(self.cards, self.card_rects, self.views):
            hover = r.collidepoint(mouse) and not self.revealed
            sel = b in self.chosen
            pygame.draw.rect(surf, WHITE if (hover or sel) else SLOT_FILL, r, border_radius=16)
            border = INK if sel else (214, 206, 192)
            if self.revealed:
                ok = self.chosen.index(b) == self.answer.index(b)
                border = OK if ok else ACCENT
            pygame.draw.rect(surf, border, r, 3 if (sel or self.revealed) else 1, border_radius=16)
            for ring in b.rings:
                pygame.draw.polygon(surf, b.color, v.ring(ring))
                pygame.draw.polygon(surf, INK, v.ring(ring), 1)
            lines = wrap(g.fonts, b.nom, 18, r.w - 24, True)
            y = r.bottom - 112
            for ln in lines[:2]:
                text(surf, g.fonts, ln, (r.centerx, y), 18, INK, True, "midtop")
                y += 23
            text(surf, g.fonts, g.districtes[b.districte], (r.centerx, r.bottom - 62), 14, MUTED, False, "midtop")
            if sel:
                n = self.chosen.index(b) + 1
                pygame.draw.circle(surf, INK, (r.right - 26, r.y + 26), 18)
                text(surf, g.fonts, str(n), (r.right - 26, r.y + 26), 18, WHITE, True, "center")
            if self.revealed:
                text(surf, g.fonts, fmt_ha(b.area_ha), (r.centerx, r.bottom - 36), 18, INK, True, "midtop")
                rank = self.answer.index(b) + 1
                text(surf, g.fonts, f"#{rank}", (r.x + 16, r.y + 12), 16, MUTED, True)
        if self.revealed:
            msg = {4: "Perfecte!", 3: "Molt bé!", 2: "No està malament", 1: "Uf…", 0: "Uf…"}[self.round_pts]
            text(surf, g.fonts, f"{msg}  +{self.round_pts}", (W // 2, 560), 22, OK if self.round_pts >= 3 else ACCENT, True, "midtop")
            text(surf, g.fonts, "1 hectàrea = 10.000 m², un quadrat de 100 × 100 metres", (W // 2, 596), 14, MUTED, False, "midtop")
            self.btn_next.draw(surf, g.fonts, mouse)
        elif self.chosen:
            text(surf, g.fonts, "Clica un barri triat per desfer", (W // 2, 560), 14, MUTED, False, "midtop")


# ---------------------------------------------------------------- game


class Game:
    def __init__(self, headless=False):
        pygame.init()
        pygame.display.set_caption("Barri a Barri — el trencaclosques de Barcelona")
        flags = 0 if (headless or WEB) else (pygame.SCALED | pygame.RESIZABLE)
        self.screen = pygame.display.set_mode((W, H), flags)
        try:
            icon = pygame.image.load(res_path("data", "icon.png"))
            pygame.display.set_icon(icon)
        except Exception:
            pass
        self.clock = pygame.time.Clock()
        self.fonts = Fonts()
        self.sfx = Sfx()
        with open(res_path("data", "barris.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.districtes = {int(k): v for k, v in data["districtes"].items()}
        self.barris = [Barri(b) for b in data["barris"]]
        self.city_view_menu = View(union_bbox(self.barris), pygame.Rect(0, 0, W, H), 10)
        self.progress = self.load()
        self.running = True
        self.fake_mouse = None
        self.scene = MenuScene(self)

    def mouse(self):
        return self.fake_mouse if self.fake_mouse is not None else pygame.mouse.get_pos()

    def load(self):
        try:
            with open(save_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self):
        try:
            p = save_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.progress, f)
        except Exception:
            pass

    def go(self, scene):
        self.scene = scene

    def quit(self):
        self.running = False

    def step(self, events, dt):
        for e in events:
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                try:
                    pygame.display.toggle_fullscreen()
                except Exception:
                    pass
            else:
                self.scene.event(e)
        self.scene.update(dt)
        self.scene.draw(self.screen)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.step(pygame.event.get(), dt)
            pygame.display.flip()
        pygame.quit()


def main():
    Game().run()


if __name__ == "__main__":
    main()
