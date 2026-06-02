"""
BoardWidget：像素风游戏棋盘。

相对原始版本的视觉变化：
  • 纯黑背景，深灰色棋盘区域（#2A2A2A）。
  • 白色网格线，不使用木纹配色。
  • 左侧显示行号（1-19），顶部显示列字母（A-S）。
  • 星位标记替换为低调的灰色圆点。
  • 获胜高光为金黄色，保证黑白棋子上都清晰可见。
"""

import math
from typing import List, Optional, Tuple

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush, QColor, QFontMetrics, QPainter, QPen, QRadialGradient,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

import ui.theme as theme
from ui.pixel_widgets import pixel_font
from utils.constants import (
    ANIM_FPS, BLACK, EMPTY, STONE_ANIM_DURATION,
    STONE_RADIUS_RATIO, WHITE, WIN_PULSE_SPEED,
)

# 控件边缘四周的外部留白
_OUTER      = 14

# 非对称内边距下限：左侧/顶部为坐标标签和外边距预留空间。
_PAD_LEFT   = 52 + _OUTER   # 行号列宽 + 外边距
_PAD_TOP    = 46 + _OUTER   # 列字母行高 + 外边距
_PAD_RIGHT  = _OUTER + 4
_PAD_BOTTOM = _OUTER + 4
_COORD_BAND_MIN = 54.0
_COORD_BAND_MAX = 104.0
_COORD_FONT_MIN = 14
_COORD_FONT_MAX = 30

# 在绘制区域内略微缩小棋盘，为坐标留出更多空间。
_BOARD_DRAW_SCALE = 0.95

# 19×19 棋盘的参考点：中心点 + 四个靠近角落的点
_REFERENCE_POINTS_19 = [
    (3, 3), (3, 15),
    (9, 9),
    (15, 3), (15, 15),
]


# ── 棋子动画 ──────────────────────────────────────────────────────────

class _StoneAnim:
    def __init__(self, row: int, col: int, color: int):
        self.row = row
        self.col = col
        self.color = color
        self._progress: float = 0.0

    def advance(self, dt: float) -> None:
        self._progress = min(1.0, self._progress + dt / STONE_ANIM_DURATION)

    @property
    def scale(self) -> float:
        t = self._progress
        if t >= 1.0:
            return 1.0
        c1, c3 = 1.70158, 1.70158 + 1
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

    @property
    def done(self) -> bool:
        return self._progress >= 1.0


# ── 主控件 ────────────────────────────────────────────────────────────

