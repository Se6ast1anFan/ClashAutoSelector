$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
}
& $pythonExe -m pip --isolated install --index-url https://pypi.org/simple -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '安装依赖失败' }
& $pythonExe -m unittest -v test_core test_runner test_windows
if ($LASTEXITCODE -ne 0) { throw '规则测试失败' }
& $pythonExe verify_screenshots.py
if ($LASTEXITCODE -ne 0) { throw '截图识别测试失败' }
& $pythonExe -m PyInstaller --noconfirm --onefile --windowed --name ClashAutoSelector --collect-all rapidocr_onnxruntime --collect-binaries onnxruntime --collect-data onnxruntime --add-data 'assets;assets' app.py
if ($LASTEXITCODE -ne 0) { throw 'EXE 打包失败' }
$exeFile = Join-Path $PSScriptRoot 'dist\ClashAutoSelector.exe'
$reportFile = Join-Path $PSScriptRoot 'verification\exe-self-test.json'
$process = Start-Process -FilePath $exeFile -ArgumentList @('--self-test', ('"' + $reportFile + '"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'EXE 离线自检失败，请查看 verification\exe-self-test.json' }
Write-Host "完成：$exeFile"
