#!/usr/bin/env python3
"""
Data initializer for MVP.
Run with PYTHONPATH=src python src/Data_Module/scripts/data_initializer.py
"""

from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import os
import random
import sys
import os

# Add parent directory to path so we can import models
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Tentar importar os modelos pelo caminho do pacote (assumindo PYTHONPATH inclui `src`)
try:
    from Data_Module.models.sql_models import (
        Base, TrabalhadorPorto, Gestor, Operador, Empresa, Condutor,
        VeiculoPesado, Conduz, Carga, Cais, Turno, ChegadaDiaria,
        HistoricoOcorrencias, Alerta, Gate, TipoTurno
    )
except Exception:
    # Fallback para execução direta
    try:
        from models.sql_models import (
            Base, TrabalhadorPorto, Gestor, Operador, Empresa, Condutor,
            VeiculoPesado, Conduz, Carga, Cais, Turno, ChegadaDiaria,
            HistoricoOcorrencias, Alerta, Gate, TipoTurno
        )
    except Exception as e:
        print("Erro ao importar modelos:", e)
        print("Certifique-se que o PYTHONPATH inclui a pasta `src` ou execute a partir da raiz do repositório.")
        sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_data(db: Session):
    """
    Inicializar a base de dados com dados fictícios para MVP.
    Função idempotente para uso em desenvolvimento/demo.
    """
    print("Populating database with initial data...")

    # Check if data already exists
    if db.query(TrabalhadorPorto).first():
        print("Data already exists. Skipping initialization.")
        return

    try:
        # ===== TRABALHADORES =====
        print("Creating workers...")

        # Gestor
        gestor1 = TrabalhadorPorto(
            nome="João Silva",
            email="joao.silva@porto.pt",
            password_hash=pwd_context.hash("password123"),
            role="manager",
            ativo=True
        )

        # Operador
        operador1 = TrabalhadorPorto(
            nome="Carlos Oliveira",
            email="carlos.oliveira@porto.pt",
            password_hash=pwd_context.hash("password123"),
            role="operator",
            ativo=True
        )

        db.add_all([gestor1, operador1])
        db.flush()

        # Criar registos de gestor e operador
        gestor_obj1 = Gestor(num_trabalhador=gestor1.num_trabalhador, nivel_acesso="admin")
        operador_obj1 = Operador(num_trabalhador=operador1.num_trabalhador)

        db.add_all([gestor_obj1, operador_obj1])
        db.flush()

        # ===== EMPRESAS =====
        print("Creating companies...")

        empresas = [
            Empresa(nome="TransPortugal Lda", nif="500123456", contacto="220123456", descricao="Transportes nacionais"),
            Empresa(nome="EuroCargas SA", nif="500234567", contacto="220234567", descricao="Transportes internacionais"),
            Empresa(nome="LogísticaPro", nif="500345678", contacto="220345678", descricao="Logística e distribuição"),
            Empresa(nome="CargoExpress", nif="500456789", contacto="220456789", descricao="Entregas expressas"),
            Empresa(nome="MegaTrans", nif="500567890", contacto="220567890", descricao="Transportes pesados"),
        ]
        db.add_all(empresas)
        db.flush()

        # ===== CONDUTORES =====
        print("Creating drivers...")

        condutores = [
            Condutor(num_carta_cond="PT12345678", nome="Rui Almeida", contacto="912345678", id_empresa=empresas[0].id_empresa),
            Condutor(num_carta_cond="PT23456789", nome="Sofia Rodrigues", contacto="913456789", id_empresa=empresas[0].id_empresa),
            Condutor(num_carta_cond="PT34567890", nome="Miguel Teixeira", contacto="914567890", id_empresa=empresas[1].id_empresa),
            Condutor(num_carta_cond="PT45678901", nome="Rita Pereira", contacto="915678901", id_empresa=empresas[1].id_empresa),
            Condutor(num_carta_cond="PT56789012", nome="Bruno Sousa", contacto="916789012", id_empresa=empresas[2].id_empresa),
            Condutor(num_carta_cond="PT67890123", nome="Carla Mendes", contacto="917890123", id_empresa=empresas[2].id_empresa),
            Condutor(num_carta_cond="PT78901234", nome="Nuno Dias", contacto="918901234", id_empresa=empresas[3].id_empresa),
            Condutor(num_carta_cond="PT89012345", nome="Patrícia Lima", contacto="919012345", id_empresa=empresas[3].id_empresa),
            Condutor(num_carta_cond="PT90123456", nome="Tiago Martins", contacto="920123456", id_empresa=empresas[4].id_empresa),
            Condutor(num_carta_cond="PT01234567", nome="Vera Castro", contacto="921234567", id_empresa=empresas[4].id_empresa),
            Condutor(num_carta_cond="PT11223344", nome="André Soares", contacto="922345678", id_empresa=empresas[0].id_empresa),
            Condutor(num_carta_cond="PT22334455", nome="Beatriz Gomes", contacto="923456789", id_empresa=empresas[1].id_empresa),
        ]
        
        # Adicionar passwords de teste para app mobile
        print("Adding test passwords for drivers...")
        for condutor in condutores:
            condutor.password_hash = pwd_context.hash("driver123")
            condutor.ativo = True
        
        db.add_all(condutores)
        db.flush()

        # ===== VEÍCULOS =====
        print("Creating vehicles...")

        marcas = ["Volvo", "Scania", "Mercedes", "MAN", "Iveco", "DAF"]
        veiculos = []
        matriculas = ["AA-11-BB", "CC-22-DD", "EE-33-FF", "GG-44-HH", "II-55-JJ",
                      "KK-66-LL", "MM-77-NN", "OO-88-PP", "QQ-99-RR", "SS-00-TT",
                      "UU-12-VV", "WW-34-XX", "YY-56-ZZ", "AB-78-CD", "EF-90-GH",
                      "IJ-12-KL", "MN-34-OP", "QR-56-ST"]

        for mat in matriculas:
            veiculos.append(VeiculoPesado(matricula=mat, marca=random.choice(marcas)))

        db.add_all(veiculos)
        db.flush()

        # ===== CONDUZ (Associações condutor-veículo) =====
        print("Creating driver-vehicle associations...")

        hoje_dt = datetime.now()
        conducoes = []
        for i, condutor in enumerate(condutores):
            veiculo_idx = i % len(veiculos)
            conducoes.append(Conduz(
                matricula_veiculo=veiculos[veiculo_idx].matricula,
                num_carta_cond=condutor.num_carta_cond,
                inicio=hoje_dt - timedelta(days=random.randint(30, 365)),
                fim=None
            ))

        db.add_all(conducoes)
        db.flush()

        # ===== CARGAS =====
        print("Creating cargos...")

        cargas = []

        cargas_perigosas = [
            {"desc": "Ácido sulfúrico (H2SO4)", "peso": 15000, "tipo": "hazardous", "estado": "liquid", "adr": True},
            {"desc": "Gás propano comprimido", "peso": 8000, "tipo": "hazardous", "estado": "gaseous", "adr": True},
            {"desc": "Produtos químicos inflamáveis", "peso": 12000, "tipo": "hazardous", "estado": "liquid", "adr": True},
            {"desc": "Refrigerado - Carne congelada", "peso": 18000, "tipo": "refrigerated", "estado": "solid", "adr": False},
            {"desc": "Refrigerado - Produtos farmacêuticos", "peso": 5000, "tipo": "refrigerated", "estado": "solid", "adr": False},
            {"desc": "Carga viva - Gado bovino", "peso": 6000, "tipo": "live", "estado": "solid", "adr": False},
            {"desc": "Carga viva - Aves de capoeira", "peso": 3000, "tipo": "live", "estado": "solid", "adr": False},
            {"desc": "A granel - Cereais (trigo)", "peso": 22000, "tipo": "bulk", "estado": "solid", "adr": False},
            {"desc": "A granel - Areia industrial", "peso": 25000, "tipo": "bulk", "estado": "solid", "adr": False},
            {"desc": "Geral - Peças automóveis", "peso": 8000, "tipo": "general", "estado": "solid", "adr": False},
            {"desc": "Geral - Material eletrónico", "peso": 5500, "tipo": "general", "estado": "solid", "adr": False},
            {"desc": "Mistura de fertilizantes (orgânicos + minerais)", "peso": 7000, "tipo": "bulk", "estado": "hybrid", "adr": False},
        ]

        for cp in cargas_perigosas:
            cargas.append(Carga(
                peso=Decimal(cp["peso"]),
                descricao=cp["desc"],
                adr=True,
                tipo_carga="hazardous",
                estado_fisico=cp["estado"],
                unidade_medida="Kg"
            ))

        cargas_refrigeradas = [
            {"desc": "Carne congelada", "peso": 18000},
            {"desc": "Produtos farmacêuticos", "peso": 5000},
            {"desc": "Peixe fresco", "peso": 12000},
            {"desc": "Frutas e vegetais", "peso": 15000},
            {"desc": "Produtos lácteos", "peso": 8000},
        ]

        for cr in cargas_refrigeradas:
            cargas.append(Carga(
                peso=Decimal(cr["peso"]),
                descricao=cr["desc"],
                adr=False,
                tipo_carga="refrigerated",
                estado_fisico="solid",
                unidade_medida="Kg"
            ))

        cargas.append(Carga(
            peso=Decimal(6000),
            descricao="Gado bovino",
            adr=False,
            tipo_carga="live",
            estado_fisico="solid",
            unidade_medida="Kg"
        ))
        cargas.append(Carga(
            peso=Decimal(3000),
            descricao="Aves de capoeira",
            adr=False,
            tipo_carga="live",
            estado_fisico="solid",
            unidade_medida="Kg"
        ))

        cargas_granel = [
            {"desc": "Cereais (trigo)", "peso": 22000},
            {"desc": "Areia industrial", "peso": 25000},
            {"desc": "Sal grosso", "peso": 20000},
            {"desc": "Farinha de milho", "peso": 18000},
            {"desc": "Açúcar a granel", "peso": 21000},
        ]

        for cg in cargas_granel:
            cargas.append(Carga(
                peso=Decimal(cg["peso"]),
                descricao=cg["desc"],
                adr=False,
                tipo_carga="bulk",
                estado_fisico="solid",
                unidade_medida="Kg"
            ))

        cargas_gerais = [
            {"desc": "Peças automóveis", "peso": 8000},
            {"desc": "Electrodomésticos", "peso": 12000},
            {"desc": "Mobiliário", "peso": 9000},
            {"desc": "Material de construção", "peso": 16000},
            {"desc": "Produtos têxteis", "peso": 6000},
            {"desc": "Maquinaria industrial", "peso": 19000},
            {"desc": "Papel e cartão", "peso": 11000},
            {"desc": "Produtos de plástico", "peso": 7500},
            {"desc": "Material eletrónico", "peso": 5500},
            {"desc": "Ferramentas industriais", "peso": 13000},
        ]

        for cg in cargas_gerais:
            cargas.append(Carga(
                peso=Decimal(cg["peso"]),
                descricao=cg["desc"],
                adr=False,
                tipo_carga="general",
                estado_fisico="solid",
                unidade_medida="Kg"
            ))

        db.add_all(cargas)
        db.flush()

        # ===== CAIS =====
        print("Creating Docks...")

        cais_list = []
        for i in range(1, 6):
            cais_list.append(Cais(
                estado="operational",
                capacidade_max=random.randint(8, 12),
                localizacao_gps=f"41.{140 + i}23N, 8.{610 + i}45W"
            ))

        db.add_all(cais_list)
        db.flush()

        # ===== GATE =====
        print("Creating 1 gate...")

        gate = Gate(
            nome="Gate Principal",
            estado="operational",
            localizacao_gps="41.1510N, 8.6210W",
            descricao="Portão principal de entrada e saída"
        )

        db.add(gate)
        db.flush()

        # ===== TURNO =====
        print("Creating 1 shift...")

        hoje = date.today()

        turno = Turno(
            tipo_turno=TipoTurno.MANHA,
            data=hoje,
            num_operador_cancela=operador1.num_trabalhador,
            num_gestor_responsavel=gestor1.num_trabalhador,
            id_gate=gate.id_gate,
            hora_inicio=time(6, 0),
            hora_fim=time(14, 0)
        )

        db.add(turno)
        db.flush()

        # ===== CHEGADAS DIÁRIAS =====
        print("📅 Creating 33 daily arrivals with varied states...")

        horarios = [
            time(6, 30), time(7, 0), time(7, 45), time(8, 20), time(9, 0),
            time(9, 40), time(10, 15), time(11, 0), time(11, 30), time(12, 15),
            time(13, 0), time(13, 45), time(14, 30), time(15, 0), time(15, 45),
            time(16, 20), time(17, 0), time(17, 40), time(18, 15), time(19, 0),
            time(19, 45), time(20, 30), time(21, 0), time(21, 45), time(22, 30),
            time(23, 0), time(23, 30), time(0, 15), time(1, 0), time(2, 0),
            time(3, 0), time(4, 0), time(5, 0)
        ]

        distribuicao_estados = (
            ["in_transit"] * 13 +
            ["delayed"] * 3 +
            ["unloading"] * 10 +
            ["completed"] * 7
        )
        random.shuffle(distribuicao_estados)

        chegadas = []
        for i in range(33):
            hora_prevista = horarios[i]
            minutos_variacao = random.randint(-20, 90)
            hora_chegada = datetime.combine(hoje, hora_prevista) + timedelta(minutes=minutos_variacao)

            estado = distribuicao_estados[i]

            gate_saida = None
            data_hora_chegada = None

            if estado == "completed":
                gate_saida = gate.id_gate
                data_hora_chegada = hora_chegada
            elif estado in ["unloading", "delayed"]:
                data_hora_chegada = hora_chegada

            observacoes_opcoes = [
                "Entrega normal",
                "Carga frágil - manusear com cuidado",
                "Documentação completa verificada",
                "Requer inspeção adicional",
                "Cliente prioritário",
                "Verificar temperatura da carga",
                "Documentação ADR em ordem",
                "Entrega urgente",
                "Primeira entrega da empresa",
                "Carga de alto valor",
            ]

            chegadas.append(ChegadaDiaria(
                id_gate_entrada=gate.id_gate,
                id_gate_saida=gate_saida,
                id_cais=random.choice(cais_list).id_cais,
                id_turno=turno.id_turno,
                matricula_pesado=random.choice(veiculos).matricula,
                id_carga=cargas[i % len(cargas)].id_carga,
                data_prevista=hoje,
                hora_prevista=hora_prevista,
                data_hora_chegada=data_hora_chegada,
                observacoes=random.choice(observacoes_opcoes),
                estado_entrega=estado
            ))

        db.add_all(chegadas)
        db.flush()
        
        # ===== GERAR PINs DE ACESSO =====
        print("Generating access PINs for arrivals...")
        for i, chegada in enumerate(chegadas):
            # Gera PIN simples: PRT-XXXX (4 dígitos)
            pin = f"PRT-{str(i+1).zfill(4)}"
            chegada.pin_acesso = pin
        
        db.flush()

        # ===== HISTÓRICO OCORRÊNCIAS =====
        print("Creating occurrence history...")

        ocorrencias = [
            HistoricoOcorrencias(
                id_turno=turno.id_turno,
                hora_inicio=datetime.combine(hoje, time(8, 30)),
                hora_fim=datetime.combine(hoje, time(9, 15)),
                descricao="Congestionamento na entrada"
            ),
            HistoricoOcorrencias(
                id_turno=turno.id_turno,
                hora_inicio=datetime.combine(hoje, time(11, 0)),
                hora_fim=datetime.combine(hoje, time(11, 45)),
                descricao="Inspeção de carga perigosa - ADR"
            ),
            HistoricoOcorrencias(
                id_turno=turno.id_turno,
                hora_inicio=datetime.combine(hoje, time(12, 30)),
                hora_fim=datetime.combine(hoje, time(13, 15)),
                descricao="Verificação de documentação aduaneira"
            ),
        ]

        db.add_all(ocorrencias)
        db.flush()

        # ===== ALERTAS =====
        print("Creating alerts...")

        alertas = [
            Alerta(
                id_historico_ocorrencia=ocorrencias[0].id_historico,
                id_carga=cargas[0].id_carga,
                severidade=3,
                descricao="Carga perigosa (ácido) - verificar contenção",
                data_hora=datetime.now() - timedelta(hours=4)
            ),
            Alerta(
                id_historico_ocorrencia=ocorrencias[1].id_historico,
                id_carga=cargas[1].id_carga,
                severidade=4,
                descricao="Gás comprimido - inspeção obrigatória ADR",
                data_hora=datetime.now() - timedelta(hours=3)
            ),
            Alerta(
                id_historico_ocorrencia=ocorrencias[1].id_historico,
                id_carga=cargas[8].id_carga,
                severidade=3,
                descricao="Temperatura fora dos parâmetros - carga refrigerada",
                data_hora=datetime.now() - timedelta(hours=2)
            ),
            Alerta(
                id_historico_ocorrencia=ocorrencias[2].id_historico,
                id_carga=cargas[3].id_carga,
                severidade=2,
                descricao="Documentação ADR incompleta - aguardando correção",
                data_hora=datetime.now() - timedelta(hours=1)
            ),
            Alerta(
                id_historico_ocorrencia=ocorrencias[1].id_historico,
                id_carga=cargas[5].id_carga,
                severidade=4,
                descricao="Combustível diesel - verificar licenças de transporte",
                data_hora=datetime.now() - timedelta(minutes=45)
            ),
        ]

        db.add_all(alertas)
        db.flush()

        # ===== COMMIT =====
        print("[Saving data to the database...]")
        db.commit()

        print("Database initialized successfully!")
        print(f"""
Summary:
- Workers: 2 (1 manager, 1 operator)
- Companies: {len(empresas)}
- Drivers: {len(condutores)} (all with password: driver123)
- Vehicles: {len(veiculos)}
- Loads: {len(cargas)} (8 hazardous, 5 refrigerated, 2 live, 5 bulk, 10 general)
- Docks: 5
- Gates: 1
- Shifts: 1 (morning 06:00-14:00)
- Arrivals (today): {len(chegadas)} (all with PIN: PRT-0001 to PRT-0033)
  · In transit: {distribuicao_estados.count('in_transit')}
  · Delayed: {distribuicao_estados.count('delayed')}
  · Unloading: {distribuicao_estados.count('unloading')}
  · Completed: {distribuicao_estados.count('completed')}
- Occurrences: {len(ocorrencias)}
- Alerts: {len(alertas)} (focus on hazardous loads)

Test credentials:

Web Portal:
Email: joao.silva@porto.pt | Password: password123 (Manager)
Email: carlos.oliveira@porto.pt | Password: password123 (Operator)

Mobile App (Drivers):
Any driver license: PT12345678, PT23456789, etc.
Password: driver123
Test PIN: PRT-0001 (First delivery)
""")
    except Exception as e:
        print("!!! Error during initialization:", e)
        db.rollback()
        raise

def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    # Cria tabelas caso não existam
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_data(db)
    finally:
        db.close()

if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://user:password@localhost/porto_db"
    print("Usando DATABASE_URL =", DATABASE_URL)
    create_and_seed(DATABASE_URL)