# UTF-8 BOM Switch
# Run from anywhere. You will be asked for a folder or file path.
# Add / remove never re-encodes: it only inserts or strips the UTF-8 BOM (EF BB BF).
# Check encoding is read-only.

$ErrorActionPreference = "Continue"

function Get-DetectedEncoding([byte[]]$bytes) {
    if ($null -eq $bytes -or $bytes.Length -eq 0) { return "Empty" }

    if ($bytes.Length -ge 4 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE -and $bytes[2] -eq 0x00 -and $bytes[3] -eq 0x00) {
        return "UTF-32 LE"
    }
    if ($bytes.Length -ge 4 -and $bytes[0] -eq 0x00 -and $bytes[1] -eq 0x00 -and $bytes[2] -eq 0xFE -and $bytes[3] -eq 0xFF) {
        return "UTF-32 BE"
    }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return "UTF-8 BOM"
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { return "UTF-16 LE" }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) { return "UTF-16 BE" }

    if ($bytes.Length -ge 4 -and $bytes.Length % 2 -eq 0) {
        if ($bytes[0] -eq 0x3C -and $bytes[1] -eq 0x00 -and $bytes[2] -eq 0x3F -and $bytes[3] -eq 0x00) {
            return "UTF-16 LE"
        }
        if ($bytes[0] -eq 0x00 -and $bytes[1] -eq 0x3C -and $bytes[2] -eq 0x00 -and $bytes[3] -eq 0x3F) {
            return "UTF-16 BE"
        }
    }

    $utf8 = New-Object System.Text.UTF8Encoding $false, $true
    try {
        [void]$utf8.GetString($bytes)
        return "UTF-8"
    }
    catch {
        $limit = [Math]::Min($bytes.Length, 1024)
        $controls = 0
        for ($i = 0; $i -lt $limit; $i++) {
            $b = $bytes[$i]
            $isTextControl = ($b -eq 0x09 -or $b -eq 0x0A -or $b -eq 0x0D)
            if ($b -eq 0x00 -or ($b -lt 0x20 -and -not $isTextControl) -or $b -eq 0x7F) {
                $controls++
            }
        }
        if ($limit -gt 0 -and ($controls / $limit) -gt 0.12) { return "Binary" }
        return "Windows-1252"
    }
}

function Read-UserPath {
    while ($true) {
        $hint = ""
        if ($script:lastPath) { $hint = " [$script:lastPath]" }
        $raw = Read-Host "Input folder or file path$hint"
        if ([string]::IsNullOrWhiteSpace($raw)) {
            if ($script:lastPath) { $raw = $script:lastPath }
            else { continue }
        }
        $raw = $raw.Trim().Trim('"').Trim("'")
        if (-not (Test-Path -LiteralPath $raw)) {
            Write-Host "Path not found: $raw" -ForegroundColor Yellow
            continue
        }
        $item = Get-Item -LiteralPath $raw
        $script:lastPath = $item.FullName
        return $item
    }
}

function Read-Extension {
    while ($true) {
        $hint = if ($script:lastExt) { " [$script:lastExt]" } else { " (e.g. sdlxliff, xml, txt)" }
        $ext = Read-Host "Input file extension to process$hint"
        if ([string]::IsNullOrWhiteSpace($ext)) {
            if ($script:lastExt) { return $script:lastExt }
            continue
        }
        $ext = ($ext.Trim() -replace '^\.+', '')
        if ([string]::IsNullOrWhiteSpace($ext)) { continue }
        $script:lastExt = $ext
        return $ext
    }
}

$script:lastPath = ""
$script:lastExt = ""

Write-Host ""
Write-Host "UTF-8 BOM Switch" -ForegroundColor Cyan
Write-Host "Add or remove the UTF-8 BOM, or check each file's encoding."
Write-Host "The script can run from anywhere; paste a folder or file path when asked."

