# Production Hardening Plan — Keycloak TLS + Secrets

> Estado em 2026-05-30. Âmbito: V_APP (`src/V_APP/docker-compose.yml`).
> Critério de aceitação principal: **RNF5.1 — "Todas as comunicações devem usar TLS/SSL"**
> (`docs/requisitos/RNF.md`). Itens relacionados: RNF5.4 (least-privilege PG),
> RNF5.5 (bcrypt ≥12), RNF5.7 (CORS whitelist).

Este documento descreve o que falta fazer para passar a V_APP de configuração de
laboratório para produção. Keycloak-prod e a migração de secrets são tratados como
**uma única alteração coerente e testável**, porque partilham os mesmos segredos
(`KC_*`, `ENCRYPTION_KEY`, `KEYCLOAK_CLIENT_SECRET`) e o mesmo entrypoint-shim.

---

## 0. Já feito (contexto)

Endurecimento de base já aplicado ao compose (validado com `docker compose config`):

- **Kafka bootstrap uniformizado** para `kafka:29092` em todos os serviços in-network.
- **Healthchecks** no Kafka e nos engines; `kafka-init`/`redpanda-console` esperam o broker *healthy*.
- **Config Kafka morta removida** (`CONSUME_TOPIC`, `PRODUCE_TOPIC`, `KAFKA_DECISION_TOPIC`,
  `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_CONSUMER_GROUP`) do serviço e do `.env`/`.env.example`.
- **Limites de recursos** (`deploy.resources.limits`) nos 23 serviços (cap agregado ≈ 11.6 GB).

Falta o que está abaixo.

---

## 1. Decisões de ambiente (bloqueiam o arranque)

Estas duas decisões são do operador e não estão documentadas em lado nenhum — sem elas
o Keycloak em modo produção **recusa arrancar**:

1. **Onde termina o TLS?**
   - Opção A (recomendada): terminação *edge* num reverse proxy (o `api-proxy` nginx do
     `IntelligentLogistics_APP`, ou um LB externo) que faz HTTPS para o cliente e HTTP para
     o Keycloak na rede interna.
   - Opção B: TLS direto no Keycloak (montar `KC_HTTPS_CERTIFICATE_FILE` /
     `KC_HTTPS_CERTIFICATE_KEY_FILE`).
2. **Hostname público** do Keycloak (ex.: `https://auth.porto.example`) → `KC_HOSTNAME`.

O resto deste plano assume a **Opção A** (edge termination), que é a que encaixa na
arquitetura atual (UIs e driver já passam por nginx).

---

## 2. Keycloak — laboratório → produção

### 2.1 Dockerfile (`src/V_APP/keycloak/Dockerfile`)
Hoje é mínimo (`FROM ... + copy realm`). Produção exige um *build* otimizado:

```dockerfile
FROM quay.io/keycloak/keycloak:26.0 AS build
ENV KC_DB=postgres
RUN /opt/keycloak/bin/kc.sh build --db=postgres --health-enabled=true --metrics-enabled=true

FROM quay.io/keycloak/keycloak:26.0
COPY --from=build /opt/keycloak/ /opt/keycloak/
COPY realm-export.json /opt/keycloak/data/import/realm-export.json
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
```

### 2.2 Serviço no compose
Trocar `start-dev` por `start --optimized` e configurar hostname/proxy (Keycloak 26):

```yaml
  keycloak:
    command: start --optimized --import-realm
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME_FILE: /run/secrets/kc_db_password   # ver §3
      KC_DB_PASSWORD_FILE: /run/secrets/kc_db_password
      KC_HOSTNAME: https://auth.porto.example            # DECISÃO #2
      KC_HOSTNAME_STRICT: "true"
      KC_HTTP_ENABLED: "true"                            # HTTP interno; TLS no edge
      KC_PROXY_HEADERS: xforwarded                       # confia em X-Forwarded-* do reverse proxy
      KC_HEALTH_ENABLED: "true"
      KC_METRICS_ENABLED: "true"
    ports:
      - "8080:8080"   # renomear o mapeamento enganador 8443:8080 (8443 sugeria TLS)
```

> ⚠️ `KC_PROXY_HEADERS=xforwarded` só é seguro **atrás** de um reverse proxy que reescreve
> esses cabeçalhos. Nunca expor o Keycloak HTTP diretamente à internet com esta flag.

