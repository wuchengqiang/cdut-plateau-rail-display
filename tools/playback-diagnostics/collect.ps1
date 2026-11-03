param(
    [string]$RuntimeExe,
    [ValidateRange(10,600)][int]$DurationSeconds = 120,
    [switch]$UseExistingService,
    [string]$PageUrl = 'http://127.0.0.1:8000/',
    [switch]$NonInteractive,
    [switch]$HeadlessTest,
    [ValidateSet('original','release')][string]$Variant = 'original',
    [string]$ReportDirectory,
    [string]$BrowserProfilePath,
    [switch]$NoExplorer,
    [switch]$ManualStop
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$script:cdpSequence = 0
$script:report = [ordered]@{
    schema = 'rail.playback-diagnostics/v1'; startedAt = [DateTime]::UtcNow.ToString('o')
    requestedSeconds = $(if ($ManualStop) { $null } else { $DurationSeconds }); completed = $false; variant = $Variant
    stopMode = $(if ($ManualStop) { 'operator-enter' } else { 'duration' }); completionReason = $null
    mode = 'standalone-original-exe'; motionCommandsIssuedByTool = 0
    notes = @('工具不调用播放、切点、回原点或急停API。', 'original仅观察；release仅暂停并清空已经移除的旧视频，不操作当前视频。', '不修改硬件加速设置。', '不含中控密钥、管理员密码、视频内容或其他浏览器页面。')
    environment = @{}; samples = (New-Object System.Collections.Generic.List[object])
    mediaProperties = (New-Object System.Collections.Generic.List[object])
    mediaEvents = (New-Object System.Collections.Generic.List[object])
    mediaRequests = (New-Object System.Collections.Generic.List[object])
    systemSamples = (New-Object System.Collections.Generic.List[object])
    errors = (New-Object System.Collections.Generic.List[object])
}
$sessionName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$outputDirectory = Join-Path $PSScriptRoot ('reports\' + $sessionName)
if ($ReportDirectory) {
    $reportRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'reports')) + [IO.Path]::DirectorySeparatorChar
    $outputDirectory = [IO.Path]::GetFullPath($ReportDirectory)
    if (-not $outputDirectory.StartsWith($reportRoot,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $outputDirectory)) { throw '自定义报告目录必须是本工具 reports 下尚不存在的新目录。' }
}
[void][IO.Directory]::CreateDirectory($outputDirectory)
$reportFile = Join-Path $outputDirectory 'report.json'
$ownedBackend = $null; $ownedBrowser = $null; $pageCdp = $null; $browserCdp = $null
$diagnosticProfile = $null; $exitCode = 0; $cleanupApproved = $false
$script:mediaRequestsById = @{}

