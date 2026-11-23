# Pedidos Veloz

**Repositório público:** https://github.com/Seteshy/pedidos-veloz

[![CI/CD](https://github.com/Seteshy/pedidos-veloz/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Seteshy/pedidos-veloz/actions/runs/45253072887)

Projeto acadêmico de Cloud DevOps, por **Arthur Lima Pereira**, RA **133275**, Análise e Desenvolvimento de Sistemas, **UNIFECAF**.

MVP de pedidos com quatro microsserviços Python/FastAPI e PostgreSQL. A Loja Veloz é o cenário do enunciado; estoque inicial e pagamentos são exclusivamente didáticos. O pagamento **não integra um provedor financeiro real**.

**Vídeo pitch:** PENDENTE DE GRAVAÇÃO E PUBLICAÇÃO.

## Arquitetura

```text
Cliente -> Gateway :8080 -> Pedidos -> Estoque
                              |          |
                              +-> Pagamentos (simulado)
                              |          |
                              +---- PostgreSQL (volume)

Cada serviço -> /metrics/ -> Prometheus :9090
Cada serviço -> OpenTelemetry Collector -> Jaeger :16686
Logs JSON -> stdout (docker compose logs)
```

Uma imagem é reutilizada em quatro processos independentes, selecionados por `SERVICE_ROLE`. Isso reduz duplicação no MVP; em uma evolução, cada serviço poderia ter seu repositório e release. Somente o serviço responsável acessa sua tabela por meio do código, mas banco e credencial são compartilhados no laboratório. A separação por usuários/schemas e permissões é uma melhoria necessária para produção.

## Iniciar localmente

Pré-requisitos: Docker Desktop com engine Linux em execução e Docker Compose v2. Não é necessário contratar nuvem. Execute os comandos **na pasta deste README**.

1. Abra o Docker Desktop. `docker version` deve mostrar Client e Server.
2. Apenas na primeira configuração, crie o `.env` e escolha uma senha local. Se ele já existir e o ambiente estiver configurado, preserve o arquivo:

```powershell
if (!(Test-Path -LiteralPath .env)) {
    Copy-Item .env.example .env
}
notepad .env
```

3. Suba os serviços com um comando:

```powershell
docker compose up -d --build --wait --wait-timeout 300
```

4. Abra [Swagger do Gateway](http://localhost:8080/docs), [Prometheus](http://localhost:9090) e [Jaeger](http://localhost:16686).

O Compose cria a rede `backend`, o volume `postgres-data` e aguarda os healthchecks das dependências. As portas publicadas ficam restritas a localhost. O SQL de inicialização só roda quando o volume do PostgreSQL está vazio; alterar esse arquivo não migra um banco existente.

## Demonstrar e testar

No PowerShell:

```powershell
$pedidoId = [guid]::NewGuid().ToString()
$corpo = @{ order_id=$pedidoId; sku='CAMISETA'; quantity=1 } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/orders -Method Post -ContentType 'application/json' -Body $corpo
Invoke-RestMethod "http://localhost:8080/orders/$pedidoId"
Invoke-RestMethod http://localhost:8080/stock
```

Reenviar o mesmo ID e dados devolve o pedido já registrado. Reutilizar o ID com outros dados devolve HTTP 409. Para um novo pedido com pagamento recusado, use outro UUID e `simulate_decline=true`. A reserva será devolvida ao estoque. Produto inexistente gera `REJECTED_STOCK`. Timeouts no fluxo de pedidos geram `MANUAL_REVIEW`, pois um efeito remoto pode já ter ocorrido; não há retry automático nem reconciliador neste MVP. Se o processo morrer no meio do fluxo, um pedido pode permanecer `PENDING`, também exigindo conciliação.

Teste ponta a ponta, dentro da imagem já construída:

```powershell
docker compose exec -T -e BASE_URL=http://localhost:8000 gateway python - < scripts/smoke.py
```

**No PowerShell**, que não aceita esse redirecionamento de entrada, use:

```powershell
Get-Content -Raw scripts/smoke.py | docker compose exec -T -e BASE_URL=http://localhost:8000 gateway python -
```

Ou, se tiver Python 3.12+, execute `python scripts/smoke.py` no host. O teste usa biblioteca padrão, cria IDs novos, consome uma unidade de estoque e verifica confirmação, consulta, repetição do ID, falta de estoque e entrada inválida. A compensação de pagamento é verificada quando há pelo menos duas unidades disponíveis no início.

Testes unitários e lint (ambiente Python separado):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
```

Os testes unitários simulam banco e chamadas entre serviços; não substituem o smoke contra PostgreSQL real.

## Observar o fluxo

- Prometheus: `sum by (service) (rate(veloz_http_requests_total[1m]))` e `histogram_quantile(0.95, sum by (le, service) (rate(veloz_http_duration_seconds_bucket[5m])))`.
- Jaeger: faça pedidos, aguarde alguns segundos, selecione o serviço `gateway` e procure os traces. A instrumentação FastAPI/HTTPX propaga contexto entre serviços; o Collector envia spans por OTLP HTTP ao Jaeger. O tracing está ativo no Compose.
- Logs: `docker compose logs --tail 50 gateway pedidos estoque pagamentos`. São emitidos JSONs com serviço, rota, status, duração e trace_id, sem registrar senha nem corpo do pedido. Métricas usam templates de rota para evitar labels por UUID.

Não foram definidos objetivos de disponibilidade ou resultados de desempenho medidos. O alvo de CPU e os recursos dos manifests são pontos de partida didáticos a calibrar. Prometheus e Jaeger no Compose usam armazenamento efêmero; retenção durável e alertas são melhorias. Não há service mesh: OpenTelemetry demonstra o tracing com menos componentes. mTLS e controle avançado de tráfego ficam como evolução, não como funcionalidade implementada.

## Kubernetes local

O caminho verificado usa **kind 0.31.0 com Kubernetes 1.34.3**, em um nó dentro do Docker. Não exige habilitar o Kubernetes integrado do Docker Desktop. A API fica em localhost. O ambiente é de laboratório: não oferece tolerância a falha de nó e o volume do banco não deve ser tratado como backup. Remover o cluster pode remover seus dados.

Pré-requisitos: Docker Desktop em execução, `kubectl` e PowerShell. Execute na pasta deste README:

```powershell
.\scripts\iniciar_kubernetes.ps1
```

O script baixa kind e Terraform oficiais com verificação de checksum, cria o cluster, importa as imagens, usa Terraform para criar o namespace e aplica a base e o Metrics Server. Não apaga o cluster ou os volumes. Uma nova execução pode reaplicar o estado inicial de duas réplicas, que depois é controlado pelo HPA. Não reutilize o script contra produção.

Ferramentas ficam em `.tools/`; kubeconfig, senha e arquivos temporários em `.local/`; ambos estão excluídos do Git, do build e do ZIP. O state Terraform fica fora do Git e do ZIP. O arquivo de lock do provider é versionado. Para consultar em outro terminal:

```powershell
$env:KUBECONFIG = (Resolve-Path .local/kubeconfig).Path
kubectl get nodes
kubectl -n veloz get deployments,pods,pvc,hpa
Get-Content -Raw scripts/smoke.py | kubectl -n veloz exec -i deployment/gateway -- env BASE_URL=http://localhost:8000 python -
```

O smoke usa o banco do cluster, independente do banco do Compose. Para abrir a API do Kubernetes no navegador, execute e mantenha esse terminal aberto enquanto acessa [Swagger Kubernetes](http://localhost:18080/docs):

```powershell
kubectl -n veloz port-forward service/gateway 18080:8000
```

Fechar o navegador não encerra o cluster. `Ctrl+C` no terminal encerra apenas o port-forward. Não é preciso deixar navegadores abertos. O Compose continua disponível em localhost:8080 quando estiver em execução.

### Manifests e segurança

Os quatro Deployments têm duas réplicas iniciais, probes, requests/limits, PodDisruptionBudget e rolling update (`maxUnavailable=0`, `maxSurge=1`). O HPA usa CPU em 70% do request, entre duas e quatro réplicas. Os valores são didáticos e precisam ser dimensionados para um ambiente real. O PostgreSQL tem uma réplica com PVC, sem alta disponibilidade ou backup automático.

O namespace é criado pelo Terraform com Pod Security Admission `restricted:v1.34`. Aplicações usam UID 10001 e PostgreSQL Alpine usa UID/GID 70. Os pods não recebem tokens automaticamente, removem capabilities, bloqueiam elevação e usam seccomp e filesystem somente leitura com volumes graváveis. ConfigMap contém configuração; a senha é criada como Secret. Base64 sozinho não criptografa Secrets: produção também exige RBAC, criptografia em repouso e rotação.

A base nega ingresso por padrão e permite os fluxos necessários. Neste cluster foi testado: Pedidos acessa Pagamentos; Gateway acessa Estoque, mas não acessa Pagamentos diretamente. Também foi comprovada a rejeição de um pod root em dry-run pelo Pod Security Admission. O teste de rede comprova esses caminhos específicos, não uma auditoria de toda a rede. Não há política de restrição de saída.

### HPA e teste de carga

Metrics Server 0.8.0 fornece CPU para o HPA. O overlay `k8s/lab/metrics-server` usa `--kubelet-insecure-tls` somente por causa do certificado kubelet local do kind. Isso desativa essa validação de certificado nesse caminho: em produção, configure certificados confiáveis e remova a exceção.

```powershell
kubectl -n veloz top pods
kubectl apply -f k8s/lab/carga-http.yaml
kubectl -n veloz get hpa -w
```

O Job de carga faz apenas GET /stock por três minutos, com 12 trabalhadores, sem alterar estoque ou pedidos. Em outro terminal, acompanhe `kubectl -n veloz logs -f job/carga-http`. A política `allow-gateway-carga-lab` libera apenas esse gerador até o Gateway. O Job termina sozinho e é removido após dez minutos; para repetir depois da remoção, reaplique o arquivo. Caso o Job anterior ainda exista, não é preciso repetir a carga para validar a entrega: as evidências estão salvas.

Na execução de 23/11/2026, o Gateway e o Estoque aumentaram de duas para quatro réplicas, com 3.422 respostas bem-sucedidas e nenhum erro no gerador. Pedidos e Pagamentos permaneceram em duas. Esses números demonstram o mecanismo de escala neste teste, não capacidade de produção. Gateway e Estoque retornaram a duas réplicas após o fim da carga e a janela de estabilização; veja evidencias/hpa-retorno.json.

### Observabilidade e atualizações

Prometheus, Jaeger e Collector continuam demonstrados no Compose. Eles não foram instalados no cluster e o conjunto base não configura exportação OTLP. Para produção, provisionar coleta, armazenamento, retenção e alertas. Não há Ingress ou TLS público no laboratório; o acesso é por port-forward.

Para uma imagem publicada:

```powershell
kubectl -n veloz set image deployment/gateway gateway=ghcr.io/SEU_USUARIO/SEU_REPOSITORIO:sha-COMMIT
kubectl -n veloz rollout status deployment/gateway --timeout=180s
kubectl -n veloz rollout undo deployment/gateway
```

Repita para os demais serviços conforme a release. Registre a imagem no Kustomize ou use o pipeline para evitar voltar à tag local ao reaplicar a base. Rollback de Deployment não desfaz alterações no banco.

Fontes do laboratório: [kind](https://kind.sigs.k8s.io/docs/user/quick-start/), [Metrics Server](https://github.com/kubernetes-sigs/metrics-server/tree/v0.8.0) e [exportação de imagem por plataforma](https://docs.docker.com/reference/cli/docker/image/save/).

## CI/CD e registry

O projeto está publicado em https://github.com/Seteshy/pedidos-veloz, na branch `main`, com o conteúdo desta pasta na raiz. O workflow faz lint, testes unitários, build, smoke no Compose, validação Terraform e implantação em um cluster kind efêmero. Só depois publica no GHCR com `GITHUB_TOKEN` e tag `sha-COMMIT`. Essa tag permite rastrear o código; não use `latest` como referência de release. O pacote deve estar público para o cluster baixar sem login, ou será necessário configurar `imagePullSecrets` para um pacote privado.

O teste kind exercita rollout e smoke; não instala Metrics Server, não demonstra autoscaling e o CNI padrão não comprova a aplicação de NetworkPolicy. A execução remota de 23/11/2026 concluiu os três jobs obrigatórios: https://github.com/Seteshy/pedidos-veloz/actions/runs/45253072887.

O deploy em um cluster persistente é **opcional e desabilitado por padrão**. Para habilitar: criar o environment `laboratorio`, definir a variável de repositório `ENABLE_DEPLOY=true` e o secret de ambiente `KUBECONFIG_B64` com credencial de escopo mínimo. O cluster e namespace precisam existir, com o Secret `database` previamente criado e acesso às imagens. O runner hospedado do GitHub precisa alcançar o servidor Kubernetes: o cluster do seu computador normalmente não é acessível por ele. Para o trabalho, use o teste kind e o deploy local manual sem expor o cluster à internet.

As actions estão referenciadas por versão principal/versão de release; uma evolução de segurança é fixá-las por SHA revisado. Não há scan de vulnerabilidades neste MVP (opcional no enunciado). Dependências diretas são fixadas; as transitivas e imagens base por tag ainda podem mudar, portanto não se afirma reprodutibilidade bit a bit.

## Terraform

`infra/` contém um esqueleto funcional com provider Kubernetes, variáveis e módulo para criar o namespace com Pod Security Admission em **cluster já existente**. Não cria cluster, VMs nem recursos pagos. Antes do apply, confirme `kube_context`.

```powershell
.\.tools\terraform\terraform.exe -chdir=infra init
.\.tools\terraform\terraform.exe -chdir=infra fmt -check -recursive
.\.tools\terraform\terraform.exe -chdir=infra validate
.\.tools\terraform\terraform.exe -chdir=infra plan
```

Neste laboratório, o namespace já é gerenciado pelo Terraform; dispense o `kubectl apply -f k8s/namespace.yaml`. Se o namespace já existir, importe-o antes de gerenciá-lo: `.\.tools\terraform\terraform.exe -chdir=infra import module.ambiente.kubernetes_namespace_v1.this veloz`. Os manifests da base não criam o namespace. O state local é ignorado pelo Git; uma equipe real precisa de backend remoto com acesso controlado, criptografia e locking compatível. O esqueleto foi escolhido para demonstrar IaC sem escolher uma nuvem ou gerar custos.

## Encerrar e diagnosticar

`docker compose ps` mostra o estado; `docker compose logs db pedidos` ajuda a localizar falhas. Se o banco não estiver pronto, verifique senha e logs. Não altere a senha apenas no `.env` esperando que um volume antigo mude sua senha automaticamente. `docker compose down` encerra o ambiente e mantém o volume. O projeto não exige apagar dados para funcionar.

## Fontes e entregáveis

Veja `docs/REFERENCIAS.txt`, `docs/ROTEIRO_VIDEO.txt`, `docs/COMO_FINALIZAR.txt` e `docs/VALIDACAO.txt`. Os relatórios em PDF são gerados de `docs/relatorios.json` por `scripts/gerar_relatorios.py`. O case de referência é o Online Boutique do Google Cloud: https://github.com/GoogleCloudPlatform/microservices-demo. Ele demonstra uma loja em microsserviços; este projeto usa uma implementação própria simplificada e não reproduz a aplicação inteira ou seus resultados.

## Validação local realizada

Em 23/11/2026 foram concluídos o build, a subida dos oito contêineres e o smoke com PostgreSQL real. Prometheus confirmou quatro alvos ativos e Jaeger retornou um trace atravessando os quatro serviços. Veja `docs/VALIDACAO.txt` e `evidencias/`. Kubernetes e Terraform também foram verificados na etapa seguinte; o workflow remoto também foi concluído com sucesso.

## Validação remota no GitHub

Execução aprovada: https://github.com/Seteshy/pedidos-veloz/actions/runs/45253072887. Commit de código verificado: `7e65a3b6644234a6dce9b579201c177dbeaa1e66`. `validar`, `kubernetes-laboratorio` e `publicar` concluíram com sucesso. `deploy` foi ignorado porque a implantação em cluster persistente está desabilitada; não há implantação comercial em nuvem.

Imagem publicada pelo pipeline: `ghcr.io/seteshy/pedidos-veloz:sha-7e65a3b6644234a6dce9b579201c177dbeaa1e66`. O download anônimo do manifesto da imagem foi confirmado, e o digest coincide com o log de publicação. A imagem pública também foi aplicada no Kubernetes local e passou no smoke. Os logs e a evidência do Compose podem ser consultados na execução do Actions. O vídeo ainda precisa ser gravado e publicado.
Pelo overlay `k8s/overlays/registry`, a imagem fica fixada por digest. Após configurar namespace e Secret, use:

```powershell
kubectl apply -k k8s/overlays/registry
```

A base continua usando a imagem local para desenvolvimento. O deploy automático do workflow em cluster persistente continua desabilitado; a aplicação da imagem do registry foi uma verificação no cluster kind local.
