# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""PyInstaller 桌面版入口。

打包命令（在项目根目录执行）：

    python packaging/make_version_info.py
    pyinstaller --noconfirm --clean --onefile --windowed \
        --name WebLinkCrawler \
        --version-file packaging/version_info.txt \
        --collect-all ttkbootstrap \
        packaging/pyinstaller_desktop.py
"""

from weblinkcrawler.app import main

if __name__ == "__main__":
    main()
