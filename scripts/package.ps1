$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ZipPath = Join-Path $ProjectRoot "deckhud-lite.zip"

if (-not (Test-Path (Join-Path $ProjectRoot "dist/index.js"))) {
    throw "dist/index.js가 없습니다. 먼저 pnpm run build를 실행하세요."
}

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

python (Join-Path $PSScriptRoot "package_plugin.py") $ProjectRoot $ZipPath
python (Join-Path $PSScriptRoot "validate_zip.py") $ZipPath
Write-Output $ZipPath
