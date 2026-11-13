# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""支持 ``python -m weblinkcrawler`` 启动入口。

等价于仓库根目录的 ``python WebLinkCrawler.py``：调用
``weblinkcrawler.app:main`` 启动 GUI。配置与数据库按当前工作目录读写，
建议从项目根目录启动，以保持配置和数据库位置稳定。
"""

from .app import main

if __name__ == "__main__":
    main()
