# ENV Manager - Gestão de Variáveis de Ambiente

Script para sincronizar ficheiros `.env` com o Google Drive da equipa.

---

## Comandos

| Comando | Descrição |
|---------|-----------|
| `./env_manager.sh push` | Upload dos .env para o Google Drive |
| `./env_manager.sh pull` | Download dos .env do Google Drive |
| `./env_manager.sh list` | Listar .env locais |
| `./env_manager.sh setup` | Configurar acesso ao Google Drive |

---

## Setup Inicial (só uma vez por membro)

### 1. Instalar rclone
```bash
curl https://rclone.org/install.sh | sudo bash
```

### 2. Configurar acesso ao Google Drive
```bash
./env_manager.sh setup
```

Segue estes passos no terminal:
```
n/s/q>                      n
name>                       gdrive
Storage>                    22 (ou "drive")
client_id>                  [Enter - deixar vazio]
client_secret>              [Enter - deixar vazio]
scope>                      1
service_account_file>       [Enter - deixar vazio]
Edit advanced config? y/n>  n
Use web browser? y/n>       y
```

→ **Abre o browser** e faz login com a tua conta Google (a que tem acesso à pasta partilhada do projeto)

```
Shared Drive? y/n>          n
Keep remote? y/e/d>         y
e/n/d/r/c/s/q>              q
```

### 3. Testar
```bash
./env_manager.sh pull
```

---

## Uso Diário

### Depois de clonar o projeto
```bash
./env_manager.sh pull
```

### Depois de alterar um .env
```bash
./env_manager.sh push
```

---

## Ficheiros Geridos

```
src/
├── AI_APP/
│   ├── agentA/.env
│   ├── agentB/.env
│   └── agentC/.env
├── V_APP/
│   ├── api_gateway/.env
│   └── Data_Module/.env
└── streaming_middleware/.env
```

---

## Notas

- Os `.env` **não estão no Git** (estão no `.gitignore`)
- O `push` **substitui** os ficheiros no Drive
- A pasta no Drive é: `PEI-IntelligentLogistics` → `variaveis/`
- **Quando adicionado novo .env é favor meter no env_manager.sh obrigado!**
