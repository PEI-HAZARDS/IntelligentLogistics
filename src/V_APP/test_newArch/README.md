# Decision Flow Testing Suite

Suite completa de testes para o fluxo de correlação de decisões entre Agent e Operator no Data Module.

## 🖥️ Compatibilidade VM

Todos os scripts foram projetados para rodar em VM:
- ✅ Execução dentro do container (sem dependências locais)
- ✅ Usa rede interna Docker (kafka:29092)
- ✅ Verificações via `docker exec`

## 📋 Arquitetura do Fluxo

```
Decision Engine (Agent) → agent-decision-{GATE_ID} ─┐
                                                     ├─→ Data Module (Correlator) → MongoDB + PostgreSQL
API Gateway (Operator) → operator-decision-{GATE_ID}─┘
```

### Lógica de Correlação

1. **MANUAL_REVIEW**: Agent envia decisão → Data Module **aguarda** decisão do Operator
2. **ACCEPTED**: Agent envia decisão → Data Module processa **imediatamente** (sem esperar Operator)

---

## 🚀 Quick Start

### Option 1: Script All-in-One (Recomendado)

```bash
cd /home/dh11/Documents/PEI/IntelligentLogistics/src/V_APP

# Teste completo (setup + test + verify)
./test_all.sh AB-12-CD
```

### Option 2: Step-by-Step

```bash
cd /home/dh11/Documents/PEI/IntelligentLogistics/src/V_APP/test_newArch

# 1. Rebuild após mudanças de código
./rebuild.sh

# 2. Setup dados de teste
./setup_test_data.sh AB-12-CD

# 3. Enviar decisões
./run_test.sh AB-12-CD

# 4. Verificar resultados
./verify_decision.sh AB-12-CD

# 5. Teste específico de infração (Kafka infraction-decision)
./run_infraction_test.sh AB-12-CD 1 true
```

---

## 📁 Scripts Disponíveis

### `rebuild.sh` 🔧
Rebuild do Data Module após alterações de código.

**Uso:**
```bash
./test_newArch/rebuild.sh
```

**O que faz:**
- Para Data Module
- Rebuild imagem (sem cache)
- Reinicia container
- Aguarda 15s startup

---

### `setup_test_data.sh` 
Cria dados de teste no PostgreSQL.

**Uso:**
```bash
./test_newArch/setup_test_data.sh <LICENSE_PLATE> [GATE_ID]
```

**O que cria:**
- Terminal, Gate, Company, Driver, Truck, Booking, Appointment
- Appointment com status `in_transit` pronto para teste

**Exemplo:**
```bash
./test_newArch/setup_test_data.sh AB-12-CD 1
```

---

### `run_test.sh` ⭐
Script principal que executa teste completo.

**Uso:**
```bash
./test_newArch/run_test.sh <LICENSE_PLATE>
```

**O que faz:**
1. Chama `setup_test_data.sh` automaticamente
2. Copia script Python para container
3. Envia decisão Agent (MANUAL_REVIEW) com header `truckId`
4. Aguarda 5 segundos
5. Envia decisão Operator (ACCEPTED) com header `truckId`
6. Aguarda 3 segundos

**Exemplo:**
```bash
./test_newArch/run_test.sh AB-12-CD
```

---

### `send_test_decisions.py`
Script Python que usa `KafkaProducerWrapper` para enviar mensagens com headers corretos.

**Variáveis de ambiente:**
- `LICENSE_PLATE`: License plate para teste (default: AB-12-CD)
- `GATE_ID`: Gate ID (default: 1)
- `KAFKA_BOOTSTRAP`: Kafka bootstrap servers (default: kafka:29092)

**Uso direto (dentro do container):**
```bash
docker exec -e LICENSE_PLATE="AB-12-CD" dm_data_module python /app/send_test_decisions.py
```

---

### `verify_decision.sh`
Verifica se o fluxo foi processado corretamente.

**Uso:**
```bash
./test_newArch/verify_decision.sh <LICENSE_PLATE>
```

**O que verifica:**
- ✅ Logs do Data Module mostrando correlação
- ✅ MongoDB com evento de decisão persistido
- ✅ PostgreSQL com appointment atualizado para `in_process`
- ✅ Campos esperados: `agent_decision`, `operator_decision`, `decision_source`

**Exemplo:**
```bash
./test_newArch/verify_decision.sh AB-12-CD
```

---

### `run_infraction_test.sh` 🚛⚠️
Script específico para validar a feature de infração no appointment (`highway_infraction`).

**Uso:**
```bash
./test_newArch/run_infraction_test.sh <LICENSE_PLATE> [GATE_ID] [INFRACTION] [WAIT_SECONDS]
```

**Parâmetros:**
- `LICENSE_PLATE` (default: `AB-12-CD`)
- `GATE_ID` (default: `1`)
- `INFRACTION` (default: `true`) — `true` ou `false`
- `WAIT_SECONDS` (default: `6`)

**O que faz:**
1. Garante/atualiza dados de teste (`setup_test_data.sh`)
2. Reseta appointment para baseline (`status=in_transit`, `highway_infraction=false`)
3. Publica mensagem no tópico `infraction-decision-{gate_id}` com header `truckId`
4. Aguarda processamento do consumer
5. Valida no PostgreSQL se `highway_infraction` foi alterado conforme esperado

**Exemplos:**
```bash
# Caso principal: infração detectada (espera highway_infraction=true)
./test_newArch/run_infraction_test.sh AB-12-CD 1 true

# Caso sem infração (espera manter valor anterior)
./test_newArch/run_infraction_test.sh AB-12-CD 1 false
```

---

### `debug_appointment.sh`
Script de debug para verificar appointments no banco.

