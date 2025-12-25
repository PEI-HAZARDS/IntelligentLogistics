# Jenkins CI/CD - Direct Deploy

Jenkins pipeline for direct deployment to VMs via SSH.

## ✅ Advantages

- **No VPN credentials on GitHub** - VPN runs on Jenkins VM
- **Full control** - Deploy whenever you want
- **More secure** - SSH keys stay on Jenkins server

---

## Architecture

```
Jenkins VM (10.255.32.132)
    │
    └── SSH ──> Service VMs
                ├── agentA (10.255.32.134)
                ├── agentB (10.255.32.32)
                ├── agentC (10.255.32.128)
                ├── kafka (10.255.32.143)
                ├── data-module (10.255.32.82)
                ├── decision-engine (10.255.32.104)
                ├── api-gateway (10.255.32.100)
                └── ui (10.255.32.108)
```

---

## Quick Start

### 1. Access Jenkins

Open: **http://10.255.32.132:8089**

### 2. Run a Build

1. Click on the pipeline → **Build with Parameters**
2. Select DEPLOY_MODE and SERVICE
3. Click **Build**

---

## Deploy Modes

| Mode | Description |
|------|-------------|
| `auto` | Detects changed files and deploys only affected services |
| `manual` | You choose which service to deploy |

---

## Available Services

| Service | VM IP | Components |
|---------|-------|------------|
| `all` | - | All services |
| `agentA` | 10.255.32.134 | Agent A |
| `agentB` | 10.255.32.32 | Agent B |
| `agentC` | 10.255.32.128 | Agent C |
| `kafka` | 10.255.32.143 | Kafka + Zookeeper + UI |
| `data-module` | 10.255.32.82 | Data Module + MinIO |
| `decision-engine` | 10.255.32.104 | Decision Engine |
| `api-gateway` | 10.255.32.100 | API Gateway + Nginx |
| `ui` | 10.255.32.108 | Frontend UI |

---

## Automatic Deployment

The pipeline is configured with **Poll SCM** (`H/5 * * * *`):
- Checks GitHub every 5 minutes
- Automatically deploys when changes are detected
- Only deploys services that have changed files

---

## Credentials Required (Jenkins)

| ID | Type | Description |
|----|------|-------------|
| `ssh-vm-key` | SSH Username with private key | SSH access to VMs |
| `minio-credentials` | Username/Password | MinIO credentials (optional) |

---

## Ports

| Service | Port |
|---------|------|
| Jenkins UI | 8089 |
| Jenkins Agent | 50000 |
