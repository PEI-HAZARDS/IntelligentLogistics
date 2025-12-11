from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import SystemResourceMetrics
from app.schemas import ResourceMetricCreate, ResourceMetricResponse


router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@router.post("/metrics", response_model=ResourceMetricResponse, status_code=status.HTTP_201_CREATED)
async def ingest_metric(
    metric_data: ResourceMetricCreate,
    db: AsyncSession = Depends(get_db)
):
    """Ingest a new resource telemetry metric."""
    metric = SystemResourceMetrics(
        timestamp=datetime.utcnow(),
        node_id=metric_data.node_id,
        cpu_usage_pct=metric_data.cpu_usage_pct,
        gpu_usage_pct=metric_data.gpu_usage_pct,
        power_consumption_watts=metric_data.power_consumption_watts,
        active_camera_streams=metric_data.active_camera_streams,
        traffic_volume_in_gate=metric_data.traffic_volume_in_gate
    )
    db.add(metric)
    await db.flush()
    await db.refresh(metric)
    return metric


@router.get("/metrics", response_model=List[ResourceMetricResponse])
async def get_metrics(
    node_id: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get telemetry metrics with optional node filter."""
    query = select(SystemResourceMetrics)
    
    if node_id:
        query = query.where(SystemResourceMetrics.node_id == node_id)
    
    query = query.order_by(SystemResourceMetrics.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    metrics = result.scalars().all()
    return metrics


@router.get("/metrics/latest/{node_id}", response_model=ResourceMetricResponse)
async def get_latest_metric(
    node_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the latest telemetry metric for a specific node."""
    result = await db.execute(
        select(SystemResourceMetrics)
        .where(SystemResourceMetrics.node_id == node_id)
        .order_by(SystemResourceMetrics.timestamp.desc())
        .limit(1)
    )
    metric = result.scalar_one_or_none()
    
    if not metric:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No metrics found for node {node_id}"
        )
    
    return metric
