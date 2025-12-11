"""
Worker Service - Gestão de trabalhadores (operadores e gestores).
Usado por: Frontend backoffice, autenticação.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from utils.hashing_pass import hash_password, verify_password

from models.sql_models import TrabalhadorPorto as Trabalhador, Gestor, Operador, Turno, Gate, ChegadaDiaria


# ==================== AUTHENTICATION ====================

def authenticate_worker(db: Session, email: str, password: str) -> Optional[Trabalhador]:
    """
    Autentica trabalhador (operador ou gestor).
    Retorna trabalhador se credenciais válidas, None caso contrário.
    """
    trabalhador = db.query(Trabalhador).filter(Trabalhador.email == email).first()
    
    if not trabalhador:
        return None
    
    if not verify_password(password, trabalhador.password_hash):
        return None
    
    return trabalhador


def get_worker_by_email(db: Session, email: str) -> Optional[Trabalhador]:
    """Obtém trabalhador pelo email."""
    return db.query(Trabalhador).filter(Trabalhador.email == email).first()


def get_worker_by_id(db: Session, num_trabalhador: int) -> Optional[Trabalhador]:
    """Obtém trabalhador pelo ID."""
    return db.query(Trabalhador).filter(Trabalhador.num_trabalhador == num_trabalhador).first()


# ==================== TRABALHADOR QUERIES ====================

def get_all_workers(db: Session, skip: int = 0, limit: int = 100, only_active: bool = True) -> List[Trabalhador]:
    """Obtém lista de trabalhadores (ativo não é mais rastreado)."""
    query = db.query(Trabalhador)
    return query.offset(skip).limit(limit).all()


def get_operators(db: Session, skip: int = 0, limit: int = 100) -> List[Operador]:
    """Obtém lista de operadores de cancela."""
    return db.query(Operador).offset(skip).limit(limit).all()


def get_managers(db: Session, skip: int = 0, limit: int = 100) -> List[Gestor]:
    """Obtém lista de gestores."""
    return db.query(Gestor).offset(skip).limit(limit).all()


# ==================== OPERATOR FUNCTIONS ====================

def get_operator_info(db: Session, num_trabalhador: int) -> Optional[Dict[str, Any]]:
    """Obtém informação completa de um operador."""
    operador = db.query(Operador).filter(Operador.num_trabalhador == num_trabalhador).first()
    
    if not operador:
        return None
    
    trabalhador = operador.trabalhador
    
    return {
        "num_trabalhador": trabalhador.num_trabalhador,
        "nome": trabalhador.nome,
        "email": trabalhador.email
    }


def get_operator_current_shift(db: Session, num_trabalhador: int, id_gate: int) -> Optional[Turno]:
    """
    Obtém turno atual do operador.
    Filtra por data de hoje, gate e horário.
    """
    from datetime import date, time
    
    hoje = date.today()
    agora = datetime.now().time()
    
    turno = db.query(Turno).filter(
        Turno.num_operador_cancela == num_trabalhador,
        Turno.id_gate == id_gate,
        Turno.data == hoje,
        Turno.hora_inicio <= agora,
        Turno.hora_fim >= agora
    ).first()
    
    return turno


def get_operator_shifts(db: Session, num_trabalhador: int, id_gate: Optional[int] = None) -> List[Turno]:
    """
    Obtém turnos de um operador.
    Filtra por gate se fornecido.
    """
    query = db.query(Turno).filter(Turno.num_operador_cancela == num_trabalhador)
    
    if id_gate:
        query = query.filter(Turno.id_gate == id_gate)
    
    return query.order_by(Turno.data.desc(), Turno.hora_inicio.desc()).all()


def get_operator_gate_dashboard(db: Session, num_trabalhador: int, id_gate: int) -> Dict[str, Any]:
    """
    Obtém dados do dashboard do operador para um gate.
    Inclui: próximas chegadas, alertas, estatísticas.
    """
    from datetime import date
    from sqlalchemy import func
    
    hoje = date.today()
    
    # Próximas chegadas
    proximas = db.query(ChegadaDiaria).filter(
        ChegadaDiaria.id_gate_entrada == id_gate,
        ChegadaDiaria.data_prevista == hoje,
        ChegadaDiaria.estado_entrega.in_(['in_transit', 'delayed'])
    ).order_by(ChegadaDiaria.hora_prevista.asc()).limit(10).all()
    
    # Estatísticas por estado
    stats = db.query(
        ChegadaDiaria.estado_entrega,
        func.count(ChegadaDiaria.id_chegada)
    ).filter(
        ChegadaDiaria.id_gate_entrada == id_gate,
        ChegadaDiaria.data_prevista == hoje
    ).group_by(ChegadaDiaria.estado_entrega).all()
    
    stats_dict = {estado: count for estado, count in stats}
    
    return {
        "operador": num_trabalhador,
        "gate": id_gate,
        "data": hoje.isoformat(),
        "proximas_chegadas": [
            {
                "id_chegada": c.id_chegada,
                "matricula": c.matricula_pesado,
                "hora_prevista": c.hora_prevista.isoformat() if c.hora_prevista else None,
                "cais": c.id_cais,
                "carga_adr": c.carga.adr if c.carga else False,
                "estado": c.estado_entrega
            }
            for c in proximas
        ],
        "stats": {
            "in_transit": stats_dict.get("in_transit", 0),
            "delayed": stats_dict.get("delayed", 0),
            "unloading": stats_dict.get("unloading", 0),
            "completed": stats_dict.get("completed", 0)
        }
    }


# ==================== MANAGER FUNCTIONS ====================

def get_manager_info(db: Session, num_trabalhador: int) -> Optional[Dict[str, Any]]:
    """Obtém informação completa de um gestor."""
    gestor = db.query(Gestor).filter(Gestor.num_trabalhador == num_trabalhador).first()
    
    if not gestor:
        return None
    
    trabalhador = gestor.trabalhador
    
    return {
        "num_trabalhador": trabalhador.num_trabalhador,
        "nome": trabalhador.nome,
        "email": trabalhador.email,
        "nivel_acesso": gestor.nivel_acesso
    }


def get_manager_shifts(db: Session, num_trabalhador: int) -> List[Turno]:
    """Obtém turnos geridos por um gestor."""
    return db.query(Turno).filter(
        Turno.num_gestor_responsavel == num_trabalhador
    ).order_by(Turno.data.desc(), Turno.hora_inicio.desc()).all()


def get_manager_overview(db: Session, num_trabalhador: int) -> Dict[str, Any]:
    """
    Obtém visão geral do gestor: gates, turnos, alertas, performance.
    """
    from datetime import date
    from sqlalchemy import func
    
    hoje = date.today()
    
    # Gates supervisionados
    gates_supervisionados = db.query(Gate).all()  # Ou filtrar se gestor supervisa gates específicos
    
    # Turnos de hoje
    turnos_hoje = db.query(Turno).filter(
        Turno.num_gestor_responsavel == num_trabalhador,
        Turno.data == hoje
    ).all()
    
    # Alertas últimas 24h
    from models.sql_models import Alerta
    alertas_recentes = db.query(Alerta).order_by(Alerta.data_hora.desc()).limit(20).all()
    
    # Chegadas por estado (hoje)
    stats = db.query(
        ChegadaDiaria.estado_entrega,
        func.count(ChegadaDiaria.id_chegada)
    ).filter(
        ChegadaDiaria.data_prevista == hoje
    ).group_by(ChegadaDiaria.estado_entrega).all()
    
    return {
        "gestor": num_trabalhador,
        "data": hoje.isoformat(),
        "gates_ativos": len(gates_supervisionados),
        "turnos_hoje": len(turnos_hoje),
        "alertas_recentes": len(alertas_recentes),
        "estatisticas": {
            estado: count
            for estado, count in stats
        }
    }


# ==================== ADMIN FUNCTIONS ====================

def create_worker(
    db: Session,
    nome: str,
    email: str,
    password: str,
    role: str,  # "operador" ou "gestor"
    nivel_acesso: Optional[str] = None
) -> Optional[Trabalhador]:
    """
    Cria novo trabalhador (operador ou gestor).
    """
    # Verificar se email já existe
    if db.query(Trabalhador).filter(Trabalhador.email == email).first():
        return None
    
    trabalhador = Trabalhador(
        nome=nome,
        email=email,
        password_hash=hash_password(password)
    )
    db.add(trabalhador)
    db.commit()
    db.refresh(trabalhador)
    
    # Se gestor, criar registro em Gestor
    if role == "gestor":
        gestor = Gestor(
            num_trabalhador=trabalhador.num_trabalhador,
            nivel_acesso=nivel_acesso or "basic"
        )
        db.add(gestor)
        db.commit()
    
    # Se operador, criar registro em Operador
    elif role == "operador":
        operador = Operador(
            num_trabalhador=trabalhador.num_trabalhador
        )
        db.add(operador)
        db.commit()
    
    return trabalhador


def update_worker_password(db: Session, num_trabalhador: int, new_password: str) -> Optional[Trabalhador]:
    """Atualiza password de um trabalhador."""
    trabalhador = get_worker_by_id(db, num_trabalhador)
    if not trabalhador:
        return None
    
    trabalhador.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(trabalhador)
    return trabalhador


def update_worker_email(db: Session, num_trabalhador: int, new_email: str) -> Optional[Trabalhador]:
    """Atualiza email de um trabalhador."""
    trabalhador = get_worker_by_id(db, num_trabalhador)
    if not trabalhador:
        return None
    
    # Verificar se novo email já existe
    if db.query(Trabalhador).filter(
        Trabalhador.email == new_email,
        Trabalhador.num_trabalhador != num_trabalhador
    ).first():
        return None
    
    trabalhador.email = new_email
    db.commit()
    db.refresh(trabalhador)
    return trabalhador


def deactivate_worker(db: Session, num_trabalhador: int) -> Optional[Trabalhador]:
    """Remove um trabalhador (hard delete por não existir mais flag ativo)."""
    trabalhador = get_worker_by_id(db, num_trabalhador)
    if not trabalhador:
        return None

    db.delete(trabalhador)
    db.commit()
    return trabalhador


def promote_to_manager(db: Session, num_trabalhador: int, nivel_acesso: str = "basic") -> Optional[Gestor]:
    """Promove um operador a gestor."""
    trabalhador = get_worker_by_id(db, num_trabalhador)
    if not trabalhador:
        return None
    
    # Remover de Operador se existir
    db.query(Operador).filter(Operador.num_trabalhador == num_trabalhador).delete()
    
    # Criar em Gestor
    gestor = Gestor(
        num_trabalhador=num_trabalhador,
        nivel_acesso=nivel_acesso
    )
    db.add(gestor)
    db.commit()
    db.refresh(gestor)
    
    return gestor
