from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel
from enum import Enum


# ==========================
# ENUMS
# ==========================

class EstadoEntregaEnum(str, Enum):
    in_transit = "in_transit"
    delayed = "delayed"
    unloading = "unloading"
    completed = "completed"


class TipoCargaEnum(str, Enum):
    general = "general"
    hazardous = "hazardous"
    refrigerated = "refrigerated"
    live = "live"
    bulk = "bulk"


class EstadoFisicoEnum(str, Enum):
    liquid = "liquid"
    solid = "solid"
    gaseous = "gaseous"
    hybrid = "hybrid"


class NivelAcessoEnum(str, Enum):
    admin = "admin"
    basic = "basic"


class EstadoEnum(str, Enum):
    maintenance = "maintenance"
    operational = "operational"
    closed = "closed"


# ==========================
# EMPRESA
# ==========================

class EmpresaBase(BaseModel): # Modelo Base
    nome: str
    nif: Optional[str] = None
    contacto: Optional[str] = None
    descricao: Optional[str] = None


class EmpresaCreate(EmpresaBase): # Modelo para criação
    pass


class EmpresaUpdate(BaseModel): # Modelo para atualização
    nome: Optional[str] = None
    nif: Optional[str] = None
    contacto: Optional[str] = None
    descricao: Optional[str] = None


class Empresa(EmpresaBase): # Modelo para leitura
    id_empresa: int

    model_config = {"from_attributes": True}


# ==========================
# CONDUTOR
# ==========================

class CondutorBase(BaseModel):
    nome: str
    contacto: Optional[str] = None
    id_empresa: Optional[int] = None


class CondutorCreate(CondutorBase):
    num_carta_cond: str
    password: str  # Password em texto simples (será hasheada)


class Condutor(CondutorBase):
    num_carta_cond: str
    empresa: Optional[Empresa] = None

    model_config = {"from_attributes": True}


# ==========================
# VEÍCULO PESADO
# ==========================

class VeiculoBase(BaseModel):
    marca: Optional[str] = None


class VeiculoCreate(VeiculoBase):
    matricula: str


class Veiculo(VeiculoBase):
    matricula: str

    model_config = {"from_attributes": True}


# ==========================
# CONDUZ (Ligação condutor-veículo)
# ==========================

class ConduzBase(BaseModel):
    matricula_veiculo: str
    num_carta_cond: str
    inicio: datetime
    fim: Optional[datetime] = None


class Conduz(ConduzBase):
    veiculo: Optional[Veiculo]
    condutor: Optional[Condutor]

    model_config = {"from_attributes": True}



# ==========================
# CARGA
# ==========================

class CargaBase(BaseModel):
    peso: Decimal
    descricao: Optional[str] = None
    adr: bool = False
    tipo_carga: TipoCargaEnum
    estado_fisico: EstadoFisicoEnum
    unidade_medida: str = "Kg"


class CargaCreate(CargaBase):
    pass


class Carga(CargaBase):
    id_carga: int

    model_config = {"from_attributes": True}


# ==========================
# CAIS
# ==========================

class CaisBase(BaseModel):
    estado: EstadoEnum = EstadoEnum.operational
    capacidade_max: Optional[int] = None
    localizacao_gps: Optional[str] = None


class CaisCreate(CaisBase):
    pass


class Cais(CaisBase):
    id_cais: int

    model_config = {"from_attributes": True}


# ==========================
# GATE
# ==========================

class GateBase(BaseModel):
    nome: str
    estado: EstadoEnum = EstadoEnum.operational
    localizacao_gps: Optional[str] = None
    descricao: Optional[str] = None


class GateCreate(GateBase):
    pass


class Gate(GateBase):
    id_gate: int

    model_config = {"from_attributes": True}

# ==========================
# HISTÓRICO OCORRÊNCIAS
# ==========================

class HistoricoBase(BaseModel):
    id_turno: int
    hora_inicio: datetime
    hora_fim: Optional[datetime] = None
    descricao: Optional[str] = None


class HistoricoCreate(HistoricoBase):
    pass


class Historico(HistoricoBase):
    id_historico: int

    model_config = {"from_attributes": True}



# ==========================
# ALERTA
# ==========================

class AlertaBase(BaseModel):
    id_historico_ocorrencia: int
    id_carga: int
    tipo: Optional[str] = None
    severidade: Optional[int] = None
    descricao: Optional[str] = None


class AlertaCreate(AlertaBase):
    pass


class Alerta(AlertaBase):
    id_alerta: int
    data_hora: datetime

    class Config:
        from_attributes = True


# ==========================
# TURNO
# ==========================

class TurnoBase(BaseModel):
    """Base para turno"""
    num_operador_cancela: Optional[int] = None
    num_gestor_responsavel: Optional[int] = None
    id_gate: Optional[int] = None
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None
    descricao: Optional[str] = None


class TurnoCreate(TurnoBase):
    """Request para criar turno"""
    pass


class Turno(TurnoBase):
    """Modelo de turno"""
    id_turno: int

    model_config = {"from_attributes": True}

# ==========================
# CHEGADAS DIÁRIAS
# ==========================

