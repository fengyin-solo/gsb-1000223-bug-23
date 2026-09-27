"""发电监测业务规则：采集状态与零值口径统一收在这里，列表、详情、按日汇总、结果文件共用同一套判断。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "power_data"
# 发电量允许为空：空表示该上报时段尚未采到数（缺测），不是 0。
REQUIRED_FIELDS = ["记录编号", "电站编号"]
STATUS_ORDER = ["正常", "偏低", "异常", "补录"]
ACTION_RULES = {"标记偏低": "偏低", "确认异常": "异常", "数据补录": "正常"}
NEGATIVE_ACTIONS = ["确认异常"]

# 采集状态口径（全模块唯一判断来源）：
# 已采集 = 有真实读数，包括真实的 0（如夜间时段）；缺测 = 该上报时段没有采到数。
# 任何出口都不得把缺测写成 0，也不得把真实的 0 标成缺测。
COLLECTED = "已采集"
MISSING = "缺测"
DEFAULT_MISSING_REASON = "该时段未采集到上报数据"
DEFAULT_ABNORMAL_REASON = "发电量明显偏离理论值，待现场核查"

EXPORT_COLUMNS = [
    "记录编号", "电站编号", "记录时间", "上报时段", "发电量",
    "辐照度", "组件温度", "环境温度", "采集状态", "缺测原因", "数据状态",
]


def parse_generation(value: Any) -> float | None:
    """把发电量解析成数值；空串、None、非数值都视为未采集，返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """把一条发电记录规整成统一口径，三个出口（列表/详情/结果文件）都用它。

    - 发电量：已采集为数值（0 是真实读数），缺测为 None；
    - 采集状态：已采集 / 缺测，缺测行必须带缺测原因；
    - 是否缺口：详情出口用来标记缺测缺口；
    - 异常说明：异常行给出可读原因，页面空态直接展示。
    """
    row = dict(entry)
    amount = parse_generation(row.get("发电量"))
    if amount is None:
        row["发电量"] = None
        row["采集状态"] = MISSING
        row["缺测原因"] = str(row.get("缺测原因") or "").strip() or DEFAULT_MISSING_REASON
    else:
        row["发电量"] = amount
        row["采集状态"] = COLLECTED
        row["缺测原因"] = ""
    row["是否缺口"] = row["采集状态"] == MISSING
    if row.get("abnormal") or row.get("status") == "异常":
        row["异常说明"] = str(row.get("异常说明") or "").strip() or DEFAULT_ABNORMAL_REASON
    else:
        row["异常说明"] = ""
    return row


class PowerDataService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        collection: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [normalize_entry(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if collection:
            rows = [row for row in rows if row.get("采集状态") == collection]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return normalize_entry(entry)

    def daily_summary(
        self,
        *,
        plant: str | None = None,
        day: str | None = None,
    ) -> list[dict[str, Any]]:
        """按电站+日期汇总：缺测时段单独计数，日发电量只累加已采集时段。

        缺测时段不计入发电量（也不是 0），汇总行用缺测时段数与完整性标记暴露缺口，
        避免把没采到数的日子误读成全天正常发电。
        """
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in store.rows(MODULE):
            normalized = normalize_entry(row)
            key = (str(normalized.get("电站编号", "")), str(normalized.get("记录时间", "")))
            groups.setdefault(key, []).append(normalized)
        summaries: list[dict[str, Any]] = []
        for (plant_no, day_text), rows in sorted(groups.items()):
            if plant and plant not in plant_no:
                continue
            if day and day != day_text:
                continue
            collected = [row for row in rows if row["采集状态"] == COLLECTED]
            missing = [row for row in rows if row["采集状态"] == MISSING]
            summaries.append({
                "电站编号": plant_no,
                "日期": day_text,
                "应报时段数": len(rows),
                "已采集时段数": len(collected),
                "缺测时段数": len(missing),
                "日发电量": round(sum(float(row["发电量"]) for row in collected), 2),
                "完整性": "完整" if not missing else "有缺口",
                "缺测原因": sorted({row["缺测原因"] for row in missing}),
            })
        return summaries

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记发电记录；按记录编号幂等，接口重试不会产生重复空白行。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, False
        record_no = str(values.get("记录编号") or "").strip()
        rows = store.rows(MODULE)
        for row in rows:
            if str(row.get("记录编号", "")) == record_no:
                return normalize_entry(row), [], True
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["记录编号"] = record_no
        entry["电站编号"] = str(values.get("电站编号") or "").strip()
        entry["记录时间"] = str(values.get("记录时间") or "").strip() or date.today().isoformat()
        entry["上报时段"] = str(values.get("上报时段") or "").strip()
        entry["发电量"] = parse_generation(values.get("发电量"))
        for field in ("辐照度", "组件温度", "环境温度"):
            entry[field] = parse_generation(values.get(field))
        if entry["发电量"] is None:
            entry["缺测原因"] = str(values.get("缺测原因") or "").strip() or DEFAULT_MISSING_REASON
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return normalize_entry(entry), [], False

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"发电记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于发电监测可执行范围"
        values = values or {}
        if action == "数据补录":
            amount = parse_generation(values.get("发电量"))
            if amount is None:
                return None, "数据补录需要提供有效的发电量数值，缺测时段不能直接置零"
            entry["发电量"] = amount
            entry["缺测原因"] = ""
        if action == "确认异常":
            reason = str(values.get("异常说明") or "").strip()
            entry["异常说明"] = reason or DEFAULT_ABNORMAL_REASON
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return normalize_entry(entry), f"发电记录已{action}"

    def export_entries(self) -> dict[str, Any]:
        """结果文件出口：与列表、详情同一套口径，缺测时段发电量写空值而不是 0。"""
        items = []
        for row in store.rows(MODULE):
            normalized = normalize_entry(row)
            exported = dict(normalized)
            if exported["采集状态"] == MISSING:
                exported["发电量"] = ""
            items.append(exported)
        return {
            "module": MODULE,
            "generated_at": date.today().isoformat(),
            "columns": EXPORT_COLUMNS,
            "total": len(items),
            "items": items,
        }
