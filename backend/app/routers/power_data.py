"""发电监测接口：维护发电记录，覆盖标记偏低、确认异常、数据补录等动作。

注意路由顺序：/daily、/export 必须声明在 /{entry_id} 之前，
否则字面值路径会被路径参数抢占，结果文件出口会直接 422。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.power_data import EXPORT_COLUMNS, PowerDataService

router = APIRouter(prefix="/api/power_data", tags=["发电监测"])

service = PowerDataService()

LIST_FIELDS = ["记录编号", "电站编号", "记录时间", "上报时段", "发电量", "辐照度", "组件温度", "环境温度", "采集状态"]
STATUSES = ["正常", "偏低", "异常", "补录"]
COLLECTION_STATUSES = ["已采集", "缺测"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="正常、偏低、异常、补录"),
    collection: str | None = Query(default=None, description="已采集、缺测"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、状态与采集状态过滤列表；缺测行发电量返回空值，绝不回写成 0。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, collection=collection, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/daily")
def daily_summary(
    plant: str | None = Query(default=None, description="按电站编号过滤"),
    day: str | None = Query(default=None, description="按日期过滤，如 2026-09-26"),
) -> dict[str, Any]:
    """按日汇总：缺测时段单独计数，日发电量只累加已采集时段，与列表同一口径。"""
    items = service.daily_summary(plant=plant, day=day)
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """结果文件出口：缺测时段发电量写空值并带缺测原因，与列表、详情口径一致。"""
    return service.export_entries()


@router.get("/meta")
def meta() -> dict[str, Any]:
    """页面字典：列表字段、状态序列与结果文件列，前端不用各自硬编码。"""
    return {"list_fields": LIST_FIELDS, "statuses": STATUSES, "collection_statuses": COLLECTION_STATUSES, "export_columns": EXPORT_COLUMNS}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条发电记录明细；缺测记录标记为缺口并给出缺测原因。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"发电记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条发电记录；同一记录编号重复提交（接口重试）不会产生重复行。"""
    entry, missing, duplicated = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if duplicated:
        return ActionResult(ok=True, message=f"发电记录 {payload.values.get('记录编号')} 已存在，未重复登记", entry=entry)
    return ActionResult(ok=True, message="发电记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条发电记录执行标记偏低、确认异常、数据补录；补录必须带发电量数值。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
