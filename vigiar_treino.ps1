# Vigia o treino: repassa o progresso (a cada 25 passos, avaliações, erros) e o espaço livre do C:.
# Se o C: ficar abaixo de 3 GB, para o treino para não encher o disco.
param([string]$Log, [switch]$SoNovas)
$lidas = 0
# -SoNovas: ao rearmar o vigia, não repete o que já foi informado
if ($SoNovas -and (Test-Path $Log)) { $lidas = @(Get-Content $Log -Encoding UTF8 -ErrorAction SilentlyContinue).Count }
$ultimoAvisoDisco = 99
$tempMax = 0
$avisouCalor = $false
while ($true) {
    if (Test-Path $Log) {
        $linhas = @(Get-Content $Log -Encoding UTF8 -ErrorAction SilentlyContinue)
        for ($i = $lidas; $i -lt $linhas.Count; $i++) {
            $l = $linhas[$i]
            if ($l -match 'dados:|antes do treino|avalia|passo \d*(00)/\d+|situa|Traceback|Error|error|modelo salvo|retomando|out of memory') {
                if ($l -match '^passo') { $l = "$l | placa agora $temp C (máx. até aqui $tempMax C)" }
                Write-Output $l
            }
        }
        $lidas = $linhas.Count
    }
    # Temperatura da placa: avisa acima de 90 C; para o treino em 93 C (máxima de operação da RTX 3060).
    $temp = [int](nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)
    if ($temp -gt $tempMax) { $tempMax = $temp }
    if ($temp -ge 93) {
        Get-Process python -ErrorAction SilentlyContinue | Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -like "*treinar_laya*" } | Stop-Process -Force
        Write-Output "Placa a $temp C: TREINO PARADO para proteger a placa"
        exit 1
    }
    if ($temp -ge 90 -and -not $avisouCalor) { Write-Output "Atenção: placa a $temp C"; $avisouCalor = $true }
    if ($temp -lt 88) { $avisouCalor = $false }
    $livre = (Get-PSDrive C).Free / 1GB
    if ($livre -lt 3) {
        Get-Process python -ErrorAction SilentlyContinue | Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -like "*treinar_laya*" } | Stop-Process -Force
        Write-Output ("C: com {0:N2} GB livres: TREINO PARADO para proteger o disco" -f $livre)
        exit 1
    }
    if ($livre -lt 5 -and [math]::Floor($livre) -lt $ultimoAvisoDisco) {
        Write-Output ("Atenção: C: com {0:N2} GB livres" -f $livre)
        $ultimoAvisoDisco = [math]::Floor($livre)
    }
    $vivo = Get-Process python -ErrorAction SilentlyContinue | Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -like "*treinar_laya*" }
    if (-not $vivo -and $lidas -gt 0) { Write-Output "processo do treino terminou"; exit 0 }
    Start-Sleep 15
}
