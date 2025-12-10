"""
Worker Routes - Endpoints para operadores de cancela e gestores.
Consumido por: Frontend backoffice, API Gateway (autenticação).
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from models.pydantic_models import Trabalhador as TrabalhadorPydantic
from services.worker_service import (
    authenticate_worker,
    get_worker_by_id,
    get_all_workers,
    get_operators,
    get_managers,
    get_operator_info,
    get_operator_current_shift,
    get_operator_shifts,
    get_operator_gate_dashboard,
    get_manager_info,
    get_manager_shifts,
    get_manager_overview,
    create_worker,
    update_worker_password,
    update_worker_email,
    deactivate_worker,
    promote_to_manager,
    hash_password
)
from db.postgres import get_db

router = APIRouter(prefix="/workers", tags=["Workers"])


# ==================== PYDANTIC MODELS ====================

class WorkerLoginRequest(BaseModel):
    """Request para login de trabalhador."""
    email: str
    password: str


class WorkerLoginResponse(BaseModel):
    """Response do login com JWT token."""
    token: str
    num_trabalhador: int
    nome: str
    email: str
    role: str  # "operador" ou "gestor"
    ativo: bool


class CreateWorkerRequest(BaseModel):
    """Request para criar novo trabalhador."""
    nome: str
    email: str
    password: str
    role: str  # "operador" ou "gestor"
    nivel_acesso: Optional[str] = None  # Para gestores


class UpdatePasswordRequest(BaseModel):
    """Request para atualizar password."""
    current_password: str
    new_password: str


class UpdateEmailRequest(BaseModel):
    """Request para atualizar email."""
    new_email: str


class WorkerInfo(BaseModel):
    """Informação de trabalhador."""
    num_trabalhador: int
    nome: str
    email: str
    role: str
    ativo: bool


class OperatorDashboard(BaseModel):
    """Dashboard do operador."""
    operador: int
    gate: int
    data: str
    proximas_chegadas: List[Dict[str, Any]]
    stats: Dict[str, int]


class ManagerOverview(BaseModel):
    """Visão geral do gestor."""
    gestor: int
    data: str
    gates_ativos: int
    turnos_hoje: int
    alertas_recentes: int
    estatisticas: Dict[str, int]


# ==================== AUTH ENDPOINTS ====================

@router.post("/login", response_model=WorkerLoginResponse)
def login(
    credentials: WorkerLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login de trabalhador (operador ou gestor).
    Retorna token para autenticação.
    """
    trabalhador = authenticate_worker(
        db,
        email=credentials.email,
        password=credentials.password
    )
    
    if not trabalhador:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas ou conta desativada"
        )
    
    # MVP: gerar token simples (em produção usar JWT)
    import secrets
    token = secrets.token_hex(32)
    
    return WorkerLoginResponse(
        token=token,
        num_trabalhador=trabalhador.num_trabalhador,
        nome=trabalhador.nome,
        email=trabalhador.email,
        role=trabalhador.role,
        ativo=trabalhador.ativo
    )


# ==================== OPERATOR ENDPOINTS ====================

