param([string]$AppDirectory, [switch]$Rollback, [switch]$Yes)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$script:manifest = $null
$script:runtimeRoot = $null
$script:backupRoot = $null
$script:statePath = $null
$script:state = $null

function Assert-NoLinks([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $entry = Get-Item -LiteralPath $cursor -Force
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $entry.LinkType) { throw ('拒绝目录链接/文件链接：' + $cursor) }
        }
        $next = [IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
        if (-not $next -or $next -eq $cursor) { break }
        $cursor = $next
    }
}
function Program-Path([string]$Root, [string]$Relative) {
    if ($Relative -notmatch '^(slider-screen-service\.exe|_internal/[^\\:]+)$' -or $Relative.StartsWith('/') -or $Relative.Contains('\')) { throw ('非法补丁路径：' + $Relative) }
    $parts = $Relative.Split('/')
    foreach ($part in $parts) {
        if (-not $part -or $part -in @('.','..','config','content','browser-profile','logs','patch-backups') -or $part.EndsWith('.') -or $part.EndsWith(' ')) { throw ('非法补丁路径段：' + $Relative) }
    }
    if ([IO.Path]::GetExtension($Relative) -in @('.key','.mp4','.webm','.mov','.mkv','.avi')) { throw '拒绝媒体或密钥载荷。' }
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $full = [IO.Path]::GetFullPath((Join-Path $Root $Relative.Replace('/','\')))
    if (-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw '补丁路径超出目标目录。' }
    Assert-NoLinks $full
    return $full
}
function Hash([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Save-State {
    $json = ConvertTo-Json -InputObject $script:state -Depth 10
    [IO.File]::WriteAllText($script:statePath, $json, (New-Object Text.UTF8Encoding($false)))
}
function Assert-Stopped {
    $targetExe = Join-Path $script:runtimeRoot 'slider-screen-service.exe'
    $profile = Join-Path $script:runtimeRoot 'browser-profile'
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if ($process.Name -eq 'slider-screen-service.exe') {
            if (-not $process.ExecutablePath) { throw '无法核实正在运行的播放器路径，请先正常退出播放器后台再重试。' }
            if ([IO.Path]::GetFullPath($process.ExecutablePath).Equals($targetExe,[StringComparison]::OrdinalIgnoreCase)) { throw ('目标播放器仍在运行（PID ' + $process.ProcessId + '），请先退出数字人Host和后台。工具不会强制结束进程。') }
        }
        if ($process.Name -in @('msedge.exe','msedgewebview2.exe') -and $process.CommandLine -and $process.CommandLine.IndexOf($profile,[StringComparison]::OrdinalIgnoreCase) -ge 0) { throw '目标播放器的专用浏览器仍在运行，请先正常退出。' }
    }
}
function Restore-Files($Entries) {
    # Restore only listed program files, never directories/configuration/media.
    foreach ($item in $Entries) {
        Assert-Stopped
        $destination = Program-Path $script:runtimeRoot $item.path
        if ($item.existed) {
            $saved = Program-Path (Join-Path $script:backupRoot 'files') $item.path
            if (-not (Test-Path -LiteralPath $saved -PathType Leaf) -or (Hash $saved) -ne $item.oldSha256) { throw ('备份校验失败：' + $item.path) }
            if ((Test-Path -LiteralPath $destination -PathType Leaf) -and (Hash $destination) -eq $item.oldSha256) { continue }
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
            [IO.File]::Copy($saved,$destination,$true)
            if ((Hash $destination) -ne $item.oldSha256) { throw ('恢复校验失败：' + $item.path) }
        } elseif (Test-Path -LiteralPath $destination -PathType Leaf) {
            # Exact validated program file added by this patch; no recursive deletion.
            Remove-Item -LiteralPath $destination -Force
        }
    }
}

try {
    Set-Location -LiteralPath $env:TEMP
    Assert-NoLinks $PSScriptRoot
    $script:manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'patch-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema -ne 'rail.runtime-delta-patch/v1' -or $manifest.baseVersion -ne '1.1.7' -or $manifest.appId -ne 'cdut-slider-screen' -or $manifest.patchId -notmatch '^[a-z0-9-]{1,80}$') { throw '补丁清单格式或版本不正确。' }
    if ($manifest.baseExeSha256 -notmatch '^[a-f0-9]{64}$' -or $manifest.newExeSha256 -notmatch '^[a-f0-9]{64}$') { throw '补丁程序哈希不正确。' }
    $fileNames = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($file in @($manifest.files)) {
        if (-not $fileNames.Add([string]$file.path) -or $file.sha256 -notmatch '^[a-f0-9]{64}$') { throw '补丁文件列表存在重复或错误哈希。' }
        $payload = Program-Path (Join-Path $PSScriptRoot 'payload') $file.path
        if (-not (Test-Path -LiteralPath $payload -PathType Leaf) -or (Hash $payload) -ne $file.sha256 -or (Get-Item -LiteralPath $payload).Length -ne $file.bytes) { throw ('补丁损坏或缺失：' + $file.path) }
    }
    if (-not $fileNames.Contains('slider-screen-service.exe')) { throw '补丁缺少主程序。' }
    $exeEntry = @($manifest.files | Where-Object path -eq 'slider-screen-service.exe')[0]
    if ($exeEntry.sha256 -ne $manifest.newExeSha256) { throw '主程序哈希与清单不一致。' }
    if (-not $AppDirectory) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object Windows.Forms.FolderBrowserDialog
        $dialog.Description = '选择现场原 app 文件夹（其中包含 app.json 和 runtime）'
        $dialog.ShowNewFolderButton = $false
        try {
            if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { Write-Host '已取消，未修改任何文件。'; exit 0 }
            $AppDirectory = $dialog.SelectedPath
        } finally { $dialog.Dispose() }
    }
    Assert-NoLinks $AppDirectory
    $AppDirectory = (Resolve-Path -LiteralPath $AppDirectory).Path.TrimEnd('\')
    if (-not (Test-Path -LiteralPath $AppDirectory -PathType Container) -or $AppDirectory -eq [IO.Path]::GetPathRoot($AppDirectory).TrimEnd('\')) { throw '不能将磁盘根目录作为 app。' }
    foreach ($forbidden in @('D:\成都理工大学70周年视频播放器','D:\成都理工大学70周年投影播放器','D:\中控软件穿越成理双视频')) {
        if ($AppDirectory.Equals($forbidden,[StringComparison]::OrdinalIgnoreCase) -or $AppDirectory.StartsWith($forbidden+'\',[StringComparison]::OrdinalIgnoreCase)) { throw '此补丁不能用于70周年展示系统。' }
    }
    $appInfo = Get-Content -LiteralPath (Join-Path $AppDirectory 'app.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($appInfo.appId -ne 'cdut-slider-screen' -or $appInfo.type -ne 'service') { throw '所选目录不是青藏高原滑轨屏 app。' }
    $script:runtimeRoot = Join-Path $AppDirectory 'runtime'
    Assert-NoLinks $runtimeRoot
    $targetExe = Program-Path $runtimeRoot 'slider-screen-service.exe'
    $releaseInfo = Join-Path (Split-Path $AppDirectory -Parent) 'release-info.json'
    if (Test-Path -LiteralPath $releaseInfo -PathType Leaf) {
        $releaseVersion = (Get-Content -LiteralPath $releaseInfo -Raw -Encoding UTF8 | ConvertFrom-Json).version
        if ($releaseVersion -and $releaseVersion -ne $manifest.baseVersion) { throw '外层发布清单不是V1.1.7，停止更新。' }
    }
    $script:backupRoot = Join-Path $AppDirectory ('patch-backups\' + $manifest.patchId)
    Assert-NoLinks $backupRoot
    $script:statePath = Join-Path $backupRoot 'state.json'
    Assert-Stopped
    if ($Rollback) {
        $script:state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($state.patchId -ne $manifest.patchId -or $state.appDirectory -ne $AppDirectory -or $state.status -ne 'installed') { throw '没有可用的已安装补丁备份，或此前已回滚。' }
        $restoreNames = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in @($state.files)) {
            $target = Program-Path $runtimeRoot $entry.path
            $expected = @($manifest.files | Where-Object path -eq $entry.path)
            if (-not $restoreNames.Add([string]$entry.path) -or $expected.Count -ne 1 -or $entry.newSha256 -ne $expected[0].sha256 -or $entry.existed -isnot [bool]) { throw '备份文件列表格式不正确。' }
            if (-not $fileNames.Contains($entry.path) -or -not (Test-Path -LiteralPath $target -PathType Leaf) -or (Hash $target) -ne $entry.newSha256) { throw ('程序文件在安装后发生变化，拒绝自动回滚：' + $entry.path) }
            if ($entry.existed) {
                if ($entry.oldSha256 -notmatch '^[a-f0-9]{64}$') { throw '原文件备份哈希无效。' }
                $saved = Program-Path (Join-Path $backupRoot 'files') $entry.path
                if ((Hash $saved) -ne $entry.oldSha256) { throw '原文件备份损坏，停止回滚。' }
            }
        }
        if (@($state.files).Count -ne @($manifest.files).Count) { throw '备份文件列表不完整。' }
        if (-not $Yes -and (Read-Host '将恢复旧程序，不影响配置和视频。确认Host已退出，输入 YES 继续') -cne 'YES') { Write-Host '已取消。'; exit 0 }
        Assert-Stopped
        Restore-Files $state.files
        $state.status = 'rolled-back'
        Save-State
        Write-Host '回滚成功。仅恢复程序文件；配置、视频和密钥未改变。'
        exit 0
    }
    $currentHash = Hash $targetExe
    if ($currentHash -eq $manifest.newExeSha256 -and (Test-Path -LiteralPath $statePath)) { throw '这个补丁已安装；无需重复安装。需要回退请运行回滚补丁。' }
    if ($currentHash -ne $manifest.baseExeSha256) { throw '原程序版本/哈希不匹配，不能强行覆盖。请把提示交给开发者核对。' }
    foreach ($property in $manifest.requiredUnchangedFiles.PSObject.Properties) {
        $required = Program-Path $runtimeRoot $property.Name
        if (-not (Test-Path -LiteralPath $required -PathType Leaf) -or (Hash $required) -ne $property.Value) { throw ('原包依赖缺失或已改变，停止更新：' + $property.Name) }
    }
    foreach ($item in $manifest.files) { [void](Program-Path $runtimeRoot $item.path) }
    if (Test-Path -LiteralPath $backupRoot) { throw '已存在本补丁备份目录，请勿覆盖旧备份；需要再次安装时先由开发者核对。' }
    Write-Host ('目标：' + $AppDirectory)
    Write-Host ('版本：V' + $manifest.baseVersion + '；更新程序文件：' + @($manifest.files).Count)
    Write-Host '不会覆盖配置、视频、图片、密码、密钥或数字人Host。'
    if (-not $Yes -and (Read-Host '确认轨道静止、Host与后台均已退出，输入 YES 安装') -cne 'YES') { Write-Host '已取消，未修改文件。'; exit 0 }
    Assert-Stopped
    [void][IO.Directory]::CreateDirectory($backupRoot)
    $entries = @()
    foreach ($item in $manifest.files) {
        $target = Program-Path $runtimeRoot $item.path
        $exists = Test-Path -LiteralPath $target -PathType Leaf
        $oldHash = $null
        if ($exists) {
            $oldHash = Hash $target
            $saved = Program-Path (Join-Path $backupRoot 'files') $item.path
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($saved))
            [IO.File]::Copy($target,$saved,$false)
            if ((Hash $saved) -ne $oldHash) { throw ('原程序备份校验失败：' + $item.path) }
        }
        $entries += [ordered]@{ path=$item.path; existed=[bool]$exists; oldSha256=$oldHash; newSha256=$item.sha256 }
    }
    $script:state = [ordered]@{ patchId=$manifest.patchId; appDirectory=$AppDirectory; status='prepared'; installedAt=[DateTime]::UtcNow.ToString('o'); files=$entries }
    Save-State
    $applied = New-Object 'System.Collections.Generic.List[object]'
    try {
        Assert-Stopped
        # Dependencies first, new HTML entry and EXE last. Service must remain off.
        $ordered = @($entries | Sort-Object @{Expression={if($_.path -eq 'slider-screen-service.exe'){2}elseif($_.path -eq '_internal/backend/static/index.html'){1}else{0}}},path)
        foreach ($item in $ordered) {
            Assert-Stopped
            $target = Program-Path $runtimeRoot $item.path
            if ($item.existed -and (Hash $target) -ne $item.oldSha256) { throw '目标文件在备份后发生变化，停止更新。' }
            if (-not $item.existed -and (Test-Path -LiteralPath $target)) { throw '目标新文件在备份后被创建，停止更新。' }
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            $applied.Add($item)
            [IO.File]::Copy((Program-Path (Join-Path $PSScriptRoot 'payload') $item.path),$target,$true)
            if ((Hash $target) -ne $item.newSha256) { throw ('安装后校验失败：' + $item.path) }
        }
        $state.status = 'installed'
        Save-State
    } catch {
        $installError = $_.Exception.Message
        try { Restore-Files ($applied.ToArray()); $state.status='installation-failed-restored'; Save-State }
        catch { $state.status='rollback-needs-attention'; Save-State; throw ('安装失败且回退未完成。不要启动程序；保留备份并联系开发者。原错误：' + $installError + '；回退错误：' + $_.Exception.Message) }
        throw ('安装失败，已恢复本次改动的程序文件：' + $installError)
    }
    Write-Host '补丁安装成功。配置、视频、点位、密钥未改变。现在可重新启动原数字人Host。'
    Write-Host ('备份：' + $backupRoot)
    Write-Host ('异常日志：' + (Join-Path $runtimeRoot 'logs\media-errors.jsonl'))
} catch {
    Write-Host ('操作未完成：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
