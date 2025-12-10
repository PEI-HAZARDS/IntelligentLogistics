from datetime import datetime
from sqlalchemy import func
from sqlalchemy import Column, Integer, String, Date, Time, TIMESTAMP, DECIMAL, Boolean, ForeignKey, Text, Enum as SEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

# ENUMs traduzidos
estado_entrega_enum = SEnum('in_transit', 'delayed', 'unloading', 'completed', name='delivery_status')
tipo_carga_enum = SEnum('general', 'hazardous', 'refrigerated', 'live', 'bulk', name='cargo_type')
estado_fisico_enum = SEnum('liquid', 'solid', 'gaseous', 'hybrid', name='physical_state')
nivel_acesso_enum = SEnum('admin', 'basic', name='access_level')
estado_enum = SEnum('maintenance', 'operational', 'closed', name='operational_status')
tipo_trabalhador_enum = SEnum('manager', 'operator', name='worker_type')

class TipoTurno(SEnum):
    MANHA = "06:00-14:00"
    TARDE = "14:00-22:00"
    NOITE = "22:00-06:00"

    def get_horarios(self):
        """Converte as strings do enum para objetos time."""
        ini_str, fim_str = self.value.split("-")
        hora_inicio = datetime.strptime(ini_str, "%H:%M").time()
        hora_fim = datetime.strptime(fim_str, "%H:%M").time()
        return hora_inicio, hora_fim

# Tabelas
class TrabalhadorPorto(Base):
    __tablename__ = "trabalhador_porto"
    num_trabalhador = Column(Integer, primary_key=True)
    nome = Column(Text, nullable=False)
    email = Column(Text, unique=True)
    password_hash = Column(Text)
    role = Column(tipo_trabalhador_enum, nullable=False)

    gestor = relationship("Gestor", back_populates="trabalhador", uselist=False)
    operador = relationship("Operador", back_populates="trabalhador", uselist=False)

class Gestor(Base):
    __tablename__ = "gestor"
    num_trabalhador = Column(Integer, ForeignKey('trabalhador_porto.num_trabalhador'), primary_key=True)
    nivel_acesso = Column(nivel_acesso_enum, default='basic')
    trabalhador = relationship("TrabalhadorPorto", back_populates="gestor")

class Operador(Base):
    __tablename__ = "operador"
    num_trabalhador = Column(Integer, ForeignKey('trabalhador_porto.num_trabalhador'), primary_key=True)
    trabalhador = relationship("TrabalhadorPorto", back_populates="operador")

class Empresa(Base):
    __tablename__ = "empresa"
    id_empresa = Column(Integer, primary_key=True)
    nome = Column(Text, nullable=False)
    nif = Column(Text, unique=True)
    contacto = Column(Text)
    descricao = Column(Text)

class Condutor(Base):
    __tablename__ = "condutor"
    num_carta_cond = Column(Text, primary_key=True)
    id_empresa = Column(Integer, ForeignKey('empresa.id_empresa'))
    nome = Column(Text, nullable=False)
    contacto = Column(Text)
    
    # Autenticação para app mobile
    password_hash = Column(Text)
    
    empresa = relationship("Empresa")

class VeiculoPesado(Base):
    __tablename__ = "veiculo_pesado"
    matricula = Column(Text, primary_key=True)
    marca = Column(Text)

class Conduz(Base):
    __tablename__ = "conduz"
    matricula_veiculo = Column(Text, ForeignKey('veiculo_pesado.matricula'), primary_key=True)
    num_carta_cond = Column(Text, ForeignKey('condutor.num_carta_cond'), primary_key=True)
    inicio = Column(TIMESTAMP, primary_key=True)
    fim = Column(TIMESTAMP)
    veiculo = relationship("VeiculoPesado")
    condutor = relationship("Condutor")

class Carga(Base):
    __tablename__ = "carga"
    id_carga = Column(Integer, primary_key=True)
    peso = Column(DECIMAL(10,2), nullable=False)
    descricao = Column(Text)
    adr = Column(Boolean, default=False)
    tipo_carga = Column(tipo_carga_enum, nullable=False)
    estado_fisico = Column(estado_fisico_enum, nullable=False)
    unidade_medida = Column(String(10), default='Kg')

class Cais(Base):
    __tablename__ = "cais"
    id_cais = Column(Integer, primary_key=True)
    estado = Column(estado_enum, default='operational')
    capacidade_max = Column(Integer)
    localizacao_gps = Column(Text)

