param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]

function Await-Result($Operation, [Type]$Type) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    return $method.MakeGenericMethod($Type).Invoke($null, @($Operation)).GetAwaiter().GetResult()
}

$languages = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
$language = $languages | Where-Object { $_.LanguageTag -like 'zh*' } | Select-Object -First 1
if (!$language) { $language = $languages | Where-Object { $_.LanguageTag -like 'en*' } | Select-Object -First 1 }
if (!$language) { throw 'Install a Chinese or English Windows OCR language, or configure Docling.' }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
$file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path -LiteralPath $Path).ProviderPath)) ([Windows.Storage.StorageFile])
$stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
    $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $text = ($result.Lines | ForEach-Object { $_.Text }) -join "`n"
        [IO.File]::WriteAllText($Output, (@{text=$text;language=$language.LanguageTag} | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
    } finally { $bitmap.Dispose() }
} finally { $stream.Dispose() }