class BoardWidget(QWidget):
    stone_clicked  = pyqtSignal(int, int)
    undo_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._board_size: int = 19
        self._board = None
        self._hover: Optional[Tuple[int, int]] = None
        self._hover_color: int = BLACK
        self._interactive: bool = False
        self._winning_line: List[Tuple[int, int]] = []
        self._win_phase: float = 0.0
        self._current_turn_cells: set = set()

        self._animating: List[_StoneAnim] = []

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // ANIM_FPS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 400)
        self.setStyleSheet(f"background: {theme.BG};")

    # ── 公共 API ─────────────────────────────────────────────────────

    def set_board(self, board) -> None:
        self._board = board
        self._board_size = board.size
        self._animating.clear()
        self._winning_line.clear()
        self._current_turn_cells = set()
        self.update()

    def set_current_turn_stones(self, cells: List[Tuple[int, int]]) -> None:
        self._current_turn_cells = set(cells)
        self.update()

    def set_hover_color(self, color: int) -> None:
        self._hover_color = color

    def set_interactive(self, enabled: bool) -> None:
        self._interactive = enabled
        if not enabled:
            self._hover = None
        self.update()

    def animate_stone(self, move) -> None:
        self._animating.append(_StoneAnim(move.row, move.col, move.color))

    def show_winning_line(self, line: List[Tuple[int, int]]) -> None:
        self._winning_line = line
        self._win_phase = 0.0

    def clear_winning_line(self) -> None:
        self._winning_line = []
        self.update()

    # ── 动画 ─────────────────────────────────────────────────────────

    def _tick(self) -> None:
        dt = 1.0 / ANIM_FPS
        needs = False
        if self._animating:
            for a in self._animating:
                a.advance(dt)
            self._animating = [a for a in self._animating if not a.done]
            needs = True
        if self._winning_line:
            self._win_phase = (self._win_phase + dt * WIN_PULSE_SPEED) % (2 * math.pi)
            needs = True
        if needs:
            self.update()

    # ── 坐标辅助方法 ─────────────────────────────────────────────────

    def _draw_scale(self) -> float:
        win = self.window()
        if win is not None and win.isFullScreen():
            return 1.0
        return _BOARD_DRAW_SCALE

    def _coordinate_band_size(self) -> float:
        raw_w = max(1.0, self.width() - _PAD_LEFT - _PAD_RIGHT)
        raw_h = max(1.0, self.height() - _PAD_TOP - _PAD_BOTTOM)
        raw_cell = min(raw_w, raw_h) / max(1, self._board_size - 1)
        return max(_COORD_BAND_MIN, min(_COORD_BAND_MAX, raw_cell * 0.9))

    def _padding(self) -> Tuple[float, float, float, float]:
        band = self._coordinate_band_size()
        return _OUTER + band, _OUTER + band, float(_PAD_RIGHT), float(_PAD_BOTTOM)

    def _cell_size(self) -> float:
        pad_left, pad_top, pad_right, pad_bottom = self._padding()
        w_avail = self.width()  - pad_left - pad_right
        h_avail = self.height() - pad_top  - pad_bottom
        raw = max(1.0, min(w_avail, h_avail)) / (self._board_size - 1)
        return raw * self._draw_scale()

    def _to_pixel(self, row: int, col: int) -> QPointF:
        cs = self._cell_size()
        pad_left, pad_top, _, _ = self._padding()
        return QPointF(pad_left + col * cs, pad_top + row * cs)

    def _to_cell(self, px: float, py: float) -> Optional[Tuple[int, int]]:
        cs = self._cell_size()
        pad_left, pad_top, _, _ = self._padding()
        col = round((px - pad_left) / cs)
        row = round((py - pad_top)  / cs)
        if 0 <= row < self._board_size and 0 <= col < self._board_size:
            return row, col
        return None

    # ── 绘制 ─────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._draw_bg(p)
        self._draw_coordinates(p)
        self._draw_grid(p)
        self._draw_star_points(p)
        self._draw_stones(p)
        self._draw_hover(p)

    def _draw_bg(self, p: QPainter) -> None:
        cs = self._cell_size()
        n  = self._board_size
        pad_left, pad_top, _, _ = self._padding()

        # 整个控件：黑色
        p.fillRect(self.rect(), QColor(theme.BG))

        # 棋盘区域：深灰色
        board_rect = QRectF(
            pad_left - cs * 0.5,
            pad_top  - cs * 0.5,
            cs * (n - 1) + cs,
            cs * (n - 1) + cs,
        )
        p.fillRect(board_rect, QColor(theme.BOARD_BG))

    def _draw_coordinates(self, p: QPainter) -> None:
        cs  = self._cell_size()
        n   = self._board_size
        pad_left, pad_top, _, _ = self._padding()

        # 保持坐标文本可读，并避免与第一行/列棋子重叠。
        radius = cs * STONE_RADIUS_RATIO
        stone_clearance_y = radius + 5.0

        top_band_y = 2.0
        top_band_h = max(18.0, pad_top - stone_clearance_y - top_band_y)
        left_band_x = float(_OUTER)
        left_band_right = min(pad_left - 8.0, pad_left - radius - 2.0)
        left_band_w = max(28.0, left_band_right - left_band_x)

        # 窗口放大时按棋格尺寸放大坐标，再按标签区域收紧以避免重叠。
        base_size = max(
            _COORD_FONT_MIN,
            min(_COORD_FONT_MAX, int(cs * 0.44)),
        )
        fnt_size = base_size
        fnt = pixel_font(fnt_size)
        metrics = QFontMetrics(fnt)
        while (
            fnt_size > 10
            and (
                metrics.height() > top_band_h - 2
                or metrics.horizontalAdvance("19") > left_band_w - 2
                or metrics.horizontalAdvance("W") > cs - 2
            )
        ):
            fnt_size -= 1
            fnt = pixel_font(fnt_size)
            metrics = QFontMetrics(fnt)

        p.setFont(fnt)
        p.setPen(QColor(theme.DIM))

        # 列字母（A、B、C …）
        for c in range(n):
            letter = chr(ord('A') + c)
            cx = pad_left + c * cs
            p.drawText(
                QRectF(cx - cs / 2, top_band_y, cs, top_band_h),
                Qt.AlignCenter, letter,
            )

        # 行号（1、2、3 …）
        for r in range(n):
            num = str(r + 1)
            cy = pad_top + r * cs
            p.drawText(
                QRectF(left_band_x, cy - cs / 2, left_band_w, cs),
                Qt.AlignCenter, num,
            )

    def _draw_grid(self, p: QPainter) -> None:
        n   = self._board_size
        pen = QPen(QColor(theme.BOARD_LINE), 0.8)
        p.setPen(pen)
        for i in range(n):
            p.drawLine(self._to_pixel(i, 0), self._to_pixel(i, n - 1))
            p.drawLine(self._to_pixel(0, i), self._to_pixel(n - 1, i))

    def _draw_star_points(self, p: QPainter) -> None:
        if self._board_size != 19:
            return
        cs = self._cell_size()
        dot_r = max(3.0, min(6.0, cs * 0.09))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(245, 245, 245, 190))
        for r, c in _REFERENCE_POINTS_19:
            ctr = self._to_pixel(r, c)
            p.drawEllipse(ctr, dot_r, dot_r)

    def _draw_stones(self, p: QPainter) -> None:
        if self._board is None:
            return
        cs       = self._cell_size()
        radius   = cs * STONE_RADIUS_RATIO
        win_set  = set(self._winning_line)
        anim_set = {(a.row, a.col) for a in self._animating}

        for r in range(self._board_size):
            for c in range(self._board_size):
                color = self._board.get(r, c)
                if color == EMPTY or (r, c) in anim_set:
                    continue
                self._draw_stone(p, self._to_pixel(r, c), radius,
                                 color, 1.0, (r, c) in win_set,
                                 (r, c) in self._current_turn_cells)

        for anim in self._animating:
            self._draw_stone(p, self._to_pixel(anim.row, anim.col),
                             radius, anim.color, anim.scale,
                             (anim.row, anim.col) in win_set,
                             (anim.row, anim.col) in self._current_turn_cells)

    def _draw_stone(self, p: QPainter, center: QPointF, radius: float,
                    color: int, scale: float, glowing: bool,
                    current: bool = False) -> None:
        r = radius * max(0.01, scale)
        p.save()

        # 获胜高光
        if glowing:
            pulse    = 0.5 + 0.5 * math.sin(self._win_phase)
            glow_r   = r * 1.55
            glow_col = QColor(theme.WIN_GLOW)
            glow_col.setAlpha(int(60 + 180 * pulse))
            p.setPen(Qt.NoPen)
            p.setBrush(glow_col)
            p.drawEllipse(
                QRectF(center.x() - glow_r, center.y() - glow_r,
                       2 * glow_r, 2 * glow_r)
            )

        # 投影
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawEllipse(QRectF(center.x() - r + 2, center.y() - r + 3,
                             2 * r, 2 * r))

        # 棋子渐变
        grad = QRadialGradient(center.x() - r * 0.3,
                               center.y() - r * 0.35, r * 1.3)
        if color == BLACK:
            grad.setColorAt(0.0, QColor(theme.BLACK_STONE_HIGHLIGHT))
            grad.setColorAt(1.0, QColor(theme.BLACK_STONE_TOP))
            p.setPen(Qt.NoPen)
        else:
            grad.setColorAt(0.0, QColor(theme.WHITE_STONE_HIGHLIGHT))
            grad.setColorAt(0.6, QColor(theme.WHITE_STONE_TOP))
            grad.setColorAt(1.0, QColor(theme.WHITE_STONE_SHADOW))
            p.setPen(QPen(QColor(160, 160, 160, 140), 0.5))

        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r))

        # 当前回合标记：中心的小型反差色圆点
        if current:
            dot_r = r * 0.27
            p.setPen(Qt.NoPen)
            if color == BLACK:
                p.setBrush(QColor(255, 255, 255, 210))
            else:
                p.setBrush(QColor(40, 40, 40, 200))
            p.drawEllipse(QRectF(
                center.x() - dot_r, center.y() - dot_r,
                2 * dot_r, 2 * dot_r,
            ))

        p.restore()

    def _draw_hover(self, p: QPainter) -> None:
        if not self._interactive or self._hover is None or self._board is None:
            return
        r, c = self._hover
        if not self._board.is_empty(r, c):
            return
        cs     = self._cell_size()
        radius = cs * STONE_RADIUS_RATIO
        center = self._to_pixel(r, c)
        rect   = QRectF(center.x() - radius, center.y() - radius,
                        2 * radius, 2 * radius)
        if self._hover_color == BLACK:
            fill   = QColor(60, 60, 60, 150)
            border = QColor(140, 140, 140, 180)
        else:
            fill   = QColor(220, 220, 220, 150)
            border = QColor(200, 200, 200, 180)
        p.setPen(QPen(border, 1.0))
        p.setBrush(fill)
        p.drawEllipse(rect)

    # ── 鼠标事件 ─────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:
        cell = self._to_cell(event.x(), event.y())
        if cell != self._hover:
            self._hover = cell
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.undo_requested.emit()
            return
        if not self._interactive:
            return
        if event.button() == Qt.LeftButton:
            cell = self._to_cell(event.x(), event.y())
            if cell is not None:
                self.stone_clicked.emit(*cell)

    def resizeEvent(self, _event) -> None:
        # 防止控件宽度超过方形绘制区域。
        # 高度受限时，cs = h_avail / (n-1)；棋盘视觉宽度
        # 约为 _PAD_LEFT + cs * n + _PAD_RIGHT。限制宽度可避免空白间隙。
        h = self.height()
        if h > 0:
            pad_left, pad_top, pad_right, pad_bottom = self._padding()
            cs = (
                max(1.0, h - pad_top - pad_bottom)
                / (self._board_size - 1)
            ) * self._draw_scale()
            ideal_w = int(pad_left + cs * self._board_size + pad_right + 8)
            self.setMaximumWidth(max(400, ideal_w))
        self.update()
