**Entidades principais**

# 1. Camião

Descrição: Representa cada veículo que entra no porto.

    Atributos:

        - Matrícula (PK)
        - Marca
        - Tipo_carroçaria (cisterna, contentor, etc.)
        - Condutor [carta condução] (FK) 

    Relações:

        Cada camião é conduzido por um Condutor (1:N)
        Pode ter várias Entradas no porto ao longo do tempo (1:N)
        Pode estar associado a várias entragas programadas (1:N)

# 2. Condutor

Descrição: Motorista responsável pelo camião.

    Atributos:

        - Nome
        - Nº Carta de Condução (PK)
        - Contacto

    Relações:

        Um condutor pode conduzir vários camiões (1:N)
        Um condutor pertence apenas a uma Empresa (1:1) (FK)

# 3.  Deteções (? Não relacional) -> (outra bd em mongo db para persitência de logs ajuda na manutenção) Aqui ficariam as deteções válidas

Descrição: Evento de deteção e registo da chegada de um camião ao porto.

    Atributos:

        - ID_deteção (PK)
        - Data e hora da deteção
        - Estado da autorização (pendente, autorizado, negado)
        - Origem da deteção (IA/manual)
        - Nível de confiança da deteção
        - Observações (alertas, condições, etc.)

    Relações:
        É retificada por um Operador (N:1) (sempre) (FK)


# 4. Chegadas_Diarias

Descrição: Entregas agendadas para cada dia.

    Atributos:

        - ID_gerado (PK)
        - Data esperada
        - hora esperada
        - Estado da entrega (concluida, em caminho, atrasada)
        - Estado atual de descarga (em espera, em descarga, concluido)
        - Observações (alertas, condições, etc.)

    Relações:

        É encaminhada para um Cais (N:1) (FK)
        Pode gerar Alertas (1:N) (FK)
        Referencia uma Carga (N:1) (FK)
        Está associada a um Condutor (N:1, via camião) -> (matricula (FK))
        É acompanhada por um Operador (N:1) (FK)
        Se a deteção IA corresponde a uma entrega prevista → ligas as duas.
        Se não houver correspondência → cria-se alerta automático.

# 5. Cais

Descrição: Zona física do porto onde o camião deve ir descarregar.

    Atributos:

        - Identificador (PK)
        - Localização exata (gps)
        - Capacidade máxima
        - Estado (ativo/inativo)

    Relações:

        Recebe várias Entradas (1:N) (FK)
        Associado às operações logísticas (?)

# 6. Carga

Descrição: tipo de mercadoria transportada pelo camião.

    Atributos:

        - ID (PK)
        - Tipo (ex: solido, liquido, gasoso)
        - Descrição
        - É perigosa? (ADR)
        - Peso

    Relações:

        Pode gerar Alertas de risco se for ADR (FK) (?)

# 7. Trabalhador_Porto

Descrição: Funcionário do porto.
    
    Atributos:

        - Número de trabalhador (PK)
        - Nome
        - email
        - Password

    Relações:
        - Classe base de Operador e de Gestor

# 8. Gestor (Classe filha de Trabalhador_Porto)

Descrição: Funcionário com acesso a registos e responsável pela logística e coordenação das operações do porto.
    
Atributos:

    - numero_trabalhador (PK, FK -> Trabalhador_Porto)
    - cargo (ex: ChefeLogistica, ...)
    - nivel_acesso (ex: admin, supervisor)
    - contacto

Relações:

    - Gere vários Operadores (1:N -> Operador)
    - Supervisiona Chegadas_Diarias / Operações (1:N)
    - Pode estar associado a vários Cais via tabela de atribuição (N:M -> Cais) usando uma tabela Gestor_Cais(se necessário)


# 9. Operador (Classe filha de Trabalhador_Porto)

Descrição: Funcionário responsável por validar/retificar deteções, autorizar entradas e acompanhar chegadas diárias.
    
Atributos:

    - numero_trabalhador (PK, FK -> Trabalhador_Porto.numero_trabalhador)
    - turno_id (FK -> Turno.id)

Relações:

    - Pertence a um Turno (N:1 -> Turno)
    - Processa múltiplas Deteções (1:N -> Deteções)
    - Acompanha/Processa Chegadas_Diarias (1:N -> Chegadas_Diarias)
    - É supervisionado por um Gestor (N:1 -> Gestor)


# 10. Alerta

Descrição: registo de eventos anómalos ou críticos durante a deteção ou entrada.

    Atributos:

        - ID (PK)
        - Tipo de alerta (erro de leitura, carga perigosa, matrícula desconhecida, etc.)
        - Mensagem / descrição
        - Data
        - hora
        - Nível de severidade [1-5]
        - Comentário

    Relações:

    Associado a uma Deteção/Entrega diária (N:1)
    Pode estar relacionado a um Camião e/ou Carga (1:1)

# 11. Empresa

Descrição: Entidade responsável pela entrega de cargas.

    Atributos:

        - ID/nif (PK)
        - Nome
        - Contacto
        - Descrição

    Relações:

        Possui associada vários condutores (1:N)


# 12. Turno

Descrição: Entidade responsável pela definição do turno.

    Atributos:

        - ID (PK)
        - HoraInicio
        - HoraFim
        - Descrição

    Relações:

        Está associado a um histórico (1:1)
        Possui associada um operador (1:1)
        Possui registo das entradas diárias (1:N)


# 13. Histórico de Ocorrências

Descrição: Entidade responsável por agregar ocorrências de um turno.

    Atributos:

        - ID (PK)
        - Data
        - Hora
        - Descrição 
        - Operador (FK)
        - Gestor_responsável (FK)

    Relações:

        Possui associado um gestor (1:1)
        Possui associado um operador (1:1)
        Possui registo dos alertas diárias (1:N)

**Tabela de Relações e Cardinalidade**

| Entidade A          | Relação                                 | Entidade B                           | Cardinalidade (A:B) |
|--------------------|----------------------------------------|-------------------------------------|----------------------|
| Trabalhador_Porto  | superclasse de                          | Operador                             |              |
| Trabalhador_Porto  | superclasse de                          | Gestor                               |               |
|  Gestor             | supervisiona                            | Turno                             | 1:N                  |
| *Gestor             |         gere                            | Cais                             | 1:N                  |
| Condutor           | conduz                                   | Camião                               | 1:N                  |
| Camião             | associado                             | Chegadas_Diarias                     | 1:N                  |
| Chegadas_Diarias   | encaminhada                        | Cais                                 | N:1                  |
| Chegadas_Diarias   | gera                                | Alerta                               | 1:N                  |
| Chegadas_Diarias   | referencia                                | Carga                                | N:1                  |
| Chegadas_Diarias   | acompanhada                        | Operador                             | N:1                  |
| Carga              | gera                                | Alerta                               | 1:N                  |
| Operador           | valida                         | Alerta                              | 1:N                  |
| Operador           | processa                                  | Chegadas_Diarias                     | 1:N                  |
| Alerta             | está associado a                          | Deteções / Chegadas_Diarias          | N:1                  |
| Alerta             | pode referir                              | Camião                               | 0..1:1               |
| Alerta             | pode referir                              | Carga                                | 0..1:1               |
| Empresa            | emprega                                  | Condutor                             | 1:N                  |
| Turno              | agrupa                                    | Operador                             | 1:N                  |

princípios de normalização até à 3ª forma normal, para já