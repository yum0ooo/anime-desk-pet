<#
    桌面宠物 / Desktop Pet —— 一键创建桌面快捷方式（Windows）
    ------------------------------------------------------------------
    用法（在本文件所在目录打开 PowerShell）：
        .\install.ps1                     创建名为“桌面宠物”的快捷方式
        .\install.ps1 -Name "Desktop Pet" 自定义快捷方式名字
        .\install.ps1 -Uninstall          删除快捷方式
#>
param(
    [string]$Name = '桌面宠物',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$root   = $PSScriptRoot
$script = Join-Path $root 'desktop_pet.py'
$icon   = Join-Path $root 'assets\icon.ico'
$lnk    = Join-Path ([Environment]::GetFolderPath('Desktop')) "$Name.lnk"

if ($Uninstall) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "已删除快捷方式：$lnk" }
    else { Write-Host "没有找到快捷方式：$lnk" }
    return
}

if (-not (Test-Path $script)) { throw "找不到 desktop_pet.py：$script" }

# 优先用 pythonw.exe：双击时不会弹黑框
function Find-Pythonw {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $patterns = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\pythonw.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\*\pythonw.exe'),
        'C:\Python3*\pythonw.exe',
        (Join-Path $env:ProgramFiles 'Python3*\pythonw.exe')
    )
    foreach ($p in $patterns) {
        $hit = Get-ChildItem $p -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$pythonw = Find-Pythonw
if (-not $pythonw) { throw '没有找到 pythonw.exe，请先安装 Python 3.9+ 并加入 PATH' }

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath       = $pythonw
$sc.Arguments        = '"' + $script + '"'
$sc.WorkingDirectory = $root
if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
$sc.Description = 'Desktop Pet - transparent, draggable, with a pomodoro timer'
$sc.Save()

Write-Host ""
Write-Host "✅ 快捷方式已创建：$lnk"
Write-Host "   解释器：$pythonw"
Write-Host ""

# 依赖自检
$python = $pythonw -replace 'pythonw\.exe$', 'python.exe'
if (Test-Path $python) {
    foreach ($mod in 'PIL', 'PySide6') {
        $ok = & $python -c "import $mod" 2>$null; $code = $LASTEXITCODE
        if ($code -eq 0) { Write-Host "   [ok]   $mod" }
        else { Write-Host "   [缺失] $mod  →  $python -m pip install -r requirements.txt" }
    }
}
Write-Host ""
