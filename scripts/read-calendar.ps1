param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Path = (Resolve-Path -LiteralPath $Path).ProviderPath
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]

function Await-Result($Operation, [Type]$Type) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    $task = $method.MakeGenericMethod($Type).Invoke($null, @($Operation))
    return $task.GetAwaiter().GetResult()
}

$language = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -like 'zh*' } | Select-Object -First 1
if (!$language) { throw 'Chinese OCR language is unavailable. Set the semester date manually.' }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
$file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$pdf = Await-Result ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
if ($pdf.PageCount -gt 4) { throw 'The school calendar must contain at most four pages.' }
$texts = @()
for ($index = 0; $index -lt $pdf.PageCount; $index++) {
    $page = $pdf.GetPage($index)
    $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
    try {
        $options = [Windows.Data.Pdf.PdfPageRenderOptions]::new()
        $options.DestinationWidth = [uint32][Math]::Min(2400, [Windows.Media.Ocr.OcrEngine]::MaxImageDimension)
        $actionMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and !$_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
        } | Select-Object -First 1
        $actionTask = $actionMethod.Invoke($null, @($page.RenderToStreamAsync($stream, $options)))
        $null = $actionTask.GetAwaiter().GetResult()
        $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $texts += ($result.Lines | ForEach-Object { $_.Text }) -join "`n"
        } finally { $bitmap.Dispose() }
    } finally { $page.Dispose(); $stream.Dispose() }
}
@{ pages=$texts; language=$language.LanguageTag } | ConvertTo-Json -Depth 3 -Compress
