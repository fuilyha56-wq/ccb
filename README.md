# ccb

适用于 [Neo-MoFox](https://github.com/MoFox-Studio/Neo-MoFox) 的娱乐插件，将原 AstrBot 版本的 `astrbot_plugin_ccb_plus` 重写为 Neo-MoFox 插件系统的标准结构。

> 原项目：基于灵煞 / ccb 的「和 QQ 群群友发生赛博 sex」插件改进版。

## 功能

| 命令 | 说明 |
| ---- | ---- |
| `/ccb [@目标 \| QQ号]` | 与目标进行一次 ccb；支持暴击与随机养胃 |
| `/ccb top` | 按被 ccb 次数 TOP5 排行 |
| `/ccb vol` | 按累计被注入量 TOP5 排行 |
| `/ccb max` | 按单次最大注入量 TOP5 排行 |
| `/ccb info [@目标 \| QQ号]` | 查看个人 ccb 档案 |
| `/xnn` | 💎 小南梁 TOP5 排行（被 ccb 次数 + 累计注入 - 主动 ccb 次数） |

## 配置

配置文件位于 `config/plugins/ccb/config.toml`，主要分为三部分：

- `[plugin]`：插件总开关与版本号
- `[limit]`：滑动窗口、阈值、养胃概率与时长
- `[rule]`：暴击概率、是否允许 0721、白名单、是否记录详细日志

数据保存在 `data/json_storage/ccb/`，与主程序数据库隔离，不会和旧版 AstrBot 的存储冲突。

## 安装

将本目录放置到 Neo-MoFox 实例的 `plugins/` 下，或者通过 `mpdt market install ccb` 安装。

## 许可证

GPL-3.0，详见 [`LICENSE`](LICENSE)。