**Uso:**
```bash
./test_newArch/debug_appointment.sh <LICENSE_PLATE>
```

---

## ✅ Resultados Esperados

### Logs do Data Module
```
Agent MANUAL_REVIEW for truck_id=test-truck-123456, waiting for operator decision
Operator decision received for truck_id=test-truck-123456, merging with agent decision
Persisting final decision for truck_id=test-truck-123456
Decision event persisted with id=67891abcdef...
Appointment updated for license_plate=AB-12-CD
```

### MongoDB - Evento de Decisão
```json
{
  "type": "decision",
  "license_plate": "AB-12-CD",
  "decision": "ACCEPTED",              // Decisão final (operator)
  "decision_data": {
    "agent_decision": "MANUAL_REVIEW",   // Decisão original do agent
    "operator_decision": "ACCEPTED",     // Decisão do operator
    "decision_source": "operator",       // Fonte final
    "un": "1203",
    "kemler": "33"
  }
}
```

### PostgreSQL - Appointment
```
 id | truck_license_plate |   status   | gate_in_id
----+---------------------+------------+------------
 21 | AB-12-CD            | in_process |          1
```

---

## 🔍 Verificação Manual

### 1. Logs do Data Module

```bash
docker logs dm_data_module --tail=50 | grep -E "MANUAL_REVIEW|Operator decision|Persisting"
```

### 2. MongoDB - Evento de Decisão

```bash
docker exec dm_mongo mongosh --username pei_user --password "peiHazards**" \
  --authenticationDatabase admin intelligent_logistics --quiet --eval \
  'db.events.find({license_plate: "AB-12-CD"}).sort({_id: -1}).limit(1).pretty()'
```

### 3. PostgreSQL - Appointment Status

```bash
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c \
  "SELECT id, truck_license_plate, status FROM appointment WHERE truck_license_plate = 'AB-12-CD';"
```

### 4. Kafka Topics - Mensagens Enviadas

```bash
# Agent decision topic
docker exec v-kafka kafka-console-consumer \
  --bootstrap-server localhost:29092 \
  --topic agent-decision-1 \
  --from-beginning \
  --max-messages 1

# Operator decision topic
docker exec v-kafka kafka-console-consumer \
  --bootstrap-server localhost:29092 \
  --topic operator-decision-1 \
  --from-beginning \
  --max-messages 1
```

---

## 🐛 Troubleshooting

### Erro: "UNKNOWN_TOPIC_OR_PARTITION"

**Causa**: Tópicos não foram criados ou consumer iniciou antes dos tópicos existirem.

**Solução:**
```bash
# Verificar se tópicos existem
docker exec v-kafka kafka-topics --list --bootstrap-server localhost:29092

# Recriar ambiente
docker-compose down -v
docker-compose up -d
sleep 30  # Aguardar inicialização completa
```

### Consumer não inicia

**Verificar:**
```bash
# Status do container
docker ps | grep dm_data_module

# Logs de startup
docker logs dm_data_module | grep "Kafka decision consumer"

# Erros
docker logs dm_data_module | grep -i error
```

### Appointment não encontrado

**Criar manualmente:**
```bash
./test_newArch/setup_test_data.sh AB-12-CD
```

### Mensagens antigas sem truckId header

**Sintoma**: Logs mostram `WARNING: Message from agent-decision-1 has no truckId header, skipping`

**Causa**: Mensagens antigas de testes anteriores no Kafka.

**Solução**: Ignorar warnings. Novas mensagens de `run_test.sh` têm headers corretos ✅

### Container Data Module não rodando

**Sintoma**: `✗ Error: dm_data_module container is not running`

**Solução**: 
```bash
docker-compose up -d data-module
```

---

## 🎯 Casos de Teste Adicionais

### Caso 1: ACCEPTED direto (sem operator)

Editar `send_test_decisions.py` linha ~56:
```python
decision="ACCEPTED",
decision_reason="license_plate_matched",
```

**Resultado esperado**: Processamento imediato, sem aguardar operator decision.

### Caso 2: Múltiplos MANUAL_REVIEW

Executar script múltiplas vezes com `LICENSE_PLATE` diferente:
```bash
./test_newArch/run_test.sh XY-11-AB
./test_newArch/run_test.sh CD-22-EF
./test_newArch/run_test.sh GH-33-IJ
```

**Verificar:**
```bash
# Quantos pending manual reviews
docker logs dm_data_module | grep "waiting for operator" | wc -l
```

### Caso 3: Operator decision sem Agent decision

Modificar `send_test_decisions.py` para comentar Step 1 (linhas ~53-70).

**Resultado esperado**: Log de warning "no pending agent decision found".

---

## 📝 Notas Técnicas

- **truck_id**: Gerado automaticamente com timestamp para evitar colisões
- **license_plate**: Padrão é `AB-12-CD`, pode ser passado como argumento
- **GATE_ID**: Padrão é `1`, pode ser alterado no `.env`
- **Timestamps**: Gerados automaticamente no formato ISO 8601 UTC
- **Headers Kafka**: Script Python usa `KafkaProducerWrapper` garantindo headers corretos
- **Credenciais**: MongoDB e PostgreSQL usam `pei_user:peiHazards**`
- **Schema PostgreSQL**: Tabelas com estrutura simplificada (truck, driver, booking apenas campos essenciais)

---

## 🔗 Referências

- [kafka_decision_consumer.py](../Data_Module/services/kafka_decision_consumer.py) - Lógica do consumer
- [decision_service.py](../Data_Module/services/decision_service.py) - Persistência no banco
- [decision_engine.py](../decision_engine/src/decision_engine.py) - Produtor de agent decisions
- [docker-compose.yml](../docker-compose.yml) - Configuração dos serviços
