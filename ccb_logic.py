"""ccb 业务逻辑核心。

把 ccb 主流程、排行榜、个人信息、xnn 排行等放到一个无状态模块里，
命令组件只负责参数解析和文本/图片输出。
"""
from __future__ import annotations

import random
from typing import Any

from src.app.plugin_system.api.log_api import get_logger

from .storage import (
    FIELD_CCB_BY,
    FIELD_ID,
    FIELD_MAX,
    FIELD_NUM,
    FIELD_VOL,
    append_log,
    read_all_data,
    write_all_data,
)
from .utils import safe_float, safe_int

logger = get_logger("ccb.logic")


def _find_record(group_data: list[dict[str, Any]], target_id: str) -> dict[str, Any] | None:
    """在群数据中查找目标用户的记录。"""
    for item in group_data:
        if str(item.get(FIELD_ID)) == str(target_id):
            return item
    return None


def _ensure_max(record: dict[str, Any]) -> float:
    """读取或推算记录中的单次最大注入量。"""
    raw = record.get(FIELD_MAX)
    if raw is not None:
        value = safe_float(raw, 0.0)
        if value > 0.0:
            return value
    total_vol = safe_float(record.get(FIELD_VOL), 0.0)
    total_num = safe_int(record.get(FIELD_NUM), 0)
    if total_num > 0:
        return round(total_vol / total_num, 2)
    return 0.0


async def perform_ccb(
    *,
    group_id: str,
    actor_id: str,
    target_id: str,
    crit_prob: float,
    is_log: bool,
) -> dict[str, Any]:
    """执行一次 ccb 行为并写回数据。

    Args:
        group_id: 数据分组键
        actor_id: 执行者 ID
        target_id: 目标 ID
        crit_prob: 暴击概率
        is_log: 是否记录详细日志

    Returns:
        结果字典，包含：
            duration: 持续分钟
            vol: 注入量 (ml)
            crit: 是否暴击
            num: 该目标当前累计被 ccb 次数
            is_first: 是否首次被 ccb
    """
    duration = round(random.uniform(1, 60), 2)
    volume = round(random.uniform(1, 100), 2)
    crit = random.random() < float(crit_prob)
    if crit:
        volume = round(volume * 2.0, 2)

    all_data = await read_all_data()
    group_data = list(all_data.get(group_id, []))

    record = _find_record(group_data, target_id)
    is_first = record is None

    if record is None:
        record = {
            FIELD_ID: str(target_id),
            FIELD_NUM: 1,
            FIELD_VOL: volume,
            FIELD_CCB_BY: {
                str(actor_id): {"count": 1, "first": True, "max": True},
            },
            FIELD_MAX: volume,
        }
        group_data.append(record)
    else:
        record[FIELD_NUM] = safe_int(record.get(FIELD_NUM), 0) + 1
        record[FIELD_VOL] = round(safe_float(record.get(FIELD_VOL), 0.0) + volume, 2)

        ccb_by_raw = record.get(FIELD_CCB_BY) or {}
        if not isinstance(ccb_by_raw, dict):
            ccb_by_raw = {}
        ccb_by: dict[str, dict[str, Any]] = {str(k): dict(v) for k, v in ccb_by_raw.items()}

        actor_key = str(actor_id)
        if actor_key in ccb_by:
            ccb_by[actor_key]["count"] = safe_int(ccb_by[actor_key].get("count"), 0) + 1
            ccb_by[actor_key].setdefault("first", False)
        else:
            ccb_by[actor_key] = {"count": 1, "first": False, "max": False}

        prev_max = _ensure_max(record)
        if volume > prev_max:
            record[FIELD_MAX] = volume
            for key in ccb_by:
                ccb_by[key]["max"] = False
            ccb_by[actor_key]["max"] = True
        else:
            for key in ccb_by:
                ccb_by[key].setdefault("max", False)

        record[FIELD_CCB_BY] = ccb_by

    all_data[group_id] = group_data
    await write_all_data(all_data)

    if is_log:
        try:
            await append_log(group_id, str(actor_id), str(target_id), duration, volume)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"日志记录失败: {exc}")

    return {
        "duration": duration,
        "vol": volume,
        "crit": crit,
        "num": safe_int(record.get(FIELD_NUM), 1),
        "is_first": is_first,
    }


