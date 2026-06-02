"""
sound_manager.py：全局音频单例。

用法：
    from ui.sound_manager import SoundManager
    SoundManager.instance().play_stone()
    SoundManager.instance().play_hover()
    SoundManager.instance().play_click()
    SoundManager.instance().toggle_mute()  # 返回新的静音状态（bool）
    SoundManager.instance().is_muted()     # 返回 bool

如果 PyQt5.QtMultimedia 不可用，则平滑降级为空操作。
"""

import os

_AUDIO_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "audio")
)

_FILE_STONE = "在棋盘上落子的声音_耳聆网_[声音ID：39400].mp3"
_FILE_HOVER = "程序生成音效_耳聆网_[声音ID：12614].wav"
_FILE_CLICK = "ezyZip.mp3"


try:
    from PyQt5.QtCore import QUrl
    from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

    class SoundManager:
        """懒加载单例，每个音效持有一个 QMediaPlayer。"""

        _instance: "SoundManager | None" = None

        @classmethod
        def instance(cls) -> "SoundManager":
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

        def __init__(self) -> None:
            self._muted = False
            self._stone = self._make_player(_FILE_STONE)
            self._hover = self._make_player(_FILE_HOVER)
            self._click = self._make_player(_FILE_CLICK)

        @staticmethod
        def _make_player(filename: str) -> QMediaPlayer:
            path = os.path.abspath(os.path.join(_AUDIO_DIR, filename))
            player = QMediaPlayer()
            player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            return player

        def _play(self, player: QMediaPlayer) -> None:
            if self._muted:
                return
            player.setPosition(0)
            player.play()

        def play_stone(self) -> None:
            self._play(self._stone)

        def play_hover(self) -> None:
            self._play(self._hover)

        def play_click(self) -> None:
            self._play(self._click)

        def toggle_mute(self) -> bool:
            self._muted = not self._muted
            return self._muted

        def is_muted(self) -> bool:
            return self._muted

except ImportError as _e:
    print(f"[sound_manager] QtMultimedia unavailable ({_e}), audio disabled")

    class SoundManager:  # type: ignore[no-redef]
        """QtMultimedia 缺失时使用的空操作兜底实现。"""

        _instance: "SoundManager | None" = None

        @classmethod
        def instance(cls) -> "SoundManager":
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

        def play_stone(self) -> None: pass
        def play_hover(self) -> None: pass
        def play_click(self) -> None: pass
        def toggle_mute(self) -> bool: return False
        def is_muted(self) -> bool: return False
