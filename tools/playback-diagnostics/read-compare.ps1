param(
    [string]$RuntimeExe,
    [string]$VideoPath,
    [switch]$ReverseOrder,
    [ValidateRange(5,600)][int]$DurationSeconds = 120,
    [switch]$UseExistingService,
    [string]$RuntimeRoot,
    [string]$PageUrl = 'http://127.0.0.1:8000/',
    [switch]$NonInteractive,
    [switch]$HeadlessTest
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$manualStop=-not $PSBoundParameters.ContainsKey('DurationSeconds')
$runFolder=Join-Path $PSScriptRoot ('reports\read-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
[void][IO.Directory]::CreateDirectory($runFolder)
$reportFile=Join-Path $runFolder 'read-comparison-report.json'
$order=@('file','http'); if($ReverseOrder){$order=@('http','file')}
$report=[ordered]@{
    schema='rail.read-path-comparison/v1'; toolVersion='1.0'; startedAt=[DateTime]::UtcNow.ToString('o'); completed=$false
    stopMode=$(if($manualStop){'operator-enter'}else{'duration'}); order=$order
    motionCommandsIssuedByTool=0; controlRequestsObserved=0; sharedBackend=$true; freshBrowserProcessPerPhase=$true
    sharedIsolatedProfile=$true; cacheCleared=$false; phases=(New-Object 'System.Collections.Generic.List[object]')
    readChecks=(New-Object 'System.Collections.Generic.List[object]'); errors=(New-Object 'System.Collections.Generic.List[object]')
    limitations=@('两轮使用同一简化页面、同一文件、同一独立浏览器配置；仅改变file/http读取方式。',
        '这不是原界面、数字人或切点测试。后台播放状态可以一直为idle，不代表测试视频暂停。',
        '不清操作系统文件缓存，后测可能享有热缓存优势；可反向复核。',
        '片段读取测速在两轮播放结束后执行，避免提前预读；它是缓存条件下的测试，不是硬盘冷读基准。',
        '不更改正式程序、配置、视频、硬件加速、端口或鉴权。原后台启动可能按原逻辑发送PING/STATUS，但不发送移动命令。')
}
$ownedBackend=$null; $ownedBrowser=$null; $pageCdp=$null; $browserCdp=$null; $exitCode=0; $sequence=0
$phase=$null; $requestsById=@{}; $readBrowserProfile=Join-Path $runFolder 'browser-profile'
function Save-ReadReport {
    $report.updatedAt=[DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText($reportFile+'.tmp',(ConvertTo-Json -InputObject $report -Depth 40),(New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath ($reportFile+'.tmp') -Destination $reportFile -Force
}
function Local-Request([string]$Address,[string]$Method='GET') {
    $uri=[uri]$Address
    if($uri.Scheme -ne 'http' -or $uri.Host -ne '127.0.0.1' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment){throw '只允许无密钥的本机HTTP地址。'}
    if($Method -notin @('GET','HEAD')){throw '只允许只读请求。'}
    $req=[Net.HttpWebRequest]::Create($uri); $req.Method=$Method; $req.Proxy=$null; $req.AllowAutoRedirect=$false
    $req.Timeout=5000; $req.ReadWriteTimeout=5000
    return $req
}
function Read-Status {
    $response=(Local-Request ($PageUrl+'api/status')).GetResponse()
    try {
        $reader=New-Object IO.StreamReader($response.GetResponseStream(),[Text.Encoding]::UTF8)
        try { $value=$reader.ReadToEnd() | ConvertFrom-Json } finally {$reader.Dispose()}
        if(-not $value.PSObject.Properties['pointIds'] -or -not $value.PSObject.Properties['motorState']){throw '不是预期的滑轨状态接口。'}
        return @{motorState=$value.motorState;targetPointId=$value.targetPointId;currentPointId=$value.currentPointId;carouselMode=$value.carouselMode;playbackState=$value.playbackState}
    } finally {$response.Dispose()}
}
function Assert-Stationary($status) {
    if($status.motorState -eq 'moving' -or $status.targetPointId -or $status.carouselMode){throw '检测到移动/巡展，读取对照已中止；工具不会发送急停，请在厂家软件确认现场安全。'}
}
function Cdp($Connection,[string]$Method,$Parameters=@{}) {
    $script:sequence++
    $result=$Connection.Call((@{id=$script:sequence;method=$Method;params=$Parameters}|ConvertTo-Json -Depth 12 -Compress),$script:sequence)|ConvertFrom-Json
    if($result.error){throw ('CDP '+$Method+': '+$result.error.message)}
    return $result.result
}
function Local-Json([string]$Address) {
    $response=(Local-Request $Address).GetResponse()
    try {$reader=New-Object IO.StreamReader($response.GetResponseStream(),[Text.Encoding]::UTF8); try{return ($reader.ReadToEnd()|ConvertFrom-Json)}finally{$reader.Dispose()}}
    finally {$response.Dispose()}
}
function Safe-MediaState($value) {
    if($null -eq $value){return $null}
    if($value -is [string]){if($value.Length -le 160 -and $value -match '^[A-Za-z0-9_ .():-]+$'){return $value};return '[omitted]'}
    if($value -is [ValueType]){return $value}
    $safe=@{}
    foreach($key in @('event','state','reason','pipeline_state','video_buffering_state','audio_buffering_state','pipeline_buffering_state','seek_target','duration','for_suspended_start')){
        if($value.PSObject.Properties[$key]){$safe[$key]=Safe-MediaState $value.$key}
    }
    return $safe
}
function Safe-Headers($headers) {
    $safe=@{}
    foreach($item in $headers.PSObject.Properties){
        $name=$item.Name.ToLowerInvariant(); $value=[string]$item.Value
        if($name -in @('range','content-range','content-length','accept-ranges','content-type') -and $value.Length -le 240 -and $value -match '^[a-zA-Z0-9 /,;=.+_*:-]+$'){$safe[$name]=$value}
    }
    return $safe
}
function Drain-Media {
    foreach($raw in $pageCdp.DrainEvents()){
        $e=$raw|ConvertFrom-Json
        if($e.method -eq 'Media.playerPropertiesChanged'){
            $allowed=@($e.params.properties|Where-Object {$_.name -in @('kVideoDecoderName','kIsPlatformVideoDecoder','kAudioDecoderName','kResolution','kVideoTracks','kAudioTracks','kBitrate','kMaxDuration','kRendererName')})
            if($allowed.Count -and $phase.mediaProperties.Count -lt 2000){$phase.mediaProperties.Add(@{at=[DateTime]::UtcNow.ToString('o');playerId=$e.params.playerId;properties=$allowed})}
        } elseif($e.method -eq 'Media.playerEventsAdded'){
            foreach($item in $e.params.events){try{$value=$item.value|ConvertFrom-Json}catch{continue};if($phase.mediaEvents.Count -lt 6000){$phase.mediaEvents.Add(@{at=[DateTime]::UtcNow.ToString('o');playerId=$e.params.playerId;timestamp=$item.timestamp;data=(Safe-MediaState $value)})}}
        } elseif($e.method -eq 'Network.requestWillBeSent'){
            $uri=[uri]$e.params.request.url
            if($uri.Scheme -eq 'http' -and $uri.Host -eq '127.0.0.1' -and $uri.Port -eq $pageAddress.Port -and $uri.AbsolutePath.StartsWith('/api/control')){
                $report.controlRequestsObserved++;throw '检测到意外播控请求，停止测试。'
            }
            if($e.params.request.url -eq $sourceUri -and $phase.mediaRequests.Count -lt 4000){
                $request=@{id=$e.params.requestId;sourceKind=$phase.kind;started=$e.params.timestamp;active=$true;dataBytes=0L;wireBytes=0L;headers=(Safe-Headers $e.params.request.headers)}
                $requestsById[$e.params.requestId]=$request; $phase.mediaRequests.Add($request)
            }
        } elseif($e.method -like 'Network.*' -and $requestsById.ContainsKey([string]$e.params.requestId)){
            $q=$requestsById[$e.params.requestId]
            if($e.method -eq 'Network.dataReceived'){$q.dataBytes+=[long]$e.params.dataLength;$q.wireBytes+=[long]$e.params.encodedDataLength}
            elseif($e.method -eq 'Network.responseReceived'){
                $q.responseAt=$e.params.timestamp; $q.status=$e.params.response.status; $q.fromDiskCache=$e.params.response.fromDiskCache -eq $true
                $q.fromServiceWorker=$e.params.response.fromServiceWorker -eq $true; $q.responseHeaders=Safe-Headers $e.params.response.headers
                $q.remoteAddress=$e.params.response.remoteIPAddress
                $q.timing=@{};foreach($key in @('requestTime','proxyStart','proxyEnd','dnsStart','dnsEnd','connectStart','connectEnd','sendStart','sendEnd','receiveHeadersStart','receiveHeadersEnd')){
                    if($null -ne $e.params.response.timing.$key){$q.timing[$key]=$e.params.response.timing.$key}
                }
            } elseif($e.method -in @('Network.loadingFinished','Network.loadingFailed')){
                $q.active=$false;$q.finished=$e.params.timestamp;$q.result=$e.method
                if($e.params.errorText -match '^net::ERR_[A-Z0-9_]+$'){$q.error=$e.params.errorText}
                [void]$requestsById.Remove($e.params.requestId)
            }
        }
    }
}
function Close-TestBrowser {
    if($browserCdp){try{[void](Cdp $browserCdp 'Browser.close')}catch{}}
    if($ownedBrowser){try{if(-not $ownedBrowser.WaitForExit(3000)){Stop-Process -InputObject $ownedBrowser -ErrorAction SilentlyContinue}}catch{}}
    if($pageCdp){$pageCdp.Dispose()};if($browserCdp){$browserCdp.Dispose()}
    $script:ownedBrowser=$null;$script:pageCdp=$null;$script:browserCdp=$null
}
function Read-Fragment([string]$Kind,[long]$Offset,[long]$Count) {
    $response=$null;$stream=$null;$sha=[Security.Cryptography.SHA256]::Create();$clock=[Diagnostics.Stopwatch]::StartNew()
    $result=@{kind=$Kind;offset=$Offset;requestedBytes=$Count;completed=$false;bytes=0L}
    try {
        if($Kind -eq 'file'){
            $stream=[IO.File]::Open($VideoPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
            [void]$stream.Seek($Offset,[IO.SeekOrigin]::Begin)
        } else {
            $request=Local-Request $httpUri; $request.AddRange($Offset,($Offset+$Count-1));$response=$request.GetResponse()
            $result.headerMs=[Math]::Round($clock.Elapsed.TotalMilliseconds,1);$result.status=[int]$response.StatusCode
            $result.contentRange=$response.Headers['Content-Range'];$result.contentLength=$response.ContentLength
            $expected='bytes '+$Offset+'-'+($Offset+$Count-1)+'/'+$videoInfo.Length
            if($result.status -ne 206 -or $result.contentRange -ne $expected -or $response.ContentLength -ne $Count){throw 'HTTP分段范围/文件大小与选择的视频不一致。'}
            $stream=$response.GetResponseStream()
        }
        $buffer=New-Object byte[] 65536
        while($result.bytes -lt $Count){
            if($clock.Elapsed.TotalSeconds -gt 30){throw '片段读取超过30秒，保留已读数据。'}
            $n=$stream.Read($buffer,0,[int][Math]::Min($buffer.Length,$Count-$result.bytes))
            if($n -eq 0){throw '文件或HTTP响应提前结束。'}
            if($result.bytes -eq 0){$result.firstByteMs=[Math]::Round($clock.Elapsed.TotalMilliseconds,1)}
            [void]$sha.TransformBlock($buffer,0,$n,$buffer,0);$result.bytes+=$n
        }
        [void]$sha.TransformFinalBlock((New-Object byte[] 0),0,0)
        $result.sha256=[BitConverter]::ToString($sha.Hash).Replace('-','');$result.completed=$true
    } catch {$result.error=$_.Exception.Message}
    finally {
        $result.elapsedMs=[Math]::Round($clock.Elapsed.TotalMilliseconds,1)
        $result.mibPerSecond=[Math]::Round(($result.bytes/1MB)/[Math]::Max($clock.Elapsed.TotalSeconds,0.0001),2)
        if($stream){$stream.Dispose()};if($response){$response.Dispose()};$sha.Dispose()
    }
    return $result
}

try {
    if($PSVersionTable.PSEdition -eq 'Core'){throw '请双击随包BAT，使用Windows PowerShell 5.1。'}
    if(($NonInteractive -or $HeadlessTest) -and -not $UseExistingService){throw '自动化参数只能用于隔离测试服务。'}
    if($manualStop -and [Console]::IsInputRedirected){throw '手动结束需要交互控制台，请双击start-read-test.bat。'}
    Write-Host '固定视频读取对照：直接文件 / 本机Web。没有点位按钮，不发送滑轨动作。' -ForegroundColor Cyan
    Write-Host '请先确认滑轨静止并关闭巡展，退出原播放页面和数字人Host；测试期间不要用中控发命令。'
    if(-not $UseExistingService){
        Add-Type -AssemblyName System.Windows.Forms
        if(-not $RuntimeExe){
            $picker=New-Object Windows.Forms.OpenFileDialog;$picker.Title='选择现场 app\runtime\slider-screen-service.exe';$picker.Filter='滑轨播放器|slider-screen-service.exe'
            try{if($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){throw '已取消选择。'};$RuntimeExe=$picker.FileName}finally{$picker.Dispose()}
        }
        $RuntimeExe=(Resolve-Path -LiteralPath $RuntimeExe).Path
        if([IO.Path]::GetFileName($RuntimeExe) -ne 'slider-screen-service.exe'){throw '请选择现场滑轨播放器EXE。'}
        $RuntimeRoot=Split-Path -Parent $RuntimeExe
        $settings=[IO.File]::ReadAllText((Join-Path $RuntimeRoot 'config\app.json'),[Text.Encoding]::UTF8)|ConvertFrom-Json
        if($settings.apiHost -ne '127.0.0.1' -or $settings.apiPort -lt 1 -or $settings.apiPort -gt 65535){throw '本机服务配置不符合预期，未修改。'}
        $PageUrl='http://127.0.0.1:'+$settings.apiPort+'/'
        $oldProfile=Join-Path $RuntimeRoot 'browser-profile'
        $busy=@(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'"|Where-Object {$_.CommandLine -and $_.CommandLine.IndexOf($oldProfile,[StringComparison]::OrdinalIgnoreCase) -ge 0})
        if($busy.Count -or @(Get-NetTCPConnection -LocalPort $settings.apiPort -State Listen -ErrorAction SilentlyContinue).Count){throw '旧网页/后台尚未退出，请完整退出后重试；工具不终止已有程序。'}
    } elseif(-not $RuntimeRoot){throw '隔离测试必须明确提供RuntimeRoot。'}
    $RuntimeRoot=(Resolve-Path -LiteralPath $RuntimeRoot).Path
    $mediaRoot=[IO.Path]::GetFullPath((Join-Path $RuntimeRoot 'content\videos'))+[IO.Path]::DirectorySeparatorChar
    if(-not $VideoPath){
        Add-Type -AssemblyName System.Windows.Forms
        $picker=New-Object Windows.Forms.OpenFileDialog;$picker.Title='选择这次固定测试的视频，建议选发生卡顿的p04';$picker.Filter='视频|*.mp4;*.webm;*.m4v;*.mov';$picker.InitialDirectory=$mediaRoot
        try{if($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){throw '已取消选择视频。'};$VideoPath=$picker.FileName}finally{$picker.Dispose()}
    }
    $VideoPath=(Resolve-Path -LiteralPath $VideoPath).Path
    if(-not $VideoPath.StartsWith($mediaRoot,[StringComparison]::OrdinalIgnoreCase)){throw '必须选择这个播放器 runtime\content\videos 内的视频，确保文件和Web对应同一资源。'}
    $videoInfo=Get-Item -LiteralPath $VideoPath
    if($videoInfo.PSIsContainer -or $videoInfo.Length -lt 1){throw '视频文件不存在或为空。'}
    $pageAddress=[uri]$PageUrl
    if($pageAddress.Scheme -ne 'http' -or $pageAddress.Host -ne '127.0.0.1' -or $pageAddress.AbsolutePath -ne '/' -or $pageAddress.UserInfo -or $pageAddress.Query -or $pageAddress.Fragment){throw '只允许本机服务根地址。'}
    $PageUrl=$pageAddress.AbsoluteUri
    $relative=$VideoPath.Substring($mediaRoot.Length)
    $urlParts=@($relative -split '[\\/]'|ForEach-Object {[uri]::EscapeDataString($_)})
    $httpUri=$PageUrl+'content/videos/'+($urlParts -join '/')
    $fileUri=([uri]$VideoPath).AbsoluteUri
    $report.media=@{name=$videoInfo.Name;relativePath=$relative;bytes=$videoInfo.Length;lastWriteUtc=$videoInfo.LastWriteTimeUtc.ToString('o')}
    $report.servicePort=$pageAddress.Port
    if(-not $UseExistingService){
        [void](Read-Host '确认轨道静止、旧程序已退出后按Enter；原服务只初始化连接，工具不发移动命令')
        $ownedBackend=Start-Process -FilePath $RuntimeExe -ArgumentList '--no-browser' -WorkingDirectory $RuntimeRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runFolder 'backend-out.log') -RedirectStandardError (Join-Path $runFolder 'backend-error.log')
    }
    $ready=$null;$deadline=[DateTime]::UtcNow.AddSeconds(30)
    while([DateTime]::UtcNow -lt $deadline){try{$ready=Read-Status;break}catch{Start-Sleep -Milliseconds 400};if($ownedBackend -and $ownedBackend.HasExited){throw '原后台启动失败。'}}
    if(-not $ready){throw '原后台未就绪。'};Assert-Stationary $ready;$report.initialStatus=$ready
    $head=(Local-Request $httpUri 'HEAD').GetResponse()
    try{
        $report.httpHead=@{status=[int]$head.StatusCode;bytes=$head.ContentLength;acceptRanges=$head.Headers['Accept-Ranges'];contentType=$head.ContentType}
        if([int]$head.StatusCode -ne 200 -or $head.ContentLength -ne $videoInfo.Length){throw 'Web资源大小与选择的本地文件不一致，不能进行有效对照。'}
    }finally{$head.Dispose()}
    $edge=$null
    foreach($base in @(${env:ProgramFiles(x86)},$env:ProgramFiles,$env:LOCALAPPDATA)){
        if($base){$candidate=Join-Path $base 'Microsoft\Edge\Application\msedge.exe';if(Test-Path -LiteralPath $candidate){$edge=$candidate;break}}
    }
    if(-not $edge){throw '未安装Microsoft Edge。'}
    $report.environment=@{
        edgeVersion=(Get-Item -LiteralPath $edge).VersionInfo.FileVersion;headlessTest=[bool]$HeadlessTest
        os=(Get-CimInstance Win32_OperatingSystem|Select-Object Caption,Version,BuildNumber,TotalVisibleMemorySize)
        cpu=@(Get-CimInstance Win32_Processor|Select-Object Name,NumberOfLogicalProcessors)
        gpu=@(Get-CimInstance Win32_VideoController|Select-Object Name,DriverVersion,CurrentHorizontalResolution,CurrentVerticalResolution)
    }
    $driveName=[IO.Path]::GetPathRoot($VideoPath).TrimEnd('\')
    try{$report.environment.mediaVolume=Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='"+$driveName+"'")|Select-Object DeviceID,DriveType,FileSystem,Size,FreeSpace}catch{}
    if(-not ('RailDiagnosticCdp' -as [type])){Add-Type -Path (Join-Path $PSScriptRoot 'CdpConnection.cs') -ReferencedAssemblies 'System.Web.Extensions','System.Net.Http'}
    foreach($kind in $order){
        Assert-Stationary (Read-Status)
        $phase=[ordered]@{kind=$kind;startedAt=[DateTime]::UtcNow.ToString('o');completed=$false;stopMode=$report.stopMode;samples=(New-Object 'System.Collections.Generic.List[object]');mediaProperties=(New-Object 'System.Collections.Generic.List[object]');mediaEvents=(New-Object 'System.Collections.Generic.List[object]');mediaRequests=(New-Object 'System.Collections.Generic.List[object]');systemSamples=(New-Object 'System.Collections.Generic.List[object]')}
        $report.phases.Add($phase);$requestsById=@{};Save-ReadReport
        $label=if($kind -eq 'file'){'直接读取文件'}else{'通过本机Web读取'}
        if(-not $NonInteractive){[void](Read-Host ('即将开始「'+$label+'」。准备好后按Enter，网页将自动播放同一个视频'))}
        $busy=@(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'"|Where-Object {$_.CommandLine -and $_.CommandLine.IndexOf($readBrowserProfile,[StringComparison]::OrdinalIgnoreCase) -ge 0})
        if($busy.Count){throw '上一轮测试浏览器未完全退出，不打开重叠播放器。'}
        $launch=[DateTime]::UtcNow
        $edgeArgs=@('--kiosk','about:blank','--edge-kiosk-type=fullscreen','--no-first-run','--autoplay-policy=no-user-gesture-required','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',('--user-data-dir="'+$readBrowserProfile+'"'))
        if($HeadlessTest){$edgeArgs+='--headless=new'}
        $style=if($HeadlessTest){'Hidden'}else{'Normal'}
        $ownedBrowser=Start-Process -FilePath $edge -ArgumentList $edgeArgs -WindowStyle $style -PassThru
        $portFile=Join-Path $readBrowserProfile 'DevToolsActivePort';$debugPort=0;$deadline=[DateTime]::UtcNow.AddSeconds(25)
        while([DateTime]::UtcNow -lt $deadline){
            if((Test-Path -LiteralPath $portFile) -and (Get-Item -LiteralPath $portFile).LastWriteTimeUtc -ge $launch.AddSeconds(-1)){
                $lines=[IO.File]::ReadAllLines($portFile);if($lines.Length -ge 2 -and [int]::TryParse($lines[0],[ref]$debugPort) -and $debugPort -gt 0){break}
            };Start-Sleep -Milliseconds 200
        }
        if(-not $debugPort){throw '浏览器诊断启动失败，不修改浏览器策略。'}
        $listeners=@(Get-NetTCPConnection -LocalPort $debugPort -State Listen)
        if(-not $listeners.Count -or @($listeners|Where-Object {$_.LocalAddress -notin @('127.0.0.1','::1')}).Count){throw '调试端口没有限制在本机回环，停止测试。'}
        $debugBase='http://127.0.0.1:'+$debugPort
        $version=Local-Json ($debugBase+'/json/version');$browserCdp=New-Object RailDiagnosticCdp($version.webSocketDebuggerUrl)
        $target=@(Local-Json ($debugBase+'/json/list'))|Where-Object {$_.type -eq 'page' -and $_.url -eq 'about:blank'}|Select-Object -First 1
        if(-not $target){throw '没有找到本次测试页，不连接其他网页。'}
        $pageCdp=New-Object RailDiagnosticCdp($target.webSocketDebuggerUrl)
        $gpu=Cdp $browserCdp 'SystemInfo.getInfo';$phase.browserGpu=@{devices=$gpu.gpu.devices;featureStatus=$gpu.gpu.featureStatus}
        [void](Cdp $pageCdp 'Page.enable');[void](Cdp $pageCdp 'Media.enable')
        [void](Cdp $pageCdp 'Network.enable' @{maxTotalBufferSize=1048576;maxResourceBufferSize=65536})
        $sourceUri=if($kind -eq 'file'){$fileUri}else{$httpUri}
        $options=@{kind=$kind;source=$sourceUri;name=$videoInfo.Name}|ConvertTo-Json -Compress
        [void](Cdp $pageCdp 'Page.addScriptToEvaluateOnNewDocument' @{source=('window.__railReadOptions='+$options+';')})
        [void](Cdp $pageCdp 'Page.navigate' @{url=([uri](Join-Path $PSScriptRoot 'read-player.html')).AbsoluteUri})
        if($manualStop){while([Console]::KeyAvailable){[void][Console]::ReadKey($true)}}
        Write-Host ('正在采集「'+$label+'」。观察充分后，Alt+Tab切回此黑色窗口按Enter结束本轮。') -ForegroundColor Green
        $watch=[Diagnostics.Stopwatch]::StartNew();$nextSave=0;$nextSystem=0;$probeSeen=$false
        while($manualStop -or $watch.Elapsed.TotalSeconds -lt $DurationSeconds){
            $t=$watch.Elapsed.TotalSeconds
            $value=Cdp $pageCdp 'Runtime.evaluate' @{expression='window.__railReadProbe ? window.__railReadProbe.read() : null';returnByValue=$true}
            if($value.exceptionDetails){throw '页面采样执行失败。'}
            $sample=@{elapsedSeconds=[Math]::Round($t,3);at=[DateTime]::UtcNow.ToString('o');browser=$value.result.value}
            if($sample.browser){$probeSeen=$true;if($sample.browser.kind -ne $kind -or ($sample.browser.video.actualSourceKind -and $sample.browser.video.actualSourceKind -ne $kind)){throw '实际媒体读取方式不匹配。'}}
            elseif($t -gt 15){throw '测试页面没有正确加载。'}
            $phase.samples.Add($sample);Drain-Media
            $sample.activeMediaRequests=@($requestsById.Values|ForEach-Object {@{id=$_.id;dataBytes=$_.dataBytes;wireBytes=$_.wireBytes}})
            if($t -ge $nextSystem){
                $sample.status=Read-Status;Assert-Stationary $sample.status
                $sys=@{elapsedSeconds=[Math]::Round($t,3)}
                try{$sys.cpuPercent=(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime;$sys.availableMemoryMb=(Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory).AvailableMBytes}catch{$sys.cpuMemoryUnavailable=$true}
                try{$disk=Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'";$sys.diskReadBytesPerSecond=$disk.DiskReadBytesPersec;$sys.diskQueueLength=$disk.CurrentDiskQueueLength}catch{$sys.diskUnavailable=$true}
                $phase.systemSamples.Add($sys);$nextSystem=$t+5
            }
            if($t -ge $nextSave){Save-ReadReport;$nextSave=$t+15}
            $Host.UI.RawUI.WindowTitle=$label+' 已记录 '+[int]$watch.Elapsed.TotalSeconds+' 秒；Enter结束'
            if($manualStop){$stop=$false;while([Console]::KeyAvailable){if([Console]::ReadKey($true).Key -eq [ConsoleKey]::Enter){$stop=$true}};if($stop){$phase.completionReason='operator-enter';break}}
            $remaining=1000-($watch.Elapsed.TotalSeconds-$t)*1000;if($remaining -gt 0){Start-Sleep -Milliseconds ([int]$remaining)}
        }
        Drain-Media
        if(-not $probeSeen){throw '没有采集到测试页面数据。'}
        if(-not $manualStop){$phase.completionReason='duration-elapsed'}
        $phase.elapsedSeconds=[Math]::Round($watch.Elapsed.TotalSeconds,3);$phase.cdpEventsDiscarded=$pageCdp.DroppedEvents;$phase.completed=$true
        $phase.playbackObserved=@($phase.samples|Where-Object {$_.browser -and $_.browser.video.currentTime -gt 0 -and $_.browser.video.totalFrames -gt 0}).Count -gt 0
        Save-ReadReport;Close-TestBrowser
        Write-Host ('「'+$label+'」已保存，测试网页已关闭。') -ForegroundColor Green
    }
    Write-Host '两轮完成。正在自动校验文件开头/中间/尾部数据片段与Web响应，不播放、不移动。' -ForegroundColor Cyan
    $size=[long][Math]::Min(8MB,$videoInfo.Length)
    $offsets=@(0L,[long][Math]::Floor(($videoInfo.Length-$size)/2),[long]($videoInfo.Length-$size))|Select-Object -Unique
    foreach($offset in $offsets){
        Assert-Stationary (Read-Status)
        Write-Host ('校验片段，偏移 '+$offset+'，长度 '+$size+' 字节。')
        $local=Read-Fragment 'file' $offset $size;$remote=Read-Fragment 'http' $offset $size
        $report.readChecks.Add(@{offset=$offset;file=$local;http=$remote;matching=($local.completed -and $remote.completed -and $local.sha256 -eq $remote.sha256)})
        Save-ReadReport
    }
    $after=Get-Item -LiteralPath $VideoPath
    $report.fileUnchangedDuringRun=$after.Length -eq $videoInfo.Length -and $after.LastWriteTimeUtc.ToString('o') -eq $report.media.lastWriteUtc
    $report.sampledContentMatches=@($report.readChecks|Where-Object {-not $_.matching}).Count -eq 0
    $report.validComparison=$report.fileUnchangedDuringRun -and $report.sampledContentMatches
    $report.completed=$true
    if($report.validComparison){Write-Host '完成。只需发送 read-comparison-report.json，并说明哪一轮卡顿。' -ForegroundColor Green}
    else{Write-Host '采集完成，但文件一致性校验未通过；请发送报告，暂不能据此判断读取差异。' -ForegroundColor Yellow}
} catch {
    $exitCode=1;$report.errors.Add(@{message=$_.Exception.Message});Write-Host ('测试中止，保留部分报告：'+$_.Exception.Message) -ForegroundColor Yellow
} finally {
    Close-TestBrowser
    if($ownedBackend -and -not $ownedBackend.HasExited){
        try{$status=Read-Status;Assert-Stationary $status;Stop-Process -InputObject $ownedBackend -ErrorAction SilentlyContinue}
        catch{$report.backendLeftRunning=$true;Write-Host '无法确认滑轨静止，原后台保留运行；请现场确认安全后手动退出。' -ForegroundColor Yellow}
    }
    try{Save-ReadReport}catch{Write-Host ('报告保存失败：'+$_.Exception.Message) -ForegroundColor Red}
    Write-Host $reportFile
    if(-not $NonInteractive -and (Test-Path -LiteralPath $reportFile)){Start-Process explorer.exe -ArgumentList ('/select,"'+$reportFile+'"')}
}
exit $exitCode