async def get_ranking(
    group_id: str,
    *,
    rank_by: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """读取群组排行榜（按次数或累计注入量）。

    Args:
        group_id: 数据分组键
        rank_by: 排序字段，FIELD_NUM 或 FIELD_VOL
        limit: 返回数量上限

    Returns:
        排行榜列表，每项包含 user_id 与 value
    """
    all_data = await read_all_data()
    group_data = all_data.get(group_id, [])
    if not group_data:
        return []

    def _key(item: dict[str, Any]) -> float:
        if rank_by == FIELD_NUM:
            return float(safe_int(item.get(FIELD_NUM), 0))
        return safe_float(item.get(FIELD_VOL), 0.0)

    sorted_data = sorted(group_data, key=_key, reverse=True)[:limit]
    result: list[dict[str, Any]] = []
    for item in sorted_data:
        result.append(
            {
                "user_id": str(item.get(FIELD_ID)),
                "num": safe_int(item.get(FIELD_NUM), 0),
                "vol": round(safe_float(item.get(FIELD_VOL), 0.0), 2),
            }
        )
    return result


async def get_max_ranking(group_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """读取单次最大注入量排行榜。

    Args:
        group_id: 数据分组键
        limit: 返回数量上限

    Returns:
        排行榜列表，每项包含 user_id、max_vol、producer_id
    """
    all_data = await read_all_data()
    group_data = all_data.get(group_id, [])
    if not group_data:
        return []

    entries: list[tuple[dict[str, Any], float]] = []
    for record in group_data:
        max_val = _ensure_max(record)
        entries.append((record, max_val))

    entries.sort(key=lambda x: x[1], reverse=True)
    result: list[dict[str, Any]] = []
    for record, max_val in entries[:limit]:
        ccb_by = record.get(FIELD_CCB_BY) or {}
        producer_id: str | None = None
        if isinstance(ccb_by, dict):
            for actor_id, info in ccb_by.items():
                if isinstance(info, dict) and info.get("max"):
                    producer_id = str(actor_id)
                    break
            if not producer_id and ccb_by:
                try:
                    producer_id = max(
                        ccb_by.items(),
                        key=lambda x: safe_int(x[1].get("count") if isinstance(x[1], dict) else 0, 0),
                    )[0]
                except Exception:  # noqa: BLE001
                    producer_id = None
        result.append(
            {
                "user_id": str(record.get(FIELD_ID)),
                "max_vol": round(float(max_val), 2),
                "producer_id": producer_id,
            }
        )
    return result


async def get_user_info(group_id: str, target_id: str) -> dict[str, Any] | None:
    """获取个人 ccb 信息。

    Args:
        group_id: 数据分组键
        target_id: 目标用户 ID

    Returns:
        信息字典，未找到返回 None
    """
    all_data = await read_all_data()
    group_data = all_data.get(group_id, [])
    if not group_data:
        return None

    record = _find_record(group_data, target_id)
    if record is None:
        return None

    total_num = safe_int(record.get(FIELD_NUM), 0)
    total_vol = round(safe_float(record.get(FIELD_VOL), 0.0), 2)
    max_val = round(_ensure_max(record), 2)

    ccb_by = record.get(FIELD_CCB_BY) or {}
    first_actor: str | None = None
    if isinstance(ccb_by, dict):
        for actor_id, info in ccb_by.items():
            if isinstance(info, dict) and info.get("first"):
                first_actor = str(actor_id)
                break

    cb_total = 0
    for rec in group_data:
        by = rec.get(FIELD_CCB_BY) or {}
        if not isinstance(by, dict):
            continue
        info = by.get(str(target_id))
        if isinstance(info, dict):
            cb_total += safe_int(info.get("count"), 0)

    return {
        "user_id": str(target_id),
        "total_num": total_num,
        "total_vol": total_vol,
        "max_val": max_val,
        "first_actor": first_actor,
        "cb_total": cb_total,
    }


async def get_xnn_ranking(
    group_id: str,
    *,
    w_num: float = 1.0,
    w_vol: float = 0.1,
    w_action: float = 0.5,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """计算群中最 xnn 特质的群友排行榜。

    Args:
        group_id: 数据分组键
        w_num: 被 ccb 次数权重
        w_vol: 累计注入量权重
        w_action: 主动 ccb 次数权重
        limit: 返回数量

    Returns:
        排行榜列表
    """
    all_data = await read_all_data()
    group_data = all_data.get(group_id, [])
    if not group_data:
        return []

    actor_actions: dict[str, int] = {}
    for record in group_data:
        ccb_by = record.get(FIELD_CCB_BY) or {}
        if not isinstance(ccb_by, dict):
            continue
        for actor_id, info in ccb_by.items():
            if isinstance(info, dict):
                actor_actions[str(actor_id)] = (
                    actor_actions.get(str(actor_id), 0) + safe_int(info.get("count"), 0)
                )

    ranking: list[dict[str, Any]] = []
    for record in group_data:
        uid = str(record.get(FIELD_ID))
        num = safe_int(record.get(FIELD_NUM), 0)
        vol = safe_float(record.get(FIELD_VOL), 0.0)
        actions = actor_actions.get(uid, 0)
        xnn_value = num * w_num + vol * w_vol - actions * w_action
        ranking.append(
            {
                "user_id": uid,
                "xnn": round(xnn_value, 2),
                "num": num,
                "vol": round(vol, 2),
                "actions": actions,
            }
        )

    ranking.sort(key=lambda x: x["xnn"], reverse=True)
    return ranking[:limit]
