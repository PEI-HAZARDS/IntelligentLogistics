"""
Alert Service - Gestão de alertas (PostgreSQL).
Responsabilidades:
- Criar alertas (ADR/hazmat, delays, segurança)
- Associar alertas a chegadas via HistoricoOcorrencias
- Listar e filtrar alertas
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from db.postgres import SessionLocal
from models.sql_models import Alerta, HistoricoOcorrencias, ChegadaDiaria


# ==================== ADR/HAZMAT CODES ====================

# Códigos UN perigosos comuns (simplificado para MVP)
ADR_CODES = {
    "1203": {"descricao": "Gasolina", "classe": "3", "perigo": "Líquido inflamável"},
    "1202": {"descricao": "Gasóleo", "classe": "3", "perigo": "Líquido inflamável"},
    "1073": {"descricao": "Oxigénio líquido", "classe": "2.2", "perigo": "Gás não inflamável"},
    "1978": {"descricao": "Propano", "classe": "2.1", "perigo": "Gás inflamável"},
    "1789": {"descricao": "Ácido clorídrico", "classe": "8", "perigo": "Corrosivo"},
    "2031": {"descricao": "Ácido nítrico", "classe": "8", "perigo": "Corrosivo/Oxidante"},
    "1830": {"descricao": "Ácido sulfúrico", "classe": "8", "perigo": "Corrosivo"},
    "1005": {"descricao": "Amoníaco anidro", "classe": "2.3", "perigo": "Gás tóxico"},
    "1017": {"descricao": "Cloro", "classe": "2.3", "perigo": "Gás tóxico"},
}

# Códigos Kemler (número de perigo)
KEMLER_CODES = {
    "33": "Líquido muito inflamável",
    "30": "Líquido inflamável",
    "23": "Gás inflamável",
    "22": "Gás refrigerado",
    "20": "Gás asfixiante",
    "X80": "Corrosivo - reage com água",
    "80": "Corrosivo",
    "60": "Tóxico",
    "X66": "Muito tóxico - reage com água",
}


# ==================== ALERT CREATION ====================

def create_alert(
    db: Session,
    id_historico_ocorrencia: int,
    id_carga: int,
    tipo: str,
    severidade: int,
    descricao: str
) -> Alerta:
    """
    Cria um alerta associado a um histórico de ocorrência.
    """
    alerta = Alerta(
        id_historico_ocorrencia=id_historico_ocorrencia,
        id_carga=id_carga,
        tipo=tipo,
        severidade=severidade,
        descricao=descricao,
        data_hora=datetime.now(timezone.utc)
    )
    db.add(alerta)
    db.commit()
    db.refresh(alerta)
    return alerta


def create_alerts_for_arrival(
    db: Session,
    chegada: ChegadaDiaria,
    alertas_payload: List[Dict[str, Any]]
) -> List[Alerta]:
    """
    Cria alertas para uma chegada.
    Primeiro cria HistoricoOcorrencias, depois os alertas associados.
    
    alertas_payload esperado:
    [
        {"tipo": "ADR", "severidade": 3, "descricao": "UN 1203 - Gasolina"},
        {"tipo": "delay", "severidade": 1, "descricao": "Atraso de 30 min"}
    ]
    """
    if not alertas_payload:
        return []
    
    # Criar HistoricoOcorrencias se não existir
    historico = HistoricoOcorrencias(
        id_turno=chegada.id_turno,
        hora_inicio=datetime.now(),
        descricao=f"Alertas para chegada {chegada.id_chegada} - {chegada.matricula_pesado}"
    )
    db.add(historico)
    db.commit()
    db.refresh(historico)
    
    # Criar alertas
    alertas_criados = []
    for alert_data in alertas_payload:
        alerta = Alerta(
            id_historico_ocorrencia=historico.id_historico,
            id_carga=chegada.id_carga,
            tipo=alert_data.get("tipo", "generic"),
            severidade=alert_data.get("severidade", 2),
            descricao=alert_data.get("descricao", "Alerta sem descrição"),
            data_hora=datetime.now(timezone.utc)
        )
        db.add(alerta)
        alertas_criados.append(alerta)
    
    db.commit()
    
    # Refresh all alerts
    for a in alertas_criados:
        db.refresh(a)
    
    return alertas_criados


def create_adr_alert(
    db: Session,
    chegada: ChegadaDiaria,
    un_code: Optional[str] = None,
    kemler_code: Optional[str] = None,
    detected_hazmat: Optional[str] = None
) -> Optional[Alerta]:
    """
    Cria alerta ADR/hazmat específico.
    Usado pelo Decision Engine quando detecta carga perigosa.
    """
    # Construir descrição
    descricao_parts = ["Carga perigosa detectada"]
    severidade = 3  # Default: alta
    
    if un_code and un_code in ADR_CODES:
        info = ADR_CODES[un_code]
        descricao_parts.append(f"UN {un_code} - {info['descricao']}")
        descricao_parts.append(f"Classe: {info['classe']}")
        descricao_parts.append(f"Perigo: {info['perigo']}")
        severidade = 4 if info['classe'] in ['2.3', '6.1'] else 3  # Tóxicos = crítico
    
    if kemler_code and kemler_code in KEMLER_CODES:
        descricao_parts.append(f"Kemler {kemler_code}: {KEMLER_CODES[kemler_code]}")
        if kemler_code.startswith('X'):
            severidade = 5  # Reage com água = máximo
    
    if detected_hazmat:
        descricao_parts.append(f"Deteção: {detected_hazmat}")
    
    # Criar histórico de ocorrência
    historico = HistoricoOcorrencias(
        id_turno=chegada.id_turno,
        hora_inicio=datetime.now(),
        descricao=f"Alerta ADR - Chegada {chegada.id_chegada}"
    )
    db.add(historico)
    db.commit()
    db.refresh(historico)
    
    # Criar alerta
    alerta = Alerta(
        id_historico_ocorrencia=historico.id_historico,
        id_carga=chegada.id_carga,
        tipo="ADR",
        severidade=severidade,
        descricao=" | ".join(descricao_parts),
        data_hora=datetime.now(timezone.utc)
    )
    db.add(alerta)
    db.commit()
    db.refresh(alerta)
    
    return alerta


# ==================== QUERY FUNCTIONS ====================

def get_alerts(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    tipo: Optional[str] = None,
    severidade_min: Optional[int] = None,
    id_carga: Optional[int] = None
) -> List[Alerta]:
    """Obtém alertas com filtros."""
    query = db.query(Alerta)
    
    if tipo:
        query = query.filter(Alerta.tipo == tipo)
    if severidade_min:
        query = query.filter(Alerta.severidade >= severidade_min)
    if id_carga:
        query = query.filter(Alerta.id_carga == id_carga)
    
    return query.order_by(Alerta.data_hora.desc()).offset(skip).limit(limit).all()


def get_alert_by_id(db: Session, id_alerta: int) -> Optional[Alerta]:
    """Obtém alerta por ID."""
    return db.query(Alerta).filter(Alerta.id_alerta == id_alerta).first()


def get_alerts_by_historico(db: Session, id_historico: int) -> List[Alerta]:
    """Obtém alertas de um histórico de ocorrência."""
    return db.query(Alerta).filter(
        Alerta.id_historico_ocorrencia == id_historico
    ).order_by(Alerta.data_hora.desc()).all()


def get_active_alerts(db: Session, limit: int = 50) -> List[Alerta]:
    """
    Obtém alertas recentes (últimas 24h) por severidade.
    Usado no painel do operador.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    return db.query(Alerta).filter(
        Alerta.data_hora >= cutoff
    ).order_by(Alerta.severidade.desc(), Alerta.data_hora.desc()).limit(limit).all()


