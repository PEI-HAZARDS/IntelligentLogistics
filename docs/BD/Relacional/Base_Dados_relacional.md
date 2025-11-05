# Modelo Base de Dados — Intelligent Logistics (Base de Dados Relacional)

## Objetivo
Representar a base de dados central do **Porto Inteligente**, usada pelo backend (FastAPI/Flask) para gerir camiões, cargas, deteções, operadores e operações logísticas.  
Complementa-se futuramente com uma base de dados **não relacional (MongoDB)** para persistência e análise de logs de deteção.

---

## Normalização
O modelo foi estruturado até à **3ª Forma Normal (3FN)**:

| Forma Normal | Condição Cumprida |
|---------------|------------------|
| **1FN** | Todos os atributos são atómicos |
| **2FN** | Todos os atributos dependem da chave primária completa |
| **3FN** | Não há dependências transitivas entre atributos não-chave |
| **Relações M:N** | Resolvidas com tabelas intermédias |
| **Herança (Gestor/Operador)** | Implementada via chave estrangeira (FK) para Trabalhador_Porto |

---

## Entidades Principais

### **EMPRESA**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_empresa | SERIAL | PK | Identificador único |
| nome | VARCHAR |  | Nome da empresa |
| nif | VARCHAR(20) | UNIQUE | Número fiscal |
| contacto | VARCHAR |  | Telefone/email |
| descricao | TEXT |  | Observações gerais |

**Relações:**
- 1:N com **Condutor**

---

### **CONDUTOR**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| num_carta | VARCHAR(20) | PK | Nº da carta de condução |
| nome | VARCHAR |  | Nome completo |
| contacto | VARCHAR |  | Telefone  |
| id_empresa | INT | FK → Empresa.id_empresa | Empresa empregadora |

**Relações:**
- 1:N com **Camião**  
- N:M com **Camião** via tabela `Condutor_Camiao`

---

### **CAMIÃO**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| matricula | VARCHAR(15) | PK | Matrícula única |
| marca | VARCHAR |  | Marca |
| tipo_carrocaria | VARCHAR |  | Tipo (cisterna, contentor, etc.) |

**Relações:**
- N:M com **Condutor** via `Condutor_Camiao`
- 1:N com **Chegadas_Diarias**

---

### **CONDUTOR_CAMIAO**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_condutor | VARCHAR(20) | FK → Condutor.num_carta | Condutor |
| matricula | VARCHAR(15) | FK → Camiao.matricula | Camião |
| data_inicio | DATE |  | Início da afetação |
| data_fim | DATE |  | Fim da afetação |

Tabela de associação M:N entre Condutor e Camião, com histórico.

---

### **CARGA**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_carga | SERIAL | PK | Identificador |
| tipo | VARCHAR |  | Sólido, líquido, gasoso |
| descricao | TEXT |  | Detalhes da carga |
| adr | BOOLEAN |  | É perigosa (ADR)? |
| peso | DECIMAL(10,2) |  | Peso total (kg) |

**Relações:**
- 1:N com **Alerta**

---

### **CAIS**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_cais | SERIAL | PK | Identificador |
| localizacao | VARCHAR |  | Localização/GPS |
| capacidade_max | INT |  | Capacidade máxima |
| estado | VARCHAR |  | Ativo / Inativo |

---

### **TRABALHADOR_PORTO**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| num_trabalhador | SERIAL | PK | Identificador |
| nome | VARCHAR |  | Nome |
| email | VARCHAR | UNIQUE | Email institucional |
| password | VARCHAR |  | Palavra-passe |

Superclasse de **Gestor** e **Operador**

---

### **GESTOR**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| num_trabalhador | INT | PK, FK → Trabalhador_Porto | Identificador |
| nivel_acesso | VARCHAR |  | Gestor Logistico / supervisor |
| contacto | VARCHAR |  | Telefone/email |

**Relações:**
- 1:N → Turno  
---

### **TURNO**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_turno | SERIAL | PK | Identificador |
| id_gestor| SERIAL | FK | Responsável | 
| id_operador | INT | FK → operador.num_trabalhador | Operador responsável pela cancela|
| hora_inicio | TIME |  | Início |
| hora_fim | TIME |  | Fim |
| descricao | TEXT |  | Observações |

---

### **OPERADOR**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| num_trabalhador | INT | PK, FK → Trabalhador_Porto | Identificador |

**Relações:**
- 1:N → Deteções  
- 1:N → Turno  

