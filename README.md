# Pedidos Veloz

[![CI/CD](https://github.com/Seteshy/pedidos-veloz/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Seteshy/pedidos-veloz/actions/runs/45254549698)

**Arthur Lima Pereira · RA 133275**

Análise e Desenvolvimento de Sistemas · UNIFECAF

Cloud DevOps Orchestrating Containers and Micro Services

**Repositório:** https://github.com/Seteshy/pedidos-veloz

**Vídeo pitch:** https://youtu.be/AsaNpzbPS1k

## Proposta

Neste projeto, implementei um MVP de uma plataforma de pedidos para o cenário da Loja Veloz. O objetivo é integrar desenvolvimento local padronizado, conteinerização, Kubernetes, CI/CD e observabilidade em uma aplicação distribuída.

O pagamento é simulado e o estoque inicial de 100 camisetas é uma massa de teste. O projeto não processa transações financeiras reais.

## Arquitetura

```text
Cliente -> Gateway :8080 -> Pedidos -> Estoque
                              |
                              +-----> Pagamentos simulado

Pedidos, Estoque e Pagamentos -> PostgreSQL

Serviços -> /metrics/ -> Prometheus :9090
Serviços -> OpenTelemetry Collector -> Jaeger :16686
Logs JSON -> stdout
```

Adotei quatro serviços Python/FastAPI, executados em processos independentes. Uma imagem compartilhada utiliza `SERVICE_ROLE` para selecionar as responsabilidades de cada processo. Essa escolha reduz duplicação no MVP; a separação de releases pode ser feita em uma evolução.

O serviço de Pedidos registra a solicitação, reserva o estoque e consulta o pagamento. A aprovação confirma o pedido. A recusa devolve a reserva. O UUID identifica a operação e evita repetir seus efeitos. O PostgreSQL mantém o estado persistente, com tabelas de pedidos, estoque, reservas e pagamentos.

## Organização

| Pasta ou arquivo | Responsabilidade |
|---|---|
| `app/` | API, acesso ao banco e instrumentação |
| `db/` | Estrutura SQL e dados de teste |
| `compose.yaml` e `Dockerfile` | Ambiente local e construção da imagem |
| `k8s/base/` | Deployments, Services, HPA, banco e políticas |
| `k8s/lab/` | Metrics Server e carga HTTP |
| `k8s/overlays/registry/` | Imagem publicada, fixada por digest |
| `infra/` | Módulo Terraform do namespace |
| `observability/` | Configuração do Prometheus e Collector |
| `.github/workflows/` | Pipeline de validação e publicação |
| `tests/` e `scripts/` | Testes e preparação do ambiente Kubernetes |
| `docs/` e `relatorios/` | Referências, resultados e relatórios técnicos |

## Execução local

Pré-requisitos: Docker Desktop com engine Linux e Docker Compose v2. Os comandos são executados na raiz do repositório, em PowerShell.

O arquivo `.env` contém `POSTGRES_PASSWORD` e `IMAGE_TAG`, conforme `.env.example`. A senha é exclusiva do ambiente local e não é versionada. Na primeira configuração:

```powershell
if (!(Test-Path -LiteralPath .env)) {
    Copy-Item .env.example .env
}
```

Com `POSTGRES_PASSWORD` definido no `.env`, a inicialização ocorre com um comando:

```powershell
docker compose up -d --build --wait --wait-timeout 300
```

| Interface | Endereço |
|---|---|
| API e Swagger | http://localhost:8080/docs |
| Prometheus | http://localhost:9090 |
| Jaeger | http://localhost:16686 |

O Compose cria a rede `backend` e o volume `postgres-data`. Os healthchecks controlam a ordem de início das dependências. As portas publicadas são restritas a localhost. O SQL inicial é executado apenas em um volume vazio; alterações no arquivo não substituem migrações de um banco existente.

## API de pedidos

```powershell
$pedidoId = [guid]::NewGuid().ToString()
$corpo = @{ order_id=$pedidoId; sku='CAMISETA'; quantity=1 } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/orders -Method Post -ContentType 'application/json' -Body $corpo
Invoke-RestMethod "http://localhost:8080/orders/$pedidoId"
Invoke-RestMethod http://localhost:8080/stock
```

| Situação | Resultado |
|---|---|
| Reserva e pagamento aprovados | `CONFIRMED` |
| Produto inexistente ou estoque insuficiente | `REJECTED_STOCK` |
| Pagamento simulado recusado | `REJECTED_PAYMENT`, com devolução da reserva |
| Resultado remoto incerto | `MANUAL_REVIEW` |
| Mesmo UUID e mesmos dados | Retorno do pedido existente, sem nova baixa |
| Mesmo UUID e dados diferentes | HTTP 409 |

`simulate_decline=true` reproduz uma recusa de pagamento. Uma interrupção do processo pode deixar o pedido em `PENDING`; a conciliação desses casos é manual neste MVP.

## Testes

Teste de integração contra o Compose em execução:

```powershell
Get-Content -Raw scripts/smoke.py | docker compose exec -T -e BASE_URL=http://localhost:8000 gateway python -
```

O smoke verifica criação, consulta, idempotência, produto inexistente, entrada inválida e compensação da reserva. A compensação exige pelo menos duas unidades disponíveis no início. O pedido aprovado consome uma unidade de teste.

Testes unitários e lint com Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
```

Os testes unitários isolam banco e chamadas HTTP com mocks. O smoke complementa essa verificação utilizando os serviços e o PostgreSQL reais.

## Containers e segurança

O Dockerfile utiliza duas etapas, separando a instalação de dependências da execução. As aplicações usam UID 10001, filesystem somente leitura, diretório temporário gravável, capabilities removidas e bloqueio de elevação de privilégios. O PostgreSQL mantém seus dados em volume próprio.

As dependências diretas são fixadas. A imagem local usa `0.1.0`, e o pipeline publica tags `sha-COMMIT`. A referência usada no overlay do registry é fixada por digest. Imagens base por tag e dependências transitivas ainda podem mudar; não há garantia de reprodução byte a byte do build.

## Kubernetes e Terraform

O ambiente validado utiliza kind 0.31.0 e Kubernetes 1.34.3, com um nó dentro do Docker e API restrita a localhost. A preparação está no script:

```powershell
.\scripts\iniciar_kubernetes.ps1
$env:KUBECONFIG = (Resolve-Path .local/kubeconfig).Path
kubectl -n veloz get deployments,pods,pvc,hpa
```

O script obtém kind e Terraform oficiais com verificação de checksum, cria o cluster, carrega as imagens, provisiona o namespace com Terraform e aplica os manifests e o Metrics Server. Ferramentas, kubeconfig, credenciais e state ficam fora do versionamento. Um namespace existente sem state exige importação antes de ser gerenciado pelo Terraform.

Os Deployments usam duas réplicas iniciais, requests/limits, probes e PodDisruptionBudget. A atualização é rolling update, com `maxUnavailable=0` e `maxSurge=1`. O HPA utiliza CPU em 70% do request e varia de duas a quatro réplicas. O PostgreSQL utiliza StatefulSet e PVC de 1 GiB, sem alta disponibilidade ou backup automático.

O namespace aplica Pod Security Admission `restricted:v1.34`. Os pods usam seccomp, não recebem tokens de ServiceAccount automaticamente e executam sem root. ConfigMaps armazenam configuração e Secrets fornecem credenciais. A política de rede nega ingresso por padrão e permite os fluxos necessários; não há restrição de saída neste MVP.

No laboratório, o Metrics Server usa `--kubelet-insecure-tls` por causa do certificado kubelet local. Essa exceção não faz parte de uma configuração de produção com certificados confiáveis.

Aplicação da imagem pública verificada:

```powershell
kubectl apply -k k8s/overlays/registry
Get-Content -Raw scripts/smoke.py | kubectl -n veloz exec -i deployment/gateway -- env BASE_URL=http://localhost:8000 python -
kubectl -n veloz port-forward service/gateway 18080:8000
```

A API do cluster fica acessível em http://localhost:18080/docs enquanto o port-forward estiver ativo. O banco do cluster é independente do banco do Compose. A remoção do cluster pode remover seus dados; o volume local não constitui backup.

O módulo `infra/modules/ambiente` cria apenas o namespace em cluster existente. O state é local e protegido pelo `.gitignore`. Uma operação em equipe exigiria backend remoto com controle de acesso, criptografia e locking.

## CI/CD e registry

O workflow executa lint, 11 testes unitários, build, smoke no Compose e validação Terraform. Em seguida, cria um cluster kind temporário, aguarda os rollouts e executa o smoke. A publicação no GHCR ocorre após essas verificações, utilizando `GITHUB_TOKEN` com permissão de escrita em packages. Pull requests não publicam imagens.

- [Execução aprovada do pipeline](https://github.com/Seteshy/pedidos-veloz/actions/runs/45254549698)
- [Execução da imagem validada no cluster local](https://github.com/Seteshy/pedidos-veloz/actions/runs/45253072887)
- Imagem: `ghcr.io/seteshy/pedidos-veloz:sha-7e65a3b6644234a6dce9b579201c177dbeaa1e66`
- Digest: `sha256:743a37eea9ee676d12c06f3a0eafb83ab7003b9521655e631c5afef3e1dd7243`

O manifesto da imagem foi consultado sem autenticação e seu digest foi conferido. O overlay do registry utiliza essa referência. O deploy automático em cluster persistente permanece desabilitado; sua ativação depende de `ENABLE_DEPLOY`, environment `laboratorio` e `KUBECONFIG_B64`, com acesso de rede e permissões adequados. O job `deploy` ignorado nas execuções registradas corresponde a essa configuração.

As actions usam tags de versão. A fixação por SHA e o scan de vulnerabilidades são melhorias previstas. O cluster temporário do CI testa implantação e integração; os testes de HPA e políticas foram realizados no cluster local.

## Observabilidade e escala

Prometheus, Collector e Jaeger estão configurados no Compose. Métricas de requisições e duração são expostas em `/metrics/`. Os logs JSON incluem serviço, rota, status, duração e `trace_id`, sem corpo completo de pedido ou senha. As labels usam templates de rota para limitar cardinalidade. O OpenTelemetry instrumenta FastAPI e HTTPX e propaga contexto entre os serviços.

Consultas PromQL:

```promql
sum by (service) (veloz_http_requests_total)
sum by (service) (rate(veloz_http_requests_total[1m]))
histogram_quantile(0.95, sum by (le, service) (rate(veloz_http_duration_seconds_bucket[5m])))
```

O teste `k8s/lab/carga-http.yaml` executa GET `/stock` por 180 segundos, com 12 trabalhadores. Foram registradas 3.422 respostas bem-sucedidas e nenhum erro no gerador. Gateway e Estoque passaram de duas para quatro réplicas e retornaram a duas após a carga; Pedidos e Pagamentos permaneceram em duas. Esse resultado comprova a reação do HPA nesse teste, não uma capacidade comercial.

A coleta de métricas confirmou quatro alvos ativos, e um trace no Jaeger percorreu os quatro serviços. O Pod Security Admission rejeitou um pod root em dry-run. A NetworkPolicy permitiu Pedidos acessar Pagamentos e bloqueou o acesso direto do Gateway. O registro completo está em [docs/VALIDACAO.txt](docs/VALIDACAO.txt).

## Limitações e evolução

O pagamento simulado, o banco de uma réplica, a credencial compartilhada e a ausência de autenticação limitam o escopo ao MVP acadêmico. Uma evolução inclui pagamento real, conciliação automática, isolamento de permissões, migrações, backup e restauração testados.

Prometheus e Jaeger usam armazenamento efêmero no Compose. A coleta no cluster, retenção durável e alertas permanecem como evolução. Não há service mesh ou mensageria: o fluxo síncrono foi escolhido para limitar a complexidade. Não foram estabelecidos SLOs nem dimensionamento de produção.

## Operação

```powershell
docker compose ps
docker compose logs --tail 50 gateway pedidos estoque pagamentos
docker compose down
```

`docker compose down` mantém o volume. Alterar apenas a senha no `.env` não altera a credencial de um banco já inicializado.

## Relatórios e referências

- [Relatório teórico](relatorios/Relatorio_Teorico_Arthur_Lima.pdf)
- [Relatório prático](relatorios/Relatorio_Pratico_Arthur_Lima.pdf)
- [Referências consultadas](docs/REFERENCIAS.txt)
- [Vídeo pitch](https://youtu.be/AsaNpzbPS1k)

O Online Boutique, do [Google Cloud](https://github.com/GoogleCloudPlatform/microservices-demo), foi a referência pública para a decomposição de uma loja em microsserviços e a implantação em Kubernetes. As unidades da disciplina fundamentam as escolhas de arquitetura, containers, orquestração e automação. O Pedidos Veloz utiliza uma implementação própria com escopo reduzido.
