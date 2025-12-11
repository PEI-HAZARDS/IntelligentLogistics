from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.truck import TruckService
from app.schemas import TruckCreate, TruckUpdate, TruckResponse, PaginatedResponse


router = APIRouter(prefix="/trucks", tags=["Trucks"])


@router.get("", response_model=PaginatedResponse)
async def list_trucks(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all trucks with pagination."""
    truck_service = TruckService(db)
    trucks = await truck_service.get_all(skip=skip, limit=limit)
    total = await truck_service.count()
    
    return PaginatedResponse(
        items=[TruckResponse.model_validate(t) for t in trucks],
        total=total,
        skip=skip,
        limit=limit
    )


@router.post("", response_model=TruckResponse, status_code=status.HTTP_201_CREATED)
async def create_truck(
    truck_data: TruckCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new truck."""
    truck_service = TruckService(db)
    truck = await truck_service.create(truck_data)
    return truck


@router.get("/{truck_id}", response_model=TruckResponse)
async def get_truck(
    truck_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a truck by ID."""
    truck_service = TruckService(db)
    truck = await truck_service.get_by_id(truck_id)
    
    if not truck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Truck with ID {truck_id} not found"
        )
    
    return truck


@router.get("/plate/{license_plate}", response_model=TruckResponse)
async def get_truck_by_plate(
    license_plate: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a truck by license plate."""
    truck_service = TruckService(db)
    truck = await truck_service.get_by_plate(license_plate)
    
    if not truck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Truck with plate {license_plate} not found"
        )
    
    return truck


@router.put("/{truck_id}", response_model=TruckResponse)
async def update_truck(
    truck_id: int,
    truck_data: TruckUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing truck."""
    truck_service = TruckService(db)
    truck = await truck_service.update(truck_id, truck_data)
    
    if not truck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Truck with ID {truck_id} not found"
        )
    
    return truck


@router.delete("/{truck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_truck(
    truck_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a truck."""
    truck_service = TruckService(db)
    deleted = await truck_service.delete(truck_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Truck with ID {truck_id} not found"
        )
