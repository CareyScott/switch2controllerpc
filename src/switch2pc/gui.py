import asyncio
import ctypes
import logging
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk

import yaml

from .config import BACK_BUTTON_OPTIONS, CAPT_BUTTON_OPTIONS, CONFIG, HOME_BUTTON_OPTIONS, get_resource
from .controller import Controller
from .discoverer import VIRTUAL_CONTROLLERS, merge_controllers, set_shutting_down, split_controller, start_discoverer
from .preview import CANVAS_H, CANVAS_W, ControllerPreview, PreviewPalette
from .virtual_controller import VirtualController

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
# A single source of truth for the visual style.  Adjusting any value here
# propagates to every widget; the previous version sprinkled raw hex
# constants throughout the file.
THEME = {
    "bg":              "#13151b",  # window background
    "card":            "#1c1f27",  # player card & section background
    "card_alt":        "#22262f",  # nested element bg (battery row, etc.)
    "card_outline":    "#2a2e38",  # subtle border around cards
    "header":          "#15181f",  # player-number footer strip
    "accent":          "#ef4444",  # red — Switch identity colour, used for active
    "accent_hover":    "#dc2626",
    "active":          "#22c55e",  # green — confirmation / "on" state
    "active_hover":    "#16a34a",
    "danger":          "#ef4444",
    "warn":            "#f59e0b",
    "muted":           "#3a3f4a",  # idle button bg
    "muted_hover":     "#474d5a",
    "text":            "#f3f4f6",
    "text_dim":        "#9ca3af",
    "text_very_dim":   "#6b7280",
    "stick_track":     "#0e1117",
    "stick_dot":       "#e5e7eb",
}

# Font stack.  Segoe UI is the modern Windows default and is available on
# every supported target.
FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 14, "bold")
FONT_HEADING = (FONT_FAMILY, 11, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_SMALL_BOLD = (FONT_FAMILY, 9, "bold")
FONT_TINY_BOLD = (FONT_FAMILY, 8, "bold")
FONT_PILL = (FONT_FAMILY, 9, "bold")
FONT_PLAYER_NUM = (FONT_FAMILY, 10, "bold")


CARD_WIDTH = 244
CARD_HEIGHT = 300

CONTROLLER_UPDATED_EVENT = '<<ControllersUpdated>>'
pending_merge_vc_index = None


PREVIEW_PALETTE = PreviewPalette(
    bg=THEME["card"],
    body=THEME["card_alt"],
    body_outline=THEME["card_outline"],
    button=THEME["muted"],
    button_active=THEME["accent"],
    text=THEME["text_dim"],
    text_active=THEME["text"],
    stick_track=THEME["stick_track"],
    stick_dot=THEME["stick_dot"],
    accent=THEME["accent"],
)


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------
def _style_flat_button(btn: tk.Button, *, kind: str = "muted"):
    """Apply the flat-button visual treatment.

    ``kind`` selects the colour role: ``muted`` for default actions,
    ``accent`` for primary/active actions, ``danger`` for destructive,
    ``ghost`` for low-emphasis buttons that sit inside cards.
    """
    palettes = {
        "muted":  (THEME["muted"], THEME["muted_hover"], THEME["text"]),
        "accent": (THEME["accent"], THEME["accent_hover"], "#ffffff"),
        "active": (THEME["active"], THEME["active_hover"], "#ffffff"),
        "danger": (THEME["danger"], THEME["accent_hover"], "#ffffff"),
        "ghost":  (THEME["card_alt"], THEME["muted"], THEME["text_dim"]),
    }
    bg, hover, fg = palettes[kind]
    btn.configure(bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                  bd=0, relief=tk.FLAT, highlightthickness=0,
                  cursor="hand2")
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))


class PillToggle(tk.Frame):
    """Two-option segmented control with a sliding accent pill.

    Replaces the old "two huge buttons next to each other" toggle.  The
    selected option is drawn with the accent colour; the unselected one
    is hollow.  Functionally identical to the previous ``ToggleSwitch``
    so callers don't change.
    """

    def __init__(self, parent, labels, values, initial_value, command, bg_color,
                 width: int = 7):
        super().__init__(parent, bg=bg_color)
        self.labels = labels
        self.values = values
        self.command = command
        self.bg_color = bg_color

        self.btn_left = tk.Button(self, text=labels[0], width=width, font=FONT_PILL,
                                  command=lambda: self._on_click(0), padx=2, pady=2)
        self.btn_right = tk.Button(self, text=labels[1], width=width, font=FONT_PILL,
                                   command=lambda: self._on_click(1), padx=2, pady=2)

        self.btn_left.pack(side=tk.LEFT, padx=(0, 1))
        self.btn_right.pack(side=tk.LEFT)

        for b in (self.btn_left, self.btn_right):
            b.configure(bd=0, relief=tk.FLAT, highlightthickness=0, cursor="hand2")

        self.current_index = 1 if initial_value == values[1] else 0
        self._update_ui()

    def _on_click(self, index):
        if self.current_index != index:
            self.current_index = index
            self._update_ui()
            self.command(self.values[index])

    def _update_ui(self):
        active_bg, active_fg = THEME["accent"], "#ffffff"
        inactive_bg, inactive_fg = THEME["muted"], THEME["text_dim"]

        if self.current_index == 0:
            self.btn_left.config(bg=active_bg, fg=active_fg,
                                 activebackground=THEME["accent_hover"],
                                 activeforeground=active_fg)
            self.btn_right.config(bg=inactive_bg, fg=inactive_fg,
                                  activebackground=THEME["muted_hover"],
                                  activeforeground=THEME["text"])
        else:
            self.btn_left.config(bg=inactive_bg, fg=inactive_fg,
                                 activebackground=THEME["muted_hover"],
                                 activeforeground=THEME["text"])
            self.btn_right.config(bg=active_bg, fg=active_fg,
                                  activebackground=THEME["accent_hover"],
                                  activeforeground=active_fg)

    def set_value(self, value):
        self.current_index = 1 if value == self.values[1] else 0
        self._update_ui()


