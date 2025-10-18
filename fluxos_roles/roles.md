Roles

- Backend and Middleware (Rafa e Diogo)

- Frontend and Databases (Bernardo e Paulo)

- Computer Vision/ Ml Engineer (Diogo e Tomás)

- DevOps (Paulo e Bernardo)
 
- Integration & QA Engineer (Tomás e Rafa)

---

## 🧭 1. Reorganização de papéis por fase do projeto

| Fase                              | Objetivo                                               | Foco das pessoas                                                                           | Comentário                                             |
| --------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| **MS1 — Inception (agora)**       | Apresentar proposta, arquitetura, PoC conceptual       | Rafa (backend lead), Diogo + Tomás (CV), Paulo (infra), Bernardo (apoio infra + slides)    | Frontend quase inexistente — só wireframes ou mock UI. |
| **MS2 — PoC técnico (até 18/11)** | Detetar camião + ler matrícula + gerar decisão via API | CV (Tomás, Diogo), BE (Rafa), Infra (Paulo), Bernardo apenas ajuda em DB + suporte DevOps  | Ainda sem frontend visual. Foco é pipeline técnica.    |
| **MS3 — MVP final (até 16/12)**   | Ter sistema completo + UI operável + demo visual       | Bernardo (frontend lead), Paulo (deploy/UI integration), outros ajudam testes e otimização | Aqui sim o frontend entra em força.                    |

---

## 🧩 2. Distribuição ajustada de esforço (% por fase)

| Nome         | MS1 (Inception)                | MS2 (PoC técnico)                 | MS3 (Frontend + MVP)              | Função dominante     |
| ------------ | ------------------------------ | --------------------------------- | --------------------------------- | -------------------- |
| **Rafa**     | 40% documentação / 60% backend | 80% backend / integration         | 60% QA / integration              | Backend + QA lead    |
| **Diogo**    | 40% inception + arch           | 70% CV (Agent-A/B)                | 60% ML / OCR tuning               | ML / backend support |
| **Tomás**    | 40% inception + datasets       | 80% CV (model training, accuracy) | 50% ML / QA tests                 | CV / ML lead         |
| **Paulo**    | 40% infra setup                | 70% DevOps + CI/CD                | 50% deploy + frontend integration | DevOps lead          |
| **Bernardo** | 50% inception slides + DB      | 40% support infra + DB            | 80% frontend / UI design          | UI lead (fase final) |

---

## ⚙️ 3. Como aproveitar o **Bernardo e Paulo** (frontend & DB) nas fases iniciais

Durante **MS1 e MS2**, podem e devem contribuir em tarefas *cross-functionais*, como:

| Pessoa       | Contribuição temporária (antes da UI real)                                                                                                                                                                                  |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Bernardo** | - Montar e manter o schema da base de dados<br>- Criar scripts de seed e queries para os agentes testarem<br>- Ajudar na arquitetura da API (modelos JSON, endpoints)<br>- Desenhar mockups da UI no Figma para o Inception |
| **Paulo**    | - Montar toda a stack Docker / K3s<br>- Configurar pipelines CI/CD e monitorização<br>- Fazer build automatizado da UI dummy<br>- Garantir que os containers se comunicam corretamente                                      |

Isto mantém os dois produtivos até que a UI entre em fase ativa, **sem ficarem subutilizados**.

---

## 🧱 4. Estrutura final recomendada (equipa equilibrada)

| Role                                  | Lead     | Apoio    | Observações                                |
| ------------------------------------- | -------- | -------- | ------------------------------------------ |
| **Computer Vision / ML**              | Tomás    | Diogo    | Foco no modelo e deteção.                  |
| **Backend & Middleware**              | Rafa     | Diogo    | Foco na orquestração, APIs e eventos.      |
| **DevOps / Infraestrutura**           | Paulo    | Bernardo | Foco em deploy, containers e CI/CD.        |
| **Frontend & Databases (Fase Final)** | Bernardo | Paulo    | Entra em MS3 para UI real e integração.    |
| **Integration & QA**                  | Rafa     | Tomás    | Validação end-to-end e testes automáticos. |

👉 Assim:

* **Tomás, Diogo e Rafa** são o core técnico até MS2.
* **Paulo e Bernardo** sustentam infra e DB, e depois assumem o **Frontend na reta final**.
* O projeto ganha **eficiência energética e técnica** — não há gente “sem tarefas” nas primeiras semanas.

---

## 🎯 5. Quando ativar o Frontend

Ativa o desenvolvimento do frontend **após o PoC técnico (MS2)**, quando já existir:

1. Endpoint `/authorize` funcional.
2. JSON de decisão final (truck_id, plate, hazard_code, status).
3. Dataset simulado com eventos de entrada.

Nessa altura, o **frontend pode mostrar:**

* Stream snapshot + box da deteção,
* Placa lida, hazard, destino,
* Botão “abrir cancela” e estado do gate.

---

