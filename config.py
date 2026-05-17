"""ccb 插件配置定义。

定义滑动窗口、养胃、暴击、白名单等参数。
"""
from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class CCBConfig(BaseConfig):
    """ccb 插件配置。"""

    config_name: ClassVar[str] = "config"
    config_description: ClassVar[str] = "ccb 插件配置"

    @config_section("plugin", title="插件设置", tag="plugin")
    class PluginSection(SectionBase):
        """插件基本设置。"""

        enabled: bool = Field(
            default=True,
            description="是否启用插件",
            label="启用插件",
            tag="plugin",
        )
        version: str = Field(
            default="1.0.0",
            description="插件版本",
            label="插件版本",
            disabled=True,
            tag="plugin",
        )

    @config_section("limit", title="限流与养胃", tag="performance")
    class LimitSection(SectionBase):
        """滑动窗口限流与养胃配置。"""

        yw_window: int = Field(
            default=60,
            description="触发赛博阳痿的窗口时间（秒），统计多少秒内的调用次数。",
            label="窗口时长",
            tag="timer",
            ge=1,
        )
        yw_threshold: int = Field(
            default=5,
            description="窗口时间内最大 ccb 数。同一人多少次请求后会被禁用。",
            label="窗口次数阈值",
            tag="performance",
            ge=1,
        )
        yw_ban_duration: int = Field(
            default=900,
            description="养胃时长（秒）。被触发限流后禁用多长时间。",
            label="养胃时长",
            tag="timer",
            ge=1,
        )
        yw_probability: float = Field(
            default=0.1,
            description="每次 ccb 完成后随机进入养胃的概率。",
            label="随机养胃概率",
            tag="performance",
            ge=0.0,
            le=1.0,
        )

    @config_section("rule", title="ccb 规则", tag="general")
    class RuleSection(SectionBase):
        """ccb 行为规则。"""

        crit_prob: float = Field(
            default=0.2,
            description="ccb 时暴击概率。",
            label="暴击概率",
            tag="performance",
            ge=0.0,
            le=1.0,
        )
        self_ccb: bool = Field(
            default=False,
            description="为 true 时当 ccb 指令未指定对象时进行 0721。",
            label="允许 0721",
            tag="general",
        )
        is_log: bool = Field(
            default=False,
            description="是否独立保留每一条 ccb 记录，包括双方与注入量。",
            label="完整日志",
            tag="debug",
        )
        white_list: list[str] = Field(
            default_factory=list,
            description="不能进行 ccb 的 user_id 列表。当目标在此列表中时，不能对其 ccb。",
            label="白名单",
            tag="list",
            item_type="str",
        )

    plugin: PluginSection = Field(default_factory=PluginSection)
    limit: LimitSection = Field(default_factory=LimitSection)
    rule: RuleSection = Field(default_factory=RuleSection)
