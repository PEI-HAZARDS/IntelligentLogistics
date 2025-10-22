**Entidades principais**

# 1. Camião

Descrição: Representa cada veículo que entra no porto.

    Atributos:

        - Matrícula (PK)
        - Marca / Modelo
        - Estado atual (em espera, em descarga, saiu)
        - Tipo (cisterna, contentor, etc.)
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
        - Estado da entrega (entregue, em caminho, atrasada)
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
        - Tipo de cais (contentores, líquidos, sólidos, etc.)
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

    Relações:

        Pode gerar Alertas de risco se for ADR (FK) (?)

# 7. Operador

Descrição: funcionário ou sistema que autoriza e controla entradas.
    
    Atributos:

        - Nome
        - Número de trabalhador (PK)
        - Turno (Pode ser entidade)
        - Nível de acesso (normal / supervisor [Logistica geral])
        - Password

    Relações:

        Acompanha várias deteções (1:N) (?)
        Processa várias entregas diárias (1:N) (FKs)

# 8. Alerta (?)

Descrição: registo de eventos anómalos ou críticos durante a deteção ou entrada.

    Atributos:

        - ID (PK)
        - Tipo de alerta (erro de leitura, carga perigosa, matrícula desconhecida, etc.)
        - Mensagem / descrição
        - Data / hora
        - Nível de severidade [1-5] (?)

    Relações:

    Associado a uma Deteção/Entrega diária (N:1)
    Pode estar relacionado a um Camião e/ou Carga (1:1)

# 9. Empresa

Descrição: Entidade responsável pela entrega de cargas.

    Atributos:

        - ID/nif (PK)
        - Nome
        - Contacto
        - Descrição

    Relações:

        Possui associada vários condutores (1:N)


# 10. Turno

Descrição: Entidade responsável pela definição do turno.

    Atributos:

        - ID (PK)
        - HoraInicio
        - HoraFim
        - Descrição
        - Comentários/histórico de ocorrências

    Relações:

        Possui associada um operador (1:1)
        Possui registo das entradas diárias (1:N)



# Pequeno Fluxo:

[Empresa] 1 ────< tem >──── N [Condutor] 1 ────< conduz >──── N [Camião]

[Camião] 1 ────< realiza >──── N [Chegada_Diaria] ────< processada por >──── N [Operador]

[Chegada_Diaria] ────< refere >──── [Carga]
[Chegada_Diaria] ────< tem deteção associada >──── [Deteção]
[Chegada_Diaria] ────< encaminhada para >──── [Cais]
[Deteção] ────< gera >──── N [Alerta] (De segurança, chegada de entrega, etc.)

[Deteção] ────< validada por >──── [Operador/IA] (operador se necessário)
[Alerta] ────< refere >──── [Carga] (opcional)


princípios de normalização até à 3ª forma normal, para já