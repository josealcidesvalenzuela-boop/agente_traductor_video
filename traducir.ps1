# Agrega las DLLs de CUDA al PATH y lanza el pipeline.
# Uso: .\traducir.ps1 demo.mkv --source en --target es

$base = "$PSScriptRoot\.venv\Lib\site-packages\nvidia"
if (Test-Path $base) {
    $nvDirs = Get-ChildItem $base -Directory |
        ForEach-Object { "$($_.FullName)\bin" } |
        Where-Object { Test-Path $_ }
    $env:PATH = ($nvDirs -join ";") + ";$env:PATH"
}

uv run python "$PSScriptRoot\main.py" @args
