import io
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import cairo
from PIL import Image

Color = Tuple[float, float, float, float]  # RGBA (0.0 - 1.0)


@dataclass
class Annotation:
    x1: float
    y1: float
    x2: float
    y2: float
    color: Color = (0.61, 0.36, 0.90, 1.0)  # Cute Purple (#9b5de5)
    line_width: float = 3.0

    def bounds(self) -> Tuple[float, float, float, float]:
        return (
            min(self.x1, self.x2),
            min(self.y1, self.y2),
            max(self.x1, self.x2),
            max(self.y1, self.y2),
        )

    def hit_test(self, x: float, y: float, pad: float = 8.0) -> bool:
        bx1, by1, bx2, by2 = self.bounds()
        return (bx1 - pad) <= x <= (bx2 + pad) and (by1 - pad) <= y <= (by2 + pad)

    def translate(self, dx: float, dy: float) -> None:
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy

    def scale(self, sx: float, sy: float) -> None:
        self.x1 *= sx
        self.y1 *= sy
        self.x2 *= sx
        self.y2 *= sy

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        raise NotImplementedError


@dataclass
class FreehandAnnotation(Annotation):
    points: List[Tuple[float, float]] = field(default_factory=list)

    def bounds(self) -> Tuple[float, float, float, float]:
        if not self.points:
            return super().bounds()
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx: float, dy: float) -> None:
        super().translate(dx, dy)
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def scale(self, sx: float, sy: float) -> None:
        super().scale(sx, sy)
        self.points = [(x * sx, y * sy) for x, y in self.points]

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        if len(self.points) < 2:
            return
        cr.save()
        cr.set_source_rgba(*self.color)
        cr.set_line_width(self.line_width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(*self.points[0])
        for px, py in self.points[1:]:
            cr.line_to(px, py)
        cr.stroke()
        cr.restore()


@dataclass
class RectAnnotation(Annotation):
    fill: bool = False

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        x1, y1, x2, y2 = self.bounds()
        cr.save()
        cr.set_source_rgba(*self.color)
        cr.set_line_width(self.line_width)
        cr.rectangle(x1, y1, x2 - x1, y2 - y1)
        if self.fill:
            cr.fill()
        else:
            cr.stroke()
        cr.restore()


@dataclass
class EllipseAnnotation(Annotation):
    fill: bool = False

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        x1, y1, x2, y2 = self.bounds()
        w, h = x2 - x1, y2 - y1
        if w < 1 or h < 1:
            return
        cr.save()
        cr.translate(x1 + w / 2.0, y1 + h / 2.0)
        cr.scale(w / 2.0, h / 2.0)
        cr.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
        cr.restore()
        cr.save()
        cr.set_source_rgba(*self.color)
        cr.set_line_width(self.line_width)
        if self.fill:
            cr.fill()
        else:
            cr.stroke()
        cr.restore()


@dataclass
class LineAnnotation(Annotation):
    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        cr.save()
        cr.set_source_rgba(*self.color)
        cr.set_line_width(self.line_width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(self.x1, self.y1)
        cr.line_to(self.x2, self.y2)
        cr.stroke()
        cr.restore()


@dataclass
class ArrowAnnotation(Annotation):
    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        length = math.hypot(dx, dy)
        if length < 2:
            return

        angle = math.atan2(dy, dx)
        head_len = max(14.0, self.line_width * 4.5)
        head_angle = math.radians(28)

        cr.save()
        cr.set_source_rgba(*self.color)
        cr.set_line_width(self.line_width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        shaft_end_x = self.x2 - math.cos(angle) * (head_len * 0.6)
        shaft_end_y = self.y2 - math.sin(angle) * (head_len * 0.6)
        cr.move_to(self.x1, self.y1)
        cr.line_to(shaft_end_x, shaft_end_y)
        cr.stroke()

        p1x = self.x2 - head_len * math.cos(angle - head_angle)
        p1y = self.y2 - head_len * math.sin(angle - head_angle)
        p2x = self.x2 - head_len * math.cos(angle + head_angle)
        p2y = self.y2 - head_len * math.sin(angle + head_angle)
        cr.move_to(self.x2, self.y2)
        cr.line_to(p1x, p1y)
        cr.line_to(p2x, p2y)
        cr.close_path()
        cr.fill()
        cr.restore()


@dataclass
class HighlightAnnotation(Annotation):
    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        x1, y1, x2, y2 = self.bounds()
        cr.save()
        cr.set_source_rgba(1.0, 0.92, 0.23, 0.42)
        cr.set_operator(cairo.OPERATOR_MULTIPLY)
        cr.rectangle(x1, y1, x2 - x1, y2 - y1)
        cr.fill()
        cr.restore()


@dataclass
class TextAnnotation(Annotation):
    text: str = ""
    font_size: float = 20.0

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        if not self.text:
            return
        cr.save()
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(self.font_size)
        ext = cr.text_extents(self.text)
        self.x2 = self.x1 + ext.width + 12
        self.y2 = self.y1 + ext.height + 10

        cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
        cr.rectangle(self.x1 - 4, self.y1 - 4, ext.width + 12, ext.height + 12)
        cr.fill()

        cr.set_source_rgba(*self.color)
        cr.move_to(self.x1 + 2, self.y1 + ext.height + 2)
        cr.show_text(self.text)
        cr.restore()


@dataclass
class CounterAnnotation(Annotation):
    number: int = 1
    radius: float = 15.0

    def bounds(self) -> Tuple[float, float, float, float]:
        return (
            self.x1 - self.radius,
            self.y1 - self.radius,
            self.x1 + self.radius,
            self.y1 + self.radius,
        )

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        cr.save()
        cr.arc(self.x1, self.y1, self.radius, 0, 2 * math.pi)
        cr.set_source_rgba(*self.color)
        cr.fill_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.set_line_width(2.0)
        cr.stroke()

        label = str(self.number)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(self.radius * 1.1)
        ext = cr.text_extents(label)
        cr.move_to(
            self.x1 - (ext.width / 2 + ext.x_bearing),
            self.y1 - (ext.height / 2 + ext.y_bearing),
        )
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.show_text(label)
        cr.restore()


@dataclass
class ObfuscateAnnotation(Annotation):
    block_size: int = 10
    _cached_surface: Optional[cairo.ImageSurface] = field(default=None, repr=False)
    _cached_box: Optional[Tuple[int, int, int, int]] = field(default=None, repr=False)

    def translate(self, dx: float, dy: float) -> None:
        super().translate(dx, dy)
        self._cached_surface = None

    def scale(self, sx: float, sy: float) -> None:
        super().scale(sx, sy)
        self._cached_surface = None

    def draw(self, cr: cairo.Context, base_image: Image.Image) -> None:
        x1, y1, x2, y2 = self.bounds()
        ix1 = max(0, int(x1))
        iy1 = max(0, int(y1))
        ix2 = min(base_image.width, int(x2))
        iy2 = min(base_image.height, int(y2))
        if ix2 - ix1 < 2 or iy2 - iy1 < 2:
            return

        box = (ix1, iy1, ix2, iy2)
        if self._cached_surface is None or self._cached_box != box:
            patch = base_image.crop(box)
            small_w = max(1, patch.width // self.block_size)
            small_h = max(1, patch.height // self.block_size)
            pixelated = patch.resize(
                (small_w, small_h), Image.Resampling.NEAREST
            ).resize(patch.size, Image.Resampling.NEAREST)
            buf = io.BytesIO()
            pixelated.save(buf, format="PNG")
            buf.seek(0)
            self._cached_surface = cairo.ImageSurface.create_from_png(buf)
            self._cached_box = box

        cr.save()
        cr.set_source_surface(self._cached_surface, ix1, iy1)
        cr.paint()
        cr.restore()


def pil_to_cairo_surface(image: Image.Image) -> cairo.ImageSurface:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return cairo.ImageSurface.create_from_png(buf)
