param(
    [string]$RuntimeExe,
    [ValidateRange(10,600)][int]$DurationSeconds = 120,
    [switch]$ReverseOrder,
    [switch]$UseExistingService,
    [string]$PageUrl = 'http://127.0.0.1:8000/',
    [switch]$NonInteractive,
    [switch]$HeadlessTest
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
# No duration argument means the field operator ends each phase with Enter.
# Explicit DurationSeconds remains available for automated regression tests.
$manualPhaseStop = -not $PSBoundParameters.ContainsKey('DurationSeconds')
$runName = 'ab-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$comparisonDirectory = Join-Path $PSScriptRoot ('reports\' + $runName)
[void][IO.Directory]::CreateDirectory($comparisonDirectory)
$comparisonFile = Join-Path $comparisonDirectory 'comparison-report.json'
$order = @('original','release')
if ($ReverseOrder) { $order = @('release','original') }
$comparison = [ordered]@{
    schema='rail.playback-comparison/v1'; startedAt=[DateTime]::UtcNow.ToString('o')
    completed=$false; order=$order; secondsPerPhase=$(if ($manualPhaseStop) { $null } else { $DurationSeconds }); motionCommandsIssuedByTool=0
    stopMode=$(if ($manualPhaseStop) { 'operator-enter' } else { 'duration' }); toolVersion='2.0-manual-stop'
    sharedBackend=$true; sharedBrowserProfile=$true; freshBrowserProcessPerPhase=$true; cacheCleared=$false
    limitations=@('同一台电脑、同一组视频、同一浏览器配置；不清磁盘和操作系统缓存。', 'B较晚运行可能受热缓存影响；必要时应反向顺序复核，不凭一次对照宣称根因。', '后台全程保留，不重置实际点位；每轮请手动从点位1开始。初始点位和媒体状态会记录。', '仅B轮释放已移除的旧视频；当前视频、播放时序和电机API均不修改。')
    phases=(New-Object System.Collections.Generic.List[object]); errors=(New-Object System.Collections.Generic.List[object])
}
$comparisonBackend=$null; $playerProfile=$null; $comparisonExit=0
function Save-Comparison {
    $comparison.updatedAt=[DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText($comparisonFile + '.tmp', (ConvertTo-Json -InputObject $comparison -Depth 40), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath ($comparisonFile + '.tmp') -Destination $comparisonFile -Force
}
function Read-ComparisonStatus {
    $request=[Net.HttpWebRequest]::Create($PageUrl + 'api/status')
    $request.Method='GET'; $request.Proxy=$null; $request.AllowAutoRedirect=$false
    $request.Timeout=2000; $request.ReadWriteTimeout=2000
    $response=$request.GetResponse()
    try {
        $reader=New-Object IO.StreamReader($response.GetResponseStream(),[Text.Encoding]::UTF8)
        try { return (ConvertFrom-Json -InputObject $reader.ReadToEnd()) } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
}
function Import-PhaseReports {
    foreach ($variantName in $order) {
        if (@($comparison.phases | Where-Object { $_.variant -eq $variantName }).Count) { continue }
        $file=Join-Path $comparisonDirectory ($variantName + '\report.json')
        if (Test-Path -LiteralPath $file) {
            try { $comparison.phases.Add(([IO.File]::ReadAllText($file,[Text.Encoding]::UTF8) | ConvertFrom-Json)) }
            catch { $comparison.errors.Add(@{phase=$variantName;message='子报告无法读取，保留原文件供检查。'}) }
        }
    }
}

try {
    if (($NonInteractive -or $HeadlessTest) -and -not $UseExistingService) { throw '无人确认参数仅用于隔离测试服务。' }
    if ($manualPhaseStop -and [Console]::IsInputRedirected) { throw '手动结束需要交互控制台，请双击start-ab-test.bat；自动化测试请显式指定DurationSeconds。' }
    if ($manualPhaseStop) {
        Write-Host '滑轨屏视频资源 A/B 对照：不限定两分钟，每轮切回本窗口按Enter结束记录。' -ForegroundColor Cyan
    } else { Write-Host ("滑轨屏视频资源 A/B 对照：每轮 $DurationSeconds 秒，最终只交一个报告。") -ForegroundColor Cyan }
    Write-Host 'A＝原逻辑；B＝临时释放已移除的旧视频。工具不自动切点或回原点。'
    Write-Host '请退出数字人Host和原播放器，厂家软件保持打开；轨道上不能有人或障碍物。'
    Write-Host '两轮使用同样顺序：1→2→3→4→3。每点观察约20～30秒或更久，必须等待机械动作完成；不必赶时间。'
    Write-Host '两轮保持相同音量、分辨率、VNC连接和其他软件状态。'
    if (-not $UseExistingService) {
        if (-not $RuntimeExe) {
            Add-Type -AssemblyName System.Windows.Forms
            $picker=New-Object Windows.Forms.OpenFileDialog
            $picker.Title='选择现场 app\runtime\slider-screen-service.exe'
            $picker.Filter='滑轨播放器|slider-screen-service.exe'
            if (Test-Path -LiteralPath 'C:\数字人\app\runtime') { $picker.InitialDirectory='C:\数字人\app\runtime' }
            if ($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw '取消选择；未启动播放器。' }
            $RuntimeExe=$picker.FileName; $picker.Dispose()
        }
        $RuntimeExe=(Resolve-Path -LiteralPath $RuntimeExe).Path
        if ([IO.Path]::GetFileName($RuntimeExe) -ne 'slider-screen-service.exe') { throw '请选择滑轨屏原程序，不是Host或70周年程序。' }
        $runtimeFolder=Split-Path -Parent $RuntimeExe
        $settings=[IO.File]::ReadAllText((Join-Path $runtimeFolder 'config\app.json'),[Text.Encoding]::UTF8) | ConvertFrom-Json
        if ($settings.apiHost -ne '127.0.0.1' -or $settings.apiPort -lt 1 -or $settings.apiPort -gt 65535) { throw '本机监听配置不符合预期。' }
        $PageUrl='http://127.0.0.1:' + $settings.apiPort + '/'
        $playerProfile=Join-Path $runtimeFolder 'browser-profile'
        $oldWindows=@(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($playerProfile,[StringComparison]::OrdinalIgnoreCase) -ge 0 })
        if ($oldWindows.Count -or @(Get-NetTCPConnection -State Listen -LocalPort $settings.apiPort -ErrorAction SilentlyContinue).Count) { throw '旧播放器/Host尚未退出，端口或网页仍在使用。不会强行关闭已有程序。' }
        [void](Read-Host '确认轨道安全、旧程序已退出后按回车开始A/B对照')
        $comparisonBackend=Start-Process -FilePath $RuntimeExe -ArgumentList '--no-browser' -WorkingDirectory $runtimeFolder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $comparisonDirectory 'backend-out.log') -RedirectStandardError (Join-Path $comparisonDirectory 'backend-error.log')
    } else {
        # Test mode uses one shared isolated profile, just as both field phases
        # reuse the player's profile. Never touch a real player profile in tests.
        $playerProfile=Join-Path $comparisonDirectory 'browser-profile'
    }
    $pageAddress=[uri]$PageUrl
    if ($pageAddress.Scheme -ne 'http' -or $pageAddress.Host -ne '127.0.0.1' -or $pageAddress.UserInfo -or $pageAddress.Query -or $pageAddress.Fragment -or $pageAddress.AbsolutePath -ne '/') { throw '对照只允许本机独立播放器首页。' }
    $PageUrl=$pageAddress.AbsoluteUri
    $readyDeadline=[DateTime]::UtcNow.AddSeconds(30)
    $initial=$null
    while ([DateTime]::UtcNow -lt $readyDeadline) {
        try { $initial=Read-ComparisonStatus; break } catch { Start-Sleep -Milliseconds 400 }
        if ($comparisonBackend -and $comparisonBackend.HasExited) { throw '原后台启动失败，请保留启动日志。' }
    }
    if (-not $initial -or -not $initial.PSObject.Properties['pointIds'] -or -not $initial.PSObject.Properties['motorState']) { throw '滑轨后台未就绪。' }
    $comparison.servicePort=$pageAddress.Port
    Save-Comparison
    foreach ($phaseVariant in $order) {
        $label=if ($phaseVariant -eq 'original') { 'A轮：原逻辑' } else { 'B轮：释放旧视频资源' }
        Write-Host ('即将进入 ' + $label + '。两轮之间浏览器会关闭并重新打开，后台不重启。') -ForegroundColor Cyan
        $phaseArguments=@{
            UseExistingService=$true; PageUrl=$PageUrl; DurationSeconds=$DurationSeconds; Variant=$phaseVariant
            ReportDirectory=(Join-Path $comparisonDirectory $phaseVariant); NoExplorer=$true
            NonInteractive=[bool]$NonInteractive; HeadlessTest=[bool]$HeadlessTest
            ManualStop=$manualPhaseStop
        }
        if ($playerProfile) { $phaseArguments.BrowserProfilePath=$playerProfile }
        & (Join-Path $PSScriptRoot 'collect.ps1') @phaseArguments
        $phaseExit=$LASTEXITCODE
        Import-PhaseReports
        Save-Comparison
        $phase=@($comparison.phases | Where-Object { $_.variant -eq $phaseVariant })
        if ($phaseExit -ne 0 -or $phase.Count -ne 1 -or -not $phase[0].completed) { throw ('本轮未完整完成，保留已有数据，不自动开始下一轮：' + $label) }
    }
    $comparison.completed=$true
    Write-Host '两轮完成。请只发送 comparison-report.json，不需要分别发送每轮文件。' -ForegroundColor Green
    Write-Host $comparisonFile
} catch {
    $comparisonExit=1
    $comparison.errors.Add(@{message=$_.Exception.Message})
    Write-Host ('对照中止：' + $_.Exception.Message) -ForegroundColor Yellow
} finally {
    Import-PhaseReports
    try { Save-Comparison } catch { Write-Host ('汇总报告保存失败：' + $_.Exception.Message) -ForegroundColor Red }
    if ($comparisonBackend -and -not $comparisonBackend.HasExited -and -not $NonInteractive) {
        do {
            [void](Read-Host '全部采集已结束。确认滑轨停止后按回车，关闭本工具启动的后台')
            $moving=$false
            try { $last=Read-ComparisonStatus; $moving=$last.motorState -eq 'moving' -or [bool]$last.targetPointId }
            catch { Write-Host '接口不可达，按你的人工安全确认处理。' -ForegroundColor Yellow }
            if ($moving) { Write-Host '仍有在途动作，后台暂不关闭。请等到位或在厂家软件确认安全停止后再操作。' -ForegroundColor Yellow }
        } while ($moving)
        Stop-Process -InputObject $comparisonBackend -ErrorAction SilentlyContinue
    }
    if (-not $NonInteractive -and (Test-Path -LiteralPath $comparisonFile)) { Start-Process explorer.exe -ArgumentList ('/select,"' + $comparisonFile + '"') }
}
exit $comparisonExit
