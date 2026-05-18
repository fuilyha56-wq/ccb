"""ccb 主命令组件。

提供 /ccb 主命令以及子命令：
    /ccb [@目标 | uid]      与目标进行 ccb
    /ccb top                按次数排行榜 TOP5
    /ccb vol                按累计注入量排行榜 TOP5
    /ccb max                单次最大注入量排行榜 TOP5
    /ccb info [@目标 | uid] 查看个人 ccb 信息
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from src.app.plugin_system.api import send_api
from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_image, send_text
from src.app.plugin_system.base import BaseCommand, cmd_route
from src.core.models.message import MessageType

from .. import ccb_logic
from ..config import CCBConfig
from ..storage import FIELD_NUM, FIELD_VOL, RateLimiter, get_avatar
from ..utils import (
    extract_id_from_args,
    lookup_nickname,
    parse_at_targets,
    resolve_nickname,
    stream_group_key,
)

if TYPE_CHECKING:
    from src.core.models.message import Message

    from ..plugin import CCBPlugin

logger = get_logger("ccb.command")


class CCBCommand(BaseCommand):
    """ccb 主命令实现。"""

    command_name: str = "ccb"
    command_description: str = "和群友赛博sex的娱乐命令"

    plugin: "CCBPlugin"  # 由 PluginManager 注入

    # 共享限流器（命令实例每次新建，因此挂在类上）
    _limiter: RateLimiter | None = None

    def __init__(
        self,
        plugin: "CCBPlugin",
        stream_id: str,
        message_id: str = "",
        message: "Message | None" = None,
    ) -> None:
        """初始化命令并保证限流器配置最新。

        注意：BaseCommand.__init__ 会调用 inspect.getmembers，触发本类的
        property 访问，所以限流器必须在 super().__init__() 之前就备好，
        且任何属性都不能在初始化未完成时抛异常。
        """
        cfg = self._read_cfg(plugin)
        self._ensure_limiter(cfg)
        super().__init__(plugin, stream_id, message_id, message)

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _read_cfg(plugin: "CCBPlugin") -> CCBConfig:
        """从 plugin 读取配置（静态版，便于在 super().__init__ 前调用）。"""
        cfg = plugin.config
        if not isinstance(cfg, CCBConfig):
            raise RuntimeError("ccb 插件配置未正确注入")
        return cfg

    @classmethod
    def _ensure_limiter(cls, cfg: CCBConfig) -> RateLimiter:
        """初始化或刷新共享限流器。"""
        if cls._limiter is None:
            cls._limiter = RateLimiter(
                window=cfg.limit.yw_window,
                threshold=cfg.limit.yw_threshold,
                ban_duration=cfg.limit.yw_ban_duration,
            )
        else:
            cls._limiter.update_settings(
                window=cfg.limit.yw_window,
                threshold=cfg.limit.yw_threshold,
                ban_duration=cfg.limit.yw_ban_duration,
            )
        return cls._limiter

    def _cfg(self) -> CCBConfig:
        """获取插件配置。"""
        return self._read_cfg(self.plugin)

    @property
    def limiter(self) -> RateLimiter:
        """全局限流器单例。"""
        if CCBCommand._limiter is None:
            CCBCommand._limiter = RateLimiter(
                window=60,
                threshold=5,
                ban_duration=900,
            )
        return CCBCommand._limiter

    def _sender_id(self) -> str:
        """读取消息发送者 ID。"""
        if self._message is None:
            return ""
        return str(self._message.sender_id or "")

    def _platform(self) -> str:
        """读取消息平台。"""
        if self._message is None:
            return ""
        return str(self._message.platform or "")

    def _group_key(self) -> str:
        """获取数据分组键。"""
        return stream_group_key(self.stream_id, self._message)

    async def _reply_text(self, text: str) -> None:
        """向当前流发送文本。"""
        await send_text(text, stream_id=self.stream_id)

    async def _reply_image(self, image_url: str, caption: str = "") -> None:
        """向当前流发送图片。"""
        await send_image(
            image_url,
            stream_id=self.stream_id,
            processed_plain_text=caption or "[图片]",
        )

    async def _reply_text_image_text(
        self,
        head_text: str,
        image_url: str,
        tail_text: str,
    ) -> bool:
        """在一条消息里同时发送 文本 + 图片 + 文本。

        通过 send_api 内部的 ``extra_media`` 通道把多个段拼到同一个
        MessageEnvelope 里，由适配器作为单条消息的多个 segment 一起下发，
        避免拆成 3 条消息分别推送。最终 envelope 中的段顺序为：
        text(head) → image → text(tail)。

        注意：转换器在出站路径上会优先用 ``processed_plain_text`` 作为
        第一个 text 段的内容，因此这里直接传 ``head_text``，不要把整段
        汇总文本塞进去，否则第一段会重复包含 tail。

        Args:
            head_text: 第一段文本
            image_url: 图片 URL 或 base64
            tail_text: 第三段文本

        Returns:
            是否发送成功
        """
        extra_media: list[dict] = [{"type": "image", "data": image_url}]
        if tail_text:
            extra_media.append({"type": "text", "data": tail_text})

        return await send_api._send_message(
            content=head_text,
            message_type=MessageType.TEXT,
            stream_id=self.stream_id,
            processed_plain_text=head_text,
            extra_media=extra_media,
        )

    async def _resolve_nickname(
        self,
        user_id: str,
        at_users: list[dict[str, str]] | None = None,
    ) -> str:
        """解析昵称：先用 at/sender，再回落到数据库。"""
        nickname = resolve_nickname(user_id, message=self._message, at_users=at_users)
        if nickname and nickname != user_id:
            return nickname
        platform = self._platform()
        if platform:
            return await lookup_nickname(platform, user_id)
        return user_id

    # --------------------------------------------------------------- 路由方法

    @cmd_route()
    async def handle_ccb(self, *targets: str) -> tuple[bool, str]:
        """执行一次 ccb（无子命令时的默认动作）。"""
        return await self._do_ccb(list(targets))

    @cmd_route("top")
    async def handle_top(self) -> tuple[bool, str]:
        """按 ccb 次数排行榜 TOP5。"""
        return await self._do_top(rank_by=FIELD_NUM, title="被ccb排行榜 TOP5", unit="次数")

    @cmd_route("vol")
    async def handle_vol(self) -> tuple[bool, str]:
        """按累计注入量排行榜 TOP5。"""
        return await self._do_top(rank_by=FIELD_VOL, title="被注入量排行榜 TOP5", unit="累计注入")

    @cmd_route("max")
    async def handle_max(self) -> tuple[bool, str]:
        """单次最大注入量排行榜 TOP5。"""
        return await self._do_max()

    @cmd_route("info")
    async def handle_info(self, *targets: str) -> tuple[bool, str]:
        """查看个人 ccb 信息。"""
        return await self._do_info(list(targets))

    # ----------------------------------------------------------- 核心子命令

    async def _do_ccb(self, args: list[str]) -> tuple[bool, str]:
        """执行 ccb 主流程。"""
        cfg = self._cfg()
        send_id = self._sender_id()
        if not send_id:
            await self._reply_text("无法识别当前用户，无法执行 ccb。")
            return False, "missing sender"

        actor_id = send_id

        remain = self.limiter.check_ban(actor_id)
        if remain > 0:
            m, s = divmod(remain, 60)
            await self._reply_text(f"嘻嘻，你已经一滴不剩了，养胃还剩 {m}分{s}秒")
            return True, "in cooldown"

        if self.limiter.record_action(actor_id):
            await self._reply_text("冲得出来吗你就冲，再冲就给你折了")
            return True, "rate limited"

        at_users = parse_at_targets(self._message)
        target_user_id = ""
        for item in at_users:
            uid = str(item.get("user_id") or "")
            if uid and uid != send_id:
                target_user_id = uid
                break
        if not target_user_id:
            extracted = extract_id_from_args(args)
            if extracted and extracted != send_id:
                target_user_id = extracted
        if not target_user_id:
            target_user_id = send_id

        # 白名单
        if target_user_id in cfg.rule.white_list:
            nickname = await self._resolve_nickname(target_user_id, at_users)
            await self._reply_text(f"{nickname} 的后门被后户之神霸占了，不能ccb（悲")
            return True, "whitelisted"

        if target_user_id == actor_id and not cfg.rule.self_ccb:
            await self._reply_text("兄啊金箔怎么还能捅到自己的啊（恼）")
            return True, "self ccb disabled"

        try:
            result = await ccb_logic.perform_ccb(
                group_id=self._group_key(),
                actor_id=actor_id,
                target_id=target_user_id,
                crit_prob=cfg.rule.crit_prob,
                is_log=cfg.rule.is_log,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"ccb 执行错误: {exc}")
            await self._reply_text("对方拒绝了和你ccb")
            return False, str(exc)

        nickname = await self._resolve_nickname(target_user_id, at_users)
        duration = result["duration"]
        volume = result["vol"]
        crit = result["crit"]
        num = result["num"]
        is_first = result["is_first"]

        head = (
            f"你和{nickname}发生了{duration}min长的ccb行为，"
            f"向ta注入了{'💥 暴击！' if crit else ''}{volume:.2f}ml的生命因子"
        )
        tail = "这是ta的初体验。" if is_first else f"这是ta的第{num}次。"

        # 一次性把 文本 + 头像 + 文本 拼成同一条消息发出，
        # 避免被拆成 3 条独立消息。
        await self._reply_text_image_text(
            head_text=head,
            image_url=get_avatar(target_user_id),
            tail_text=tail,
        )

        if random.random() < cfg.limit.yw_probability:
            self.limiter.trigger_random_ban(actor_id)
            await self._reply_text("💥你的牛牛炸膛了！满身疮痍，再起不能（悲）")

        return True, "ok"

    async def _do_top(self, *, rank_by: str, title: str, unit: str) -> tuple[bool, str]:
        """通用排行榜（次数 / 注入量）。"""
        ranking = await ccb_logic.get_ranking(self._group_key(), rank_by=rank_by)
        if not ranking:
            await self._reply_text("当前群暂无ccb记录。")
            return True, "empty"

        lines = [f"{title}："]
        for idx, entry in enumerate(ranking, 1):
            uid = entry["user_id"]
            nick = await self._resolve_nickname(uid)
            if rank_by == FIELD_NUM:
                lines.append(f"{idx}. {nick} - {unit}：{entry['num']}")
            else:
                lines.append(f"{idx}. {nick} - {unit}：{entry['vol']:.2f}ml")
        await self._reply_text("\n".join(lines))
        return True, "ok"

    async def _do_max(self) -> tuple[bool, str]:
        """单次最大注入量排行。"""
        ranking = await ccb_logic.get_max_ranking(self._group_key())
        if not ranking:
            await self._reply_text("当前群暂无ccb记录。")
            return True, "empty"

        lines = ["单次最大注入排行榜 TOP5："]
        for idx, entry in enumerate(ranking, 1):
            nick = await self._resolve_nickname(entry["user_id"])
            producer_id = entry.get("producer_id")
            producer_nick = (
                await self._resolve_nickname(str(producer_id))
                if producer_id
                else "未知"
            )
            lines.append(
                f"{idx}. {nick} - 单次最大：{entry['max_vol']:.2f}ml（{producer_nick}）"
            )
        await self._reply_text("\n".join(lines))
        return True, "ok"

    async def _do_info(self, args: list[str]) -> tuple[bool, str]:
        """查看个人 ccb 信息。"""
        send_id = self._sender_id()
        at_users = parse_at_targets(self._message)
        target_id = ""
        for item in at_users:
            uid = str(item.get("user_id") or "")
            if uid:
                target_id = uid
                break
        if not target_id:
            extracted = extract_id_from_args(args)
            if extracted:
                target_id = extracted
        if not target_id:
            target_id = send_id
        if not target_id:
            await self._reply_text("无法识别查询目标。")
            return False, "missing target"

        info = await ccb_logic.get_user_info(self._group_key(), target_id)
        if info is None:
            await self._reply_text("该用户暂无ccb记录。")
            return True, "empty"

        nick = await self._resolve_nickname(target_id, at_users)
        first_actor = info.get("first_actor")
        first_nick = (
            await self._resolve_nickname(str(first_actor)) if first_actor else "未知"
        )
        lines = [
            f"📒 {nick} 的 ccb 档案",
            f"被ccb总次数：{info['total_num']}",
            f"累计被注入：{info['total_vol']:.2f}ml",
            f"单次最大注入：{info['max_val']:.2f}ml",
            f"首位攻略者：{first_nick}",
            f"对他人 ccb 总次数：{info['cb_total']}",
        ]
        await self._reply_text("\n".join(lines))
        return True, "ok"