class ChegadaBase(BaseModel):
    id_gate_entrada: int
    id_gate_saida: Optional[int] = None
    id_cais: int
    id_turno: Optional[int] = None  # Nullable - atribuído após chegada ser processada
    matricula_pesado: str
    id_carga: int
    data_prevista: Optional[date] = None
    hora_prevista: Optional[time] = None
    data_hora_chegada: Optional[datetime] = None
    observacoes: Optional[str] = None
    estado_entrega: EstadoEntregaEnum = EstadoEntregaEnum.in_transit


class ChegadaCreate(ChegadaBase):
    pass


class Chegada(ChegadaBase):
    id_chegada: int
    token_acesso: Optional[str] = None  # PIN gerado automaticamente
    cais: Optional[Cais]
    carga: Optional[Carga]
    veiculo: Optional[Veiculo]
    gate_entrada: Optional[Gate]
    gate_saida: Optional[Gate]
    turno: Optional[Turno]

    model_config = {"from_attributes": True}


# ==========================
# TRABALHADORES
# ==========================

class TrabalhadorBase(BaseModel):
    """Base para trabalhador"""
    nome: str
    email: str


class TrabalhadorCreate(TrabalhadorBase):
    """Request para criar trabalhador"""
    password: str


class Trabalhador(TrabalhadorBase):
    """Modelo de trabalhador para leitura"""
    num_trabalhador: int

    model_config = {"from_attributes": True}


class GestorInfo(BaseModel):
    """Informação de gestor"""
    num_trabalhador: int
    nome: str
    email: str
    nivel_acesso: str


class OperadorInfo(BaseModel):
    """Informação de operador"""
    num_trabalhador: int
    nome: str
    email: str


# ==========================
# WORKER AUTH
# ==========================

class WorkerLoginRequest(BaseModel):
    """Request de login para trabalhador"""
    email: str
    password: str


class WorkerLoginResponse(BaseModel):
    """Response de login com token"""
    token: str
    num_trabalhador: int
    nome: str
    email: str

# ==========================
# GESTOR
# ==========================

class Gestor(BaseModel):
    num_trabalhador: int
    nivel_acesso: NivelAcessoEnum = NivelAcessoEnum.basic

    model_config = {"from_attributes": True}


# ==========================
# OPERADOR
# ==========================

class Operador(BaseModel):
    num_trabalhador: int

    model_config = {"from_attributes": True}


# ==========================
# DRIVER APP (Mobile)
# ==========================

class DriverLoginRequest(BaseModel):
    """Request para login do motorista na app mobile"""
    num_carta_cond: str
    password: str


class DriverLoginResponse(BaseModel):
    """Response do login com JWT token"""
    token: str
    num_carta_cond: str
    nome: str
    id_empresa: int
    empresa_nome: str


class ClaimChegadaRequest(BaseModel):
    """Request para motorista usar PIN e associar-se à chegada"""
    token_acesso: str


class ClaimChegadaResponse(BaseModel):
    """Response com detalhes da entrega após claim"""
    id_chegada: int
    id_cais: int
    cais_localizacao: str
    matricula_veiculo: str
    carga_descricao: str
    carga_adr: bool
    navegacao_url: Optional[str] = None


# ==========================
# ARRIVAL UPDATE MODELS (Decision Engine)
# ==========================

class AlertPayload(BaseModel):
    """Payload para criação de alerta via Decision Engine"""
    tipo: str  # "ADR", "delay", "security", etc.
    severidade: int  # 1-5
    descricao: str


class ArrivalStatusUpdate(BaseModel):
    """Request para atualização manual de estado de chegada"""
    estado_entrega: str  # "in_transit", "delayed", "unloading", "completed"
    data_hora_chegada: Optional[datetime] = None
    id_gate_saida: Optional[int] = None
    observacoes: Optional[str] = None


class ArrivalDecisionUpdate(BaseModel):
    """
    Request do Decision Engine para atualizar chegada.
    Inclui decisão, estado e alertas opcionais (ADR, etc.)
    """
    decision: str  # "approved", "rejected", "manual_review"
    estado_entrega: str  # "unloading", "delayed", etc.
    data_hora_chegada: Optional[datetime] = None
    observacoes: Optional[str] = None
    alertas: Optional[List[AlertPayload]] = None


# ==========================
# DECISION ENGINE QUERY/RESPONSE
# ==========================

class DecisionCandidate(BaseModel):
    """Candidato retornado ao Decision Engine"""
    id_chegada: int
    matricula_pesado: str
    id_gate_entrada: int
    id_cais: int
    id_turno: int
    hora_prevista: Optional[str] = None
    estado_entrega: str
    carga_adr: bool
    carga_descricao: Optional[str] = None
    cais_localizacao: Optional[str] = None


class DecisionRequest(BaseModel):
    """
    Request do Decision Engine a perguntar sobre chegadas.
    Enviado após detecção de matrícula pelo Agent B.
    """
    matricula: str
    id_gate: int
    timestamp: datetime
    confidence: Optional[float] = None  # Confiança da detecção OCR


class DecisionResponse(BaseModel):
    """
    Response ao Decision Engine com chegadas candidatas.
    """
    found: bool
    candidates: List[DecisionCandidate]
    message: Optional[str] = None

from typing import Dict, Any

class EventResponse(BaseModel):
    """Response genérico para eventos."""
    id: Optional[str] = None
    type: str
    timestamp: Optional[datetime] = None
    gate_id: Optional[int] = None
    matricula: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
