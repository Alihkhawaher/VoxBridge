# VoxBridge - Create Desktop Shortcut with Icon
# Called by setup.bat after installation completes

$ErrorActionPreference = "SilentlyContinue"

# Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$IconPath = Join-Path $ScriptDir "voxbridge.ico"
$StartBat = Join-Path $ScriptDir "start.bat"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "VoxBridge.lnk"

# ── Generate icon using .NET System.Drawing ──────────────────
Add-Type -AssemblyName System.Drawing

$size = 256
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

# Background - dark rounded square
$bgBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(15, 15, 35))
$g.FillRectangle($bgBrush, 0, 0, $size, $size)

# Gradient circle background
$rect = New-Object System.Drawing.Rectangle(20, 20, 216, 216)
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$path.AddEllipse($rect)
$brush = New-Object System.Drawing.Drawing2D.PathGradientBrush($path)
$brush.CenterColor = [System.Drawing.Color]::FromArgb(93, 173, 226)  # Blue center
$brush.SurroundColors = @([System.Drawing.Color]::FromArgb(39, 174, 96))  # Green edge
$g.FillPath($brush, $path)

# Microphone body - black rectangle
$micRect = New-Object System.Drawing.Rectangle(88, 32, 80, 120)
$micBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(20, 20, 30))
$g.FillRectangle($micBrush, $micRect)
$g.DrawRectangle((New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(60, 60, 80), 2)), 88, 32, 80, 120)

# Fence/grille lines inside mic body
$linePen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(160, 160, 180), 2)
for ($i = 0; $i -lt 10; $i++) {
    $y = 42 + $i * 10
    $g.DrawLine($linePen, 94, $y, 162, $y)
}

# Mic stand
$standPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 255, 255), 5)
$g.DrawLine($standPen, 128, 152, 128, 195)   # Vertical
$g.DrawLine($standPen, 100, 195, 156, 195)    # Horizontal base
$g.DrawLine($standPen, 100, 195, 88, 210)     # Left foot
$g.DrawLine($standPen, 156, 195, 168, 210)    # Right foot

# Sound waves
$wavePen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(180, 255, 255, 255), 3)
$g.DrawArc($wavePen, 58, 60, 28, 60, -40, 80)
$g.DrawArc($wavePen, 170, 60, 28, 60, -40, 80)

# Save as .ico
$iconH = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($iconH)
$stream = [System.IO.File]::Create($IconPath)
$icon.Save($stream)
$stream.Close()
$icon.Dispose()
$bmp.Dispose()
$g.Dispose()

Write-Host "  [OK] Icon created: voxbridge.ico"

# ── Create desktop shortcut ──────────────────────────────────
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "cmd.exe"
$shortcut.Arguments = "/c `"$StartBat`""
$shortcut.WorkingDirectory = $ScriptDir
$shortcut.Description = "VoxBridge - STT + TTS Voice Server"
$shortcut.IconLocation = "$IconPath,0"
$shortcut.WindowStyle = 1  # Normal window
$shortcut.Save()

Write-Host "  [OK] Desktop shortcut created: VoxBridge.lnk"