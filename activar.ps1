# Activar el entorno de coursera-dl
# Uso: .\activar.ps1

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\Activate.ps1
Write-Host ''
Write-Host 'Entorno listo. Ejemplos:' -ForegroundColor Green
Write-Host '  coursera-dl --help'
Write-Host '  coursera-dl -ca "TU_CAUTH" --path .\descargas NOMBRE-DEL-CURSO'
Write-Host ''
Write-Host 'El nombre del curso es el slug de la URL:' -ForegroundColor Yellow
Write-Host '  https://www.coursera.org/learn/NOMBRE-DEL-CURSO/...'