---

### **CHEGADAS_DIARIAS**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_chegada | SERIAL | PK | Identificador |
| data_prevista | DATE |  | Data planeada |
| hora_prevista | TIME |  | Hora prevista |
| estado_entrega | VARCHAR |  | Concluída / Atrasada / Em curso |
| estado_descarga | VARCHAR |  | Em espera / Em descarga / Concluída |
| observacoes | TEXT |  | Notas e alertas |
| matricula | VARCHAR(15) | FK → Camiao.matricula | Camião |
| id_carga | INT | FK → Carga.id_carga | Carga |
| id_cais | INT | FK → Cais.id_cais | Cais |
| id_turno | INT | FK → turno.id_turno | Turno associado |

---

### **DETEÇÃO Válida**
> (armazenada em PostgreSQL no MVP, migrável para MongoDB futuramente)

| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_detecao | SERIAL | PK | Identificador |
| data_hora | TIMESTAMP |  | Data e hora |
| origem | VARCHAR |  | IA / Manual |
| nivel_confianca | FLOAT |  | Percentagem de confiança |
| observacoes | TEXT |  | Notas sobre o evento |
| id_operador | INT | FK → Operador.num_trabalhador | |
| id_chegada | INT | FK → Chegadas_Diarias.id_chegada | |

---

### **ALERTA**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_alerta | SERIAL | PK | Identificador |
| tipo | VARCHAR |  | Tipo (erro leitura, carga perigosa...) |
| descricao | TEXT |  | Mensagem descritiva |
| data | DATE |  | Data do alerta |
| hora | TIME |  | Hora do alerta |
| severidade | INT |  | Escala 1–5 |
| comentario | TEXT |  | Observações |
| id_detecao | INT | FK → detecao.id_detecao | |
| id_carga | INT | FK → Carga.id_carga | |
| id_historico_ocorrencias | INT | FK → historico.id_historico | |

---

### **HISTÓRICO_OCORRENCIAS**
| Campo | Tipo | PK/FK | Descrição |
|--------|------|--------|------------|
| id_ocorrencia | SERIAL | PK | Identificador |
| data | DATE |  | Data da ocorrência |
| hora | TIME |  | Hora |
| descricao | TEXT |  | Descrição detalhada |
| id_turno | INT | FK → turno.id_turno | |

---

## **Tabela de Relações e Cardinalidades**

| Entidade A | Relação | Entidade B | Cardinalidade |
|-------------|----------|-------------|----------------|
| Operador |  is a | Trabalhador_Porto | 1:1 |
| Getsor |  is a | Trabalhador_Porto | 1:1 |
| Gestor | supervisiona | Turno | 1:N |
| Empresa | emprega | Condutor | 1:N |
| Condutor | conduz | Camião | M:N (descontruido)|
| Condutor | associado | Condutor_Camiao | 1:N |
| Camião | associado | Condutor_Camiao | 1:N |
| Camião | realiza | Chegadas_Diarias | 1:N |
| Chegadas_Diarias | refere | Cais | N:1 |
| Chegadas_Diarias | referencia | Carga | N:1 |
| Carga | gera | Alerta | 1:N |
| Operador | valida | Deteção | 1:N |
| Operador | responsavel | Turno | 1:N |
| Deteção | associada | Chegada_Diaria | 1:1 |
| Turno | agrupa | Chegadas_Diarias | 1:N |
| Histórico_Ocorrências | refere | Alerta | 1:N |

---

## **Notas Técnicas**
- Base de dados alvo: **PostgreSQL**
- Encoding: `UTF-8`
- Chaves primárias geradas com `SERIAL` ou `UUID`
- As foreign keys asseguram **integridade referencial**
- Futura integração com **MongoDB**:
  - Coleção `detections_logs`
  - Campos: `timestamp`, `camera_id`, `confidence`, `image_ref`, `truck_plate`, `status`

---

## **Resumo**
A base de dados representa o núcleo do sistema de logística inteligente do porto.  
Integra informações operacionais (Chegadas, Operadores, Cais, Cargas) com dados de deteção automatizada e alertas, garantindo:
- Escalabilidade e integridade relacional  
- Modularidade para integração com IA e sistemas de eventos (Redis/MQTT)  
- Possibilidade de expansão futura para múltiplos portos

---

**Versão:** 1.2  
**Atualização:** Novembro 2025  
**Equipa:** Porto Inteligente — Engenharia Informática @ UA
