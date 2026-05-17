"""xnn 排行榜命令。

提供 /xnn 命令，按照（被 ccb 次数 + 累计注入量 - 主动 ccb 次数）的加权方式
计算群中最 xnn 特质的群友排行榜。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_text
from src.app.plugin_system.base import BaseCommand, cmd_route

from .. import ccb_logic
from ..utils import lookup_nickname, resolve_nickname, stream_group_key

if TYPE_CHECKING:
    from src.core.models.message import Message

    from ..plugin import CCBPlugin

logger = get_logger("ccb.xnn")


class XNNCommand(BaseCommand):
    """xnn 排行榜命令。"""

    command_name: str = "xnn"
    command_description: str = "💎 小南梁 TOP5 排行榜"

    plugin: "CCBPlugin"

    def __init__(
        self,
        plugin: "CCBPlugin",
        stream_id: str,
        message_id: str = "",
        message: "Message | None" = None,
    ) -> None:
        """初始化 xnn 命令。"""
        super().__init__(plugin, stream_id, message_id, message)

    async def _resolve_nickname(self, user_id: str) -> str:
        """解析用户昵称。"""
        nickname = resolve_nickname(user_id, message=self._message)
        if nickname and nickname != user_id:
            return nickname
        platform = (
            str(self._message.platform) if self._message and self._message.platform else ""
        )
        if platform:
            return await lookup_nickname(platform, user_id)
        return user_id

    @cmd_route()
    async def handle_xnn(self) -> tuple[bool, str]:
        """执行 xnn 排行榜命令。"""
        group_key = stream_group_key(self.stream_id, self._message)
        ranking = await ccb_logic.get_xnn_ranking(group_key)
        if not ranking:
            await send_text("当前群暂无ccb记录。", stream_id=self.stream_id)
            return True, "empty"

        lines = ["💎 小南梁 TOP5 💎"]
        for idx, entry in enumerate(ranking, 1):
            nick = await self._resolve_nickname(str(entry["user_id"]))
            lines.append(f"{idx}. {nick} - XNN值：{entry['xnn']:.2f}")
        await send_text("\n".join(lines), stream_id=self.stream_id)
        return True, "ok"
