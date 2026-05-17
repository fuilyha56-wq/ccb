"""ccb 插件入口。

将原 AstrBot 版本 ccb 插件迁移到 Neo-MoFox 框架。
提供 /ccb、/ccbtop、/ccbvol、/ccbinfo、/ccbmax、/xnn 等娱乐性命令。
"""
from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BasePlugin, register_plugin

from .commands.ccb_command import CCBCommand
from .commands.xnn_command import XNNCommand
from .config import CCBConfig

logger = get_logger("ccb")


@register_plugin
class CCBPlugin(BasePlugin):
    """ccb 娱乐插件。

    支持滑动窗口限流、养胃机制、暴击、白名单与多种排行榜命令。
    """

    plugin_name: str = "ccb"
    plugin_description: str = "和群友赛博sex的娱乐插件 PLUS"
    plugin_version: str = "1.0.0"

    configs: list[type] = [CCBConfig]
    dependent_components: list[str] = []

    async def on_plugin_loaded(self) -> None:
        """插件加载完成后的钩子。"""
        logger.info("ccb 插件已加载")

    async def on_plugin_unloaded(self) -> None:
        """插件卸载时的钩子。"""
        logger.info("ccb 插件已卸载")

    def get_components(self) -> list[type]:
        """返回插件提供的组件类。"""
        return [CCBCommand, XNNCommand]
