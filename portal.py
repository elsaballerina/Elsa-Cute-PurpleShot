import tempfile
import uuid
from typing import Callable, List, Optional
import cairo
from PIL import Image
from gi.repository import Adw, Gdk, Gio, GLib, Gtk


class ScreenshotPortal:
    """Grabs the screen via XDG Desktop Portal."""

    BUS_NAME = "org.freedesktop.portal.Desktop"
    OBJECT_PATH = "/org/freedesktop/portal/desktop"
    INTERFACE = "org.freedesktop.portal.Screenshot"
    REQUEST_IFACE = "org.freedesktop.portal.Request"

    @classmethod
    def capture(
        cls,
        callback: Callable[[Optional[str]], None],
        interactive: bool = False,
    ) -> None:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        sender = bus.get_unique_name().lstrip(":").replace(".", "_")
        token = f"purpleshot_{uuid.uuid4().hex[:12]}"
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

        sub_id_holder = {"id": 0}

        def on_response(_conn, _sender, _path, _iface, _signal, params) -> None:
            if sub_id_holder["id"]:
                bus.signal_unsubscribe(sub_id_holder["id"])
                sub_id_holder["id"] = 0

            response_code, results = params.unpack()
            if response_code == 0 and "uri" in results:
                path = Gio.File.new_for_uri(results["uri"]).get_path()
                GLib.idle_add(callback, path)
            else:
                GLib.idle_add(callback, None)

        sub_id_holder["id"] = bus.signal_subscribe(
            cls.BUS_NAME,
            cls.REQUEST_IFACE,
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            on_response,
        )

        options = {
            "handle_token": GLib.Variant("s", token),
            "interactive": GLib.Variant("b", interactive),
            "modal": GLib.Variant("b", False),
        }

        bus.call(
            cls.BUS_NAME,
            cls.OBJECT_PATH,
            cls.INTERFACE,
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )


class MonitorOverlayWindow(Adw.ApplicationWindow):
    """Fast 1:1 Greenshot overlay using a GPU Gtk.Picture + lightweight Cairo HUD."""

    def __init__(
        self,
        app: Adw.Application,
        monitor: Gdk.Monitor,
        monitor_image: Image.Image,
        on_done: Callable[[Optional[str]], None],
    ) -> None:
        super().__init__(application=app, title="Elsa-Cute-PurpleShot Capture")
        self.on_done = on_done
        self.base_image = monitor_image

        # Fast GPU texture for the static background (zero CPU redraw on mouse move)
        rgba_bytes = GLib.Bytes.new(monitor_image.tobytes("raw", "RGBA"))
        bg_texture = Gdk.MemoryTexture.new(
            monitor_image.width,
            monitor_image.height,
            Gdk.MemoryFormat.R8G8B8A8,
            rgba_bytes,
            monitor_image.width * 4,
        )
        bg_picture = Gtk.Picture.new_for_paintable(bg_texture)
        bg_picture.set_content_fit(Gtk.ContentFit.FILL)

        # Direct BGRA buffer for the small 140x140 Cairo zoom scope (no PNG encoding)
        self._bgra_buf = bytearray(monitor_image.tobytes("raw", "BGRA"))
        self.base_surface = cairo.ImageSurface.create_for_data(
            self._bgra_buf,
            cairo.FORMAT_ARGB32,
            monitor_image.width,
            monitor_image.height,
            monitor_image.width * 4,
        )

        self.mouse_x = -1.0
        self.mouse_y = -1.0
        self.dragging = False
        self.start_x = 0.0
        self.start_y = 0.0
        self.end_x = 0.0
        self.end_y = 0.0

        self.set_decorated(False)
        self.fullscreen_on_monitor(monitor)

        # Transparent HUD canvas layered on top of the GPU background
        self.canvas = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.canvas.set_draw_func(self._on_draw)
        self.canvas.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.canvas.add_controller(motion)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.canvas.add_controller(drag)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        overlay = Gtk.Overlay()
        overlay.set_child(bg_picture)
        overlay.add_overlay(self.canvas)
        self.set_content(overlay)

    def _on_key_pressed(self, _ctrl, keyval: int, _keycode: int, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.on_done(None)
            return True
        return False

    def _on_motion(self, _ctrl, x: float, y: float) -> None:
        self.mouse_x = x
        self.mouse_y = y
        self.canvas.queue_draw()

    def _on_leave(self, _ctrl) -> None:
        if not self.dragging:
            self.mouse_x = -1.0
            self.mouse_y = -1.0
            self.canvas.queue_draw()

    def _on_drag_begin(self, _gesture, x: float, y: float) -> None:
        self.dragging = True
        self.start_x = x
        self.start_y = y
        self.end_x = x
        self.end_y = y
        self.mouse_x = x
        self.mouse_y = y
        self.canvas.queue_draw()

    def _on_drag_update(self, _gesture, offset_x: float, offset_y: float) -> None:
        self.end_x = self.start_x + offset_x
        self.end_y = self.start_y + offset_y
        self.mouse_x = self.end_x
        self.mouse_y = self.end_y
        self.canvas.queue_draw()

    def _on_drag_end(self, _gesture, _ox: float, _oy: float) -> None:
        self.dragging = False
        w = self.canvas.get_width() or 1
        h = self.canvas.get_height() or 1
        sx = self.base_image.width / w
        sy = self.base_image.height / h

        x1 = int(max(0, min(self.start_x, self.end_x) * sx))
        y1 = int(max(0, min(self.start_y, self.end_y) * sy))
        x2 = int(min(self.base_image.width, max(self.start_x, self.end_x) * sx))
        y2 = int(min(self.base_image.height, max(self.start_y, self.end_y) * sy))

        if (x2 - x1) < 5 or (y2 - y1) < 5:
            self.on_done(None)
            return

        cropped = self.base_image.crop((x1, y1, x2, y2))
        tmp = tempfile.NamedTemporaryFile(
            prefix="purpleshot_", suffix=".png", delete=False
        )
        cropped.save(tmp.name, "PNG")
        tmp.close()
        self.on_done(tmp.name)

    def _on_draw(self, _area, cr: cairo.Context, w: int, h: int) -> None:
        if w <= 0 or h <= 0:
            return
        sx = self.base_image.width / w
        sy = self.base_image.height / h

        # 1. Dim everything EXCEPT the dragged selection (GPU picture shows through!)
        cr.set_source_rgba(0.08, 0.05, 0.14, 0.35)
        if self.dragging:
            rx = min(self.start_x, self.end_x)
            ry = min(self.start_y, self.end_y)
            rw = abs(self.end_x - self.start_x)
            rh = abs(self.end_y - self.start_y)

            cr.rectangle(0, 0, w, ry)
            cr.rectangle(0, ry + rh, w, h - (ry + rh))
            cr.rectangle(0, ry, rx, rh)
            cr.rectangle(rx + rw, ry, w - (rx + rw), rh)
            cr.fill()

            # Cute purple selection border
            cr.set_source_rgba(0.69, 0.45, 0.98, 1.0)
            cr.set_line_width(2.0)
            cr.rectangle(rx, ry, rw, rh)
            cr.stroke()

            # Live W x H badge
            dim_text = f"{int(rw * sx)} × {int(rh * sy)}"
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(13)
            ext = cr.text_extents(dim_text)
            bx = rx + 6
            by = ry - 26 if ry > 30 else ry + 8
            cr.set_source_rgba(0.14, 0.10, 0.22, 0.90)
            cr.rectangle(bx - 4, by - 4, ext.width + 12, 22)
            cr.fill()
            cr.set_source_rgba(0.95, 0.92, 1.0, 1.0)
            cr.move_to(bx + 2, by + 12)
            cr.show_text(dim_text)
        else:
            cr.rectangle(0, 0, w, h)
            cr.fill()

        # 2. Crosshairs + 5x zoom scope on active monitor
        if self.mouse_x >= 0 and self.mouse_y >= 0:
            cr.set_source_rgba(0.75, 0.55, 1.0, 0.75)
            cr.set_line_width(1.0)
            cr.move_to(self.mouse_x, 0)
            cr.line_to(self.mouse_x, h)
            cr.move_to(0, self.mouse_y)
            cr.line_to(w, self.mouse_y)
            cr.stroke()

            self._draw_magnifier(cr, w, h, sx, sy)

    def _draw_magnifier(
        self, cr: cairo.Context, w: int, h: int, sx: float, sy: float
    ) -> None:
        loupe_size = 140
        zoom = 5.0
        ix = self.mouse_x * sx
        iy = self.mouse_y * sy

        lx = self.mouse_x + 24
        ly = self.mouse_y + 24
        if lx + loupe_size + 12 > w:
            lx = self.mouse_x - loupe_size - 24
        if ly + loupe_size + 34 > h:
            ly = self.mouse_y - loupe_size - 44

        cr.save()
        cr.rectangle(lx, ly, loupe_size, loupe_size)
        cr.clip()
        cr.translate(lx + loupe_size / 2.0, ly + loupe_size / 2.0)
        cr.scale(zoom, zoom)
        cr.translate(-ix, -iy)
        cr.set_source_surface(self.base_surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()

        cx = lx + loupe_size / 2.0
        cy = ly + loupe_size / 2.0
        cr.save()
        cr.set_source_rgba(0.69, 0.45, 0.98, 0.95)
        cr.set_line_width(1.5)
        cr.move_to(lx, cy)
        cr.line_to(lx + loupe_size, cy)
        cr.move_to(cx, ly)
        cr.line_to(cx, ly + loupe_size)
        cr.stroke()

        cr.set_source_rgba(0.75, 0.55, 1.0, 1.0)
        cr.set_line_width(2.5)
        cr.rectangle(lx, ly, loupe_size, loupe_size)
        cr.stroke()

        cr.set_source_rgba(0.14, 0.10, 0.22, 0.92)
        cr.rectangle(lx, ly + loupe_size, loupe_size, 22)
        cr.fill()
        cr.set_source_rgba(0.95, 0.92, 1.0, 1.0)
        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(11)
        cr.move_to(lx + 8, ly + loupe_size + 15)
        cr.show_text(f"X:{int(ix)}  Y:{int(iy)}")
        cr.restore()


class RegionCaptureOverlay:
    """Spawns a 1:1 MonitorOverlayWindow on every connected monitor."""

    def __init__(
        self,
        app: Adw.Application,
        full_image_path: str,
        on_cropped: Callable[[Optional[str]], None],
    ) -> None:
        self.windows: List[MonitorOverlayWindow] = []
        self.finished = False
        self.on_cropped = on_cropped

        full_img = Image.open(full_image_path).convert("RGBA")
        display = Gdk.Display.get_default()
        monitors_model = display.get_monitors()
        monitors = [
            monitors_model.get_item(i) for i in range(monitors_model.get_n_items())
        ]

        if not monitors:
            self.on_cropped(None)
            return

        geos = [m.get_geometry() for m in monitors]
        min_x = min(g.x for g in geos)
        min_y = min(g.y for g in geos)
        max_x = max(g.x + g.width for g in geos)
        max_y = max(g.y + g.height for g in geos)
        total_w = max(1, max_x - min_x)
        total_h = max(1, max_y - min_y)

        scale_x = full_img.width / total_w
        scale_y = full_img.height / total_h

        for mon, g in zip(monitors, geos):
            cx1 = int(round((g.x - min_x) * scale_x))
            cy1 = int(round((g.y - min_y) * scale_y))
            cx2 = int(round((g.x - min_x + g.width) * scale_x))
            cy2 = int(round((g.y - min_y + g.height) * scale_y))
            mon_img = full_img.crop((cx1, cy1, cx2, cy2))

            win = MonitorOverlayWindow(
                app=app,
                monitor=mon,
                monitor_image=mon_img,
                on_done=self._finish,
            )
            self.windows.append(win)

    def present(self) -> None:
        for win in self.windows:
            win.present()

    def _finish(self, crop_path: Optional[str]) -> None:
        if self.finished:
            return
        self.finished = True
        for win in self.windows:
            win.close()
        self.windows.clear()
        self.on_cropped(crop_path)
