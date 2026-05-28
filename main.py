"""
Entry point for the Connect6 (六子棋) desktop client.
"""

import sys

from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QApplication

from ui.app_window import AppWindow
from ui.pixel_widgets import load_pixel_font, pixel_font


def main() -> None:
    # Set OpenGL 3.3 Core Profile globally before any widget is created
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)

    # Load and apply pixel bitmap font as the application default
    load_pixel_font()
    app.setFont(pixel_font(12))

    window = AppWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