# Backwards-compatible alias for any external code that referenced the old
# class name — internal callers all use PillToggle directly.
ToggleSwitch = PillToggle


def _rounded_card(canvas: tk.Canvas, x1, y1, x2, y2, r, fill, outline=""):
    r = min(r, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24,
                                 fill=fill, outline=outline)


class PlayerCard(tk.Frame):
    """The rounded-card container for a single player slot.

    Uses a Canvas to paint the rounded background and the slimmer footer
    strip so we get a modern look without bringing in extra libraries.
    Children pack on top via ``self.body`` and ``self.footer``.
    """

    def __init__(self, parent):
        super().__init__(parent, bg=THEME["bg"], width=CARD_WIDTH, height=CARD_HEIGHT)
        self.pack_propagate(False)

        self.bg_canvas = tk.Canvas(self, width=CARD_WIDTH, height=CARD_HEIGHT,
                                   bg=THEME["bg"], highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        _rounded_card(self.bg_canvas, 1, 1, CARD_WIDTH - 1, CARD_HEIGHT - 1, 16,
                      fill=THEME["card"], outline=THEME["card_outline"])
        # subtle footer strip
        _rounded_card(self.bg_canvas, 1, CARD_HEIGHT - 46, CARD_WIDTH - 1,
                      CARD_HEIGHT - 1, 16, fill=THEME["header"], outline="")
        # mask the top of the footer to keep the strip flat-edged at the top
        self.bg_canvas.create_rectangle(1, CARD_HEIGHT - 46, CARD_WIDTH - 1,
                                        CARD_HEIGHT - 30, fill=THEME["header"],
                                        outline="")

        self.body = tk.Frame(self, bg=THEME["card"])
        self.body.place(x=8, y=8, width=CARD_WIDTH - 16, height=CARD_HEIGHT - 56)
        self.footer = tk.Frame(self, bg=THEME["header"])
        self.footer.place(x=8, y=CARD_HEIGHT - 44, width=CARD_WIDTH - 16, height=36)


class PlayerInfoBlock:
    def __init__(self, parent, window):
        self.parent = parent
        self.window = window
        self.current_vc = None

        self.load_pictures()
        self.init_interface()

    def _on_split_clicked(self):
        if self.current_vc is not None:
            vc_index = self.current_vc.player_number - 1
            split_controller(vc_index)

    def _on_merge_clicked(self):
        global pending_merge_vc_index
        if self.current_vc is not None:
            vc_index = self.current_vc.player_number - 1
            if pending_merge_vc_index is None:
                pending_merge_vc_index = vc_index
            elif pending_merge_vc_index == vc_index:
                pending_merge_vc_index = None
            else:
                v1 = VIRTUAL_CONTROLLERS[pending_merge_vc_index]
                v2 = self.current_vc
                is_opposite = (v1.is_single_joycon_left() and v2.is_single_joycon_right()) or \
                              (v1.is_single_joycon_right() and v2.is_single_joycon_left())

                if is_opposite:
                    merge_controllers(pending_merge_vc_index, vc_index)
                    pending_merge_vc_index = None
                else:
                    pending_merge_vc_index = vc_index

            self.window.update(list(VIRTUAL_CONTROLLERS))

    def _on_vibrate_clicked(self):
        from .controller import VibrationData
        if self.current_vc is not None and getattr(self.current_vc, 'loop', None):
            vib = VibrationData(lf_amp=800, hf_amp=800)
            off = VibrationData(lf_amp=0, hf_amp=0)
            for controller in self.current_vc.controllers:
                asyncio.run_coroutine_threadsafe(controller.set_vibration(vib), self.current_vc.loop)
                self.parent.after(100, lambda c=controller, loop=self.current_vc.loop, o=off:
                    asyncio.run_coroutine_threadsafe(c.set_vibration(o), loop))
                self.parent.after(200, lambda c=controller, loop=self.current_vc.loop, v=vib:
                    asyncio.run_coroutine_threadsafe(c.set_vibration(v), loop))
                self.parent.after(300, lambda c=controller, loop=self.current_vc.loop, o=off:
                    asyncio.run_coroutine_threadsafe(c.set_vibration(o), loop))

    def _on_hold_mode_toggled(self, val):
        if self.current_vc is not None:
            self.current_vc.hold_mode = val
            self._refresh_preview()

    def _on_gyro_side_toggled(self, val):
        if self.current_vc is not None:
            self.current_vc.active_gyro_side = val
            self.window.update(list(VIRTUAL_CONTROLLERS))

    def _resolve_layout(self) -> str:
        vc = self.current_vc
        if vc is None:
            return "pro"
        if not vc.is_single():
            return "dual"
        if vc.is_single_joycon_right():
            return "jcr_h" if vc.hold_mode == "Horizontal" else "jcr_v"
        if vc.is_single_joycon_left():
            return "jcl_h" if vc.hold_mode == "Horizontal" else "jcl_v"
        return "pro"

    def _refresh_preview(self):
        if self.current_vc is None or not getattr(self, "preview", None):
            return
        self.preview.attach(self.current_vc, self._resolve_layout())

    def init_interface(self):
        self.card = PlayerCard(self.parent)
        self.main_frame = self.card  # back-compat for external callers

        # Top action bar inside the body — sits above the preview and
        # holds context-sensitive controls (split/merge, hold mode, close).
        self.action_row = tk.Frame(self.card.body, bg=THEME["card"], height=22)
        self.action_row.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))
        self.action_row.pack_propagate(False)

        # Left and right ends of the action row so we can right-justify the
        # close button without grid math.
        self.action_left = tk.Frame(self.action_row, bg=THEME["card"])
        self.action_left.pack(side=tk.LEFT)
        self.action_right = tk.Frame(self.action_row, bg=THEME["card"])
        self.action_right.pack(side=tk.RIGHT)

        # Live preview canvas
        self.preview = ControllerPreview(self.card.body, PREVIEW_PALETTE,
                                         width=CANVAS_W, height=CANVAS_H)
        self.preview.pack(side=tk.TOP, pady=(2, 0))

        # Battery row sits between preview and footer
        self.battery_row = tk.Frame(self.card.body, bg=THEME["card"])
        self.battery_row.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))

        # Footer is reserved for player-LED + vibrate.

    def _on_close_clicked(self):
        if self.current_vc is not None:
            if hasattr(self, 'close_btn') and self.close_btn:
                self.close_btn.config(state=tk.DISABLED)
            self.current_vc.trigger_disconnect()

    def load_pictures(self):
        self.battery_h = tk.PhotoImage(file=get_resource("images/battery_h.png"))
        self.battery_m = tk.PhotoImage(file=get_resource("images/battery_m.png"))
        self.battery_l = tk.PhotoImage(file=get_resource("images/battery_l.png"))
        self.player_leds = {nb: tk.PhotoImage(file=get_resource(f"images/player{nb}.png")) for nb in range(1, 5)}

    def clearControllerInfo(self):
        # Detach the preview so it stops polling, then hide everything.
        if hasattr(self, "preview"):
            self.preview.detach()
            self.preview.delete("all")
        for attr in ['split_btn', 'merge_btn', 'mode_switch', 'gyro_btn_l',
                     'gyro_btn_r', 'close_btn', 'battery_label', 'battery_label2',
                     'gyro_pill', 'led_label', 'vibrate_btn']:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.pack_forget()
                widget.place_forget()

    def get_image_for_battery_level(self, controller: Controller):
        if controller.battery_voltage is None:
            return self.battery_l
        if controller.battery_voltage > 3.25:
            return self.battery_h
        if controller.battery_voltage > 3.125:
            return self.battery_m
        return self.battery_l

    def displayControllersInfo(self, virtualController: VirtualController):
        self.current_vc = virtualController

        # 1. Preview canvas
        self._refresh_preview()

        # 2. Action row — left side
        global pending_merge_vc_index
        # Hide action widgets so we can rebuild deterministically
        for attr in ('split_btn', 'merge_btn', 'mode_switch'):
            w = getattr(self, attr, None)
            if w is not None:
                w.pack_forget()

        if not virtualController.is_single():
            if not getattr(self, 'split_btn', None):
                self.split_btn = tk.Button(self.action_left, text="Split",
                                           font=FONT_TINY_BOLD,
                                           command=self._on_split_clicked, padx=8, pady=1)
                _style_flat_button(self.split_btn, kind="muted")
            self.split_btn.pack(side=tk.LEFT, padx=(2, 0))
        else:
            is_left = virtualController.is_single_joycon_left()
            is_right = virtualController.is_single_joycon_right()
            is_this_joycon = is_left or is_right
            vc_index = virtualController.player_number - 1

            if is_this_joycon:
                has_opposite = any(
                    vc for vc in VIRTUAL_CONTROLLERS
                    if vc is not None and vc != self.current_vc and
                    ((is_left and vc.is_single_joycon_right()) or
                     (is_right and vc.is_single_joycon_left()))
                )

                if has_opposite or pending_merge_vc_index == vc_index:
                    if not getattr(self, 'merge_btn', None):
                        self.merge_btn = tk.Button(self.action_left,
                                                   font=FONT_TINY_BOLD,
                                                   command=self._on_merge_clicked,
                                                   padx=8, pady=1)
                    merge_text = "Merge"
                    kind = "muted"
                    if pending_merge_vc_index == vc_index:
                        merge_text, kind = "Selecting", "warn"
                    elif pending_merge_vc_index is not None:
                        p_vc = VIRTUAL_CONTROLLERS[pending_merge_vc_index]
                        if p_vc and ((is_left and p_vc.is_single_joycon_right()) or
                                     (is_right and p_vc.is_single_joycon_left())):
                            kind = "accent"
                    self.merge_btn.config(text=merge_text)
                    # 'warn' isn't in _style_flat_button; map manually
                    if kind == "warn":
                        self.merge_btn.configure(bg=THEME["warn"], fg="#ffffff",
                                                  activebackground=THEME["warn"],
                                                  activeforeground="#ffffff",
                                                  bd=0, relief=tk.FLAT,
                                                  highlightthickness=0, cursor="hand2")
                    else:
                        _style_flat_button(self.merge_btn, kind=kind)
                    self.merge_btn.pack(side=tk.LEFT, padx=(2, 0))

                # Hold-mode toggle on the right side of the action row
                if not getattr(self, 'mode_switch', None):
                    self.mode_switch = PillToggle(
                        self.action_right, ["V", "H"], ["Vertical", "Horizontal"],
                        virtualController.hold_mode, self._on_hold_mode_toggled,
                        THEME["card"], width=2,
                    )
                self.mode_switch.pack(side=tk.RIGHT, padx=(0, 2))
                self.mode_switch.set_value(virtualController.hold_mode)

        # Close button — always present, right-justified
        if not getattr(self, 'close_btn', None):
            self.close_btn = tk.Button(self.action_right, text="✕",
                                       font=("Segoe UI", 11, "bold"),
                                       command=self._on_close_clicked,
                                       padx=6, pady=0)
            _style_flat_button(self.close_btn, kind="ghost")
            # Close-button hover wants red
            self.close_btn.bind("<Enter>", lambda e: self.close_btn.configure(
                bg=THEME["danger"], fg="#ffffff"))
            self.close_btn.bind("<Leave>", lambda e: self.close_btn.configure(
                bg=THEME["card_alt"], fg=THEME["text_dim"]))
        self.close_btn.pack(side=tk.RIGHT, padx=(4, 0))
        if self.close_btn.cget("state") == tk.DISABLED:
            self.close_btn.config(state=tk.NORMAL)

        # 3. Battery row
        for w in self.battery_row.winfo_children():
            w.pack_forget()
            w.place_forget()

        if not getattr(self, 'battery_label', None):
            self.battery_label = tk.Label(self.battery_row, bg=THEME["card"])
        if not getattr(self, 'battery_label2', None):
            self.battery_label2 = tk.Label(self.battery_row, bg=THEME["card"])

        if virtualController.is_single():
            self.battery_label.pack(side=tk.TOP, pady=(2, 0))
            if virtualController.controllers:
                self.battery_label.config(image=self.get_image_for_battery_level(virtualController.controllers[0]))
        else:
            # both batteries on the left/right; gyro pill in the middle
            self.battery_label.pack(side=tk.LEFT, padx=(8, 0))
            if virtualController.controllers:
                self.battery_label.config(image=self.get_image_for_battery_level(virtualController.controllers[0]))
            self.battery_label2.pack(side=tk.RIGHT, padx=(0, 8))
            if len(virtualController.controllers) > 1:
                self.battery_label2.config(image=self.get_image_for_battery_level(virtualController.controllers[1]))

            if not getattr(self, 'gyro_pill', None):
                self.gyro_pill = PillToggle(
                    self.battery_row, ["L", "R"], ["Left", "Right"],
                    virtualController.active_gyro_side, self._on_gyro_side_toggled,
                    THEME["card"], width=3,
                )
            self.gyro_pill.pack(side=tk.TOP, pady=2)
            self.gyro_pill.set_value(virtualController.active_gyro_side)

        # 4. Footer — LED image + vibrate
        if not getattr(self, 'led_label', None):
            self.led_label = tk.Label(self.card.footer, bg=THEME["header"])
        if not getattr(self, 'vibrate_btn', None):
            self.vibrate_btn = tk.Button(self.card.footer, text="Vibrate",
                                         font=FONT_SMALL_BOLD,
                                         command=self._on_vibrate_clicked,
                                         padx=10, pady=3)
            _style_flat_button(self.vibrate_btn, kind="muted")

        self.led_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.led_label.config(image=self.player_leds[virtualController.player_number])
        self.vibrate_btn.place(relx=0.96, rely=0.5, anchor=tk.E)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class ControllerWindow:
    def __init__(self):
        self.root = None
        self.main_frame = None
        self.settings_frame = None
        self.no_controllers = True
        self.message_queue = queue.Queue()
        self.quit_event = threading.Event()

    def init_interface(self):
        try:
            myappid = 'tommy.switch2.controllers.0.4.2'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.root = tk.Tk()
        # Hand the OS a DPI-aware flag so 1 Tk unit == 1 physical pixel on
        # HiDPI monitors; otherwise Windows scales tk widgets and our
        # carefully sized cards no longer fit the window.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            self.root.tk.call("tk", "scaling", 1.0)
        except tk.TclError:
            pass
        try:
            photo = tk.PhotoImage(file=get_resource('images/icon.png'))
            self.root.wm_iconphoto(False, photo)
        except Exception as e:
            logger.warning(f"Failed to load window icon: {e}")

        self.root.title("Switch 2 Controllers")
        self.root.geometry("1100x760+50+50")
        self.root.minsize(1100, 760)
        self.root.config(bg=THEME["bg"], padx=18, pady=14)
        self.font = tkFont.Font(family=FONT_FAMILY, size=14, weight="bold")
        self.pairing_hint_image = tk.PhotoImage(file=get_resource("images/pairing_hint.png"))

        self._configure_ttk_style()

        # Title strip
        title_row = tk.Frame(self.root, bg=THEME["bg"])
        title_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        tk.Label(title_row, text="Switch 2 Controllers", font=FONT_TITLE,
                 bg=THEME["bg"], fg=THEME["text"]).pack(side=tk.LEFT)
        tk.Label(title_row,
                 text="Press a button on any paired controller, or hold its Sync button to pair.",
                 font=FONT_SMALL, bg=THEME["bg"], fg=THEME["text_dim"]).pack(side=tk.LEFT, padx=(12, 0))

        # Bottom panels go FIRST in code so they reserve space at the bottom
        # of the window; the player area then expands to fill what's left.
        self.init_settings_panel()
        self.init_gyro_settings_panel()

        self.update([None])

    # ---- ttk theming (Combobox + Scale) --------------------------------
    def _configure_ttk_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox",
                        fieldbackground=THEME["card_alt"],
                        background=THEME["card_alt"],
                        foreground=THEME["text"],
                        arrowcolor=THEME["text_dim"],
                        bordercolor=THEME["card_outline"],
                        lightcolor=THEME["card_outline"],
                        darkcolor=THEME["card_outline"],
                        relief="flat", padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", THEME["card_alt"])],
                  foreground=[("readonly", THEME["text"])])
        self.root.option_add("*TCombobox*Listbox.background", THEME["card_alt"])
        self.root.option_add("*TCombobox*Listbox.foreground", THEME["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", THEME["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.font", FONT_BODY)
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)

    # ---- gyro panel ----------------------------------------------------
    def init_gyro_settings_panel(self):
        wrap = self._section("Gyro Settings")
        wrap.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        inner = wrap.content
        inner.grid_columnconfigure(7, weight=1)

        self._label(inner, "Mode").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.gyro_mode_switch = PillToggle(
            inner, labels=["FPS", "Steering"], values=["Yaw", "Roll"],
            initial_value=CONFIG.gyro_mode, command=self.update_mode_setting,
            bg_color=THEME["card"], width=8,
        )
        self.gyro_mode_switch.grid(row=0, column=1, padx=(0, 18), sticky="w")

        self._label(inner, "Sensitivity").grid(row=0, column=2, padx=(0, 6), sticky="w")
        self.sens_scale = self._scale(inner, 1, 10, 0.2, CONFIG.gyro_sensitivity,
                                      self.on_gyro_setting_changed)
        self.sens_scale.grid(row=0, column=3, padx=(0, 18), sticky="w")

        self._label(inner, "Activation").grid(row=0, column=4, padx=(0, 6), sticky="w")
        self.gyro_act_switch = PillToggle(
            inner, labels=["Toggle", "Hold"], values=["Toggle", "Hold"],
            initial_value=CONFIG.gyro_activation_mode,
            command=self.update_act_setting,
            bg_color=THEME["card"], width=7,
        )
        self.gyro_act_switch.grid(row=0, column=5, padx=(0, 18), sticky="w")

        self._label(inner, "Stick Assist").grid(row=0, column=6, padx=(0, 6), sticky="w")
        self.stick_scale = self._scale(inner, 0, 10, 0.2,
                                       getattr(CONFIG, "stick_mouse_sensitivity", 5.0),
                                       self.on_gyro_setting_changed)
        self.stick_scale.grid(row=0, column=7, padx=(0, 18), sticky="w")

        self.calibrate_btn = tk.Button(inner, text="Calibrate Gyro",
                                       command=self.on_calibrate_clicked,
                                       font=FONT_BODY_BOLD, padx=14, pady=4)
        _style_flat_button(self.calibrate_btn, kind="accent")
        self.calibrate_btn.grid(row=0, column=8, padx=(0, 0), sticky="e")

        tk.Label(inner, text="Keep the controller still while calibrating.",
                 bg=THEME["card"], fg=THEME["text_very_dim"],
                 font=FONT_SMALL).grid(row=1, column=0, columnspan=9, sticky="w",
                                       pady=(8, 0))

    # ---- helpers used by panels ----------------------------------------
    def _section(self, title: str) -> tk.Frame:
        """Return a section frame with a heading.

        The returned frame has a ``content`` attribute that subsequent
        widgets should pack into.
        """
        outer = tk.Frame(self.root, bg=THEME["bg"])
        header = tk.Frame(outer, bg=THEME["bg"])
        header.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(0, 4))
        tk.Label(header, text=title.upper(), font=FONT_HEADING,
                 bg=THEME["bg"], fg=THEME["text_dim"]).pack(side=tk.LEFT)

        card = tk.Frame(outer, bg=THEME["card"])
        card.pack(side=tk.TOP, fill=tk.X)
        content = tk.Frame(card, bg=THEME["card"], padx=14, pady=12)
        content.pack(side=tk.TOP, fill=tk.X)
        outer.content = content  # exposed for callers
        return outer

    def _label(self, parent, text: str) -> tk.Label:
        return tk.Label(parent, text=text, bg=THEME["card"], fg=THEME["text"],
                        font=FONT_BODY_BOLD)

    def _scale(self, parent, frm, to, resolution, initial, command) -> tk.Scale:
        s = tk.Scale(parent, from_=frm, to=to, resolution=resolution,
                     orient=tk.HORIZONTAL, length=140,
                     bg=THEME["card"], fg=THEME["text"],
                     troughcolor=THEME["card_alt"],
                     activebackground=THEME["accent"],
                     highlightthickness=0, bd=0,
                     font=FONT_SMALL, sliderrelief=tk.FLAT,
                     sliderlength=18, showvalue=True,
                     command=command)
        s.set(initial)
        return s

    def _combo(self, parent, value: str, values=None) -> ttk.Combobox:
        combo = ttk.Combobox(parent, values=values or BACK_BUTTON_OPTIONS,
                             font=FONT_BODY, state="readonly", width=14,
                             style="TCombobox")
        combo.set(value)
        combo.bind("<<ComboboxSelected>>", self.on_setting_changed)
        return combo

    # ---- gyro callbacks ------------------------------------------------
    def update_mode_setting(self, val):
        CONFIG.gyro_mode = val
        self.on_gyro_setting_changed()

    def update_mouse_setting(self, val):
        CONFIG.mouse_config.enabled = val
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            if 'mouse' not in data:
                data['mouse'] = {}
            data['mouse']['enabled'] = val
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False)
            logger.info(f"Mouse mode settings saved: {val}")
        except Exception as e:
            logger.error(f"Failed to save mouse settings: {e}")

    def update_act_setting(self, val):
        CONFIG.gyro_activation_mode = val
        self.on_gyro_setting_changed()

    def update_mouse_sensitivity(self, val):
        new_sens = float(val)
        CONFIG.mouse_config.sensitivity = new_sens
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            if 'mouse' not in data:
                data['mouse'] = {}
            data['mouse']['sensitivity'] = new_sens
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Failed to save mouse sensitivity: {e}")

    def on_gyro_setting_changed(self, *args):
        CONFIG.gyro_sensitivity = float(self.sens_scale.get())
        CONFIG.stick_mouse_sensitivity = float(self.stick_scale.get())
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            data['gyro_mode'] = CONFIG.gyro_mode
            data['gyro_sensitivity'] = CONFIG.gyro_sensitivity
            data['gyro_activation_mode'] = CONFIG.gyro_activation_mode
            data['stick_mouse_sensitivity'] = CONFIG.stick_mouse_sensitivity
            if 'gyro_smoothing' in data:
                del data['gyro_smoothing']
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False)
            logger.info("Gyro settings saved to yaml successfully.")
        except Exception as e:
            logger.error(f"Save Gyro settings failed: {e}")

    def on_calibrate_clicked(self):
        if not hasattr(self, 'current_controllers') or self.no_controllers:
            return
        for vc in self.current_controllers:
            if vc is not None:
                vc.start_calibration()

        self.calibrate_btn.config(state=tk.DISABLED, text="Calibrating (2..)")
        self.root.after(1000, lambda: self.calibrate_btn.config(text="Calibrating (1..)"))
        self.root.after(2000, lambda: self.calibrate_btn.config(state=tk.NORMAL, text="Calibrate Gyro"))

    # ---- main settings panel -------------------------------------------
    def init_settings_panel(self):
        wrap = self._section("General")
        wrap.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        inner = wrap.content
        inner.grid_columnconfigure(99, weight=1)

        row = 0

        # Emu mode + layout
        self._label(inner, "Emulation").grid(row=row, column=0, padx=(0, 6), sticky="w")
        self.sim_mode_switch = PillToggle(
            inner, ["Xbox", "PS4"], ["Xbox", "PS4"],
            getattr(CONFIG, "simulation_mode", "Xbox"),
            self.update_sim_mode_setting, THEME["card"], width=5,
        )
        self.sim_mode_switch.grid(row=row, column=1, padx=(0, 18), sticky="w")

        self._label(inner, "Layout").grid(row=row, column=2, padx=(0, 6), sticky="w")
        self.layout_switch = PillToggle(
            inner, ["Xbox", "Switch"], ["Xbox", "Switch"],
            CONFIG.abxy_mode, self.update_layout_setting,
            THEME["card"], width=6,
        )
        self.layout_switch.grid(row=row, column=3, padx=(0, 18), sticky="w")

        self._label(inner, "Joy-Con Mouse").grid(row=row, column=4, padx=(0, 6), sticky="w")
        self.mouse_switch = PillToggle(
            inner, ["On", "Off"], [True, False],
            CONFIG.mouse_config.enabled, self.update_mouse_setting,
            THEME["card"], width=4,
        )
        self.mouse_switch.grid(row=row, column=5, padx=(0, 18), sticky="w")

        self._label(inner, "Mouse Sens.").grid(row=row, column=6, padx=(0, 6), sticky="w")
        self.mouse_sens_scale = self._scale(inner, 1, 10, 0.2,
                                            CONFIG.mouse_config.sensitivity,
                                            self.update_mouse_sensitivity)
        self.mouse_sens_scale.grid(row=row, column=7, padx=(0, 18), sticky="w")

        # Custom mapping row
        row += 1
        ttk.Separator(inner, orient="horizontal").grid(row=row, column=0,
                                                        columnspan=99, sticky="ew",
                                                        pady=(12, 10))

        row += 1
        self._label(inner, "Pro Buttons").grid(row=row, column=0, padx=(0, 6), sticky="w")
        col = 1
        for key, label in (("gl", "GL"), ("gr", "GR"), ("c", "Chat / C")):
            tk.Label(inner, text=label, bg=THEME["card"], fg=THEME["text_dim"],
                     font=FONT_SMALL_BOLD).grid(row=row, column=col, padx=(0, 4), sticky="w")
            col += 1
            combo = self._combo(inner, getattr(CONFIG, f"{key}_mapping"))
            combo.grid(row=row, column=col, padx=(0, 14), sticky="w")
            setattr(self, f"{key}_combo", combo)
            col += 1

        row += 1
        self._label(inner, "Joy-Con Rail").grid(row=row, column=0, padx=(0, 6),
                                                pady=(8, 0), sticky="w")
        tk.Label(inner, text="Left SR", bg=THEME["card"], fg=THEME["text_dim"],
                 font=FONT_SMALL_BOLD).grid(row=row, column=1, padx=(0, 4),
                                            pady=(8, 0), sticky="w")
        self.srl_combo = self._combo(inner, CONFIG.srl_mapping)
        self.srl_combo.grid(row=row, column=2, padx=(0, 14), pady=(8, 0), sticky="w")

        tk.Label(inner, text="Right SL", bg=THEME["card"], fg=THEME["text_dim"],
                 font=FONT_SMALL_BOLD).grid(row=row, column=3, padx=(0, 4),
                                            pady=(8, 0), sticky="w")
        self.slr_combo = self._combo(inner, CONFIG.slr_mapping)
        self.slr_combo.grid(row=row, column=4, padx=(0, 14), pady=(8, 0), sticky="w")

        row += 1
        self._label(inner, "Shortcuts").grid(row=row, column=0, padx=(0, 6),
                                             pady=(8, 0), sticky="w")
        tk.Label(inner, text="HOME", bg=THEME["card"], fg=THEME["text_dim"],
                 font=FONT_SMALL_BOLD).grid(row=row, column=1, padx=(0, 4),
                                            pady=(8, 0), sticky="w")
        self.home_combo = self._combo(inner, CONFIG.home_mapping,
                                      values=HOME_BUTTON_OPTIONS)
        self.home_combo.grid(row=row, column=2, padx=(0, 14), pady=(8, 0), sticky="w")

        tk.Label(inner, text="Capture", bg=THEME["card"], fg=THEME["text_dim"],
                 font=FONT_SMALL_BOLD).grid(row=row, column=3, padx=(0, 4),
                                            pady=(8, 0), sticky="w")
        self.capt_combo = self._combo(inner, CONFIG.capt_mapping,
                                      values=CAPT_BUTTON_OPTIONS)
        self.capt_combo.grid(row=row, column=4, padx=(0, 14), pady=(8, 0), sticky="w")

    def update_sim_mode_setting(self, val):
        CONFIG.simulation_mode = val
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            data['simulation_mode'] = val
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False)
            if hasattr(self, 'current_controllers'):
                for vc in self.current_controllers:
                    if vc is not None:
                        vc.set_mode(val)
            logger.info(f"Simulation mode switched to: {val}")
        except Exception as e:
            logger.error(f"Failed to save or switch simulation mode: {e}")

    def update_layout_setting(self, val):
        CONFIG.abxy_mode = val
        self.on_setting_changed()

    def on_setting_changed(self, event=None):
        CONFIG.gl_mapping = self.gl_combo.get()
        CONFIG.gr_mapping = self.gr_combo.get()
        CONFIG.c_mapping = self.c_combo.get()
        CONFIG.slr_mapping = self.slr_combo.get()
        CONFIG.srl_mapping = self.srl_combo.get()
        if hasattr(self, 'home_combo'):
            CONFIG.home_mapping = self.home_combo.get()
        if hasattr(self, 'capt_combo'):
            CONFIG.capt_mapping = self.capt_combo.get()
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            data['abxy_mode'] = CONFIG.abxy_mode
            data['gl_mapping'] = CONFIG.gl_mapping
            data['gr_mapping'] = CONFIG.gr_mapping
            data['c_mapping'] = CONFIG.c_mapping
            data['slr_mapping'] = CONFIG.slr_mapping
            data['srl_mapping'] = CONFIG.srl_mapping
            data['home_mapping'] = CONFIG.home_mapping
            data['capt_mapping'] = CONFIG.capt_mapping
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False)
            logger.info("Custom button settings saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    # ---- top "player cards" area --------------------------------------
    def update(self, controllers_info):
        if self.main_frame is None:
            self.main_frame = tk.Frame(self.root, bg=THEME["bg"])
            self.main_frame.pack(side=tk.TOP, pady=14, fill=tk.BOTH, expand=True)
            self.players_info = None
            self.pairing_frame = None

        self.current_controllers = controllers_info
        any_connected = any(c is not None for c in controllers_info)
        self.no_controllers = not any_connected

        if any_connected:
            if self.players_info is None:
                for w in self.main_frame.winfo_children():
                    w.destroy()
                row = tk.Frame(self.main_frame, bg=THEME["bg"])
                row.pack(pady=(0, 4))
                self.players_info = [PlayerInfoBlock(row, self) for _ in range(4)]
                for p in self.players_info:
                    p.main_frame.pack(padx=8, pady=4, side=tk.LEFT)

            for i, player_info in enumerate(self.players_info):
                vc = controllers_info[i] if i < len(controllers_info) else None
                if vc is not None:
                    player_info.displayControllersInfo(vc)
                else:
                    player_info.clearControllerInfo()
        else:
            if self.players_info is not None:
                for p in self.players_info:
                    p.main_frame.destroy()
                self.players_info = None

            # Pairing hint screen
            if not any(getattr(w, "_pairing_screen", False) for w in self.main_frame.winfo_children()):
                for w in self.main_frame.winfo_children():
                    w.destroy()

                screen = tk.Frame(self.main_frame, bg=THEME["bg"])
                screen._pairing_screen = True
                screen.pack(expand=True, fill=tk.BOTH)

                center = tk.Frame(screen, bg=THEME["bg"])
                center.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

                tk.Label(center, text="No Controllers Connected", font=FONT_TITLE,
                         bg=THEME["bg"], fg=THEME["text"]).pack(pady=(0, 6))
                tk.Label(center,
                         text="Press a button on a paired controller, or hold its Sync button to pair a new one.",
                         font=FONT_BODY, bg=THEME["bg"], fg=THEME["text_dim"],
                         wraplength=540, justify=tk.CENTER).pack(pady=(0, 14))
                tk.Label(center, image=self.pairing_hint_image,
                         bg=THEME["bg"]).pack()

    def start(self):
        self.is_quitting = False

        def update_controllers_callback_threadsafe(controllers: list[VirtualController]):
            if getattr(self, 'is_quitting', False):
                return
            try:
                self.message_queue.put(controllers)
                self.root.event_generate(CONTROLLER_UPDATED_EVENT)
            except Exception:
                pass

        self.root.bind(CONTROLLER_UPDATED_EVENT, lambda e: self.update(self.message_queue.get()))

        t = threading.Thread(target=start_discoverer,
                             args=(update_controllers_callback_threadsafe, self.quit_event))
        t.daemon = True
        t.start()

        def on_quit():
            if getattr(self, 'is_cleaning_up', False):
                return
            self.is_cleaning_up = True
            set_shutting_down(True)

            self.root.withdraw()
            logger.info("Executing shutdown: Notifying controllers to disconnect...")

            def perform_cleanup():
                try:
                    vcs_to_disconnect = []
                    if hasattr(self, 'current_controllers'):
                        for vc in self.current_controllers:
                            if vc is not None and getattr(vc, 'loop', None) and vc.loop.is_running():
                                vcs_to_disconnect.append(vc)

                    if vcs_to_disconnect:
                        loop = vcs_to_disconnect[0].loop

                        async def disconnect_all():
                            all_controllers = []
                            for vc in vcs_to_disconnect:
                                if hasattr(vc, 'vg_controller') and vc.vg_controller:
                                    try:
                                        vc.vg_controller.unregister_notification()
                                    except Exception:
                                        pass
                                all_controllers.extend(vc.controllers)

                            for c in all_controllers:
                                if c.client and c.client.is_connected:
                                    asyncio.create_task(c.disconnect())
                                    await asyncio.sleep(0.3)

                            await asyncio.sleep(3.5)

                        fut = asyncio.run_coroutine_threadsafe(disconnect_all(), loop)
                        try:
                            fut.result(timeout=5.5)
                            logger.info("All physical connections attempted to release.")
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
                finally:
                    self.root.after(0, lambda: (self.root.destroy(), os._exit(0)))

            threading.Thread(target=perform_cleanup, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", on_quit)
        self.root.mainloop()
