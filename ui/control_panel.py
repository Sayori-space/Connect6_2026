"""
ControlPanel：右侧信息面板。

风格与参考截图一致：纯黑背景、像素字体文本标签显示玩家名、
当前回合和剩余棋子数，下面是 PixelButton 操作按钮。
所有字体都会随面板宽度缩放。
"""

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

import ui.theme as theme
from ui.pixel_widgets import PixelButton, pixel_font
from ui.sound_manager import SoundManager
from utils.constants import BLACK, WHITE


def _format_turn_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


# ── 信息标签控件 ───────────────────────────────────────────────────────

from PyQt5.QtWidgets import QLabel


class _InfoLabel(QLabel):
    """单行信息标签；字体随面板宽度缩放。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"color: {theme.FG}; background: transparent;")
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)


class _DimLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"color: {theme.DIM}; background: transparent;")
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)


# ── 主面板 ─────────────────────────────────────────────────────────────

class ControlPanel(QWidget):
    confirm_requested    = pyqtSignal()
    undo_stone_requested = pyqtSignal()
    undo_turn_requested  = pyqtSignal()
    save_manual_requested = pyqtSignal()
    go_home_requested    = pyqtSignal()

    _MIN_W = 180
    _MAX_W = 480
    _REF_W = 220   # 字体计算参考宽度

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {theme.BG};")
        self.setMinimumWidth(self._MIN_W)
        self.setMaximumWidth(self._MAX_W)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 24, 20, 20)
        root.setSpacing(0)

        # ── 信息标签 ─────────────────────────────────────────────────
        self._black_lbl  = _InfoLabel("黑方：—")
        self._white_lbl  = _InfoLabel("白方：—")
        self._cur_lbl    = _InfoLabel("当前：—")
        self._remain_lbl = _InfoLabel("剩余：—")
        self._timer_lbl  = _InfoLabel("思考：00:00")
        self._ai_lbl     = _DimLabel("")

        for lbl in (self._black_lbl, self._white_lbl,
                    self._cur_lbl, self._remain_lbl,
                    self._timer_lbl, self._ai_lbl):
            root.addWidget(lbl)
            root.addSpacing(4)

        root.addStretch(1)

        # ── 按钮 ─────────────────────────────────────────────────────
        self._confirm_btn    = PixelButton("确认落子")
        self._undo_stone_btn = PixelButton("撤回一步")
        self._undo_turn_btn  = PixelButton("悔棋")
        self._save_btn       = PixelButton("保存棋谱")
        self._home_btn       = PixelButton("返回主界面")
        self._mute_btn       = PixelButton("音效: 开", silent=True)

        self._confirm_btn.setVisible(False)

        for btn in (self._confirm_btn, self._undo_stone_btn,
                    self._undo_turn_btn, self._save_btn, self._home_btn,
                    self._mute_btn):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            root.addWidget(btn)
            root.addSpacing(8)

        self._confirm_btn.clicked.connect(self.confirm_requested)
        self._undo_stone_btn.clicked.connect(self.undo_stone_requested)
        self._undo_turn_btn.clicked.connect(self.undo_turn_requested)
        self._save_btn.clicked.connect(self.save_manual_requested)
        self._home_btn.clicked.connect(self.go_home_requested)
        self._mute_btn.clicked.connect(self._on_mute_clicked)

        self._apply_scale(self._REF_W)

    # ── 响应式缩放 ───────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scale(event.size().width())

    def _apply_scale(self, w: int) -> None:
        scale   = max(0.80, min(2.0, w / self._REF_W))
        lbl_sz  = max(10, round(13 * scale))
        btn_sz  = max(10, round(13 * scale))
        btn_h   = max(40, round(48 * scale))
        spacing = max(6,  round(8  * scale))

        fnt = pixel_font(lbl_sz)
        for lbl in (self._black_lbl, self._white_lbl,
                    self._cur_lbl, self._remain_lbl,
                    self._timer_lbl, self._ai_lbl):
            lbl.setFont(fnt)
            lbl.setMinimumHeight(max(22, round(26 * scale)))

        for btn in (self._confirm_btn, self._undo_stone_btn,
                    self._undo_turn_btn, self._save_btn, self._home_btn,
                    self._mute_btn):
            btn.setFont(pixel_font(btn_sz))
            btn.setMinimumHeight(btn_h)

        # 更新布局间距
        lay = self.layout()
        if lay:
            lay.setContentsMargins(
                max(12, round(20 * scale)),
                max(16, round(24 * scale)),
                max(12, round(20 * scale)),
                max(12, round(20 * scale)),
            )

    # ── 状态 API ─────────────────────────────────────────────────────

    def set_player_names(self, black_name: str, white_name: str) -> None:
        self._black_lbl.setText(f"黑方：{black_name}")
        self._white_lbl.setText(f"白方：{white_name}")

    def update_turn(self, color: int, stones_needed: int,
                    stones_placed: int = 0) -> None:
        who = "黑方" if color == BLACK else "白方"
        self._cur_lbl.setText(f"当前：{who}")
        remaining = stones_needed - stones_placed
        self._remain_lbl.setText(f"剩余：{remaining}")
        self._confirm_btn.setVisible(False)

    def update_stones_placed(self, placed: int, needed: int) -> None:
        remaining = needed - placed
        self._remain_lbl.setText(f"剩余：{remaining}")

    def update_turn_timer(self, seconds: int) -> None:
        self._timer_lbl.setText(f"思考：{_format_turn_seconds(seconds)}")

    def update_ai_time_remaining(self, seconds: float) -> None:
        self._timer_lbl.setText(f"AI剩余：{_format_turn_seconds(round(seconds))}")

    def show_confirm_button(self, visible: bool) -> None:
        self._confirm_btn.setVisible(visible)

    def set_ai_info(self, ai_name: str) -> None:
        """显示当前 AI 名称。"""
        self._ai_lbl.setText(f"AI：{ai_name}" if ai_name else "")

    def update_game_over(self, winner_color: Optional[int],
                         message: str) -> None:
        self._cur_lbl.setText(message)
        self._remain_lbl.setText("")
        self._confirm_btn.setVisible(False)
        self._undo_stone_btn.setEnabled(False)
        self._undo_turn_btn.setEnabled(False)

    def reset_for_new_game(self) -> None:
        self._save_btn.setEnabled(True)
        self._undo_stone_btn.setEnabled(True)
        self._undo_turn_btn.setEnabled(True)
        self._confirm_btn.setVisible(False)
        self._cur_lbl.setText("当前：—")
        self._remain_lbl.setText("剩余：—")
        self.update_turn_timer(0)

    def _on_mute_clicked(self) -> None:
        muted = SoundManager.instance().toggle_mute()
        self._mute_btn.setText("音效: 关" if muted else "音效: 开")

    def paintEvent(self, _event) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))
