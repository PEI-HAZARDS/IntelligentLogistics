from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import Driver
from app.schemas import DriverCreate, DriverUpdate, DriverResponse


router = APIRouter(prefix="/drivers", tags=["Drivers"])


@router.get("", response_model=List[DriverResponse])
async def list_drivers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all drivers with pagination."""
    result = await db.execute(select(Driver).offset(skip).limit(limit))
    drivers = result.scalars().all()
    return drivers


@router.post("", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
async def create_driver(
    driver_data: DriverCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new driver."""
    driver = Driver(**driver_data.model_dump())
    db.add(driver)
    await db.flush()
    await db.refresh(driver)
    return driver


@router.get("/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a driver by ID."""
    result = await db.execute(select(Driver).where(Driver.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )
    
    return driver


@router.put("/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: int,
    driver_data: DriverUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing driver."""
    result = await db.execute(select(Driver).where(Driver.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )
    
    update_data = driver_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(driver, key, value)
    
    await db.flush()
    await db.refresh(driver)
    return driver
