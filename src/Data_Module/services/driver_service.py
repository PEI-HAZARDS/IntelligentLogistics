from typing import List
from sqlalchemy.orm import Session
from models.sql_models import Condutor, Conduz, ChegadaDiaria

def get_drivers(db: Session) -> List[Condutor]:
    """
    Retorna todos os condutores.
    """
    return db.query(Condutor).all()

def get_driver_arrivals(db: Session, driver_id) -> List[ChegadaDiaria]:
    """
    Retorna chegadas associadas a um condutor.
    - driver_id pode ser int ou str (converte internamente).
    Lógica:
      1) busca as matrículas (veículos) que o condutor conduziu na tabela Conduz
      2) busca chegadas na tabela ChegadaDiaria onde matricula_pesado IN (essas matrículas)
    """
    # garantir que o id é string (coluna num_carta_cond é texto)
    driver_key = str(driver_id)

    # 1) obter matrículas associadas ao condutor
    rows = db.query(Conduz.matricula_veiculo).filter(Conduz.num_carta_cond == driver_key).distinct().all()
    vehicles = [r[0] for r in rows if r and r[0] is not None]

    if not vehicles:
        return []

    # 2) buscar chegadas correspondentes (ordenar por data_hora_chegada desc)
    query = db.query(ChegadaDiaria).filter(ChegadaDiaria.matricula_pesado.in_(vehicles)).order_by(ChegadaDiaria.data_hora_chegada.desc())
    return query.limit(50).all()
