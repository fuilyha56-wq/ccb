"""ccb 插件通用工具函数。

集中处理 @ 解析、目标判定与昵称获取等逻辑，避免在多个命令文件中重复。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from src.app.plugin_system.api.log_api import get_logger

if TYPE_CHECKING:
    from src.core.models.message import Message

logger = get_logger("ccb.utils")

_AT_TOKEN_PATTERN = re.compile(r"@<(?P<nickname>[^:>]*):(?P<user_id>[^>]+)>")


def parse_at_targets(message: "Message | None") -> list[dict[str, str]]:
    """从消息中解析出所有被 @ 的用户。

    优先从 ``message.extra['at_users']`` 取结构化数据；否则回退到正则
    解析 ``processed_plain_text`` 中的 ``@<nickname:user_id>`` 标记。

    Args:
        message: 消息对象

    Returns:
        被 @ 用户列表，每项形如 ``{"nickname": str, "user_id": str}``
    """
    if message is None:
        return []

    at_users: list[dict[str, str]] = []
    raw = message.extra.get("at_users") if hasattr(message, "extra") else None
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("user_id") or "").strip()
            if not user_id:
                continue
            at_users.append(
                {
                    "nickname": str(item.get("nickname") or user_id),
                    "user_id": user_id,
                }
            )

    if not at_users:
        text = getattr(message, "processed_plain_text", None) or ""
        for match in _AT_TOKEN_PATTERN.finditer(str(text)):
            user_id = match.group("user_id").strip()
            if not user_id:
                continue
            at_users.append(
                {
                    "nickname": (match.group("nickname") or user_id).strip() or user_id,
                    "user_id": user_id,
                }
            )

    return at_users


def extract_id_from_args(args: list[str]) -> str | None:
    """从命令参数中提取一个用户 ID。

    支持以下形式：
    - 纯数字：如 ``123456``
    - ``@<nick:uid>``：标准 at token
    - ``@123456`` / ``@昵称``：仅识别数字部分
    - ``[at:uid]``、``[at:qq=uid]`` 等常见适配器格式

    Args:
        args: 命令片段列表

    Returns:
        提取到的用户 ID，未识别返回 None
    """
    for arg in args:
        if not arg:
            continue
        token = arg.strip()
        if not token:
            continue

        if token.isdigit():
            return token

        match = _AT_TOKEN_PATTERN.search(token)
        if match:
            user_id = match.group("user_id").strip()
            if user_id:
                return user_id

        bracket = re.search(r"\[at[:=]\s*(?:qq=)?(\d+)\]", token, re.IGNORECASE)
        if bracket:
            return bracket.group(1)

        if token.startswith("@"):
            digits = re.search(r"\d+", token)
            if digits:
                return digits.group(0)

    return None


def resolve_nickname(
    user_id: str,
    message: "Message | None" = None,
    at_users: list[dict[str, str]] | None = None,
    fallback: str | None = None,
) -> str:
    """根据可用上下文解析昵称。

    优先匹配传入的 at_users，其次匹配消息发送者，最后回落到 fallback 或 user_id。

    Args:
        user_id: 目标用户 ID
        message: 消息对象（可选，用于读取 sender 信息）
        at_users: 已解析的 @ 用户列表（可选）
        fallback: 兜底昵称

    Returns:
        昵称字符串
    """
    target_id = str(user_id)
    if at_users:
        for item in at_users:
            if str(item.get("user_id")) == target_id:
                nickname = str(item.get("nickname") or "").strip()
                if nickname:
                    return nickname

    if message is not None and str(getattr(message, "sender_id", "")) == target_id:
        sender_name = str(getattr(message, "sender_name", "") or "").strip()
        if sender_name:
            return sender_name

    if fallback:
        return str(fallback)
    return target_id


async def lookup_nickname(platform: str, user_id: str) -> str:
    """查询数据库中已记录的昵称（如果有）。

    Args:
        platform: 平台标识
        user_id: 用户 ID

    Returns:
        查找到的昵称；查询失败时返回 user_id 自身
    """
    try:
        from src.core.utils.user_query_helper import get_user_query_helper

        helper = get_user_query_helper()
        person, _ = await helper.get_or_create_person(
            platform=platform,
            user_id=user_id,
        )
        nickname = (
            (getattr(person, "cardname", None) or "").strip()
            or (getattr(person, "nickname", None) or "").strip()
        )
        if nickname:
            return nickname
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"lookup_nickname 失败: {exc}")
    return user_id


def stream_group_key(stream_id: str, message: "Message | None") -> str:
    """构造数据存储中的分组键。

    优先使用 stream_id（与 Neo-MoFox 流体系一致），失败时退回 platform 兜底。

    Args:
        stream_id: 聊天流 ID
        message: 消息对象（可选）

    Returns:
        用于数据分组的键
    """
    if stream_id:
        return stream_id
    if message is not None:
        platform = getattr(message, "platform", "") or "unknown"
        return f"{platform}:default"
    return "default"


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全地把任意值转换为 float。

    Args:
        value: 原始值
        default: 转换失败时的兜底值

    Returns:
        解析出的浮点数
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """安全地把任意值转换为 int。

    Args:
        value: 原始值
        default: 转换失败时的兜底值

    Returns:
        解析出的整数
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
