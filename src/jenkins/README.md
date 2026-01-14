# Jenkins CI/CD - Control Panel

Jenkins pipeline centralizado para gestão de todos os serviços nas diferentes VMs.

## ✅ Vantagens

- **Execução Paralela** - Deploy de múltiplos serviços simultaneamente
- **Cache Docker Automático** - Reutiliza layers para builds mais rápidas
- **Controlo Granular** - Seleciona serviços individuais ou todos de uma vez
- **Múltiplas Ações** - deploy, status, restart, stop, logs
- **Sem VPN no GitHub** - VPN roda apenas no servidor Jenkins
- **Mais Seguro** - SSH keys ficam no servidor Jenkins

---

## 🚀 Performance

### Execução Paralela

```
Antes (Sequencial):
Agent A (5min) → Agent B (5min) → Kafka (3min) = 13 minutos

Agora (Paralelo):
Agent A (5min) ┐
Agent B (5min) ├─── Simultâneo
Kafka (3min)   ┘
= 5 minutos (tempo do mais lento)
```

### Cache Docker

- ✅ Reutiliza base images (python:3.11-slim, node:18-alpine)
- ✅ Reutiliza dependências (pip install, npm install)
- ✅ Reconstrói apenas código alterado
- ✅ Preserva volumes de dados (PostgreSQL, MongoDB, Redis)

**Ganhos:**

- Deploy completo (9 serviços): ~30-40 min → **8-12 min** (70% mais rápido)
- Rebuild (só código): ~15 min → **2-4 min** (80% mais rápido)

---

## Architecture

```
Jenkins VM (10.255.32.132)
    │
    ├── SSH (Paralelo) ──> Agent A (10.255.32.134)
    ├── SSH (Paralelo) ──> Agent B (10.255.32.32)
    ├── SSH (Paralelo) ──> Agent C (10.255.32.128)
    ├── SSH (Paralelo) ──> Streaming (10.255.32.80)
    ├── SSH (Paralelo) ──> Kafka (10.255.32.143)
    ├── SSH (Paralelo) ──> Data Module (10.255.32.82)
    ├── SSH (Paralelo) ──> Decision Engine (10.255.32.104)
    ├── SSH (Paralelo) ──> API Gateway (10.255.32.100)
    └── SSH (Paralelo) ──> UI (10.255.32.108)
```

---

## Quick Start

### 1. Criar Jenkins Job

1. **Jenkins** → **New Item**
2. **Nome:** `IntelligentLogistics_Deploy`
3. **Tipo:** **Pipeline** ✅ (NÃO Freestyle!)
4. **OK**

### 2. Configurar Job

**Na secção Pipeline:**

- **Definition:** `Pipeline script from SCM`
- **SCM:** `Git`
- **Repository URL:** `https://github.com/PEI-HAZARDS/IntelligentLogistics.git`
- **Branch Specifier:** `*/imp/structure` for test purposes
- **Script Path:** `src/jenkins/Jenkinsfile`

**Save** → **Build Now** (1ª vez para registar parâmetros) → **F5** → **Build with Parameters** aparece

### 3. Executar Build

1. **Build with Parameters**
2. Selecionar **ACTION** (status/deploy/restart/stop/logs)
3. Marcar serviços desejados ou **ALL_SERVICES**
4. **Build**

---

## 🎛️ Ações Disponíveis

| Ação      | Descrição                 | Exemplo de Uso                 |
| --------- | ------------------------- | ------------------------------ |
| `status`  | Ver estado dos containers | Verificar se serviços estão UP |
| `deploy`  | Build e deploy do serviço | Atualizar código após commit   |
| `restart` | Reiniciar container       | Aplicar variáveis de ambiente  |
| `stop`    | Parar container           | Manutenção temporária          |
| `logs`    | Ver últimos logs          | Debug de erros                 |

---

## 📦 Serviços Disponíveis

| Checkbox          | Serviço         | VM IP         | Componentes                            |
| ----------------- | --------------- | ------------- | -------------------------------------- |
| `ALL_SERVICES`    | Todos           | -             | Seleciona todos automaticamente        |
| `AGENT_A`         | Agent A         | 10.255.32.134 | Truck Detection                        |
| `AGENT_B`         | Agent B         | 10.255.32.32  | License Plate OCR                      |
| `AGENT_C`         | Agent C         | 10.255.32.128 | Hazard Detection                       |
| `STREAMING`       | Streaming       | 10.255.32.80  | Nginx RTMP                             |
| `KAFKA`           | Kafka           | 10.255.32.143 | Zookeeper + Kafka + Kafka UI           |
| `DATA_MODULE`     | Data Module     | 10.255.32.82  | Postgres + Mongo + Redis + MinIO + App |
| `DECISION_ENGINE` | Decision Engine | 10.255.32.104 | Decision Logic                         |
| `API_GATEWAY`     | API Gateway     | 10.255.32.100 | REST API                               |
| `UI`              | UI              | 10.255.32.108 | Frontend Web                           |

---

## 🔧 Parâmetros Adicionais

| Parâmetro   | Default | Descrição                           |
| ----------- | ------- | ----------------------------------- |
| `BRANCH`    | `main`  | Branch do Git para deploy           |
| `LOG_LINES` | `100`   | Número de linhas de log (ação logs) |

---

## 🔐 Credentials Required (Jenkins)

Configurar em: **Manage Jenkins** → **Credentials** → **System** → **Global credentials**

| ID                  | Type                          | Username        | Description                     |
| ------------------- | ----------------------------- | --------------- | ------------------------------- |
| `ssh-vm-key`        | SSH Username with private key | (user das VMs)  | Acesso SSH às VMs               |
| `minio-credentials` | Username with password        | MINIO_ROOT_USER | Credenciais MinIO (Data Module) |

### Adicionar SSH Key:

1. **Add Credentials**
2. **Kind:** SSH Username with private key
3. **ID:** `ssh-vm-key`
4. **Username:** (ex: `root` ou `ubuntu`)
5. **Private Key:** Enter directly → colar chave privada
6. **Passphrase:** (se tiver)

---

## 🐛 Troubleshooting

### "Build with Parameters" não aparece

- ✅ Job deve ser tipo **Pipeline** (não Freestyle)
- ✅ Executa **Build Now** uma vez (regista parâmetros)
- ✅ Recarrega página (F5)

### SSH Connection Failed

- ✅ Verifica VPN conectada à rede UA
- ✅ Testa: `timeout 5 bash -c 'cat < /dev/null > /dev/tcp/10.255.32.134/22'`
- ✅ Confirma credential `ssh-vm-key` configurada corretamente

### Build muito lento

- ✅ Cache Docker ativado? (não uses `--pull` desnecessário)
- ✅ Múltiplos serviços rodando em paralelo?
- ✅ Rede lenta? Verifica bandwidth Jenkins ↔ VMs

### Container não inicia

- ✅ Ver logs: ACTION=logs, seleciona serviço
- ✅ Verifica portas não estão em uso: ACTION=status
- ✅ SSH na VM e roda: `docker logs <container>`

---

## Ports

| Service       | Port  |
| ------------- | ----- |
| Jenkins UI    | 8080  |
| Jenkins Agent | 50000 |
