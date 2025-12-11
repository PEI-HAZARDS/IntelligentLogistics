from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.auth import AuthService
from app.schemas import LoginRequest, TokenResponse, CurrentUser, WorkerCreate, WorkerResponse


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate a worker and return a JWT token.
    Use email as username.
    """
    auth_service = AuthService(db)
    login_data = LoginRequest(email=form_data.username, password=form_data.password)
    result = await auth_service.login(login_data)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return result


@router.get("/me", response_model=CurrentUser)
async def get_current_user(
    worker_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get current authenticated user information."""
    auth_service = AuthService(db)
    worker = await auth_service.get_worker_by_id(worker_id)
    
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return CurrentUser(
        worker_id=worker.worker_id,
        full_name=worker.full_name,
        email=worker.email,
        role=worker.role,
        assigned_gate_id=worker.assigned_gate_id
    )


@router.post("/register", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
async def register_worker(
    worker_data: WorkerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new worker.
    Note: In production, this should be restricted to admins only.
    """
    auth_service = AuthService(db)
    worker = await auth_service.create_worker(worker_data)
    return worker
