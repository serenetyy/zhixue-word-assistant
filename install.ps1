#Requires -Version 5.1
# 智学网单词助手 - 安装脚本（由 install.bat 调用）
# 用 PowerShell 写而不是批处理：中文显示和解析都更可靠
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = "智学网单词助手 - 安装" } catch {}
Set-Location -LiteralPath $PSScriptRoot

function Read-Line([string]$Prompt) {
    Write-Host $Prompt -NoNewline
    return [Console]::ReadLine()
}

function Pause-Exit([int]$Code) {
    [void](Read-Line "`n按回车退出...")
    exit 0
}

Write-Host "============================================"
Write-Host "  智学网单词助手 - 安装"
Write-Host "============================================"
Write-Host ""

# ---------- 1. 查找 Python 3.10+ ----------
function Test-Python([string]$Exe, [string[]]$Pre) {
    try {
        & $Exe @Pre -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Resolve-Python([string]$Exe, [string[]]$Pre) {
    try {
        $p = & $Exe @Pre -c "import sys; print(sys.executable)" 2>$null
        if ($p) { return ([string]$p).Trim() }
    } catch {}
    return $null
}

$pyPath = $null
if (Test-Python "python" @()) { $pyPath = "python" }
elseif (Test-Python "py" @("-3")) { $pyPath = Resolve-Python "py" @("-3") }
else {
    $dirs = @(
        "$env:LocalAppData\Programs\Python\Python312",
        "$env:LocalAppData\Programs\Python\Python311",
        "$env:LocalAppData\Programs\Python\Python310",
        "$env:ProgramFiles\Python312",
        "$env:ProgramFiles\Python311",
        "$env:ProgramFiles\Python310"
    )
    foreach ($d in $dirs) {
        $cand = Join-Path $d "python.exe"
        if ((Test-Path -LiteralPath $cand) -and (Test-Python $cand @())) { $pyPath = $cand; break }
    }
}

if (-not $pyPath) {
    Write-Host "[提示] 没有找到 Python 3.10 或更高版本。"
    $ans = Read-Line "是否自动下载并安装 Python 3.12.8？（约 27MB，装到当前用户，不需要管理员）[Y/n] "
    $yes = (-not $ans) -or ($ans.Trim().ToLower() -in @("y", "yes"))
    if (-not $yes) {
        Write-Host "请手动安装 Python 3.10+：https://www.python.org/downloads/windows/"
        Write-Host "安装时勾选 Add python.exe to PATH，然后重新运行 install.bat。"
        Pause-Exit 1
    }

    $installer = Join-Path $env:TEMP "python-3.12.8-amd64.exe"
    $urls = @(
        "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe",
        "https://registry.npmmirror.com/-/binary/python/3.12.8/python-3.12.8-amd64.exe",
        "https://mirrors.tuna.tsinghua.edu.cn/python/3.12.8/python-3.12.8-amd64.exe"
    )
    foreach ($u in $urls) {
        if ((Test-Path -LiteralPath $installer) -and ((Get-Item -LiteralPath $installer).Length -gt 10MB)) { break }
        Write-Host "下载中（失败会自动切换国内镜像）: $u"
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force }
            Invoke-WebRequest -Uri $u -OutFile $installer -UseBasicParsing -TimeoutSec 120
        } catch {
            Write-Host ("  该源失败: " + $_.Exception.Message)
        }
    }
    if (-not ((Test-Path -LiteralPath $installer) -and ((Get-Item -LiteralPath $installer).Length -gt 10MB))) {
        Write-Host "[失败] 下载失败，请检查网络后重试，或手动安装 Python。"
        Pause-Exit 1
    }

    Write-Host "正在静默安装 Python，需要一两分钟，请稍候..."
    Start-Process -FilePath $installer -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_launcher=1" -Wait
    $pyPath = "$env:LocalAppData\Programs\Python\Python312\python.exe"
    if (-not (Test-Path -LiteralPath $pyPath)) {
        Write-Host "[失败] 没找到安装后的 Python：$pyPath"
        Write-Host "请手动安装 Python 3.10+ 后重新运行 install.bat。"
        Pause-Exit 1
    }
}

Write-Host ("Python: " + (& $pyPath --version 2>&1))
Write-Host "[OK] Python 就绪。"
Write-Host ""

# ---------- 2. 虚拟环境 ----------
$ans = Read-Line "是否创建独立的虚拟环境 .venv？（推荐：依赖隔离，防止和别的项目库冲突）[Y/n] "
$useVenv = (-not $ans) -or ($ans.Trim().ToLower() -in @("y", "yes"))
$runPy = $pyPath
if ($useVenv) {
    Write-Host "正在创建 .venv ..."
    & $pyPath -m venv ".venv"
    $venvPy = Join-Path (Get-Location).Path ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        $runPy = $venvPy
        Write-Host "[OK] 虚拟环境已就绪。"
    } else {
        Write-Host "[警告] 创建虚拟环境失败，改用系统 Python。"
    }
} else {
    Write-Host "[提示] 将直接使用系统 Python 环境。"
}
Write-Host ""

# ---------- 3. 安装依赖 ----------
Write-Host "正在安装依赖（pip 走清华镜像，失败自动换官方源）..."
& $runPy -m pip install --disable-pip-version-check -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    Write-Host "镜像安装失败，改用官方源重试..."
    & $runPy -m pip install --disable-pip-version-check -r requirements.txt
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[失败] 依赖安装失败，请检查网络后重新运行 install.bat。"
    Pause-Exit 1
}
Write-Host "[OK] 依赖安装完成。"
Write-Host ""

# ---------- 4. 语音模型（可选） ----------
Write-Host "---------- 语音模型 ----------"
& $runPy "tools\fetch_models.py"

Write-Host ""
Write-Host "============================================"
Write-Host "  安装完成！"
Write-Host ""
Write-Host "  双击 run.bat 开始使用"
Write-Host "  第一次使用前：模拟器停在智学网【单词列表】页，"
Write-Host "  在 run.bat 里选 [4] 自定义参数，输入 capture 抓取单词表。"
Write-Host "============================================"
Pause-Exit 0