function Save-Report {
    $script:report.updatedAt = [DateTime]::UtcNow.ToString('o')
    $text = ConvertTo-Json -InputObject $script:report -Depth 30
    [IO.File]::WriteAllText($reportFile + '.tmp', $text, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath ($reportFile + '.tmp') -Destination $reportFile -Force
}
function Get-LocalJson([string]$Address) {
    $uri = [uri]$Address
    if ($uri.Scheme -ne 'http' -or $uri.Host -ne '127.0.0.1' -or $uri.UserInfo -or $uri.Query) { throw '诊断 HTTP 请求只允许本机回环地址，不允许密钥或查询参数。' }
    $request = [Net.HttpWebRequest]::Create($uri)
    $request.Method = 'GET'; $request.Proxy = $null; $request.AllowAutoRedirect = $false
    $request.Timeout = 2000; $request.ReadWriteTimeout = 2000
    $response = $request.GetResponse()
    try {
        $reader = New-Object IO.StreamReader($response.GetResponseStream(), [Text.Encoding]::UTF8)
        try { return (ConvertFrom-Json -InputObject $reader.ReadToEnd()) } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
}
function Invoke-Cdp($Connection, [string]$Method, $Parameters = @{}) {
    $script:cdpSequence++
    $message = @{ id = $script:cdpSequence; method = $Method; params = $Parameters } | ConvertTo-Json -Compress -Depth 12
    $response = $Connection.Call($message, $script:cdpSequence) | ConvertFrom-Json
    if ($response.error) { throw ('CDP ' + $Method + ': ' + $response.error.message) }
    return $response.result
}
function Select-MediaState($value) {
    if ($null -eq $value) { return $null }
    if ($value -is [string]) {
        if ($value.Length -le 160 -and $value -match '^[A-Za-z0-9_ .():-]+$') { return $value }
        return '[omitted]'
    }
    if ($value -is [bool] -or $value -is [ValueType]) { return $value }
    $safe = @{}
    foreach ($key in @('event','state','reason','pipeline_state','video_buffering_state','audio_buffering_state','pipeline_buffering_state','seek_target','duration','for_suspended_start')) {
        if ($value.PSObject.Properties[$key]) { $safe[$key] = Select-MediaState $value.$key }
    }
    return $safe
}
function Read-MediaProperties {
    if (-not $pageCdp) { return }
    foreach ($raw in $pageCdp.DrainEvents()) {
        $event = $raw | ConvertFrom-Json
        if ($event.method -eq 'Media.playerPropertiesChanged') {
            $allowed = @($event.params.properties | Where-Object {
                $_.name -in @('kVideoDecoderName','kIsPlatformVideoDecoder','kAudioDecoderName','kIsPlatformAudioDecoder','kResolution','kVideoTracks','kAudioTracks','kBitrate','kMaxDuration','kIsStreaming','kIsVideoDecryptingDemuxerStream','kRendererName')
            })
            if ($allowed.Count -and $script:report.mediaProperties.Count -lt 2000) {
                $script:report.mediaProperties.Add(@{ at=[DateTime]::UtcNow.ToString('o'); playerId=$event.params.playerId; properties=$allowed })
            }
        }
        elseif ($event.method -eq 'Media.playerEventsAdded') {
            foreach ($item in $event.params.events) {
                try { $parsed = $item.value | ConvertFrom-Json } catch { continue }
                $safe = Select-MediaState $parsed
                if ($script:report.mediaEvents.Count -lt 6000) {
                    $script:report.mediaEvents.Add(@{at=[DateTime]::UtcNow.ToString('o');playerId=$event.params.playerId;timestamp=$item.timestamp;data=$safe})
                }
            }
        }
        elseif ($event.method -eq 'Network.requestWillBeSent') {
            $uri = [uri]$event.params.request.url
            if ($uri.Scheme -eq 'http' -and $uri.Host -eq '127.0.0.1' -and $uri.Port -eq $pageUri.Port -and $uri.AbsolutePath.StartsWith('/content/videos/') -and $script:report.mediaRequests.Count -lt 3000) {
                $request = @{id=$event.params.requestId;path=$uri.AbsolutePath;started=$event.params.timestamp;active=$true;dataBytes=0L;wireBytes=0L}
                $script:mediaRequestsById[$event.params.requestId] = $request
                $script:report.mediaRequests.Add($request)
            }
        }
        elseif ($event.method -like 'Network.*' -and $script:mediaRequestsById.ContainsKey([string]$event.params.requestId)) {
            $request = $script:mediaRequestsById[$event.params.requestId]
            if ($event.method -eq 'Network.dataReceived') {
                $request.dataBytes += [long]$event.params.dataLength
                $request.wireBytes += [long]$event.params.encodedDataLength
            } elseif ($event.method -eq 'Network.responseReceived') {
                $request.status = $event.params.response.status
                $request.fromDiskCache = $event.params.response.fromDiskCache -eq $true
            } elseif ($event.method -in @('Network.loadingFinished','Network.loadingFailed')) {
                $request.active = $false; $request.finished = $event.params.timestamp
                $request.result = $event.method
                if ($event.params.errorText -match '^net::ERR_[A-Z0-9_]+$') { $request.error = $event.params.errorText }
                [void]$script:mediaRequestsById.Remove($event.params.requestId)
            }
        }
    }
}
function Select-Status($status) {
    $safe = @{}
    foreach ($key in @('currentPointId','targetPointId','displayPointId','motorState','playbackState','playbackRevision','mediaSessionId','mediaError','carouselMode','error','availablePointCount','pointIds')) {
        $safe[$key] = $status.$key
    }
    return $safe
}
function Find-Edge {
    foreach ($folder in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:LOCALAPPDATA)) {
        if ($folder) {
            $candidate = Join-Path $folder 'Microsoft\Edge\Application\msedge.exe'
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    throw '没有找到 Microsoft Edge。'
}
function Assert-ProfileClosed([string]$ProfilePath) {
    $busy = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($ProfilePath, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
    if ($busy.Count) { throw '原播放器网页仍在运行。请先关闭原独立播放器和数字人 Host，再重试；工具不会强行关闭它们。' }
}

try {
    if ($PSVersionTable.PSEdition -eq 'Core') { throw '请通过随包BAT启动，使用 Windows 自带 PowerShell 5.1。' }
    if (($NonInteractive -or $HeadlessTest) -and -not $UseExistingService) { throw '自动化测试参数只能配合 UseExistingService；正式现场流程必须有人确认。' }
    if ($ManualStop -and [Console]::IsInputRedirected) { throw '手动结束需要交互控制台，请双击BAT；不要把输入重定向到文件或管道。' }
    Write-Host ('青藏高原滑轨屏 · 播放诊断 · ' + $Variant) -ForegroundColor Cyan
    if ($UseExistingService) { Write-Host '本轮复用已确认的本机后台，请勿另开其他播放页。' }
    else { Write-Host '请先退出数字人 Host 和独立播放器。厂家控制软件保持打开。' }
    Write-Host '采集期间可手动切点；请确认轨道无人、移动安全。工具不会替你发送移动指令。'

    if (-not $UseExistingService) {
        if (-not $RuntimeExe) {
            Add-Type -AssemblyName System.Windows.Forms
            $dialog = New-Object Windows.Forms.OpenFileDialog
            $dialog.Title = '选择现场 app\runtime\slider-screen-service.exe'
            $dialog.Filter = '滑轨播放器|slider-screen-service.exe'
            if (Test-Path -LiteralPath 'C:\数字人\app\runtime') { $dialog.InitialDirectory = 'C:\数字人\app\runtime' }
            if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw '已取消选择，未启动任何播放器。' }
            $RuntimeExe = $dialog.FileName
            $dialog.Dispose()
        }
        $RuntimeExe = (Resolve-Path -LiteralPath $RuntimeExe).Path
        if ([IO.Path]::GetFileName($RuntimeExe) -ne 'slider-screen-service.exe') { throw '请选择滑轨屏的 slider-screen-service.exe，不是数字人 Host 或其他播放器。' }
        $runtimeDirectory = Split-Path -Parent $RuntimeExe
        $settings = [IO.File]::ReadAllText((Join-Path $runtimeDirectory 'config\app.json'), [Text.Encoding]::UTF8) | ConvertFrom-Json
        if ($settings.apiHost -ne '127.0.0.1' -or $settings.apiPort -lt 1 -or $settings.apiPort -gt 65535) { throw '现场本机服务地址配置不符合预期，未启动。' }
        $PageUrl = 'http://127.0.0.1:' + $settings.apiPort + '/'
        $diagnosticProfile = Join-Path $runtimeDirectory 'browser-profile'
        Assert-ProfileClosed $diagnosticProfile
        $occupied = @(Get-NetTCPConnection -State Listen -LocalPort $settings.apiPort -ErrorAction SilentlyContinue)
        if ($occupied.Count) { throw ('端口 ' + $settings.apiPort + ' 仍被占用。请完整退出原播放器/Host；工具不会终止已有服务。') }
        [void](Read-Host '确认已退出旧播放窗口、轨道安全后按回车开始')
        $ownedBackend = Start-Process -FilePath $RuntimeExe -ArgumentList '--no-browser' -WorkingDirectory $runtimeDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $outputDirectory 'backend-out.log') -RedirectStandardError (Join-Path $outputDirectory 'backend-error.log')
    } else {
        $script:report.mode = 'existing-service-isolated-profile'
        $diagnosticProfile = Join-Path $outputDirectory 'test-browser-profile'
        if ($BrowserProfilePath) {
            $diagnosticProfile = [IO.Path]::GetFullPath($BrowserProfilePath)
            if ((Split-Path -Leaf $diagnosticProfile) -ne 'browser-profile') { throw '只允许复用播放器专用 browser-profile。' }
            Assert-ProfileClosed $diagnosticProfile
            $script:report.mode = 'existing-service-player-profile'
        }
    }
    $pageUri = [uri]$PageUrl
    if ($pageUri.Scheme -ne 'http' -or $pageUri.Host -ne '127.0.0.1' -or $pageUri.UserInfo -or $pageUri.Query -or $pageUri.Fragment -or $pageUri.AbsolutePath -ne '/') { throw '只允许采集本机独立播放器首页。' }
    $PageUrl = $pageUri.AbsoluteUri
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $initialStatus = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try { $initialStatus = Get-LocalJson ($PageUrl + 'api/status'); break } catch { Start-Sleep -Milliseconds 400 }
        if ($ownedBackend -and $ownedBackend.HasExited) { throw '原播放器启动失败。请保留本次 reports 子目录中的启动日志。' }
    }
    if (-not $initialStatus -or -not $initialStatus.PSObject.Properties['motorState'] -or -not $initialStatus.PSObject.Properties['pointIds']) { throw '本机滑轨服务没有就绪；未打开第二个播放页。' }
    $script:report.servicePort = $pageUri.Port
    $script:report.initialStatus = Select-Status $initialStatus

    $edge = Find-Edge
    $script:report.environment = @{
        os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,TotalVisibleMemorySize
        cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
        gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM,CurrentHorizontalResolution,CurrentVerticalResolution)
        edgeVersion = (Get-Item -LiteralPath $edge).VersionInfo.FileVersion
        headlessTest = [bool]$HeadlessTest
    }
    if (-not ('RailDiagnosticCdp' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'CdpConnection.cs') -ReferencedAssemblies 'System.Web.Extensions','System.Net.Http' }
    $launchTime = [DateTime]::UtcNow
    $arguments = @('--kiosk','about:blank','--edge-kiosk-type=fullscreen','--no-first-run','--autoplay-policy=no-user-gesture-required','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',('--user-data-dir="' + $diagnosticProfile + '"'))
    if ($HeadlessTest) { $arguments += '--headless=new' }
    $windowStyle = if ($HeadlessTest) { 'Hidden' } else { 'Normal' }
    $ownedBrowser = Start-Process -FilePath $edge -ArgumentList $arguments -WindowStyle $windowStyle -PassThru
    $portFile = Join-Path $diagnosticProfile 'DevToolsActivePort'
    $deadline = [DateTime]::UtcNow.AddSeconds(25)
    $debugPort = 0
    while ([DateTime]::UtcNow -lt $deadline) {
        if ((Test-Path -LiteralPath $portFile) -and (Get-Item -LiteralPath $portFile).LastWriteTimeUtc -ge $launchTime.AddSeconds(-1)) {
            $portLines = [IO.File]::ReadAllLines($portFile)
            if ($portLines.Length -ge 2 -and [int]::TryParse($portLines[0], [ref]$debugPort) -and $debugPort -gt 0) { break }
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $debugPort) { throw '未能启动本机浏览器诊断。可能被系统浏览器策略禁止；不修改系统策略。' }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $debugPort)
    if (-not $listeners.Count -or @($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }).Count) { throw '调试端口未限制为回环地址，停止诊断。' }
    $debugBase = 'http://127.0.0.1:' + $debugPort
    $version = Get-LocalJson ($debugBase + '/json/version')
    $browserCdp = New-Object RailDiagnosticCdp($version.webSocketDebuggerUrl)
    $targets = @(Get-LocalJson ($debugBase + '/json/list'))
    $target = $targets | Where-Object { $_.type -eq 'page' -and $_.url -eq 'about:blank' } | Select-Object -First 1
    if (-not $target) { throw '没有找到本次创建的诊断页面；不会附着到其他网页。' }
    $pageCdp = New-Object RailDiagnosticCdp($target.webSocketDebuggerUrl)
    try {
        $gpuInfo = Invoke-Cdp $browserCdp 'SystemInfo.getInfo'
        $script:report.environment.browserGpu = @{ devices=$gpuInfo.gpu.devices; featureStatus=$gpuInfo.gpu.featureStatus; videoDecoding=$gpuInfo.gpu.videoDecoding }
    } catch { $script:report.errors.Add(@{stage='gpuInfo'; message=$_.Exception.Message}) }
    [void](Invoke-Cdp $pageCdp 'Page.enable')
    try { [void](Invoke-Cdp $pageCdp 'Media.enable') } catch { $script:report.errors.Add(@{stage='mediaProtocol';message=$_.Exception.Message}) }
    try { [void](Invoke-Cdp $pageCdp 'Network.enable' @{maxTotalBufferSize=1048576;maxResourceBufferSize=65536}) } catch { $script:report.errors.Add(@{stage='networkProtocol';message=$_.Exception.Message}) }
    $probe = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'browser-probe.js'), [Text.Encoding]::UTF8)
    $options = @{releaseDetached=($Variant -eq 'release')} | ConvertTo-Json -Compress
    $probe = 'window.__railDiagnosticOptions=' + $options + ';' + $probe
    [void](Invoke-Cdp $pageCdp 'Page.addScriptToEvaluateOnNewDocument' @{source=$probe})
    [void](Invoke-Cdp $pageCdp 'Page.navigate' @{url=$PageUrl})
    if ($ManualStop) {
        # Discard leftover keys from startup confirmations; no global keyboard hook.
        while ([Console]::KeyAvailable) { [void][Console]::ReadKey($true) }
        Write-Host '采集已开始，不限两分钟。做完本轮后Alt+Tab切回这个黑色窗口，按Enter结束记录。' -ForegroundColor Green
        Write-Host '只在此窗口接收Enter；不要在播放器网页里按Enter。结束记录不会下发电机停止命令。'
    } else { Write-Host "采集已开始，共 $DurationSeconds 秒。切回全屏页面，按现场习惯手动切点。" -ForegroundColor Green }
    Write-Host '不用截图或转发；每个点位建议播放 20～30 秒，不要连续快速点多个位置。'
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $nextSystem = 0; $nextSave = 0
    while ($ManualStop -or $watch.Elapsed.TotalSeconds -lt $DurationSeconds) {
        $sampleTime = $watch.Elapsed.TotalSeconds
        $sample = @{elapsedSeconds=[Math]::Round($sampleTime,3);at=[DateTime]::UtcNow.ToString('o')}
        $value = Invoke-Cdp $pageCdp 'Runtime.evaluate' @{expression='window.__railDiagnosticProbe ? window.__railDiagnosticProbe.read() : null';returnByValue=$true}
        if ($value.exceptionDetails) { throw '页面诊断采样执行失败。' }
        $sample.browser = $value.result.value
        if ($sample.browser -and $sample.browser.variant -ne $Variant) { throw '页面探针的对照模式不匹配，停止采集。' }
        try { $sample.status = Select-Status (Get-LocalJson ($PageUrl + 'api/status')) } catch { $sample.statusError = '本机状态接口暂时不可达' }
        $script:report.samples.Add($sample)
        Read-MediaProperties
        $sample.activeMediaRequests = @($script:mediaRequestsById.Values | ForEach-Object { @{id=$_.id;path=$_.path;dataBytes=$_.dataBytes;wireBytes=$_.wireBytes} })
        if ($sampleTime -ge $nextSystem) {
            $system = @{elapsedSeconds=[Math]::Round($sampleTime,3)}
            try {
                $cpuLoad = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
                $memory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
                $system.cpuPercent = $cpuLoad.PercentProcessorTime
                $system.availableMemoryMb = $memory.AvailableMBytes
            } catch { $system.unavailable = $true }
            $script:report.systemSamples.Add($system)
            $nextSystem = $sampleTime + 5
        }
        if ($sampleTime -ge $nextSave) { Save-Report; $nextSave = $sampleTime + 15 }
        $phaseLabel = if ($Variant -eq 'release') { 'B轮释放旧视频' } else { 'A轮原逻辑' }
        if ($ManualStop) {
            $Host.UI.RawUI.WindowTitle = $phaseLabel + ' 已记录 ' + [int]$watch.Elapsed.TotalSeconds + ' 秒；Enter结束记录'
            $enterRequested = $false
            while ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq [ConsoleKey]::Enter) { $enterRequested = $true }
            }
            if ($enterRequested) { $script:report.completionReason = 'operator-enter'; break }
        } else { $Host.UI.RawUI.WindowTitle = $phaseLabel + ' ' + [int]$watch.Elapsed.TotalSeconds + '/' + $DurationSeconds + ' 秒' }
        $remaining = 1000 - ($watch.Elapsed.TotalSeconds - $sampleTime) * 1000
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([int]$remaining) }
    }
    Read-MediaProperties
    if (-not $ManualStop) { $script:report.completionReason = 'duration-elapsed' }
    $script:report.completed = $true
    $script:report.elapsedSeconds = [Math]::Round($watch.Elapsed.TotalSeconds,3)
    $script:report.cdpEventsDiscarded = $pageCdp.DroppedEvents
    if ($NoExplorer) { Write-Host '本轮已保存。两轮结束后会自动合成 comparison-report.json，暂时不用发送。' -ForegroundColor Green }
    else {
        Write-Host '采集完成。只需要发送下面的 report.json 文件：' -ForegroundColor Green
        Write-Host $reportFile
    }
} catch {
    $exitCode = 1
    $script:report.errors.Add(@{stage='collector';message=$_.Exception.Message})
    Write-Host ('诊断中止：' + $_.Exception.Message) -ForegroundColor Yellow
    Write-Host ('已采集的数据仍会保存：' + $reportFile)
} finally {
    try { Save-Report } catch { Write-Host ('保存报告失败：' + $_.Exception.Message) -ForegroundColor Red }
    if (-not $NonInteractive) {
        if (-not $NoExplorer -and (Test-Path -LiteralPath $reportFile)) { Start-Process explorer.exe -ArgumentList ('/select,"' + $reportFile + '"') }
        if ($ownedBrowser -or $ownedBackend) {
            if ($UseExistingService) { Write-Host '本轮采集结束。请先确认滑轨停止；按回车只关闭本轮诊断网页，后台保留。' -ForegroundColor Yellow }
            else { Write-Host '请先确认滑轨已经停止。按回车后，仅关闭本工具启动的网页和后台。' -ForegroundColor Yellow }
            do {
                [void](Read-Host '确认安全后按回车结束本轮；对照测试请继续按控制台提示操作')
                $stillMoving = $false
                try {
                    $lastStatus = Get-LocalJson ($PageUrl + 'api/status')
                    $stillMoving = $lastStatus.motorState -eq 'moving' -or [bool]$lastStatus.targetPointId
                    if ($stillMoving) { Write-Host '播放器仍报告在途动作，暂不关闭。请等待到位，或在厂家软件确认安全停止后再操作。' -ForegroundColor Yellow }
                } catch { Write-Host '状态接口不可达；本次按你刚才的人工安全确认结束。' -ForegroundColor Yellow }
            } while ($stillMoving)
            $cleanupApproved = $true
        }
    } else { $cleanupApproved = $true }
    if ($cleanupApproved) {
        if ($browserCdp) { try { [void](Invoke-Cdp $browserCdp 'Browser.close') } catch {} }
        if ($ownedBrowser) {
            try { if (-not $ownedBrowser.WaitForExit(3000)) { Stop-Process -InputObject $ownedBrowser -ErrorAction SilentlyContinue } } catch {}
        }
        if ($ownedBackend) { try { if (-not $ownedBackend.HasExited) { Stop-Process -InputObject $ownedBackend } } catch {} }
    } else {
        Write-Host '未确认清理，诊断网页/后台可能仍在运行。请在轨道安全停止后手动关闭。' -ForegroundColor Yellow
    }
    if ($pageCdp) { $pageCdp.Dispose() }
    if ($browserCdp) { $browserCdp.Dispose() }
}
exit $exitCode
