# Base de Dados Não Relacional — Redis (Agente de Decisão)

## Objetivo
O **Redis** será usado como **base de dados não relacional e in-memory**, servindo como camada de **decisão e cache temporária** para o sistema do **Porto Inteligente**.  
Está integrada dentro do **Agente de Decisão**, responsável por processar eventos em tempo real, decisões automáticas e comunicações rápidas entre componentes.

---

## Papel no Sistema
Redis atua como **memória de curta duração** e **broker auxiliar**:
- Armazena o **estado corrente** de camiões, cais, e deteções ativas;
- Permite **resposta imediata** a eventos de deteção e autorização;
- Garante **sincronização** entre APIs e microserviços sem necessidade de acesso constante ao PostgreSQL;
- Pode atuar como **fallback de decisão** em caso de falha de rede ou latência da BD principal.

---

## Estrutura Geral
O modelo de dados em Redis segue uma **organização baseada em coleções (namespaces)** com **tipos de dados otimizados**:

| Namespace | Tipo | Descrição |
|------------|------|------------|
| `truck:*` | Hash | Estado e informação temporária de cada camião detetado |
| `detection:*` | Hash | Dados de deteções ativas (IA/manual) |
| `alerts:*` | List / Stream | Fila de alertas ou eventos críticos |
| `gate:*` | Hash | Estado da cancela e dos cais ativos |
| `decision_queue` | Stream | Fila de decisões do agente |
| `system:metrics` | Hash | Estatísticas e contadores operacionais |

---

## **1.Estrutura — `truck:<matricula>`**
Representa o estado **atual de um camião detetado ou em trânsito**.

**Tipo:** `HASH`  
**Chave:** `truck:<matricula>`

**Campos:**
| Campo | Exemplo | Descrição |
|--------|----------|------------|
| `matricula` | "AA-11-BB" | Identificador |
| `estado` | "em_espera" / "autorizado" / "descarga" | Estado atual |
| `tipo` | "cisterna" | Tipo de veículo |
| `carga_tipo` | "líquido" | Tipo da carga |
| `adr` | true | Se é perigosa |
| `id_cais` | 5 | Cais atribuído |
| `timestamp` | 1730728000 | Epoch da última atualização |

**TTL (Time to Live):** 6h — após isso o registo é removido (evita lixo de dados).

---

## **2.Estrutura — `detection:<id>`**
Contém informações da **última deteção processada** pelo sistema de IA.

**Tipo:** `HASH`  
**Chave:** `detection:<id>` (ex: `detection:20251105153000_AA11BB`)

**Campos:**
| Campo | Exemplo | Descrição |
|--------|----------|------------|
| `id` | "20251105153000_AA11BB" | Identificador único |
| `matricula` | "AA-11-BB" | Veículo detetado |
| `origem` | "IA" / "manual" | Origem da deteção |
| `nivel_confianca` | 0.92 | Confiança da IA |
| `estado_autorizacao` | "pendente" | Estado atual |
| `imagem_ref` | "cam1_20251105_153000.jpg" | Referência ao frame da IA |
| `timestamp` | 1730728000 | Hora da deteção (epoch) |

**TTL:** 24h  
**Ações:**  
- O **Agente de Decisão** lê estas deteções e decide:  
  → autorizar entrada → atualizar `truck:<matricula>`  
  → negar → enviar `alert` e marcar `estado_autorizacao = negado`

---

## **3 Estrutura — `alerts`**
Lista de **alertas e eventos críticos recentes**, como erros de leitura ou deteções suspeitas.

**Tipo:** `LIST` (ou `STREAM` se houver integração MQTT)

**Chave:** `alerts`

**Elementos:**
```json
{
  "id": "alert:20251105_001",
  "tipo": "matricula_desconhecida",
  "descricao": "Camião sem correspondência com entregas agendadas",
  "severidade": 4,
  "timestamp": 1730728123
}

{
  ""
}