while ($true) {
    Write-Host ""
    Write-Host "1) Add BOM         (UTF-8 -> UTF-8 BOM)"
    Write-Host "2) Remove BOM      (UTF-8 BOM -> UTF-8)"
    Write-Host "3) Check encoding  (read-only)"
    Write-Host "4) Exit"
    do {
        $choice = Read-Host "Choose option (1, 2, 3 or 4)"
    } while ($choice -notin @("1", "2", "3", "4"))

    if ($choice -eq "4") {
        Write-Host "Bye."
        break
    }

    Write-Host ""
    $target = Read-UserPath

    if ($target.PSIsContainer) {
        $ext = Read-Extension
        $filter = "*.$ext"
        $files = @(Get-ChildItem -LiteralPath $target.FullName -File -Filter $filter)
        $scope = $target.FullName
    }
    else {
        $files = @($target)
        $filter = $target.Name
        $scope = $target.DirectoryName
    }

    if ($files.Count -eq 0) {
        Write-Host "No files matching $filter in $scope" -ForegroundColor Yellow
        Write-Host "Back to menu."
        continue
    }

    $modeLabel = switch ($choice) {
        "1" { "ADD BOM" }
        "2" { "REMOVE BOM" }
        default { "CHECK ENCODING" }
    }
    Write-Host ""
    Write-Host ("Found {0} file(s) matching {1}" -f $files.Count, $filter)
    Write-Host ("Path: {0}" -f $scope)
    Write-Host ("Mode: {0}" -f $modeLabel)

    if ($choice -ne "3") {
        $confirm = Read-Host "Continue? (Y/N)"
        if ($confirm -notin @("Y", "y")) {
            Write-Host "Cancelled. Back to menu."
            continue
        }
    }

    $added = 0
    $removed = 0
    $skipped = 0
    $errors = 0
    $encodingCounts = @{}

    foreach ($file in $files) {
        $filePath = $file.FullName
        try {
            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            $encoding = Get-DetectedEncoding $bytes

            if ($choice -eq "3") {
                if ($encodingCounts.ContainsKey($encoding)) {
                    $encodingCounts[$encoding]++
                }
                else {
                    $encodingCounts[$encoding] = 1
                }

                if ($bytes.Length -ge 3) {
                    $prefix = ("{0:X2} {1:X2} {2:X2}" -f $bytes[0], $bytes[1], $bytes[2])
                }
                elseif ($bytes.Length -eq 2) {
                    $prefix = ("{0:X2} {1:X2}" -f $bytes[0], $bytes[1])
                }
                elseif ($bytes.Length -eq 1) {
                    $prefix = ("{0:X2}" -f $bytes[0])
                }
                else {
                    $prefix = "-"
                }

                $color = "Gray"
                if ($encoding -eq "UTF-8 BOM") { $color = "Green" }
                elseif ($encoding -eq "UTF-8") { $color = "White" }
                elseif ($encoding -eq "Empty") { $color = "DarkGray" }
                else { $color = "Yellow" }

                Write-Host ("{0,-14}  {1,-10}  {2}" -f $encoding, $prefix, $file.Name) -ForegroundColor $color
                continue
            }

            $isUtf16 = $encoding -like "UTF-16*" -or $encoding -like "UTF-32*"
            if ($isUtf16) {
                Write-Host "Skipped ($encoding, not UTF-8): $($file.Name)" -ForegroundColor Yellow
                $skipped++
                continue
            }

            $hasBOM = ($encoding -eq "UTF-8 BOM")

            if ($choice -eq "1") {
                if ($encoding -notin @("UTF-8", "UTF-8 BOM", "Empty")) {
                    Write-Host "Skipped ($encoding, not valid UTF-8): $($file.Name)" -ForegroundColor Yellow
                    $skipped++
                    continue
                }
                if (-not $hasBOM) {
                    $newLength = $bytes.Length + 3
                    $newContent = New-Object byte[] $newLength
                    $newContent[0] = 0xEF
                    $newContent[1] = 0xBB
                    $newContent[2] = 0xBF
                    if ($bytes.Length -gt 0) {
                        [System.Array]::Copy($bytes, 0, $newContent, 3, $bytes.Length)
                    }
                    [System.IO.File]::WriteAllBytes($filePath, $newContent)
                    Write-Host "Added BOM to: $($file.Name)" -ForegroundColor Green
                    $added++
                }
                else {
                    Write-Host "Already has BOM: $($file.Name)"
                    $skipped++
                }
            }
            else {
                if ($hasBOM) {
                    $newLength = $bytes.Length - 3
                    if ($newLength -le 0) {
                        $newContent = New-Object byte[] 0
                    }
                    else {
                        $newContent = New-Object byte[] $newLength
                        [System.Array]::Copy($bytes, 3, $newContent, 0, $newLength)
                    }
                    [System.IO.File]::WriteAllBytes($filePath, $newContent)
                    Write-Host "Removed BOM from: $($file.Name)" -ForegroundColor Green
                    $removed++
                }
                else {
                    Write-Host "No BOM to remove: $($file.Name)"
                    $skipped++
                }
            }
        }
        catch {
            Write-Host "Error on $($file.Name): $($_.Exception.Message)" -ForegroundColor Red
            $errors++
        }
    }

    Write-Host ""
    if ($choice -eq "3") {
        foreach ($key in ($encodingCounts.Keys | Sort-Object)) {
            Write-Host ("{0}: {1}" -f $key, $encodingCounts[$key])
        }
        if ($errors -gt 0) {
            Write-Host ("Errors: {0}" -f $errors) -ForegroundColor Red
        }
    }
    elseif ($choice -eq "1") {
        Write-Host ("Added: {0}  |  Skipped: {1}  |  Errors: {2}" -f $added, $skipped, $errors)
    }
    else {
        Write-Host ("Removed: {0}  |  No BOM: {1}  |  Errors: {2}" -f $removed, $skipped, $errors)
    }
    Write-Host "Done. Back to menu."
}

Read-Host "Press Enter to close"
