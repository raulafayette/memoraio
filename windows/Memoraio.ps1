param([switch]$Install, [string]$Distribution = "Ubuntu")
$ErrorActionPreference = "Stop"
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "Instale WSL 2 com Ubuntu seguindo docs/windows.md e reinicie o Windows."
}
$Root = Split-Path -Parent $PSScriptRoot
if ($Install) {
    $LinuxRoot = (& wsl.exe -d $Distribution -- wslpath -a -u $Root)
    if ($LASTEXITCODE -ne 0) { throw "Abra o Ubuntu e conclua sua configuração inicial." }
    & wsl.exe -d $Distribution -- bash ($LinuxRoot.Trim() + "/windows/install-wsl.sh")
    if ($LASTEXITCODE -ne 0) { throw "Instalação interrompida. O acervo existente foi preservado." }
    Write-Host "Instalado. Use Abrir.cmd. A edição Windows usa WSL 2 e abre no navegador."
    exit 0
}
$Url = (& wsl.exe -d $Distribution -- bash -lc 'cd "$HOME/.local/share/Memoraio/engine" && exec ../runtime/bin/python windows/launch.py')
if ($LASTEXITCODE -ne 0) { throw "Não foi possível abrir. Execute Instalar.cmd primeiro." }
$Url = ($Url | Select-Object -Last 1).Trim()
if ($Url -notmatch '^http://127\.0\.0\.1:8765/\?token=[A-Za-z0-9_-]+$') { throw "O serviço não retornou uma sessão local válida." }
Start-Process -FilePath $Url