@router.get("/operators", response_model=List[WorkerInfo])
def list_operators(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista operadores de cancela."""
    operadores = get_operators(db, skip=skip, limit=limit)
    return [
        WorkerInfo(
            num_trabalhador=op.trabalhador.num_trabalhador,
            nome=op.trabalhador.nome,
            email=op.trabalhador.email,
            role=op.trabalhador.role,
            ativo=op.trabalhador.ativo
        )
        for op in operadores
    ]


@router.get("/operators/me", response_model=Dict[str, Any])
def get_my_operator_info(
    num_trabalhador: int = Query(..., description="ID do operador (do JWT)"),
    db: Session = Depends(get_db)
):
    """
    Obtém informação do operador autenticado.
    Em produção: num_trabalhador viria do JWT.
    """
    info = get_operator_info(db, num_trabalhador)
    if not info:
        raise HTTPException(status_code=404, detail="Operador não encontrado")
    return info


@router.get("/operators/{num_trabalhador}")
def get_operator(
    num_trabalhador: int = Path(..., description="ID do operador"),
    db: Session = Depends(get_db)
):
    """Obtém informação de um operador específico."""
    info = get_operator_info(db, num_trabalhador)
    if not info:
        raise HTTPException(status_code=404, detail="Operador não encontrado")
    return info


@router.get("/operators/{num_trabalhador}/current-shift/{id_gate}")
def get_operator_shift(
    num_trabalhador: int = Path(...),
    id_gate: int = Path(...),
    db: Session = Depends(get_db)
):
    """Obtém turno atual do operador para um gate."""
    turno = get_operator_current_shift(db, num_trabalhador, id_gate)
    if not turno:
        return None
    
    return {
        "id_turno": turno.id_turno,
        "data": turno.data.isoformat(),
        "hora_inicio": turno.hora_inicio.isoformat(),
        "hora_fim": turno.hora_fim.isoformat(),
        "id_gate": turno.id_gate
    }


@router.get("/operators/{num_trabalhador}/shifts")
def list_operator_shifts(
    num_trabalhador: int = Path(...),
    id_gate: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Lista turnos de um operador."""
    turnos = get_operator_shifts(db, num_trabalhador, id_gate)
    return [
        {
            "id_turno": t.id_turno,
            "data": t.data.isoformat(),
            "hora_inicio": t.hora_inicio.isoformat(),
            "hora_fim": t.hora_fim.isoformat(),
            "id_gate": t.id_gate
        }
        for t in turnos[:limit]
    ]


@router.get("/operators/{num_trabalhador}/dashboard/{id_gate}", response_model=OperatorDashboard)
def get_operator_dashboard(
    num_trabalhador: int = Path(...),
    id_gate: int = Path(...),
    db: Session = Depends(get_db)
):
    """
    Dashboard do operador para um gate.
    Próximas chegadas, alertas, estatísticas.
    """
    dashboard = get_operator_gate_dashboard(db, num_trabalhador, id_gate)
    return OperatorDashboard(**dashboard)


# ==================== MANAGER ENDPOINTS ====================

@router.get("/managers", response_model=List[WorkerInfo])
def list_managers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista gestores."""
    gestores = get_managers(db, skip=skip, limit=limit)
    return [
        WorkerInfo(
            num_trabalhador=g.trabalhador.num_trabalhador,
            nome=g.trabalhador.nome,
            email=g.trabalhador.email,
            role=g.trabalhador.role,
            ativo=g.trabalhador.ativo
        )
        for g in gestores
    ]


@router.get("/managers/me", response_model=Dict[str, Any])
def get_my_manager_info(
    num_trabalhador: int = Query(..., description="ID do gestor (do JWT)"),
    db: Session = Depends(get_db)
):
    """
    Obtém informação do gestor autenticado.
    Em produção: num_trabalhador viria do JWT.
    """
    info = get_manager_info(db, num_trabalhador)
    if not info:
        raise HTTPException(status_code=404, detail="Gestor não encontrado")
    return info


@router.get("/managers/{num_trabalhador}")
def get_manager(
    num_trabalhador: int = Path(...),
    db: Session = Depends(get_db)
):
    """Obtém informação de um gestor específico."""
    info = get_manager_info(db, num_trabalhador)
    if not info:
        raise HTTPException(status_code=404, detail="Gestor não encontrado")
    return info


@router.get("/managers/{num_trabalhador}/shifts")
def list_manager_shifts(
    num_trabalhador: int = Path(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Lista turnos supervisionados por um gestor."""
    turnos = get_manager_shifts(db, num_trabalhador)
    return [
        {
            "id_turno": t.id_turno,
            "data": t.data.isoformat(),
            "hora_inicio": t.hora_inicio.isoformat(),
            "hora_fim": t.hora_fim.isoformat(),
            "id_gate": t.id_gate,
            "num_operador_cancela": t.num_operador_cancela
        }
        for t in turnos[:limit]
    ]


@router.get("/managers/{num_trabalhador}/overview", response_model=ManagerOverview)
def get_manager_dashboard(
    num_trabalhador: int = Path(...),
    db: Session = Depends(get_db)
):
    """
    Dashboard/visão geral do gestor.
    Gates, turnos, alertas, performance.
    """
    overview = get_manager_overview(db, num_trabalhador)
    return ManagerOverview(**overview)


# ==================== GENERAL WORKER ENDPOINTS ====================

@router.get("/", response_model=List[WorkerInfo])
def list_all_workers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    only_active: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Lista todos os trabalhadores (backoffice)."""
    workers = get_all_workers(db, skip=skip, limit=limit, only_active=only_active)
    return [
        WorkerInfo(
            num_trabalhador=w.num_trabalhador,
            nome=w.nome,
            email=w.email,
            role=w.role,
            ativo=w.ativo
        )
        for w in workers
    ]


@router.get("/{num_trabalhador}", response_model=Dict[str, Any])
def get_worker(
    num_trabalhador: int = Path(...),
    db: Session = Depends(get_db)
):
    """Obtém dados de um trabalhador."""
    worker = get_worker_by_id(db, num_trabalhador)
    if not worker:
        raise HTTPException(status_code=404, detail="Trabalhador não encontrado")
    
    return {
        "num_trabalhador": worker.num_trabalhador,
        "nome": worker.nome,
        "email": worker.email,
        "role": worker.role,
        "ativo": worker.ativo,
        "criado_em": worker.criado_em.isoformat() if worker.criado_em else None
    }


# ==================== ACCOUNT MANAGEMENT ====================

@router.post("/password", status_code=status.HTTP_200_OK)
def change_password(
    request: UpdatePasswordRequest,
    num_trabalhador: int = Query(..., description="ID do trabalhador (do JWT)"),
    db: Session = Depends(get_db)
):
    """Atualiza password do trabalhador."""
    worker = get_worker_by_id(db, num_trabalhador)
    if not worker:
        raise HTTPException(status_code=404, detail="Trabalhador não encontrado")
    
    # Verificar password atual
    from services.worker_service import verify_password
    if not verify_password(request.current_password, worker.password_hash):
        raise HTTPException(status_code=401, detail="Password atual incorreta")
    
    updated = update_worker_password(db, num_trabalhador, request.new_password)
    if not updated:
        raise HTTPException(status_code=500, detail="Erro ao atualizar password")
    
    return {"message": "Password atualizada com sucesso"}


@router.post("/email", status_code=status.HTTP_200_OK)
def change_email(
    request: UpdateEmailRequest,
    num_trabalhador: int = Query(..., description="ID do trabalhador (do JWT)"),
    db: Session = Depends(get_db)
):
    """Atualiza email do trabalhador."""
    updated = update_worker_email(db, num_trabalhador, request.new_email)
    if not updated:
        raise HTTPException(status_code=400, detail="Email já em uso ou trabalhador não encontrado")
    
    return {"message": "Email atualizado com sucesso"}


# ==================== ADMIN ENDPOINTS ====================

@router.post("/", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_new_worker(
    request: CreateWorkerRequest,
    db: Session = Depends(get_db)
):
    """
    Cria novo trabalhador (operador ou gestor).
    Requer autenticação de admin.
    """
    worker = create_worker(
        db,
        nome=request.nome,
        email=request.email,
        password=request.password,
        role=request.role,
        nivel_acesso=request.nivel_acesso
    )
    
    if not worker:
        raise HTTPException(status_code=400, detail="Email já em uso ou erro na criação")
    
    return {
        "num_trabalhador": worker.num_trabalhador,
        "nome": worker.nome,
        "email": worker.email,
        "role": worker.role,
        "ativo": worker.ativo
    }


@router.delete("/{num_trabalhador}", status_code=status.HTTP_200_OK)
def deactivate_worker_endpoint(
    num_trabalhador: int = Path(...),
    db: Session = Depends(get_db)
):
    """Desativa um trabalhador."""
    worker = deactivate_worker(db, num_trabalhador)
    if not worker:
        raise HTTPException(status_code=404, detail="Trabalhador não encontrado")
    
    return {"message": f"Trabalhador {worker.nome} desativado"}


@router.post("/{num_trabalhador}/promote", status_code=status.HTTP_200_OK)
def promote_operator_to_manager(
    num_trabalhador: int = Path(...),
    nivel_acesso: str = Query("basic"),
    db: Session = Depends(get_db)
):
    """Promove um operador a gestor."""
    gestor = promote_to_manager(db, num_trabalhador, nivel_acesso)
    if not gestor:
        raise HTTPException(status_code=400, detail="Trabalhador não é operador ou não encontrado")
    
    return {"message": f"Operador promovido a gestor com acesso {nivel_acesso}"}
