"""发电监测接口：维护发电记录，并提供按日汇总、时段明细与结果文件导出。

按日汇总、时段明细、结果文件三个出口共用 services 里的同一套采集状态与
零值口径：缺测、异常的时段没有数值，任何出口都不会把它改写成 0。

注意路由顺序：/不出现在 /{entry_id} 之前的具体路径（/daily、/export）会被
路径参数抢占，请求被当成记录 id 解析而报 422。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.power_data import COLLECT_STATUSES, PowerDataService

router = APIRouter(prefix="/api/power_data", tags=["发电监测"])

service = PowerDataService()

STATUSES = ["正常", "偏低", "异常", "补录"]
DATE_FORMAT_HINT = "日期格式应为 YYYY-MM-DD"


def _checked_date(date: str | None) -> str | None:
    if date is None:
        return None
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日期「{date}」{DATE_FORMAT_HINT}")
    return date


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="正常、偏低、异常、补录"),
    collect: str | None = Query(default=None, description="采集状态：已采集、缺测、异常、补录"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、处理状态、采集状态过滤发电记录；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if collect and collect not in COLLECT_STATUSES:
        raise HTTPException(status_code=400, detail=f"采集状态「{collect}」不在允许范围：{'、'.join(COLLECT_STATUSES)}")
    items, total = service.list_entries(keyword=keyword, status=status, collect=collect, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/daily", response_model=PageResult[dict])
def daily_summary(
    station: str | None = Query(default=None, description="电站编号"),
    date: str | None = Query(default=None, description="日期 YYYY-MM-DD"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按日汇总：缺测、异常时段不计入日发电量；全天无有效数据时日发电量留空，不落 0。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.daily_summary(station=station, date=_checked_date(date), page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/daily/detail")
def daily_detail(
    station: str = Query(description="电站编号"),
    date: str = Query(description="日期 YYYY-MM-DD"),
) -> dict[str, Any]:
    """时段明细：未上报的时段标为缺口并给出原因，异常时段带异常原因。"""
    detail = service.daily_detail(station=station, date=_checked_date(date) or date)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"电站 {station} 在 {date} 没有任何上报记录，无法生成时段明细")
    return detail


@router.get("/daily/export")
def export_daily_result(
    station: str | None = Query(default=None, description="电站编号"),
    date: str | None = Query(default=None, description="日期 YYYY-MM-DD"),
) -> Response:
    """导出结果文件（CSV）：与按日汇总、明细同一口径，缺测时段留空并标注状态，不写回 0。"""
    checked = _checked_date(date)
    csv_text = service.build_result_file(station=station, date=checked)
    suffix = (checked or "all").replace("-", "")
    return Response(
        content="\ufeff" + csv_text,  # 带 BOM，Excel 打开中文不乱码
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=generation_daily_{suffix}.csv"},
    )


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出发电记录清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "power_data", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条发电记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"发电记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条发电记录；按记录编号幂等，接口重试不会产生重复行。"""
    entry, message = service.create_entry(payload.values)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条发电记录执行标记偏低、确认异常、数据补录；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
