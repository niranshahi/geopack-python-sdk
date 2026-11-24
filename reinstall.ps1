# powershell -ExecutionPolicy Bypass -File .\reinstall.ps1

$ErrorActionPreference = "Stop"

$target = Join-Path $PWD "venv\Scripts\geopack-sdk-mcp.exe"

# Stop MCP processes belonging to this venv
Get-CimInstance Win32_Process |
    Where-Object {
        $_.ExecutablePath -and
        $_.ExecutablePath -ieq $target
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }

# Reinstall the SDK
python -m pip install -e ".[mcp]" --force-reinstall --no-deps --disable-pip-version-check