Add-Type -AssemblyName System.Drawing

$sourcePath = 'C:\Users\10239\AppData\Local\Temp\codex-clipboard-a4ed9fda-eef5-401e-8642-6ebf0a5a3dad.png'
$outputPath = Join-Path $PSScriptRoot 'stamp-transparent.png'

$source = [System.Drawing.Bitmap]::FromFile($sourcePath)
$output = New-Object System.Drawing.Bitmap($source.Width, $source.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)

for ($y = 0; $y -lt $source.Height; $y++) {
    for ($x = 0; $x -lt $source.Width; $x++) {
        $pixel = $source.GetPixel($x, $y)
        $alpha = 255 - [Math]::Min($pixel.G, $pixel.B)
        if ($alpha -le 0) {
            $output.SetPixel($x, $y, [System.Drawing.Color]::Transparent)
        } else {
            $output.SetPixel($x, $y, [System.Drawing.Color]::FromArgb($alpha, 255, 0, 0))
        }
    }
}

$output.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$output.Dispose()
$source.Dispose()
