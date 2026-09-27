"""发电监测业务规则：采集状态、零值口径与状态流转都收在这里。

按日汇总、时段明细、结果文件三个出口共用同一套口径：

- 采集状态只有四种：已采集、缺测、异常、补录；
- 只有「已采集 / 补录」的记录参与数值口径，真实零值（如清晨未发电）保留为 0；
- 「缺测 / 异常」一律没有数值（None），任何出口都不得改写成 0；
- 缺测、异常记录必须带原因说明，不允许没有理由的空白行；
- 汇总与明细都按记录实时推导，不落库占位行，接口重试不会产生重复空白行。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from app.store import store

MODULE = "power_data"
REQUIRED_FIELDS = ["记录编号", "电站编号"]
STATUS_ORDER = ["正常", "偏低", "异常", "补录"]
ACTION_RULES = {"标记偏低": "偏低", "确认异常": "异常", "数据补录": "正常"}
NEGATIVE_ACTIONS = []

# 采集状态口径：全模块唯一的一份定义，列表、明细、结果文件都从这里取。
COLLECT_STATUSES = ["已采集", "缺测", "异常", "补录"]
VALUE_STATUSES = {"已采集", "补录"}  # 只有这两种状态的发电量才参与数值口径
REASON_FIELDS = {"缺测": "缺测原因", "异常": "异常原因"}

# 每个自然日应上报的时段；明细里没收到上报的时段推导为缺口。
REPORT_PERIODS = ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00"]
GAP_REASON = "该时段未收到上报"


def collect_status_of(row: dict[str, Any]) -> str:
    """读取记录的采集状态；历史数据没有该字段时按已采集处理。"""
    status = str(row.get("采集状态") or "").strip()
    return status if status in COLLECT_STATUSES else "已采集"


def effective_value(row: dict[str, Any]) -> float | None:
    """统一零值口径：只有已采集/补录的行才有数值，缺测、异常一律 None。"""
    if collect_status_of(row) not in VALUE_STATUSES:
        return None
    raw = row.get("发电量")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def reason_of(row: dict[str, Any]) -> str:
    """缺测、异常记录的原因说明；其余状态没有原因字段。"""
    field = REASON_FIELDS.get(collect_status_of(row))
    if field is None:
        return ""
    return str(row.get(field) or "").strip()


def split_time(row: dict[str, Any]) -> tuple[str, str] | None:
    """把记录时间拆成（日期, 时段）；格式不对的记录不参与日汇总，避免脏数据污染口径。"""
    stamp = str(row.get("记录时间") or "").strip()
    if len(stamp) != 16 or stamp[10] != " ":
        return None
    return stamp[:10], stamp[11:16]


class PowerDataService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        collect: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if collect:
            rows = [row for row in rows if collect_status_of(row) == collect]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记一条发电记录。

        按记录编号幂等：同一编号重复提交（含接口重试）覆盖更新，不追加重复行；
        缺测、异常必须带原因，已采集、补录必须填真实发电量，不允许填 0 冒充缺测。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        collect = str(values.get("采集状态") or "已采集").strip()
        if collect not in COLLECT_STATUSES:
            return None, f"采集状态「{collect}」不在允许范围：{'、'.join(COLLECT_STATUSES)}"
        reason_field = REASON_FIELDS.get(collect)
        reason = str(values.get(reason_field) or "").strip() if reason_field else ""
        if reason_field and not reason:
            return None, f"采集状态为「{collect}」时必须填写{reason_field}，不允许没有理由的空白行"
        value: float | None = None
        if collect in VALUE_STATUSES:
            raw = str(values.get("发电量") or "").strip()
            if not raw:
                return None, f"采集状态为「{collect}」时必须填写发电量；未采集的时段请登记为「缺测」，不要填 0"
            try:
                value = float(raw)
            except ValueError:
                return None, f"发电量「{raw}」不是有效数字"
            if value < 0:
                return None, "发电量不能为负数"
        rows = store.rows(MODULE)
        code = str(values["记录编号"]).strip()
        entry: dict[str, Any] = {
            "记录编号": code,
            "电站编号": str(values["电站编号"]).strip(),
            "记录时间": str(values.get("记录时间") or "").strip(),
            "发电量": value,
            "辐照度": values.get("辐照度"),
            "组件温度": values.get("组件温度"),
            "环境温度": values.get("环境温度"),
            "采集状态": collect,
            "缺测原因": reason if collect == "缺测" else None,
            "异常原因": reason if collect == "异常" else None,
            "status": STATUS_ORDER[0],
            "pending": collect not in VALUE_STATUSES,
            "abnormal": collect == "异常",
        }
        for index, row in enumerate(rows):
            if str(row.get("记录编号")) == code:
                entry["id"] = row.get("id")
                rows[index] = entry
                return entry, f"发电记录 {code} 已存在，已按原编号覆盖更新，未新增重复行"
        entry["id"] = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        rows.append(entry)
        return entry, "发电记录已登记"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"发电记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于发电监测可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"发电记录已{action}"

    # ------------------------------------------------------------------
    # 按日汇总、时段明细、结果文件：三个出口共用下面的推导逻辑。

    def daily_summary(
        self,
        *,
        station: str | None = None,
        date: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        groups = self._group_by_station_day(station=station, date=date)
        days = [self._summarize_day(code, day, rows) for (code, day), rows in groups.items()]
        days.sort(key=lambda item: (item["日期"], item["电站编号"]), reverse=True)
        total = len(days)
        start = max(page - 1, 0) * size
        return days[start:start + size], total

    def daily_detail(self, *, station: str, date: str) -> dict[str, Any] | None:
        """单个电站日的时段明细：没收到上报的时段标为缺口，异常时段带异常原因。"""
        groups = self._group_by_station_day(station=station, date=date)
        rows = groups.get((station, date))
        if not rows:
            return None
        by_period: dict[str, dict[str, Any]] = {}
        extras: list[dict[str, Any]] = []
        for row in rows:
            parts = split_time(row)
            if parts is None:
                continue
            period = parts[1]
            if period in REPORT_PERIODS:
                by_period[period] = row  # 同一时段多条时以最后一条为准
            else:
                extras.append(row)
        items = [self._period_item(station, date, period, by_period.get(period)) for period in REPORT_PERIODS]
        for row in extras:
            parts = split_time(row)
            items.append(self._period_item(station, date, parts[1], row))
        return {"summary": self._summarize_day(station, date, rows), "items": items}

    def build_result_file(self, *, station: str | None = None, date: str | None = None) -> str:
        """生成结果文件（CSV）：与按日汇总、明细同一口径。

        缺测、异常时段的发电量留空并标注采集状态与原因，绝不写回 0。
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["电站编号", "日期", "时段", "发电量", "采集状态", "原因说明"])
        days, _ = self.daily_summary(station=station, date=date, page=1, size=10000)
        for day in days:
            detail = self.daily_detail(station=str(day["电站编号"]), date=str(day["日期"]))
            for item in detail["items"]:
                value = item["发电量"]
                writer.writerow([
                    item["电站编号"],
                    item["日期"],
                    item["时段"],
                    "" if value is None else value,
                    item["采集状态"],
                    item["原因说明"],
                ])
        return buffer.getvalue()

    def _group_by_station_day(
        self,
        *,
        station: str | None,
        date: str | None,
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in store.rows(MODULE):
            code = str(row.get("电站编号") or "").strip()
            if not code or (station and code != station):
                continue
            parts = split_time(row)
            if parts is None:
                continue
            day, _ = parts
            if date and day != date:
                continue
            groups.setdefault((code, day), []).append(row)
        return groups

    def _summarize_day(self, station: str, date: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_period: dict[str, dict[str, Any]] = {}
        for row in rows:
            parts = split_time(row)
            if parts is not None and parts[1] in REPORT_PERIODS:
                by_period[parts[1]] = row
        valid = missing = abnormal = 0
        total = 0.0
        reasons: list[str] = []
        for period in REPORT_PERIODS:
            row = by_period.get(period)
            if row is None:
                missing += 1
                reasons.append(GAP_REASON)
                continue
            value = effective_value(row)
            if value is not None:
                valid += 1
                total += value
            elif collect_status_of(row) == "异常":
                abnormal += 1
                reasons.append(reason_of(row))
            else:
                missing += 1
                reasons.append(reason_of(row))
        if abnormal:
            day_status = "存在异常"
        elif valid == 0:
            day_status = "全日缺测"
        elif missing:
            day_status = "部分缺测"
        else:
            day_status = "正常"
        return {
            "电站编号": station,
            "日期": date,
            "日发电量": round(total, 3) if valid else None,
            "应报时段数": len(REPORT_PERIODS),
            "有效时段数": valid,
            "缺测时段数": missing,
            "异常时段数": abnormal,
            "采集状态": day_status,
            "备注": "；".join(dict.fromkeys(filter(None, reasons))),
        }

    def _period_item(
        self,
        station: str,
        date: str,
        period: str,
        row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """单个时段的明细行；row 为 None 表示该时段没收到上报，是缺口。"""
        if row is None:
            return {
                "电站编号": station,
                "日期": date,
                "时段": period,
                "发电量": None,
                "采集状态": "缺测",
                "原因说明": GAP_REASON,
                "记录编号": None,
            }
        return {
            "电站编号": station,
            "日期": date,
            "时段": period,
            "发电量": effective_value(row),
            "采集状态": collect_status_of(row),
            "原因说明": reason_of(row),
            "记录编号": row.get("记录编号"),
        }
