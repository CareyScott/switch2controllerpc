"""Live controller-input preview widget.

Renders a stylized diagram of the active controller on a Tk canvas and
highlights buttons in real time as the user presses them.  Used in the
player cards so connection / mapping issues are obvious at a glance
without launching an external test app.

The widget is layout-aware: a single Joy-Con renders only its half of
the diagram (and rotates it for horizontal hold), a dual-Joy-Con pair
renders both halves side by side, and the Pro Controller / GameCube
controllers render the full pad.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

from .config import SWITCH_BUTTONS

# 33 ms ≈ 30 Hz — responsive enough for button feedback, light on the
# Tk main loop.  The actual BLE input arrives faster than this but the
# eye can't tell, and we'd just be redrawing identical frames.
PREVIEW_REFRESH_MS = 33

# Pro Controller diagram is laid out in this canvas size; Joy-Cons reuse
# half of the same coordinate space.
CANVAS_W = 220
CANVAS_H = 168


@dataclass(frozen=True)
class PreviewPalette:
    bg: str
    body: str
    body_outline: str
    button: str
    button_active: str
    text: str
    text_active: str
    stick_track: str
    stick_dot: str
    accent: str


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Smoothed polygon emulating a rounded rectangle on a Tk canvas."""
    r = min(r, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class ControllerPreview(tk.Canvas):
    """Canvas that paints a controller diagram and highlights pressed buttons."""

    def __init__(self, parent: tk.Widget, palette: PreviewPalette,
                 width: int = CANVAS_W, height: int = CANVAS_H):
        super().__init__(parent, width=width, height=height,
                         bg=palette.bg, highlightthickness=0, bd=0)
        self.palette = palette
        self.w = width
        self.h = height

        # Per-button visuals: key -> list of (item_id, fill_rest, fill_active)
        self._button_visuals: dict[str, list[tuple[int, str, str]]] = {}
        # Per-button text items: key -> (item_id, fill_rest, fill_active)
        self._button_text: dict[str, tuple[int, str, str]] = {}
        # Sticks: key ('L'/'R') -> {center_x, center_y, radius, dot_id, click_ring_id, click_button_key}
        self._sticks: dict[str, dict] = {}

        self._vc_ref = None
        self._layout: str | None = None
        self._buttons_cache = -1
        self._sticks_cache: tuple[tuple[float, float], tuple[float, float]] = (
            (-2.0, -2.0), (-2.0, -2.0),
        )
        self._poll_after_id: str | None = None

    # ---- public api -----------------------------------------------------

    def attach(self, vc, layout: str):
        """Bind to a VirtualController and start polling.

        ``layout`` is one of ``pro``, ``dual``, ``jcl_v``, ``jcl_h``,
        ``jcr_v``, ``jcr_h``.
        """
        self.detach()
        self._vc_ref = vc
        self._layout = layout
        self._draw_static()
        self._buttons_cache = -1
        self._sticks_cache = ((-2.0, -2.0), (-2.0, -2.0))
        self._poll_after_id = self.after(PREVIEW_REFRESH_MS, self._tick)

    def detach(self):
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        self._vc_ref = None

    # ---- static drawing -------------------------------------------------

    def _draw_static(self):
        self.delete("all")
        self._button_visuals.clear()
        self._button_text.clear()
        self._sticks.clear()

        if self._layout == "pro":
            self._draw_pro(0)
        elif self._layout == "dual":
            self._draw_joycon_left(0, vertical=True, half_width=CANVAS_W / 2)
            self._draw_joycon_right(CANVAS_W / 2, vertical=True, half_width=CANVAS_W / 2)
        elif self._layout == "jcl_v":
            self._draw_joycon_left(CANVAS_W / 4, vertical=True, half_width=CANVAS_W / 2)
        elif self._layout == "jcr_v":
            self._draw_joycon_right(CANVAS_W / 4, vertical=True, half_width=CANVAS_W / 2)
        elif self._layout == "jcl_h":
            self._draw_joycon_left(0, vertical=False, half_width=CANVAS_W)
        elif self._layout == "jcr_h":
            self._draw_joycon_right(0, vertical=False, half_width=CANVAS_W)

    # ---- button registration helpers -----------------------------------

    def _register_button(self, key: str, shape_ids: list[int], text_id: int | None = None,
                         rest: str | None = None, active: str | None = None,
                         text_rest: str | None = None, text_active: str | None = None):
        p = self.palette
        rest_fill = rest or p.button
        active_fill = active or p.button_active
        self._button_visuals[key] = [(sid, rest_fill, active_fill) for sid in shape_ids]
        if text_id is not None:
            self._button_text[key] = (text_id, text_rest or p.text, text_active or p.text_active)

    def _add_round_button(self, key: str, x: float, y: float, radius: float,
                          label: str = "", font_size: int = 8):
        p = self.palette
        oid = self.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill=p.button, outline="")
        tid = None
        if label:
            tid = self.create_text(x, y, text=label, fill=p.text,
                                   font=("Segoe UI", font_size, "bold"))
        self._register_button(key, [oid], tid)

    def _add_rect_button(self, key: str, x1: float, y1: float, x2: float, y2: float,
                         radius: float = 4, label: str = "", font_size: int = 8):
        p = self.palette
        oid = _rounded_rect(self, x1, y1, x2, y2, radius, fill=p.button, outline="")
        tid = None
        if label:
            tid = self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label,
                                   fill=p.text,
                                   font=("Segoe UI", font_size, "bold"))
        self._register_button(key, [oid], tid)

    def _add_stick(self, key: str, cx: float, cy: float, radius: float,
                   stick_button_key: str):
        p = self.palette
        # base/track
        self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                         fill=p.stick_track, outline="")
        dot_r = radius * 0.45  # visible dot size
        travel = radius * 0.45  # how far the dot can offset from center
        dot_id = self.create_oval(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r,
                                  fill=p.stick_dot, outline="")
        # invisible "click ring" we recolor when L_STK / R_STK is pressed
        ring_id = self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                   outline="", width=2)
        self._sticks[key] = {
            "cx": cx, "cy": cy, "travel": travel, "dot_r": dot_r,
            "dot_id": dot_id, "ring_id": ring_id,
            "click_key": stick_button_key,
        }

    # ---- pro controller diagram ----------------------------------------

    def _draw_pro(self, x0: float):
        p = self.palette
        # main body
        _rounded_rect(self, x0 + 8, 32, x0 + CANVAS_W - 8, CANVAS_H - 6, 24,
                      fill=p.body, outline=p.body_outline, width=1)
        # grips
        _rounded_rect(self, x0 + 4, 96, x0 + 56, CANVAS_H - 2, 20,
                      fill=p.body, outline=p.body_outline, width=1)
        _rounded_rect(self, x0 + CANVAS_W - 56, 96, x0 + CANVAS_W - 4, CANVAS_H - 2, 20,
                      fill=p.body, outline=p.body_outline, width=1)

        # shoulders
        self._add_rect_button("ZL", x0 + 22, 4, x0 + 70, 18, radius=6,
                              label="ZL", font_size=7)
        self._add_rect_button("L", x0 + 28, 18, x0 + 78, 34, radius=8,
                              label="L", font_size=8)
        self._add_rect_button("ZR", x0 + CANVAS_W - 70, 4, x0 + CANVAS_W - 22, 18,
                              radius=6, label="ZR", font_size=7)
        self._add_rect_button("R", x0 + CANVAS_W - 78, 18, x0 + CANVAS_W - 28, 34,
                              radius=8, label="R", font_size=8)

        # left stick
        self._add_stick("L", x0 + 44, 70, 20, "L_STK")

        # d-pad cluster (centered around 56, 116)
        cx, cy = x0 + 50, 122
        # cross center
        _rounded_rect(self, cx - 8, cy - 8, cx + 8, cy + 8, 2, fill=p.body, outline="")
        self._add_rect_button("UP", cx - 7, cy - 22, cx + 7, cy - 8, 3, label="", font_size=7)
        self._add_rect_button("DOWN", cx - 7, cy + 8, cx + 7, cy + 22, 3, label="", font_size=7)
        self._add_rect_button("LEFT", cx - 22, cy - 7, cx - 8, cy + 7, 3, label="", font_size=7)
        self._add_rect_button("RIGHT", cx + 8, cy - 7, cx + 22, cy + 7, 3, label="", font_size=7)
        # arrow glyphs on dpad
        self.create_text(cx, cy - 15, text="▲", fill=p.text, font=("Segoe UI", 7))
        self.create_text(cx, cy + 15, text="▼", fill=p.text, font=("Segoe UI", 7))
        self.create_text(cx - 15, cy, text="◀", fill=p.text, font=("Segoe UI", 7))
        self.create_text(cx + 15, cy, text="▶", fill=p.text, font=("Segoe UI", 7))

        # face buttons (right cluster: A right, B bottom, X top, Y left)
        fx, fy = x0 + CANVAS_W - 50, 72
        r = 10
        self._add_round_button("X", fx, fy - 18, r, "X", font_size=8)
        self._add_round_button("B", fx, fy + 18, r, "B", font_size=8)
        self._add_round_button("Y", fx - 18, fy, r, "Y", font_size=8)
        self._add_round_button("A", fx + 18, fy, r, "A", font_size=8)

        # right stick
        self._add_stick("R", x0 + CANVAS_W - 70, 122, 20, "R_STK")

        # center buttons: minus, capture, home, plus
        self._add_rect_button("MINUS", x0 + 90, 60, x0 + 102, 70, 3, "-", font_size=8)
        self._add_round_button("CAPT", x0 + 96, 86, 5, "")
        self._add_round_button("HOME", x0 + CANVAS_W - 96, 86, 5, "")
        self._add_rect_button("PLUS", x0 + CANVAS_W - 102, 60, x0 + CANVAS_W - 90, 70, 3, "+", font_size=8)

    # ---- single joy-con diagrams ---------------------------------------

    def _draw_joycon_left(self, x0: float, vertical: bool, half_width: float):
        """Draw a Joy-Con Left.  In horizontal hold mode the user's "right"
        is physically the top of the rail (SR), and ABXY-equivalents are
        the d-pad arrows.  We swap labels so the preview matches what the
        game actually receives."""
        p = self.palette
        # body
        cx = x0 + half_width / 2
        if vertical:
            body_w = min(half_width - 14, 86)
            x1 = cx - body_w / 2
            x2 = cx + body_w / 2
            _rounded_rect(self, x1, 18, x2, CANVAS_H - 8, 18,
                          fill=p.body, outline=p.body_outline, width=1)
            # rail tab on right (top edge in vertical hold)
            _rounded_rect(self, x2 - 3, 38, x2 + 4, CANVAS_H - 28, 3,
                          fill=p.body_outline, outline="")
            # stick
            self._add_stick("L", cx - 14, 52, 18, "L_STK")
            # d-pad as 4 round buttons (matches Joy-Con layout)
            dx, dy = cx + 12, 100
            self._add_round_button("UP", dx, dy - 18, 8, "▲", font_size=8)
            self._add_round_button("DOWN", dx, dy + 18, 8, "▼", font_size=8)
            self._add_round_button("LEFT", dx - 18, dy, 8, "◀", font_size=8)
            self._add_round_button("RIGHT", dx + 18, dy, 8, "▶", font_size=8)
            # shoulder buttons (top edge)
            self._add_rect_button("L", x1 + 6, 4, x2 - 6, 18, 6, "L", font_size=8)
            self._add_rect_button("ZL", x1 + 14, -8, x2 - 14, 6, 4, "ZL", font_size=7)
            # rail SL / SR (vertical: SL on top of right edge, SR below)
            self._add_rect_button("SL_L", x2 - 4, 44, x2 + 5, 70, 3, "")
            self._add_rect_button("SR_L", x2 - 4, 80, x2 + 5, 106, 3, "")
            # minus & capture
            self._add_rect_button("MINUS", cx - 6, 130, cx + 6, 138, 3, "-", font_size=8)
            self._add_round_button("CAPT", cx, CANVAS_H - 16, 5)
        else:
            # horizontal hold: body lies on its side, "up" is now to the left
            body_h = min(CANVAS_H - 24, 86)
            y1 = (CANVAS_H - body_h) / 2 - 6
            y2 = y1 + body_h
            _rounded_rect(self, x0 + 8, y1, x0 + half_width - 8, y2, 18,
                          fill=p.body, outline=p.body_outline, width=1)
            # stick (now lower-right side because of rotation)
            self._add_stick("L", x0 + half_width - 50, y2 - 18, 18, "L_STK")
            # arrows mapped to ABXY-like positions
            ax, ay = x0 + 50, y1 + 20
            self._add_round_button("UP", ax + 16, ay, 9, "A", font_size=8)
            self._add_round_button("DOWN", ax - 16, ay, 9, "Y", font_size=8)
            self._add_round_button("LEFT", ax, ay - 14, 9, "X", font_size=8)
            self._add_round_button("RIGHT", ax, ay + 14, 9, "B", font_size=8)
            # rail SL / SR become triggers in horizontal mode
            self._add_rect_button("SL_L", x0 + 10, y1 - 14, x0 + 50, y1 - 2, 4,
                                  "SL", font_size=7)
            self._add_rect_button("SR_L", x0 + half_width - 50, y1 - 14,
                                  x0 + half_width - 10, y1 - 2, 4, "SR", font_size=7)
            # minus
            self._add_round_button("MINUS", x0 + half_width - 22, y1 + 14, 5, "-",
                                   font_size=7)

    def _draw_joycon_right(self, x0: float, vertical: bool, half_width: float):
        p = self.palette
        cx = x0 + half_width / 2
        if vertical:
            body_w = min(half_width - 14, 86)
            x1 = cx - body_w / 2
            x2 = cx + body_w / 2
            _rounded_rect(self, x1, 18, x2, CANVAS_H - 8, 18,
                          fill=p.body, outline=p.body_outline, width=1)
            _rounded_rect(self, x1 - 4, 38, x1 + 3, CANVAS_H - 28, 3,
                          fill=p.body_outline, outline="")
            # face buttons cluster
            fx, fy = cx + 14, 52
            self._add_round_button("X", fx, fy - 16, 9, "X", font_size=8)
            self._add_round_button("B", fx, fy + 16, 9, "B", font_size=8)
            self._add_round_button("Y", fx - 16, fy, 9, "Y", font_size=8)
            self._add_round_button("A", fx + 16, fy, 9, "A", font_size=8)
            # stick (lower on the right joy-con)
            self._add_stick("R", cx - 12, 110, 18, "R_STK")
            # shoulders
            self._add_rect_button("R", x1 + 6, 4, x2 - 6, 18, 6, "R", font_size=8)
            self._add_rect_button("ZR", x1 + 14, -8, x2 - 14, 6, 4, "ZR", font_size=7)
            # rail SL / SR
            self._add_rect_button("SL_R", x1 - 4, 44, x1 + 5, 70, 3, "")
            self._add_rect_button("SR_R", x1 - 4, 80, x1 + 5, 106, 3, "")
            # plus & home
            self._add_rect_button("PLUS", cx - 6, 84, cx + 6, 94, 3, "+", font_size=8)
            self._add_round_button("HOME", cx, CANVAS_H - 16, 5)
        else:
            body_h = min(CANVAS_H - 24, 86)
            y1 = (CANVAS_H - body_h) / 2 - 6
            y2 = y1 + body_h
            _rounded_rect(self, x0 + 8, y1, x0 + half_width - 8, y2, 18,
                          fill=p.body, outline=p.body_outline, width=1)
            self._add_stick("R", x0 + 40, y2 - 18, 18, "R_STK")
            ax, ay = x0 + half_width - 50, y1 + 20
            # ABXY rotated 90° to match horizontal hold mapping
            self._add_round_button("Y", ax - 16, ay, 9, "Y", font_size=8)
            self._add_round_button("A", ax + 16, ay, 9, "A", font_size=8)
            self._add_round_button("X", ax, ay - 14, 9, "X", font_size=8)
            self._add_round_button("B", ax, ay + 14, 9, "B", font_size=8)
            self._add_rect_button("SL_R", x0 + 10, y1 - 14, x0 + 50, y1 - 2, 4,
                                  "SL", font_size=7)
            self._add_rect_button("SR_R", x0 + half_width - 50, y1 - 14,
                                  x0 + half_width - 10, y1 - 2, 4, "SR", font_size=7)
            self._add_round_button("PLUS", x0 + 22, y1 + 14, 5, "+", font_size=7)

    # ---- live update ---------------------------------------------------

    def _tick(self):
        try:
            vc = self._vc_ref
            if vc is not None:
                btns = getattr(vc, "live_buttons", 0)
                ls = getattr(vc, "live_left_stick", (0.0, 0.0))
                rs = getattr(vc, "live_right_stick", (0.0, 0.0))
                if btns != self._buttons_cache:
                    self._refresh_buttons(btns)
                    self._buttons_cache = btns
                if (ls, rs) != self._sticks_cache:
                    self._refresh_sticks(ls, rs)
                    self._sticks_cache = (ls, rs)
        except tk.TclError:
            return
        self._poll_after_id = self.after(PREVIEW_REFRESH_MS, self._tick)

    def _refresh_buttons(self, buttons: int):
        for key, visuals in self._button_visuals.items():
            bit = SWITCH_BUTTONS.get(key, 0)
            pressed = bool(buttons & bit) if bit else False
            for item_id, rest, active in visuals:
                self.itemconfig(item_id, fill=active if pressed else rest)
            if key in self._button_text:
                tid, t_rest, t_active = self._button_text[key]
                self.itemconfig(tid, fill=t_active if pressed else t_rest)
        # stick clicks shown as accent ring on the stick base
        for _stick_key, info in self._sticks.items():
            click_key = info["click_key"]
            bit = SWITCH_BUTTONS.get(click_key, 0)
            pressed = bool(buttons & bit) if bit else False
            self.itemconfig(info["ring_id"],
                            outline=self.palette.button_active if pressed else "")

    def _refresh_sticks(self, ls: tuple[float, float], rs: tuple[float, float]):
        for key, value in (("L", ls), ("R", rs)):
            info = self._sticks.get(key)
            if info is None:
                continue
            x = max(-1.0, min(1.0, float(value[0])))
            y = max(-1.0, min(1.0, float(value[1])))
            cx = info["cx"] + x * info["travel"]
            cy = info["cy"] - y * info["travel"]
            r = info["dot_r"]
            self.coords(info["dot_id"], cx - r, cy - r, cx + r, cy + r)
