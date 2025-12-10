"""
Arrival Service - Gestão de chegadas diárias (PostgreSQL).
Usado por: Frontend operador, Decision Engine, App motorista.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from models.sql_models import ChegadaDiaria, Turno, Carga, Cais, Gate, HistoricoOcorrencias, Alerta


def get_all_arrivals(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    id_gate: Optional[int] = None,
    id_turno: Optional[int] = None,
    estado_entrega: Optional[str] = None,
    data_prevista: Optional[date] = None
) -> List[ChegadaDiaria]:
    """
    Obtém chegadas com filtros opcionais.
    Usado pelo frontend do operador para listar chegadas.
    """
    query = db.query(ChegadaDiaria)
    
    if id_gate:
        query = query.filter(ChegadaDiaria.id_gate_entrada == id_gate)
    if id_turno:
        query = query.filter(ChegadaDiaria.id_turno == id_turno)
    if estado_entrega:
        query = query.filter(ChegadaDiaria.estado_entrega == estado_entrega)
    if data_prevista:
        query = query.filter(ChegadaDiaria.data_prevista == data_prevista)
    
    return query.order_by(ChegadaDiaria.hora_prevista.asc()).offset(skip).limit(limit).all()


def get_arrival_by_id(db: Session, id_chegada: int) -> Optional[ChegadaDiaria]:
    """Obtém uma chegada específica por ID."""
    return db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == id_chegada).first()


def get_arrival_by_pin(db: Session, pin_acesso: str) -> Optional[ChegadaDiaria]:
    """Obtém chegada pelo PIN de acesso (usado pelo motorista)."""
    return db.query(ChegadaDiaria).filter(ChegadaDiaria.pin_acesso == pin_acesso).first()


def get_arrivals_by_matricula(
    db: Session,
    matricula: str,
    id_turno: Optional[int] = None,
    estado_entrega: Optional[str] = None,
    data_prevista: Optional[date] = None
) -> List[ChegadaDiaria]:
    """
    Obtém chegadas por matrícula.
    Usado pelo Decision Engine para encontrar chegadas candidatas.
    """
    query = db.query(ChegadaDiaria).filter(ChegadaDiaria.matricula_pesado == matricula)
    
    if id_turno:
        query = query.filter(ChegadaDiaria.id_turno == id_turno)
    if estado_entrega:
        query = query.filter(ChegadaDiaria.estado_entrega == estado_entrega)
    if data_prevista:
        query = query.filter(ChegadaDiaria.data_prevista == data_prevista)
    else:
        # Por defeito, filtra por hoje
        query = query.filter(ChegadaDiaria.data_prevista == date.today())
    
    return query.order_by(ChegadaDiaria.hora_prevista.asc()).all()


def get_arrivals_for_decision(
    db: Session,
    matricula: str,
    id_gate: int,
    hora_atual: Optional[time] = None
) -> List[Dict[str, Any]]:
    """
    Obtém chegadas candidatas para o Decision Engine decidir.
    Retorna chegadas com matrícula específica, no turno atual, 
    com estado 'in_transit' ou 'delayed'.
    
    Inclui informação extra: carga (ADR?), cais, gate.
    """
    hoje = date.today()
    agora = hora_atual or datetime.now().time()
    
    # Encontrar turno atual baseado na hora
    turno_atual = db.query(Turno).filter(
        Turno.data == hoje,
        Turno.id_gate == id_gate,
        Turno.hora_inicio <= agora,
        Turno.hora_fim >= agora
    ).first()
    
    query = db.query(ChegadaDiaria).filter(
        ChegadaDiaria.matricula_pesado == matricula,
        ChegadaDiaria.data_prevista == hoje,
        ChegadaDiaria.id_gate_entrada == id_gate,
        ChegadaDiaria.estado_entrega.in_(['in_transit', 'delayed'])
    )
    
    if turno_atual:
        query = query.filter(ChegadaDiaria.id_turno == turno_atual.id_turno)
    
    chegadas = query.order_by(ChegadaDiaria.hora_prevista.asc()).all()
    
    # Formatar resposta com informação extra
    result = []
    for c in chegadas:
        result.append({
            "id_chegada": c.id_chegada,
            "matricula_pesado": c.matricula_pesado,
            "id_gate_entrada": c.id_gate_entrada,
            "id_cais": c.id_cais,
            "id_turno": c.id_turno,
            "hora_prevista": c.hora_prevista.isoformat() if c.hora_prevista else None,
            "estado_entrega": c.estado_entrega,
            "carga": {
                "id_carga": c.carga.id_carga if c.carga else None,
                "descricao": c.carga.descricao if c.carga else None,
                "adr": c.carga.adr if c.carga else False,
                "tipo_carga": c.carga.tipo_carga if c.carga else None
            } if c.carga else None,
            "cais": {
                "id_cais": c.cais.id_cais if c.cais else None,
                "localizacao_gps": c.cais.localizacao_gps if c.cais else None
            } if c.cais else None
        })
    
    return result


def get_arrivals_count_by_status(db: Session, id_gate: Optional[int] = None, data: Optional[date] = None) -> Dict[str, int]:
    """
    Conta chegadas agrupadas por estado.
    Usado pelo dashboard do operador.
    """
    data_filtro = data or date.today()
    
    query = db.query(
        ChegadaDiaria.estado_entrega,
        func.count(ChegadaDiaria.id_chegada)
    ).filter(ChegadaDiaria.data_prevista == data_filtro)
    
    if id_gate:
        query = query.filter(ChegadaDiaria.id_gate_entrada == id_gate)
    
    results = query.group_by(ChegadaDiaria.estado_entrega).all()
    
    counts = {
        "in_transit": 0,
        "delayed": 0,
        "unloading": 0,
        "completed": 0,
        "total": 0
    }
    
    for estado, count in results:
        if estado in counts:
            counts[estado] = count
        counts["total"] += count
    
    return counts


def update_arrival_status(
    db: Session,
    id_chegada: int,
    novo_estado: str,
    data_hora_chegada: Optional[datetime] = None,
    id_gate_saida: Optional[int] = None,
    observacoes: Optional[str] = None
) -> Optional[ChegadaDiaria]:
    """
    Atualiza estado de uma chegada.
    Usado pelo Decision Engine após tomar decisão.
    """
    chegada = db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == id_chegada).first()
    
    if not chegada:
        return None
    
    chegada.estado_entrega = novo_estado
    
    if data_hora_chegada:
        chegada.data_hora_chegada = data_hora_chegada
    
    if id_gate_saida:
        chegada.id_gate_saida = id_gate_saida
    
    if observacoes:
        chegada.observacoes = observacoes
    
    db.commit()
    db.refresh(chegada)
    
    return chegada


def update_arrival_from_decision(
    db: Session,
    id_chegada: int,
    decision_payload: Dict[str, Any]
) -> Optional[ChegadaDiaria]:
    """
    Atualiza chegada com base na decisão do Decision Engine.
    Inclui: estado, hora de chegada, e criação de alertas se necessário.
    
    decision_payload esperado:
    {
        "decision": "approved" | "rejected" | "manual_review",
        "estado_entrega": "unloading" | "delayed" | etc,
        "data_hora_chegada": "2025-12-09T10:30:00",
        "observacoes": "...",
        "alertas": [
            {"tipo": "ADR", "severidade": 3, "descricao": "Carga inflamável - UN 1203"}
        ]
    }
    """
    chegada = db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == id_chegada).first()
    
    if not chegada:
        return None
    
    # Atualizar estado
    if "estado_entrega" in decision_payload:
        chegada.estado_entrega = decision_payload["estado_entrega"]
    
    # Atualizar hora de chegada
    if "data_hora_chegada" in decision_payload:
        if isinstance(decision_payload["data_hora_chegada"], str):
            chegada.data_hora_chegada = datetime.fromisoformat(decision_payload["data_hora_chegada"])
        else:
            chegada.data_hora_chegada = decision_payload["data_hora_chegada"]
    else:
        chegada.data_hora_chegada = datetime.now()
    
    # Atualizar observações
    if "observacoes" in decision_payload:
        chegada.observacoes = decision_payload["observacoes"]
    
    db.commit()
    db.refresh(chegada)
    
    # Criar alertas se existirem (delegar para alert_service)
    if "alertas" in decision_payload and decision_payload["alertas"]:
        from services.alert_service import create_alerts_for_arrival
        create_alerts_for_arrival(db, chegada, decision_payload["alertas"])
    
    return chegada


def get_next_arrivals(
    db: Session,
    id_gate: int,
    limit: int = 5
) -> List[ChegadaDiaria]:
    """
    Obtém próximas chegadas previstas (usadas no painel lateral do operador).
    Filtra por estado 'in_transit' ou 'delayed'.
    """
    hoje = date.today()
    agora = datetime.now().time()
    
    return db.query(ChegadaDiaria).filter(
        ChegadaDiaria.id_gate_entrada == id_gate,
        ChegadaDiaria.data_prevista == hoje,
        ChegadaDiaria.estado_entrega.in_(['in_transit', 'delayed']),
        ChegadaDiaria.hora_prevista >= agora
    ).order_by(ChegadaDiaria.hora_prevista.asc()).limit(limit).all()