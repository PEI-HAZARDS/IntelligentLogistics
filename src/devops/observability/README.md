# Observability Stack - IntelligentLogistics

Stack de monitorização completa para o projeto IntelligentLogistics:
- **Prometheus** - Recolha de métricas
- **Grafana** - Dashboards e visualização
- **Loki** - Agregação de logs
- **Alertmanager** - Alertas por email
- **Node Exporter** - Métricas do host

## Quick Start

```bash
# 1. Copiar ficheiro de ambiente
cp .env.example .env

# 2. Configurar email no .env (ver secção Email)

# 3. Iniciar stack
docker compose up -d

# 4. Verificar serviços
docker compose ps
```

## Acesso

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| Alertmanager | http://localhost:9093 | - |
| Loki | http://localhost:3100 | - |

## Configuração de Email (Gmail)

1. Acede a https://myaccount.google.com/apppasswords
2. Cria uma "App Password" para "Mail"
3. Edita `.env`:
```
SMTP_AUTH_USERNAME=email-do-projeto@gmail.com
SMTP_AUTH_PASSWORD=xxxx-xxxx-xxxx-xxxx
ALERT_EMAIL_TO=email-destino@example.com
```
4. Edita `alertmanager/alertmanager.yml` com os mesmos valores

## Dashboards Incluídos

| Dashboard | Descrição |
|-----------|-----------|
| **Overview** | Saúde geral de todos os serviços |
| **API Gateway** | Request rates, latências, erros |
| **Infrastructure** | CPU, memória, disco, databases |
| **Data Module** | Métricas do Data Module e DBs |
| **Decision Engine** | Decisões e integração Kafka |
| **ML Agents** | Agents A, B, C - inferência |
| **Kafka** | Brokers, topics, consumer lag |

## Alertas Configurados

| Alerta | Condição | Severidade |
|--------|----------|------------|
| ServiceDown | Serviço sem resposta > 2min | 🔴 Critical |
| HighErrorRate | Erros > 5% | 🟡 Warning |
| HighLatency | P95 > 500ms | 🟡 Warning |
| HighCPU | CPU > 80% por 5min | 🟡 Warning |
| HighMemory | Memória > 85% | 🟡 Warning |
| DiskAlmostFull | Disco > 90% | 🔴 Critical |

## Deploy na VM do Jenkins

```bash
# Copiar pasta para a VM
scp -r observability/ user@jenkins-vm:~/

# Na VM
cd ~/observability
docker compose up -d
```

## Estrutura

```
observability/
├── docker-compose.yml
├── .env.example
├── prometheus/
│   ├── prometheus.yml
│   └── alerts/rules.yml
├── alertmanager/alertmanager.yml
├── grafana/provisioning/
│   ├── datasources/datasources.yml
│   └── dashboards/
│       ├── dashboards.yml
│       └── json/
│           ├── overview.json
│           ├── api-gateway.json
│           └── infrastructure.json
├── loki/loki-config.yml
├── promtail/promtail-config.yml
└── README.md
```

## Troubleshooting

```bash
# Ver logs
docker compose logs -f prometheus
docker compose logs -f alertmanager

# Recarregar configs
curl -X POST http://localhost:9090/-/reload  # Prometheus
curl -X POST http://localhost:9093/-/reload  # Alertmanager

# Verificar targets do Prometheus
curl http://localhost:9090/api/v1/targets
```