def get_alerts_count_by_type(db: Session) -> Dict[str, int]:
    """Conta alertas por tipo (últimas 24h)."""
    from sqlalchemy import func
    from datetime import timedelta
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    results = db.query(
        Alerta.tipo,
        func.count(Alerta.id_alerta)
    ).filter(
        Alerta.data_hora >= cutoff
    ).group_by(Alerta.tipo).all()
    
    return {tipo: count for tipo, count in results}


# ==================== LEGACY FUNCTIONS (para compatibilidade) ====================

def create_alert_legacy(tipo: str, severidade: int, descricao: str, data: dict):
    """
    Função legacy para criar alerta sem histórico.
    DEPRECATED: usar create_alert ou create_alerts_for_arrival
    """
    db = SessionLocal()
    try:
        # Criar histórico dummy
        historico = HistoricoOcorrencias(
            id_turno=1,  # Dummy
            hora_inicio=datetime.now(),
            descricao="Alerta legacy"
        )
        db.add(historico)
        db.commit()
        db.refresh(historico)
        
        alerta = Alerta(
            id_historico_ocorrencia=historico.id_historico,
            id_carga=data.get("id_carga", 1),
            tipo=tipo,
            severidade=severidade,
            descricao=descricao,
            data_hora=datetime.now(timezone.utc)
        )
        db.add(alerta)
        db.commit()
        db.refresh(alerta)
        
        return alerta.id_alerta
    finally:
        db.close()


def get_alerts_legacy(limit: int = 100):
    """Função legacy para obter alertas."""
    db = SessionLocal()
    try:
        return db.query(Alerta).order_by(Alerta.data_hora.desc()).limit(limit).all()
    finally:
        db.close()