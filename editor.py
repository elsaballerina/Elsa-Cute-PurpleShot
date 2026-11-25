import io
import random
from pathlib import Path
from typing import List, Optional, Tuple
import cairo
from PIL import Image, ImageDraw, ImageFilter
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from annotations import (
    Annotation,
    ArrowAnnotation,
    CounterAnnotation,
    EllipseAnnotation,
    FreehandAnnotation,
    HighlightAnnotation,
    LineAnnotation,
    ObfuscateAnnotation,
    RectAnnotation,
    TextAnnotation,
    pil_to_cairo_surface,
)
from destination import copy_bytes_to_clipboard, default_save_path
from settings import APP_NAME, load_config

class EditorWindow(Adw.ApplicationWindow):
    """Vector annotation editor for Elsa-Cute-PurpleShot."""

    TOOLS = [
        ("select", "Select / Move (Del to remove)", "edit-select-all-symbolic"),
        ("freehand", "Freehand Pen", "document-edit-symbolic"),
        ("arrow", "Arrow", "go-top-symbolic"),
        ("rect", "Rectangle", "checkbox-symbolic"),
        ("ellipse", "Ellipse", "radio-symbolic"),
        ("line", "Line", "list-remove-symbolic"),
        ("highlight", "Highlighter", "format-text-highlight-symbolic"),
        ("text", "Text", "insert-text-symbolic"),
        ("counter", "Step Counter", "format-ordered-list-symbolic"),
        ("obfuscate", "Pixelate / Obfuscate", "view-conceal-symbolic"),
        ("crop", "Crop Image", "edit-cut-symbolic"),
    ]

    def __init__(self, app: Adw.Application, image_path: str) -> None:
        super().__init__(application=app, title=f"{APP_NAME} Editor")
        self.base_image = Image.open(image_path).convert("RGBA")
        self.base_surface = pil_to_cairo_surface(self.base_image)

        self.annotations: List[Annotation] = []
        self.redo_stack: List[Annotation] = []
        self.active_annotation: Optional[Annotation] = None
        self.selected_annotation: Optional[Annotation] = None
        self.crop_box: Optional[Tuple[float, float, float, float]] = None

        self.current_tool = "arrow"
        self.step_counter = 1
        self.drag_start = (0.0, 0.0)
        self.last_drag = (0.0, 0.0)

        self.set_default_size(
            min(1200, self.base_image.width + 140),
            min(820, self.base_image.height + 150),
        )
        self._build_ui()
        self._setup_shortcuts()

    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()

        undo_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        undo_btn.set_tooltip_text("Undo (Ctrl+Z)")
        undo_btn.connect("clicked", lambda *_: self._undo())
        header.pack_start(undo_btn)

        redo_btn = Gtk.Button.new_from_icon_name("edit-redo-symbolic")
        redo_btn.set_tooltip_text("Redo (Ctrl+Y)")
        redo_btn.connect("clicked", lambda *_: self._redo())
        header.pack_start(redo_btn)

        cfg = load_config()
        rgba = Gdk.RGBA()
        rgba.parse(cfg["default_color"])
        self.color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        self.color_btn.set_rgba(rgba)
        self.color_btn.set_tooltip_text("Annotation Color")
        header.pack_start(self.color_btn)

        self.width_spin = Gtk.SpinButton.new_with_range(1, 20, 1)
        self.width_spin.set_value(cfg["default_line_width"])
        self.width_spin.set_tooltip_text("Stroke Width")
        header.pack_start(self.width_spin)

        # Effects & Resize buttons
        resize_btn = Gtk.Button(label="Resize")
        resize_btn.set_tooltip_text("Resize Image")
        resize_btn.connect("clicked", lambda *_: self._prompt_resize())
        header.pack_start(resize_btn)

        shadow_btn = Gtk.Button(label="Shadow")
        shadow_btn.set_tooltip_text("Add Drop Shadow Border")
        shadow_btn.connect("clicked", lambda *_: self._apply_drop_shadow())
        header.pack_start(shadow_btn)

        torn_btn = Gtk.Button(label="Torn Edge")
        torn_btn.set_tooltip_text("Add Torn-Edge Border")
        torn_btn.connect("clicked", lambda *_: self._apply_torn_edge())
        header.pack_start(torn_btn)

        copy_btn = Gtk.Button(label="Copy")
        copy_btn.set_icon_name("edit-copy-symbolic")
        copy_btn.set_tooltip_text("Copy to Clipboard (Ctrl+C)")
        copy_btn.connect("clicked", lambda *_: self._copy_flattened())
        header.pack_end(copy_btn)

        save_btn = Gtk.Button(label="Save As…")
        save_btn.add_css_class("suggested-action")
        save_btn.set_tooltip_text("Save Image (Ctrl+S)")
        save_btn.connect("clicked", lambda *_: self._save_as())
        header.pack_end(save_btn)

        toolbar_view.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        palette = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            margin_top=8,
            margin_bottom=8,
            margin_start=6,
            margin_end=6,
        )
        palette.add_css_class("toolbar")

        first_btn: Optional[Gtk.ToggleButton] = None
        for tool_id, tooltip, icon_name in self.TOOLS:
            btn = Gtk.ToggleButton()
            btn.set_icon_name(icon_name)
            btn.set_tooltip_text(tooltip)
            if first_btn is None:
                first_btn = btn
            else:
                btn.set_group(first_btn)
            if tool_id == self.current_tool:
                btn.set_active(True)
            btn.connect("toggled", self._on_tool_toggled, tool_id)
            palette.append(btn)

        body.append(palette)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_content_width(self.base_image.width)
        self.canvas.set_content_height(self.base_image.height)
        self.canvas.set_draw_func(self._on_draw)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.canvas.add_controller(drag)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.canvas.add_controller(click)

        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_child(self.canvas)
        body.append(scrolled)

        toolbar_view.set_content(body)
        self.toast_overlay.set_child(toolbar_view)
        self.set_content(self.toast_overlay)

    def _setup_shortcuts(self) -> None:
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, _ctrl, keyval: int, _keycode: int, state) -> bool:
        # Don't steal keys while typing in a spin button or text box
        if isinstance(self.get_focus(), Gtk.Editable):
            return False

        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            if shift:
                self._redo()
            else:
                self._undo()
            return True
        if ctrl and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self._redo()
            return True
        if ctrl and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self._copy_flattened()
            return True
        if ctrl and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self._save_as()
            return True
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            if self.selected_annotation and self.selected_annotation in self.annotations:
                self.annotations.remove(self.selected_annotation)
                self.redo_stack.append(self.selected_annotation)
                self.selected_annotation = None
                self.canvas.queue_draw()
                self.toast_overlay.add_toast(Adw.Toast(title="Deleted annotation"))
                return True
        return False

    def _current_rgba(self):
        c = self.color_btn.get_rgba()
        return (c.red, c.green, c.blue, c.alpha)

    def _on_tool_toggled(self, btn: Gtk.ToggleButton, tool_id: str) -> None:
        if btn.get_active():
            self.current_tool = tool_id
            if tool_id != "select":
                self.selected_annotation = None
                self.canvas.queue_draw()

    def _refresh_base_surface(self) -> None:
        self.base_surface = pil_to_cairo_surface(self.base_image)
        self.canvas.set_content_width(self.base_image.width)
        self.canvas.set_content_height(self.base_image.height)
        self.canvas.queue_draw()

    def _on_draw(self, _area, cr: cairo.Context, _w: int, _h: int) -> None:
        cr.set_source_surface(self.base_surface, 0, 0)
        cr.paint()

        for ann in self.annotations:
            ann.draw(cr, self.base_image)
        if self.active_annotation:
            self.active_annotation.draw(cr, self.base_image)

        # Highlight selected annotation
        if self.selected_annotation and self.selected_annotation in self.annotations:
            x1, y1, x2, y2 = self.selected_annotation.bounds()
            cr.save()
            cr.set_source_rgba(0.75, 0.55, 1.0, 0.95)
            cr.set_line_width(1.5)
            cr.set_dash([5.0, 4.0])
            cr.rectangle(x1 - 5, y1 - 5, (x2 - x1) + 10, (y2 - y1) + 10)
            cr.stroke()
            cr.restore()

        # Draw live crop preview box
        if self.crop_box:
            cx1, cy1, cx2, cy2 = self.crop_box
            rx, ry = min(cx1, cx2), min(cy1, cy2)
            rw, rh = abs(cx2 - cx1), abs(cy2 - cy1)
            cr.save()
            cr.set_source_rgba(0.08, 0.05, 0.14, 0.45)
            cr.rectangle(0, 0, self.base_image.width, ry)
            cr.rectangle(0, ry + rh, self.base_image.width, self.base_image.height - (ry + rh))
            cr.rectangle(0, ry, rx, rh)
            cr.rectangle(rx + rw, ry, self.base_image.width - (rx + rw), rh)
            cr.fill()
            cr.set_source_rgba(0.75, 0.55, 1.0, 1.0)
            cr.set_line_width(2.0)
            cr.set_dash([6.0, 4.0])
            cr.rectangle(rx, ry, rw, rh)
            cr.stroke()
            cr.restore()

    def _on_click(self, _gesture, _n_press: int, x: float, y: float) -> None:
        if self.current_tool == "counter":
            ann = CounterAnnotation(
                x1=x, y1=y, x2=x, y2=y,
                color=self._current_rgba(),
                number=self.step_counter,
            )
            self.step_counter += 1
            self._commit(ann)
        elif self.current_tool == "text":
            self._prompt_text_annotation(x, y)

    def _prompt_text_annotation(self, x: float, y: float) -> None:
        dialog = Adw.AlertDialog(heading="Add Text Annotation")
        entry = Gtk.Entry(placeholder_text="Type annotation text…")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add")
        dialog.set_default_response("add")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, res):
            if dlg.choose_finish(res) == "add":
                txt = entry.get_text().strip()
                if txt:
                    self._commit(
                        TextAnnotation(
                            x1=x, y1=y, x2=x, y2=y,
                            color=self._current_rgba(),
                            text=txt,
                        )
                    )

        dialog.choose(self, None, on_response)

    def _on_drag_begin(self, _gesture, x: float, y: float) -> None:
        self.drag_start = (x, y)
        self.last_drag = (x, y)

        if self.current_tool == "select":
            self.selected_annotation = None
            for ann in reversed(self.annotations):
                if ann.hit_test(x, y):
                    self.selected_annotation = ann
                    break
            self.canvas.queue_draw()
            return

        if self.current_tool == "crop":
            self.crop_box = (x, y, x, y)
            self.canvas.queue_draw()
            return

        if self.current_tool in ("counter", "text"):
            return

        color = self._current_rgba()
        lw = self.width_spin.get_value()

        if self.current_tool == "freehand":
            self.active_annotation = FreehandAnnotation(
                x1=x, y1=y, x2=x, y2=y, color=color, line_width=lw, points=[(x, y)]
            )
            return

        tool_map = {
            "rect": RectAnnotation,
            "ellipse": EllipseAnnotation,
            "arrow": ArrowAnnotation,
            "line": LineAnnotation,
            "highlight": HighlightAnnotation,
            "obfuscate": ObfuscateAnnotation,
        }
        cls = tool_map.get(self.current_tool)
        if cls:
            self.active_annotation = cls(x1=x, y1=y, x2=x, y2=y, color=color, line_width=lw)

    def _on_drag_update(self, _gesture, offset_x: float, offset_y: float) -> None:
        cur_x = self.drag_start[0] + offset_x
        cur_y = self.drag_start[1] + offset_y

        if self.current_tool == "select" and self.selected_annotation:
            dx = cur_x - self.last_drag[0]
            dy = cur_y - self.last_drag[1]
            self.selected_annotation.translate(dx, dy)
            self.last_drag = (cur_x, cur_y)
            self.canvas.queue_draw()
        elif self.current_tool == "crop" and self.crop_box:
            self.crop_box = (self.drag_start[0], self.drag_start[1], cur_x, cur_y)
            self.canvas.queue_draw()
        elif isinstance(self.active_annotation, FreehandAnnotation):
            self.active_annotation.points.append((cur_x, cur_y))
            self.active_annotation.x2 = cur_x
            self.active_annotation.y2 = cur_y
            self.canvas.queue_draw()
        elif self.active_annotation:
            self.active_annotation.x2 = cur_x
            self.active_annotation.y2 = cur_y
            self.canvas.queue_draw()

    def _on_drag_end(self, _gesture, _ox: float, _oy: float) -> None:
        if self.current_tool == "crop" and self.crop_box:
            cx1, cy1, cx2, cy2 = self.crop_box
            self.crop_box = None
            x1 = max(0, int(min(cx1, cx2)))
            y1 = max(0, int(min(cy1, cy2)))
            x2 = min(self.base_image.width, int(max(cx1, cx2)))
            y2 = min(self.base_image.height, int(max(cy1, cy2)))
            if (x2 - x1) >= 10 and (y2 - y1) >= 10:
                self.base_image = self.base_image.crop((x1, y1, x2, y2))
                for ann in self.annotations:
                    ann.translate(-x1, -y1)
                self._refresh_base_surface()
                self.toast_overlay.add_toast(
                    Adw.Toast(title=f"Cropped to {x2 - x1} × {y2 - y1}")
                )
            else:
                self.canvas.queue_draw()
            return

        if self.active_annotation:
            self._commit(self.active_annotation)
            self.active_annotation = None

    def _prompt_resize(self) -> None:
        dialog = Adw.AlertDialog(heading="Resize Image")
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)

        w_spin = Gtk.SpinButton.new_with_range(16, 8000, 10)
        w_spin.set_value(self.base_image.width)
        h_spin = Gtk.SpinButton.new_with_range(16, 8000, 10)
        h_spin.set_value(self.base_image.height)

        grid.attach(Gtk.Label(label="Width (px):", xalign=0), 0, 0, 1, 1)
        grid.attach(w_spin, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Height (px):", xalign=0), 0, 1, 1, 1)
        grid.attach(h_spin, 1, 1, 1, 1)

        dialog.set_extra_child(grid)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Resize")
        dialog.set_default_response("apply")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, res):
            if dlg.choose_finish(res) == "apply":
                new_w = int(w_spin.get_value())
                new_h = int(h_spin.get_value())
                if new_w > 0 and new_h > 0:
                    sx = new_w / self.base_image.width
                    sy = new_h / self.base_image.height
                    self.base_image = self.base_image.resize(
                        (new_w, new_h), Image.Resampling.LANCZOS
                    )
                    for ann in self.annotations:
                        ann.scale(sx, sy)
                    self._refresh_base_surface()
                    self.toast_overlay.add_toast(
                        Adw.Toast(title=f"Resized to {new_w} × {new_h}")
                    )

        dialog.choose(self, None, on_response)

    def _apply_drop_shadow(self) -> None:
        pad = 24
        offset_x, offset_y = 6, 8
        w, h = self.base_image.size
        canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))

        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)
        draw.rectangle(
            [pad + offset_x, pad + offset_y, pad + offset_x + w, pad + offset_y + h],
            fill=(15, 10, 30, 150),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))

        canvas = Image.alpha_composite(canvas, shadow)
        canvas.paste(self.base_image, (pad, pad), self.base_image)
        self.base_image = canvas

        for ann in self.annotations:
            ann.translate(pad, pad)
        self._refresh_base_surface()
        self.toast_overlay.add_toast(Adw.Toast(title="Added drop shadow"))

    def _apply_torn_edge(self) -> None:
        w, h = self.base_image.size
        tooth = 10
        depth = 7

        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        pts = [(0, 0), (w, 0)]

        # Jagged right edge
        y = 0
        while y < h:
            pts.append((w - random.randint(0, depth), y))
            y += tooth
        pts.append((w - random.randint(0, depth), h))

        # Jagged bottom edge
        x = w
        while x > 0:
            pts.append((x, h - random.randint(0, depth)))
            x -= tooth
        pts.append((0, h - random.randint(0, depth)))

        draw.polygon(pts, fill=255)
        torn = self.base_image.copy()
        torn.putalpha(mask)
        self.base_image = torn
        self._apply_drop_shadow()
        self.toast_overlay.add_toast(Adw.Toast(title="Added torn-edge border"))

    def _commit(self, ann: Annotation) -> None:
        self.annotations.append(ann)
        self.redo_stack.clear()
        self.canvas.queue_draw()

    def _undo(self) -> None:
        if self.annotations:
            self.redo_stack.append(self.annotations.pop())
            self.canvas.queue_draw()

    def _redo(self) -> None:
        if self.redo_stack:
            self.annotations.append(self.redo_stack.pop())
            self.canvas.queue_draw()

    def _render_flattened_png(self) -> bytes:
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self.base_image.width, self.base_image.height
        )
        cr = cairo.Context(surface)
        cr.set_source_surface(self.base_surface, 0, 0)
        cr.paint()
        for ann in self.annotations:
            ann.draw(cr, self.base_image)
        buf = io.BytesIO()
        surface.write_to_png(buf)
        return buf.getvalue()

    def _copy_flattened(self) -> None:
        png_bytes = self._render_flattened_png()
        copy_bytes_to_clipboard(png_bytes)
        self.toast_overlay.add_toast(Adw.Toast(title="Copied to clipboard!"))

    def _save_as(self) -> None:
        dialog = Gtk.FileDialog(title="Save Annotated Screenshot")
        dialog.set_initial_name(default_save_path().name)
        dialog.save(self, None, self._on_save_done)

    def _on_save_done(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.save_finish(result)
            if gfile:
                out_path = Path(gfile.get_path())
                png_bytes = self._render_flattened_png()
                if out_path.suffix.lower() in (".jpg", ".jpeg"):
                    Image.open(io.BytesIO(png_bytes)).convert("RGB").save(out_path, "JPEG", quality=92)
                else:
                    out_path.write_bytes(png_bytes)
                self.toast_overlay.add_toast(Adw.Toast(title=f"Saved {out_path.name}"))
        except GLib.Error:
            pass
