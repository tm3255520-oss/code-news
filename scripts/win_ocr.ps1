# win_ocr.ps1 - Windows OCR (Windows.Media.Ocr) word boxes, zero dependency.
#
# Why this helper: this machine has no tesseract / paddleocr / rapidocr / winocr,
# but Windows ships its own OCR language packs (Language.OCR~~~zh-CN was verified
# Installed), reachable through WinRT with nothing to install.
#
# NOTE 1: ASCII-only on purpose. Windows PowerShell 5.1 decodes .ps1 as the system
#         ANSI codepage (GBK here), so non-ASCII comments break parsing.
# NOTE 2: must run under Windows PowerShell 5.1 (powershell.exe). PowerShell 7
#         (pwsh) does not support the WinRT type projection used below.
#
# Usage: powershell.exe -NoProfile -File win_ocr.ps1 -Path <image> [-Lang zh-CN]
# Output: one JSON object per line: {"text":..,"x":..,"y":..,"w":..,"h":..}
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Lang = "zh-CN"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

$abs = (Resolve-Path -LiteralPath $Path).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($abs)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lang))
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { Write-Error "no OCR engine available (missing language pack)"; exit 3 }

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
    foreach ($word in $line.Words) {
        $r = $word.BoundingRect
        Write-Output ([ordered]@{
                text = $word.Text
                x    = [int]$r.X
                y    = [int]$r.Y
                w    = [int]$r.Width
                h    = [int]$r.Height
            } | ConvertTo-Json -Compress)
    }
}
