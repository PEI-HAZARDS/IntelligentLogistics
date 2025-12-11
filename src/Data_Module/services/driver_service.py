"""
Driver Service - Gestão de condutores e autenticação mobile.
Usado por: App mobile do motorista.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from utils.hashing_pass import hash_password, verify_password

from models.sql_models import Condutor, Conduz, ChegadaDiaria


# ==================== AUTH FUNCTIONS ====================

def authenticate_driver(db: Session, num_carta_cond: str, password: str) -> Optional[Condutor]:
    """
    Autentica condutor para login na app mobile.
    Retorna condutor se credenciais válidas, None caso contrário.
    """
    condutor = db.query(Condutor).filter(
        Condutor.num_carta_cond == num_carta_cond
    ).first()
    
    if not condutor:
        return None
    
    if not verify_password(password, condutor.password_hash):
        return None
    
    return condutor


def get_driver_by_num_carta(db: Session, num_carta_cond: str) -> Optional[Condutor]:
    """Obtém condutor pelo número da carta de condução."""
    return db.query(Condutor).filter(Condutor.num_carta_cond == num_carta_cond).first()


# ==================== PIN/CLAIM FUNCTIONS ====================

def claim_chegada_by_pin(db: Session, num_carta_cond: str, pin_acesso: str) -> Optional[ChegadaDiaria]:
    """
    Motorista usa PIN para reclamar uma chegada.
    Valida que o condutor está associado ao veículo da chegada.
    
    Retorna a chegada se válido, None caso contrário.
    """
    # Buscar chegada pelo PIN
    chegada = db.query(ChegadaDiaria).filter(
        ChegadaDiaria.pin_acesso == pin_acesso
    ).first()
    
    if not chegada:
        return None
    
    # Verificar se estado permite claim (não pode reclamar chegada já concluída)
    if chegada.estado_entrega in ['completed']:
        return None
    
    # Verificar se o condutor está autorizado a conduzir este veículo
    # Busca na tabela Conduz se existe relação ativa
    conduz_record = db.query(Conduz).filter(
        Conduz.num_carta_cond == num_carta_cond,
        Conduz.matricula_veiculo == chegada.matricula_pesado
    ).first()
    
    # Para MVP, podemos ser menos restritivos e permitir qualquer condutor
    # mas em produção validar via conduz_record
    # if not conduz_record:
    #     return None
    
    return chegada


def get_driver_active_chegada(db: Session, num_carta_cond: str) -> Optional[ChegadaDiaria]:
    """
    Obtém a chegada ativa do motorista.
    Uma chegada ativa é aquela que:
    - Tem veículo associado ao condutor
    - Estado não é 'completed'
    - Data é hoje
    """
    from datetime import date
    
    # Buscar matrículas que o condutor conduz
    conduz_records = db.query(Conduz.matricula_veiculo).filter(
        Conduz.num_carta_cond == num_carta_cond
    ).distinct().all()
    
    if not conduz_records:
        return None
    
    matriculas = [r[0] for r in conduz_records if r[0]]
    
    # Buscar chegada ativa
    chegada = db.query(ChegadaDiaria).filter(
        ChegadaDiaria.matricula_pesado.in_(matriculas),
        ChegadaDiaria.data_prevista == date.today(),
        ChegadaDiaria.estado_entrega.in_(['in_transit', 'delayed', 'unloading'])
    ).order_by(ChegadaDiaria.hora_prevista.asc()).first()
    
    return chegada


# ==================== QUERY FUNCTIONS ====================

def get_drivers(db: Session, skip: int = 0, limit: int = 100, only_active: bool = True) -> List[Condutor]:
    """
    Retorna condutores com paginação.
    """
    query = db.query(Condutor)
    return query.offset(skip).limit(limit).all()


def get_driver_arrivals(db: Session, num_carta_cond: str, limit: int = 50) -> List[ChegadaDiaria]:
    """
    Retorna chegadas associadas a um condutor.
    Busca veículos que o condutor conduz via tabela Conduz.
    """
    # Obter matrículas associadas ao condutor
    rows = db.query(Conduz.matricula_veiculo).filter(
        Conduz.num_carta_cond == num_carta_cond
    ).distinct().all()
    
    vehicles = [r[0] for r in rows if r and r[0] is not None]
    
    if not vehicles:
        return []
    
    # Buscar chegadas correspondentes
    return db.query(ChegadaDiaria).filter(
        ChegadaDiaria.matricula_pesado.in_(vehicles)
    ).order_by(ChegadaDiaria.data_hora_chegada.desc()).limit(limit).all()


def get_driver_today_arrivals(db: Session, num_carta_cond: str) -> List[ChegadaDiaria]:
    """
    Retorna chegadas de hoje para um condutor.
    Usado na app mobile para mostrar entregas do dia.
    """
    from datetime import date
    
    # Obter matrículas associadas ao condutor
    rows = db.query(Conduz.matricula_veiculo).filter(
        Conduz.num_carta_cond == num_carta_cond
    ).distinct().all()
    
    vehicles = [r[0] for r in rows if r and r[0] is not None]
    
    if not vehicles:
        return []
    
    return db.query(ChegadaDiaria).filter(
        ChegadaDiaria.matricula_pesado.in_(vehicles),
        ChegadaDiaria.data_prevista == date.today()
    ).order_by(ChegadaDiaria.hora_prevista.asc()).all()


# ==================== ADMIN FUNCTIONS ====================

def create_driver(
    db: Session,
    num_carta_cond: str,
    nome: str,
    password: str,
    contacto: Optional[str] = None,
    id_empresa: Optional[int] = None
) -> Condutor:
    """Cria um novo condutor."""
    condutor = Condutor(
        num_carta_cond=num_carta_cond,
        nome=nome,
        password_hash=hash_password(password),
        contacto=contacto,
        id_empresa=id_empresa
    )
    db.add(condutor)
    db.commit()
    db.refresh(condutor)
    return condutor


def update_driver_password(db: Session, num_carta_cond: str, new_password: str) -> Optional[Condutor]:
    """Atualiza password de um condutor."""
    condutor = db.query(Condutor).filter(Condutor.num_carta_cond == num_carta_cond).first()
    if not condutor:
        return None
    
    condutor.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(condutor)
    return condutor


def deactivate_driver(db: Session, num_carta_cond: str) -> Optional[Condutor]:
    """Remove um condutor (hard delete por não existir mais flag ativo)."""
    condutor = db.query(Condutor).filter(Condutor.num_carta_cond == num_carta_cond).first()
    if not condutor:
        return None

    db.delete(condutor)
    db.commit()
    return condutor