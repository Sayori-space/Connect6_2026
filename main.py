"""
六子棋桌面客户端入口。
"""

import sys

from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QApplication

from ui.app_window import AppWindow
from ui.pixel_widgets import load_pixel_font, pixel_font


def main() -> None:
    # 在创建任何控件前全局设置 OpenGL 3.3 Core Profile。
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)

    # 加载像素位图字体，并作为应用默认字体。
    load_pixel_font()
    app.setFont(pixel_font(12))

    window = AppWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