class Turno(Base):
    __tablename__ = "turno"

    id_turno = Column(Integer, primary_key=True)

    tipo_turno = Column(SEnum(TipoTurno), nullable=False)

    num_operador_cancela = Column(Integer, ForeignKey('operador.num_trabalhador'))
    num_gestor_responsavel = Column(Integer, ForeignKey('gestor.num_trabalhador'))
    id_gate = Column(Integer, ForeignKey('gate.id_gate'))

    hora_inicio = Column(Time, nullable=False)
    hora_fim = Column(Time, nullable=False)
    data = Column(Date, nullable=False)

    operador = relationship("Operador")
    gestor = relationship("Gestor")
    gate = relationship("Gate")
    chegadas = relationship("ChegadaDiaria", backref="turno")
    historicos = relationship("HistoricoOcorrencias", backref="turno")

    def __init__(self, tipo_turno: TipoTurno, data, **kwargs):
        """Inicia o turno definindo nas horas com base no enum."""
        self.tipo_turno = tipo_turno
        self.data = data

        # Obtém horários do enum automaticamente
        inicio, fim = tipo_turno.get_horarios()
        self.hora_inicio = inicio
        self.hora_fim = fim

        # Atribui outros campos normais
        for key, value in kwargs.items():
            setattr(self, key, value)

class ChegadaDiaria(Base):
    __tablename__ = "chegadas_diarias"
    id_chegada = Column(Integer, primary_key=True)
    id_gate_entrada = Column(Integer, ForeignKey('gate.id_gate'))
    id_gate_saida = Column(Integer, ForeignKey('gate.id_gate'), nullable=True)
    id_cais = Column(Integer, ForeignKey('cais.id_cais'))
    id_turno = Column(Integer, ForeignKey('turno.id_turno'))
    matricula_pesado = Column(Text, ForeignKey('veiculo_pesado.matricula'))
    id_carga = Column(Integer, ForeignKey('carga.id_carga'))
    data_prevista = Column(Date)
    hora_prevista = Column(Time)
    data_hora_chegada = Column(TIMESTAMP)
    observacoes = Column(Text)
    estado_entrega = Column(estado_entrega_enum, default='in_transit')
    
    # PIN para app mobile do motorista
    pin_acesso = Column(String(12), unique=True, index=True)

    cais = relationship("Cais")
    carga = relationship("Carga")
    veiculo = relationship("VeiculoPesado")
    
    gate_entrada = relationship(
        "Gate",
        foreign_keys=[id_gate_entrada],
        back_populates="chegadas_entrada"
    )

    gate_saida = relationship(
        "Gate",
        foreign_keys=[id_gate_saida],
        back_populates="chegadas_saida"
    )

class HistoricoOcorrencias(Base):
    __tablename__ = "historico_ocorrencias"
    id_historico = Column(Integer, primary_key=True)
    id_turno = Column(Integer, ForeignKey('turno.id_turno'))
    hora_inicio = Column(TIMESTAMP)
    hora_fim = Column(TIMESTAMP)
    descricao = Column(Text)
    turno = relationship("Turno")

class Alerta(Base):
    __tablename__ = "alerta"
    id_alerta = Column(Integer, primary_key=True)
    id_historico_ocorrencia = Column(Integer, ForeignKey('historico_ocorrencias.id_historico'))
    id_carga = Column(Integer, ForeignKey('carga.id_carga'))
    data_hora = Column(TIMESTAMP, server_default=func.now())

    url_imagem = Column(Text)
    severidade = Column(Integer)
    descricao = Column(Text)

    historico = relationship("HistoricoOcorrencias")
    carga = relationship("Carga")

class Gate(Base):
    __tablename__ = "gate"
    id_gate = Column(Integer, primary_key=True)
    nome = Column(Text, nullable=False)
    estado = Column(estado_enum, default='operational')
    localizacao_gps = Column(Text)
    descricao = Column(Text)

    chegadas_entrada = relationship(
        "ChegadaDiaria",
        foreign_keys="ChegadaDiaria.id_gate_entrada",
        back_populates="gate_entrada"
    )

    chegadas_saida = relationship(
        "ChegadaDiaria",
        foreign_keys="ChegadaDiaria.id_gate_saida",
        back_populates="gate_saida"
    )
