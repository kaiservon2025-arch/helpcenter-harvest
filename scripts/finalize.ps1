param(
  [Parameter(Mandatory=$true)][string]$Docx,
  [string]$Pdf = ""
)
$ErrorActionPreference = "Continue"
if (-not (Test-Path $Docx)) { Write-Output "MISSING $Docx"; exit 1 }
if (-not $Pdf) { $Pdf = [System.IO.Path]::ChangeExtension($Docx, ".pdf") }

Write-Output "opening $Docx"
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
$doc = $w.Documents.Open($Docx, $false, $false)
try {
  $doc.Fields.Update() | Out-Null
  # update TOC fields specifically (some builds need it twice)
  for ($i = 1; $i -le $doc.TablesOfContents.Count; $i++) {
    $doc.TablesOfContents.Item($i).Update() | Out-Null
  }
} catch { Write-Output "field update warn: $($_.Exception.Message)" }
$doc.Repaginate()
try { Write-Output ("pages: " + $doc.ComputeStatistics(2)) } catch {}
$doc.Save()
try {
  $doc.SaveAs([ref]$Pdf, [ref]17)
  Write-Output ("pdf: " + $Pdf + "  " + [math]::Round((Get-Item $Pdf).Length/1MB,1) + " MB")
} catch { Write-Output "pdf export failed: $($_.Exception.Message)" }
try { $doc.Close(0) } catch {}
try { $w.Quit() } catch {}
Write-Output "done"
