# Execute na sua maquina para preparar um laboratorio local. Nao cria recursos em nuvem.
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
Push-Location $raizProjeto
try {
    New-Item -ItemType Directory -Path '.tools','.local','evidencias' -Force | Out-Null
    docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Abra o Docker Desktop antes de continuar.' }

    if (!(Test-Path -LiteralPath '.tools\kind.exe')) {
        Invoke-WebRequest 'https://github.com/kubernetes-sigs/kind/releases/download/v0.31.0/kind-windows-amd64' -OutFile '.tools\kind.exe'
        Invoke-WebRequest 'https://github.com/kubernetes-sigs/kind/releases/download/v0.31.0/kind-windows-amd64.sha256sum' -OutFile '.tools\kind.sha256sum'
    }
    $hashKind = ((Get-Content -LiteralPath '.tools\kind.sha256sum' -Raw).Trim() -split '\s+')[0]
    if ((Get-FileHash -LiteralPath '.tools\kind.exe' -Algorithm SHA256).Hash -ne $hashKind) { throw 'Checksum kind divergente.' }

    if (!(Test-Path -LiteralPath '.tools\terraform\terraform.exe')) {
        Invoke-WebRequest 'https://releases.hashicorp.com/terraform/1.11.4/terraform_1.11.4_windows_amd64.zip' -OutFile '.tools\terraform.zip'
        if ((Get-FileHash -LiteralPath '.tools\terraform.zip' -Algorithm SHA256).Hash -ne '4e1dc85419dda723f2bb3afdf63a0d282a2de858588d56dd57d2e4e4c4c83f2b') { throw 'Checksum Terraform divergente.' }
        Expand-Archive -LiteralPath '.tools\terraform.zip' -DestinationPath '.tools\terraform' -Force
    }

    $clustersProjeto = @(& '.\.tools\kind.exe' get clusters)
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel consultar os clusters kind.' }
    if ('veloz-local' -notin $clustersProjeto) {
        & '.\.tools\kind.exe' create cluster --config 'k8s\kind-local.yaml' --kubeconfig '.local\kubeconfig' --wait 180s
    } else {
        & '.\.tools\kind.exe' export kubeconfig --name veloz-local --kubeconfig '.local\kubeconfig'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Falha na configuracao do cluster.' }
    $env:KUBECONFIG = (Resolve-Path -LiteralPath '.local\kubeconfig').Path

    docker build -t pedidos-veloz/app:0.1.0 .
    if ($LASTEXITCODE -ne 0) { throw 'Build falhou.' }
    docker pull --platform=linux/amd64 postgres:17-alpine
    if ($LASTEXITCODE -ne 0) { throw 'Download do PostgreSQL falhou.' }
    # Exportar apenas amd64 evita referencias a plataformas/atestacoes nao disponiveis.
    docker image save --platform=linux/amd64 --output '.local\imagens-amd64.tar' pedidos-veloz/app:0.1.0 postgres:17-alpine
    if ($LASTEXITCODE -ne 0) { throw 'Exportacao de imagens falhou.' }
    & '.\.tools\kind.exe' load image-archive '.local\imagens-amd64.tar' --name veloz-local
    if ($LASTEXITCODE -ne 0) { throw 'Importacao de imagens falhou.' }

    $terraformProjeto = Join-Path $raizProjeto '.tools\terraform\terraform.exe'
    & $terraformProjeto '-chdir=infra' init '-backend=false'
    if ($LASTEXITCODE -ne 0) { throw 'Terraform init falhou.' }
    & $terraformProjeto '-chdir=infra' fmt '-check' '-recursive'
    if ($LASTEXITCODE -ne 0) { throw 'Terraform fmt falhou.' }
    & $terraformProjeto '-chdir=infra' validate
    if ($LASTEXITCODE -ne 0) { throw 'Terraform validate falhou.' }
    & $terraformProjeto '-chdir=infra' plan '-out=../.local/namespace.tfplan'
    if ($LASTEXITCODE -ne 0) { throw 'Terraform plan falhou. Se o namespace existir sem state, consulte a importacao no README.' }
    & $terraformProjeto '-chdir=infra' apply '../.local/namespace.tfplan'
    if ($LASTEXITCODE -ne 0) { throw 'Terraform apply falhou.' }

    if (!(Test-Path -LiteralPath '.local\database.env')) {
        $bytesSenhaProjeto = New-Object byte[] 24
        $geradorProjeto = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $geradorProjeto.GetBytes($bytesSenhaProjeto) } finally { $geradorProjeto.Dispose() }
        $senhaProjeto = [Convert]::ToBase64String($bytesSenhaProjeto)
        [IO.File]::WriteAllText((Join-Path $raizProjeto '.local\database.env'), "password=$senhaProjeto", (New-Object System.Text.UTF8Encoding($false)))
        Remove-Variable senhaProjeto,bytesSenhaProjeto
    }
    $secretProjeto = kubectl -n veloz get secret database --ignore-not-found -o name
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao consultar o Secret do banco.' }
    if (!$secretProjeto) {
        kubectl -n veloz create secret generic database --from-env-file=.local/database.env
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o Secret.' }
    }
    kubectl apply -k k8s/base
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao aplicar a base.' }
    kubectl -n veloz rollout status statefulset/db --timeout=240s
    if ($LASTEXITCODE -ne 0) { throw 'Banco nao ficou pronto.' }
    foreach ($servicoProjeto in @('gateway','pedidos','estoque','pagamentos')) {
        kubectl -n veloz rollout status "deployment/$servicoProjeto" --timeout=240s
        if ($LASTEXITCODE -ne 0) { throw "Servico $servicoProjeto nao ficou pronto." }
    }
    kubectl apply -k k8s/lab/metrics-server
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao aplicar Metrics Server.' }
    kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s
    if ($LASTEXITCODE -ne 0) { throw 'Metrics Server nao ficou pronto.' }
    kubectl -n veloz get deployments,pvc,hpa
    Write-Output 'Laboratorio pronto. Para acesso no navegador: kubectl -n veloz port-forward service/gateway 18080:8000'
} finally {
    Pop-Location
}
