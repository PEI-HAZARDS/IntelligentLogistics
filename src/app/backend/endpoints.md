# API Porto Logística

**Autenticação:**
Todos os endpoints protegidos devem receber o header:
Os tokens podem conter claims com o tipo_de_usuario ou nivel_acesso (facilita a autorização por função)

```
Authorization: Bearer <token>
```

---
## 0. Gerais

| Método | Endpoint                               | Descrição               |
| ------ | -------------------------------------- | ----------------------- |
| GET    | `/api/v1/gestores`                     | Listar todos gestores   |
| GET    | `/api/v1/gestores/{num_trabalhador}`   | Detalhes de um gestor   |
| GET    | `/api/v1/operadores`                   | Listar operadores       |
| GET    | `/api/v1/operadores/{num_trabalhador}` | Detalhes de um operador |
| GET    | `/api/v1/empresas`                     | Listar empresas         |
| GET    | `/api/v1/empresas/{id_empresa}`        | Detalhes de uma empresa |
| GET    | `/api/v1/condutores`                   | Listar condutores       |
| GET    | `/api/v1/condutores/{num_carta_cond}`  | Detalhes de um condutor |
| GET    | `/api/v1/camioes`                      | Listar camiões          |
| GET    | `/api/v1/camioes/{matricula}`          | Detalhes de um camião   |


## 1. Gestor Logístico

### Cargas / Cais / Turnos

| Método | Endpoint                                 | Descrição                                                    |
| ------ | ---------------------------------------- | ------------------------------------------------------------ |
| GET    | `/api/v1/cargas`                         | Listar cargas                                                |
| GET    | `/api/v1/cargas/{id_carga}`              | Detalhes da carga                                            |
| GET    | `/api/v1/cais`                           | Listar cais                                                  |
| GET    | `/api/v1/cais/{id_cais}`                 | Detalhes do cais                                             |
| GET    | `/api/v1/turnos`                         | Listar turnos                                                |
| GET    | `/api/v1/turnos/{id_turno}`              | Detalhes do turno                                            |
| GET    | `/api/v1/turnos/{id_turno}/estatisticas` | Dados agregados: nº de chegadas, cargas processadas, alertas |


### Chegadas / Histórico / Alertas

| Método | Endpoint                        | Descrição                                           |
| ------ | ------------------------------- | --------------------------------------------------- |
| GET    | `/api/v1/chegadas`              | Listar chegadas (filtros: `data`, `cais`, `estado`) |
| GET    | `/api/v1/chegadas/{id_chegada}` | Detalhes da chegada                                 |
| GET    | `/api/v1/historico`             | Listar ocorrências por turno, operador ou carga     |
| GET    | `/api/v1/alertas`               | Listar alertas (filtros: severidade, tipo, período) |
| GET    | `/api/v1/alertas/estatisticas`  | Número de alertas por tipo, turno, operador         |

---

## 2. Operador Cancela

###  Chegadas

| Método | Endpoint                    | Descrição                                                    |
| ------ | --------------------------- | ------------------------------------------------------------ |
| GET    | `/api/v1/operadores/me`     | Perfil do operador logado                                    |
| GET    | `/api/v1/turnos/ativos`     | Turno atual do operador                                      |
| GET    | `/api/v1/chegadas/proximas` | Listar chegadas para próximas 2–3 horas (`horas=2` opcional) |
| POST   | `/api/v1/chegadas`                     | Criar chegada                        |
| PUT    | `/api/v1/chegadas/{id_chegada}/estado` | Atualizar estado de descarga/entrega |


### Turno e deteções

| Método | Endpoint                               | Descrição                            |
| ------ | -------------------------------------- | ------------------------------------ |
| POST   | `/api/v1/turnos`                       | Criar turno                          |
| POST   | `/api/v1/deteccoes`              | Criar validação (associar operador + chegada + imagem) |
| GET    | `/api/v1/deteccoes`              | Listar validações (filtros: data, operador, chegada)   |
| GET    | `/api/v1/deteccoes/{id_detecao}` | Detalhes da validação                                  |


### Histórico / Alertas

| Método | Endpoint            | Descrição        |
| ------ | ------------------- | ---------------- |
| POST   | `/api/v1/historico` | Criar ocorrência |
| POST   | `/api/v1/alertas`   | Criar alerta     |

### Streaming / Notificações em tempo real
| Método    | Endpoint                           | Descrição                                       |
| --------- | ---------------------------------- | ----------------------------------------------- |
| GET       | `/api/v1/cameras/{id_cais}/stream` | Stream de vídeo do portão                       |
| WebSocket | `/ws/deteccoes`                    | Notificação em tempo real de deteções validadas |


---

## 3. Motorista

| Método    | Endpoint                                            | Descrição                                     |
| --------- | --------------------------------------------------- | --------------------------------------------- |
| GET       | `/api/v1/motoristas/me`                             | Perfil do motorista logado                    |
| GET       | `/api/v1/motoristas/{num_carta_cond}/rotas`         | Rotas atribuídas                              |
| GET       | `/api/v1/motoristas/entrega{id}`                    | Obter cais e horário de chegada atual         |
| PATCH     |`/api/v1/motoristas/{num_carta_cond}/entrega{id}`    | Atualizar estado da entrega                   |
| WebSocket | `/ws/entregas`                                      | Notificações de validação e instrução de cais |


---

## 4. Decision Engine

| Método | Endpoint                               | Descrição                                         |
| ------ | -------------------------------------- | ------------------------------------------------- |
|GET     | `/api/v1/internal/chegadas/matriculas?range=72h ` | Ir buscar as matriculas associadas ás para comparar com a matricula do camião detetado |
|POST    | `/api/v1/internal/chegadas/deteccao`   | Guardar deteção válida da associada à chegada certa|
|POST    |`/api/v1/internal/chegada/alerta`       | Guardar alertas de segurança |
|PATCH   | `/api/v1/internal/chegada/{id}/{hora_chegada}` | Atualizar hora de chegada de none para o timestamp|
|...     |


---

### Observações gerais:

* **query params** para filtros, por exemplo:

  ```
  /api/v1/chegadas?data=2025-11-21
  ```

* IDs inválidos devem retornar `404`.
* Todos endpoints que alteram dados devem ter autenticação e privilégios adequados.