### 2.3 Reverse proxy (Opção A)
Acrescentar ao nginx do `api-proxy` (APP) uma `location`/`server` que termina TLS para
`auth.porto.example` e faz `proxy_pass http://<keycloak>:8080` com
`X-Forwarded-Proto https` / `X-Forwarded-Host`.

---

## 3. Secrets — Docker `secrets:`

### 3.1 Imagens oficiais (suportam `_FILE` nativamente)
`postgres`, `keycloak-db`, `mongo`, `minio`, `keycloak` → trocar env plano por `*_FILE`:

```yaml
secrets:
  postgres_password:   { file: ./secrets/postgres_password }
  mongo_password:      { file: ./secrets/mongo_password }
  minio_password:      { file: ./secrets/minio_password }
  kc_db_password:      { file: ./secrets/kc_db_password }
  kc_admin_password:   { file: ./secrets/kc_admin_password }
  encryption_key:      { file: ./secrets/encryption_key }
  keycloak_client_secret: { file: ./secrets/keycloak_client_secret }
```

(adicionar `secrets:` a cada serviço; `POSTGRES_PASSWORD_FILE`, `MONGO_INITDB_ROOT_PASSWORD_FILE`,
`MINIO_ROOT_PASSWORD_FILE`, etc.)

### 3.2 Serviços Python (não suportam `_FILE`) — entrypoint-shim
Os serviços custom (`data-module`, `outbox-worker`, `statistics-aggregator`, `api-gateway`,
`keycloak-sync`) fazem `os.getenv(...)` plano e o **`DATABASE_URL` traz a password embutida**.
Solução sem mexer no código: um shim partilhado que exporta os secrets e *recompõe* a URL.

```sh
#!/bin/sh
# /usr/local/bin/with-secrets.sh
set -e
for f in /run/secrets/*; do
  [ -f "$f" ] && export "$(basename "$f" | tr '[:lower:]' '[:upper:]')"="$(cat "$f")"
done
# Recompor DATABASE_URL a partir das partes + secret (em vez de password embutida no .env)
if [ -n "$POSTGRES_PASSWORD" ]; then
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi
exec "$@"
```

- Bakar o shim na imagem `v_app-data-module` (e na do `keycloak-sync`) e prefixar os
  `entrypoint`/`command` existentes com `with-secrets.sh`.
- ⚠️ Cuidado com os serviços que **já fazem override de `entrypoint`** (`outbox-worker`,
  `statistics-aggregator`, `keycloak-sync`): mover o comando atual para argumentos do shim.

### 3.3 Limpeza do `.env`
Após a migração, remover do `.env` os valores em claro (`POSTGRES_PASSWORD`, `DATABASE_URL`
com password, `MONGO_INITDB_ROOT_PASSWORD`, `MINIO_ROOT_PASSWORD`, `KC_*_PASSWORD`,
`ENCRYPTION_KEY`, `KEYCLOAK_CLIENT_SECRET`). Manter apenas refs não-secretas.
Acrescentar `secrets/` ao `.gitignore`.

---

## 4. Ordem de execução (1 PR coerente)
1. Criar ficheiros `secrets/*` (fora do git) + bloco `secrets:`.
2. Migrar imagens oficiais para `*_FILE` (§3.1).
3. Bakar o shim + ajustar `entrypoint`/`command` dos serviços Python (§3.2).
4. Dockerfile do Keycloak com `kc build` + serviço `start --optimized` (§2).
5. Reverse proxy TLS (§2.3).
6. Limpar `.env` (§3.3).

## 5. Verificação (smoke tests)
- `docker compose config` sem avisos.
- `docker compose up -d` → todos `healthy`; `keycloak` arranca em modo produção sem erro de hostname.
- Login pelo gateway (`/api`) emite JWT; `/arrivals` responde 200 (cadeia Keycloak intacta).
- `docker inspect <serviço>` **não** mostra passwords no `Env`.
- HTTPS no hostname público; HTTP do Keycloak só acessível na rede interna.

---

## Notas
- Estas mudanças são **outward-facing e não testáveis offline** — exigem o Docker do operador
  e a rede do porto. Tratar como um PR único com os smoke tests acima.
- Sem TLS/hostname (§1) o Keycloak-prod não arranca; é o primeiro bloqueio a resolver.
