"""ccb 插件数据访问与限流共享逻辑。

把窗口限流、养胃禁用与 ccb 数据读写集中到本模块，避免在多个命令间复制。
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any

from src.app.plugin_system.api import storage_api
from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("ccb.storage")

STORE_NAME = "ccb"
DATA_KEY = "ccb_data"
LOG_KEY = "ccb_log"

# 数据字段名常量（保持与旧版本兼容的语义）
FIELD_ID = "id"
FIELD_NUM = "num"
FIELD_VOL = "vol"
FIELD_CCB_BY = "ccb_by"
FIELD_MAX = "max"


def get_avatar(user_id: str) -> str:
    """根据 QQ 号生成头像 URL。

    Args:
        user_id: 目标用户 QQ 号

    Returns:
        头像图片地址
    """
    return f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"


async def read_all_data() -> dict[str, list[dict[str, Any]]]:
    """读取整个 ccb 数据集。

    Returns:
        以 group_id（或 stream_id）为键、记录列表为值的数据字典
    """
    data = await storage_api.load_json(STORE_NAME, DATA_KEY)
    if not isinstance(data, dict):
        return {}
    return data  # type: ignore[return-value]


async def write_all_data(data: dict[str, list[dict[str, Any]]]) -> None:
    """写回整个 ccb 数据集。

    Args:
        data: 完整数据字典
    """
    await storage_api.save_json(STORE_NAME, DATA_KEY, data)


async def append_log(
    group_id: str,
    executor_id: str,
    target_id: str,
    duration: float,
    vol: float,
) -> None:
    """追加一条详细 ccb 日志。

    Args:
        group_id: 群/会话标识
        executor_id: 执行者 ID
        target_id: 目标 ID
        duration: 持续分钟数
        vol: 注入量 (ml)
    """
    try:
        existing = await storage_api.load_json(STORE_NAME, LOG_KEY)
        logs: list[dict[str, Any]]
        if isinstance(existing, list):
            logs = existing  # type: ignore[assignment]
        elif isinstance(existing, dict) and isinstance(existing.get("entries"), list):
            logs = existing["entries"]
        else:
            logs = []

        logs.append(
            {
                "group": group_id,
                "executor": executor_id,
                "target": target_id,
                "duration": round(float(duration), 2),
                "vol": round(float(vol), 2),
                "ts": time.time(),
            }
        )

        await storage_api.save_json(STORE_NAME, LOG_KEY, {"entries": logs})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"append_log 失败: {exc}")


class RateLimiter:
    """ccb 滑动窗口限流与养胃状态。

    Attributes:
        window: 滑动窗口长度（秒）
        threshold: 窗口内最大允许动作次数
        ban_duration: 触发限流后禁用时长（秒）
    """

    def __init__(self, window: int, threshold: int, ban_duration: int) -> None:
        """初始化限流器。

        Args:
            window: 滑动窗口长度
            threshold: 窗口内最大允许动作次数
            ban_duration: 限流禁用时长
        """
        self.window = window
        self.threshold = threshold
        self.ban_duration = ban_duration
        self._times: dict[str, deque[float]] = {}
        self._ban_list: dict[str, float] = {}

    def update_settings(self, window: int, threshold: int, ban_duration: int) -> None:
        """更新限流参数（配置热更新支持）。

        Args:
            window: 滑动窗口长度
            threshold: 窗口内最大允许动作次数
            ban_duration: 限流禁用时长
        """
        self.window = window
        self.threshold = threshold
        self.ban_duration = ban_duration

    def check_ban(self, actor_id: str) -> int:
        """检查是否处于禁用期。

        Args:
            actor_id: 行为者标识

        Returns:
            剩余秒数，0 表示未被禁用
        """
        ban_end = self._ban_list.get(actor_id, 0.0)
        now = time.time()
        if now < ban_end:
            return int(ban_end - now)
        return 0

    def record_action(self, actor_id: str) -> bool:
        """记录一次动作并判断是否触发限流。

        Args:
            actor_id: 行为者标识

        Returns:
            True 表示已经触发限流并被加入禁用列表
        """
        now = time.time()
        bucket = self._times.setdefault(actor_id, deque())
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        bucket.append(now)

        if len(bucket) > self.threshold:
            self._ban_list[actor_id] = now + self.ban_duration
            bucket.clear()
            return True
        return False

    def trigger_random_ban(self, actor_id: str) -> None:
        """主动触发养胃禁用（用于随机养胃事件）。

        Args:
            actor_id: 行为者标识
        """
        self._ban_list[actor_id] = time.time() + self.ban_duration
