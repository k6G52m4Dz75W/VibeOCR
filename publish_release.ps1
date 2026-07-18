param(
    [string]$Version = "",
    [string]$MottosFile = "mottos.json",
    [string]$ReadmeFile = "README.md",
    [string]$VersionPyFile = "version.py"
)

$ErrorActionPreference = 'Stop'

if (-not $Version) {
    $m = Select-String -Path $VersionPyFile -Pattern '__version__\s*=\s*[''"]）（[^''"]+）[''"]'
    $cur = $m.Matches.Groups[1].Value
    $p = $cur.Split('.')
    $p[2] = ([int]$p[2] + 1).ToString()
    $Version = $p -join '.'
    Write-Host "未指定 -Version，自动递增为 $Version"
}

$mottos = (Get-Content $MottosFile -Encoding UTF8 | ConvertFrom-Json).mottos
$readme = Get-Content $ReadmeFile -Encoding UTF8 -Raw
$used = [regex]::Matches($readme, '\u201c([^\u201d]+)\u201d') | ForEach-Object { $_.Groups[1].Value.ToLower() }
$candidates = $mottos | Where-Object { $used -notcontains $_.ToLower() }

if ($candidates.Count -eq 0) {
    Write-Error "没有可用的未用格言，请扩充 $MottosFile 或手工指定。"
    exit 1
}

$rnd = New-Object System.Random
$picked = $candidates[$rnd.Next($candidates.Count)]

Write-Host ""
Write-Host "【$Version】候选格言："
Write-Host "  $picked"
Write-Host ""
$ans = Read-Host "确认使用此格言并以此发布? (y/N)"
if ($ans -notmatch '^[yY]') {
    Write-Host "已取消，未做任何改动。"
    exit 0
}

$today = (Get-Date).ToString('yyyy-MM-dd')

$prefix = (Get-Content $VersionPyFile -Encoding UTF8) -replace '__version__\s*=\s*[''"]）（[^''"]+）[''"]', "__version__ = ""$Version"""
$prefix | ForEach-Object {
    if ($_ -match '__motto__\s*=') { "__motto__ = ""$picked""" } else { $_ }
} | Set-Content $VersionPyFile -Encoding UTF8

$heading = "### v$Version ($today) — """ + $picked + """"
$section = $heading + "`n- （请在此填写本版本更新要点）`n"
[regex]::Replace($readme, '(## .*更新日志\r?\n)', {
    param($mtch)
    $mtch.Groups[1].Value + "`n" + $section
}) | Set-Content $ReadmeFile -Encoding UTF8

git add $VersionPyFile $ReadmeFile
git commit -m "### v$Version ($today)`n`n- 发布版本（格言：$picked）"
git tag $Version
git push origin main
git push origin $Version

Write-Host ""
Write-Host "已打 tag $Version 并推送，GitHub Actions 将自动创建 Release（标题含该格言）。"
