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

## 🔐 Setup SSH - Chaves Persistentes

As chaves SSH são armazenadas em `ssh_keys/` e montadas no container. Persistem entre rebuilds.

### Setup Inicial (Uma Vez)

As chaves já estão configuradas. Se precisares de regenerar:

```bash
# Gerar novas chaves
ssh-keygen -t ed25519 -f ssh_keys/id_ed25519 -N "" -C "jenkins@intelligentlogistics"

# Copiar para a VM do Jenkins
scp ssh_keys/* pei_user@10.255.32.132:~/jenkins/ssh_keys/
ssh pei_user@10.255.32.132 "sudo chown root:root ~/jenkins/ssh_keys/* && sudo chmod 600 ~/jenkins/ssh_keys/id_ed25519"

# Rebuild
docker compose up -d --build
```

### Adicionar Nova VM

Quando surgir uma nova VM, usa o script:

```bash
# Adicionar chave do Jenkins a uma nova VM
./add-vm.sh 10.255.32.XXX

# Ou com outro utilizador
./add-vm.sh 10.255.32.XXX outro_user
```

O script:

1. ✅ Verifica conectividade à VM
2. ✅ Adiciona a chave pública ao `~/.ssh/authorized_keys`
3. ✅ Testa se o Jenkins consegue conectar

### Testar Conexão

```bash
# Testar SSH do Jenkins
docker exec jenkins ssh pei_user@10.255.32.134 "hostname"

# Testar Docker remoto
docker exec jenkins docker -H "ssh://pei_user@10.255.32.134" ps
```

### Estrutura de Ficheiros

```
ssh_keys/
├── id_ed25519      # Chave privada (NÃO vai para o git)
├── id_ed25519.pub  # Chave pública
├── config          # Configuração SSH
└── .gitignore      # Ignora chaves privadas
```

---

## 🔒 Configurar Ficheiros .env (Secrets)

Os ficheiros `.env` contêm segredos (passwords, API keys, endpoints) e **não estão no git**.
O Jenkins injeta automaticamente os `.env` durante o deploy usando **Credentials**.

### Passo 1: Criar o .env real

Usa o `.env.example` de cada serviço como base:

```bash
cd src/agentA_microservice
cp .env.example .env
# Editar com valores reais
```

### Passo 2: Adicionar ao Jenkins

1. **Jenkins** → **Manage Jenkins** → **Credentials**
2. **System** → **Global credentials (unrestricted)**
3. **Add Credentials**
4. Preencher:
   - **Kind:** `Secret file`
   - **File:** Selecionar o `.env` criado
   - **ID:** Ver tabela abaixo (IMPORTANTE: usar ID exato!)
   - **Description:** Nome do serviço
5. **Create**

### Mapeamento de Credentials

O Jenkinsfile usa o padrão `env-{containerName}`. IDs a configurar:

| Container         | Credential ID         | Ficheiro Base                                   |
| ----------------- | --------------------- | ----------------------------------------------- |
| `agenta`          | `env-agenta`          | `src/agentA_microservice/.env.example`          |
| `agentb`          | `env-agentb`          | `src/agentB_microservice/.env.example`          |
| `agentc`          | `env-agentc`          | `src/agentC_microservice/.env.example`          |
| `nginx-rtmp`      | `env-nginx-rtmp`      | `src/streaming_middleware/.env.example`         |
| `dm_data_module`  | `env-dm_data_module`  | `src/Data_Module/.env.example`                  |
| `decision-engine` | `env-decision-engine` | `src/decision_engine_microservice/.env.example` |
| `api_gateway`     | `env-api_gateway`     | `src/api_gateway/.env.example`                  |

### Verificar nos Logs

Durante o deploy, verás:

```
✅ .env injectado do Jenkins Credentials (env-agenta)
```

Se a credential não existir:

```
⚠️  Credential 'env-agenta' não encontrada - usando .env existente (se houver)
```

### Atualizar um .env

Para alterar variáveis de ambiente:

1. Editar o `.env` localmente
2. No Jenkins: **Credentials** → Selecionar a credential → **Update**
3. Fazer upload do novo ficheiro
4. Re-deploy do serviço

---

## 🐛 Troubleshooting

### "Build with Parameters" não aparece

- ✅ Job deve ser tipo **Pipeline** (não Freestyle)
- ✅ Executa **Build Now** uma vez (regista parâmetros)
- ✅ Recarrega página (F5)

### SSH Connection Failed

- ✅ Verifica VPN conectada à rede UA
- ✅ Testa: `docker exec jenkins ssh pei_user@10.255.32.134 "docker ps"`
- ✅ Chave SSH gerada? `docker exec jenkins ls -la /var/jenkins_home/.ssh/`
- ✅ Chave pública adicionada à VM? `ssh pei_user@<VM_IP> "cat ~/.ssh/authorized_keys"`

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
