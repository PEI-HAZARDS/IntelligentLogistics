"""
Driver Routes - Endpoints para condutores e autenticação mobile.
Consumido por: App mobile do motorista, backoffice.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from models.pydantic_models import (
    Condutor, Chegada,
    DriverLoginRequest, DriverLoginResponse,
    ClaimChegadaRequest, ClaimChegadaResponse
)
from services.driver_service import (
    get_drivers,
    get_driver_arrivals,
    get_driver_today_arrivals,
    get_driver_by_num_carta,
    authenticate_driver,
    claim_chegada_by_pin,
    get_driver_active_chegada,
    create_driver,
    hash_password
)
from db.postgres import get_db

router = APIRouter(prefix="/drivers", tags=["Drivers"])


# ==================== AUTH ENDPOINTS (Mobile App) ====================

@router.post("/login", response_model=DriverLoginResponse)
def login(
    credentials: DriverLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login do motorista na app mobile.
    Retorna token JWT para autenticação subsequente.
    
    Para MVP: token é placeholder, em produção usar JWT real.
    """
    condutor = authenticate_driver(
        db,
        num_carta_cond=credentials.num_carta_cond,
        password=credentials.password
    )
    
    if not condutor:
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas ou conta desativada"
        )
    
    # MVP: gerar token simples (em produção usar JWT)
    import secrets
    token = secrets.token_hex(32)
    
    return DriverLoginResponse(
        token=token,
        num_carta_cond=condutor.num_carta_cond,
        nome=condutor.nome,
        id_empresa=condutor.id_empresa or 0,
        empresa_nome=condutor.empresa.nome if condutor.empresa else "Sem empresa"
    )


@router.post("/claim", response_model=ClaimChegadaResponse)
def claim_arrival(
    claim_data: ClaimChegadaRequest,
    num_carta_cond: str = Query(..., description="Número carta condução (do token)"),
    db: Session = Depends(get_db)
):
    """
    Motorista usa PIN para reclamar uma chegada.
    Após validação, retorna detalhes para navegação ao cais.
    
    Em produção: num_carta_cond viria do JWT token decodificado.
    """
    chegada = claim_chegada_by_pin(db, num_carta_cond, claim_data.pin_acesso)
    
    if not chegada:
        raise HTTPException(
            status_code=404,
            detail="PIN inválido ou chegada não disponível"
        )
    
    # Construir URL de navegação para o cais
    navegacao_url = None
    if chegada.cais and chegada.cais.localizacao_gps:
        # Formato: "lat,lon" -> Google Maps URL
        gps = chegada.cais.localizacao_gps
        navegacao_url = f"https://www.google.com/maps/dir/?api=1&destination={gps}"
    
    return ClaimChegadaResponse(
        id_chegada=chegada.id_chegada,
        id_cais=chegada.id_cais,
        cais_localizacao=chegada.cais.localizacao_gps if chegada.cais else "N/A",
        matricula_veiculo=chegada.matricula_pesado,
        carga_descricao=chegada.carga.descricao if chegada.carga else "N/A",
        carga_adr=chegada.carga.adr if chegada.carga else False,
        navegacao_url=navegacao_url
    )


@router.get("/me/active", response_model=Optional[Chegada])
def get_my_active_arrival(
    num_carta_cond: str = Query(..., description="Número carta condução (do token)"),
    db: Session = Depends(get_db)
):
    """
    Obtém a chegada ativa do motorista.
    Retorna None se não houver chegada ativa.
    
    Em produção: num_carta_cond viria do JWT token decodificado.
    """
    chegada = get_driver_active_chegada(db, num_carta_cond)
    
    if not chegada:
        return None
    
    return Chegada.model_validate(chegada)


@router.get("/me/today", response_model=List[Chegada])
def get_my_today_arrivals(
    num_carta_cond: str = Query(..., description="Número carta condução (do token)"),
    db: Session = Depends(get_db)
):
    """
    Obtém chegadas de hoje do motorista.
    
    Em produção: num_carta_cond viria do JWT token decodificado.
    """
    chegadas = get_driver_today_arrivals(db, num_carta_cond)
    return [Chegada.model_validate(c) for c in chegadas]


# ==================== QUERY ENDPOINTS ====================

@router.get("", response_model=List[Condutor])
def list_all_drivers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista todos os condutores (backoffice)."""
    drivers = get_drivers(db, skip=skip, limit=limit, only_active=True)
    return [Condutor.model_validate(d) for d in drivers]


@router.get("/{num_carta_cond}", response_model=Condutor)
def get_driver(
    num_carta_cond: str = Path(..., description="Número da carta de condução"),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de um condutor específico."""
    driver = get_driver_by_num_carta(db, num_carta_cond)
    if not driver:
        raise HTTPException(status_code=404, detail="Condutor não encontrado")
    return Condutor.model_validate(driver)


@router.get("/{num_carta_cond}/arrivals", response_model=List[Chegada])
def get_arrivals_for_driver(
    num_carta_cond: str = Path(..., description="Número da carta de condução"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Obtém histórico de chegadas de um condutor."""
    chegadas = get_driver_arrivals(db, num_carta_cond, limit=limit)
    return [Chegada.model_validate(c) for c in chegadas]
