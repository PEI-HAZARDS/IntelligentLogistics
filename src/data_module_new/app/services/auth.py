from datetime import timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, get_password_hash, create_access_token
from app.repositories.worker import WorkerRepository
from app.models import Worker
from app.schemas import LoginRequest, TokenResponse, WorkerCreate


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.worker_repo = WorkerRepository(db)
    
    async def authenticate(self, email: str, password: str) -> Optional[Worker]:
        """Authenticate a worker by email and password."""
        worker = await self.worker_repo.get_by_email(email)
        if not worker:
            return None
        if not worker.is_active:
            return None
        if not verify_password(password, worker.password_hash):
            return None
        return worker
    
    async def login(self, login_data: LoginRequest) -> Optional[TokenResponse]:
        """Login and return JWT token."""
        worker = await self.authenticate(login_data.email, login_data.password)
        if not worker:
            return None
        
        access_token = create_access_token(
            data={
                "sub": str(worker.worker_id),
                "email": worker.email,
                "role": worker.role
            }
        )
        return TokenResponse(access_token=access_token)
    
    async def get_worker_by_id(self, worker_id: int) -> Optional[Worker]:
        """Get worker by ID."""
        return await self.worker_repo.get_by_id(worker_id)
    
    async def create_worker(self, worker_data: WorkerCreate) -> Worker:
        """Create a new worker with hashed password."""
        password_hash = get_password_hash(worker_data.password)
        return await self.worker_repo.create_worker(
            full_name=worker_data.full_name,
            email=worker_data.email,
            password_hash=password_hash,
            role=worker_data.role,
            assigned_gate_id=worker_data.assigned_gate_id
        )
