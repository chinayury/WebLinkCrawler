# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""WebLinkCrawler —— 网页链接抓取工具。

模块化包结构；入口为 console script ``weblinkcrawler`` 与
``python -m weblinkcrawler``（见 ``weblinkcrawler.cli``），GUI 实现见
``weblinkcrawler.app``。版本历史见仓库根目录 CHANGELOG.md。
"""

# 版本号单一事实源之一（与 pyproject.toml version 严格对齐，随发布递增）
APP_VERSION = "0.4.3"
APP_NAME = "网页链接抓取工具"
APP_NAME_EN = "WebLinkCrawler"
APP_VENDOR = "智维ITMSKY"
APP_SITE = "http://www.itmsky.com"
APP_COPYRIGHT = "Copyright (C) 2026 智维ITMSKY"
APP_LICENSE = "AGPL-3.0-or-later"
APP_LICENSE_NAME = "GNU Affero General Public License v3.0 or later"

__all__ = [
    "APP_VERSION",
    "APP_NAME",
    "APP_NAME_EN",
    "APP_VENDOR",
    "APP_SITE",
    "APP_COPYRIGHT",
    "APP_LICENSE",
    "APP_LICENSE_NAME",
]
