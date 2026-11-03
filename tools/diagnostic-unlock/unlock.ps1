param([string]$TargetDirectory,[switch]$ScanOnly)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
Set-Location -LiteralPath $env:TEMP
$result=[ordered]@{startedAt=[DateTime]::UtcNow.ToString('o');actions=(New-Object 'System.Collections.Generic.List[object]');errors=(New-Object 'System.Collections.Generic.List[string]');filesDeleted=0;hardwareCommandsSent=0}
$outputFile=Join-Path $PSScriptRoot ('unlock-report-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)+'.json')
function Inside([string]$Path,[string]$Root) {
 if(-not $Path){return $false}
 try{$p=[IO.Path]::GetFullPath($Path).TrimEnd('\');$r=[IO.Path]::GetFullPath($Root).TrimEnd('\');return $p.Equals($r,[StringComparison]::OrdinalIgnoreCase) -or $p.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase)}catch{return $false}
}
function Association($proc) {
 if(-not $proc.CommandLine){return $null}
 $parts=[RailLockQuery]::Args($proc.CommandLine)
 if($proc.Name -in @('powershell.exe','pwsh.exe')){
  for($i=0;$i -lt $parts.Length-1;$i++){
   if($parts[$i] -in @('-File','-f')){
    $path=$parts[$i+1]
    if([IO.Path]::IsPathRooted($path) -and (Inside $path $TargetDirectory) -and [IO.Path]::GetFileName($path) -in @('collect.ps1','compare.ps1','read-compare.ps1')){return '诊断脚本'}
   }
  }
 }
 if($proc.Name -eq 'msedge.exe'){
  for($i=0;$i -lt $parts.Length;$i++){
   $profilePath=$null
   if($parts[$i].StartsWith('--user-data-dir=')){$profilePath=$parts[$i].Substring(16)}
   elseif($parts[$i] -eq '--user-data-dir' -and $i+1 -lt $parts.Length){$profilePath=$parts[$i+1]}
   if($profilePath -and [IO.Path]::IsPathRooted($profilePath) -and (Inside $profilePath (Join-Path $TargetDirectory 'reports'))){return '目录内的诊断浏览器'}
  }
 }
 if($proc.Name -eq 'cmd.exe'){
  # Only an exact known batch argument, never a substring match or all cmd.exe.
  foreach($arg in $parts){$path=$arg.Trim('"');if([IO.Path]::IsPathRooted($path) -and (Inside $path $TargetDirectory) -and [IO.Path]::GetFileName($path) -in @('start-diagnostics.bat','start-ab-test.bat','start-read-test.bat')){return '诊断启动窗口'}}
 }
 return $null
}
function Inspect-Locks {
 $all=@(Get-CimInstance Win32_Process)
 $safe=@{};$entries=@{};$excluded=@{};$selfId=$PID
 while($selfId -and -not $excluded.ContainsKey([int]$selfId)){
  $excluded[[int]$selfId]=$true;$parent=$all|Where-Object ProcessId -eq $selfId|Select-Object -First 1;$selfId=$parent.ParentProcessId
 }
 foreach($proc in $all){
  if($excluded.ContainsKey([int]$proc.ProcessId)){continue}
  $why=Association $proc
  if($why){$safe[[int]$proc.ProcessId]=$why}
 }
 # Edge children inherit only from an identified diagnostic Edge process.
 for($pass=0;$pass -lt 8;$pass++){
  foreach($proc in $all){
   if($proc.Name -eq 'msedge.exe' -and $safe.ContainsKey([int]$proc.ParentProcessId) -and $safe[[int]$proc.ParentProcessId] -like '*浏览器*' -and -not $excluded.ContainsKey([int]$proc.ProcessId)){
    $parent=$all|Where-Object ProcessId -eq $proc.ParentProcessId|Select-Object -First 1
    if($parent -and $proc.CreationDate -ge $parent.CreationDate){$safe[[int]$proc.ProcessId]='诊断浏览器子进程'}
   }
  }
 }
 $files=New-Object 'System.Collections.Generic.List[string]';$stack=New-Object 'System.Collections.Generic.Stack[string]';$stack.Push($TargetDirectory);$scanWarnings=New-Object 'System.Collections.Generic.List[string]'
 while($stack.Count -and $files.Count -lt 4096){
  $directory=$stack.Pop()
  try{foreach($item in Get-ChildItem -LiteralPath $directory -Force){
   if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
   if($item.PSIsContainer){$stack.Push($item.FullName)}else{$files.Add($item.FullName);if($files.Count -ge 4096){break}}
  }}catch{$scanWarnings.Add('部分目录不可读取；扫描不完整。')}
 }
 if($files.Count -ge 4096){$scanWarnings.Add('文件数量达到4096上限；扫描可能不完整。')}
 $holders=New-Object 'System.Collections.Generic.HashSet[int]'
 for($offset=0;$offset -lt $files.Count;$offset+=128){
  $end=[Math]::Min($offset+127,$files.Count-1)
  try{foreach($id in [RailLockQuery]::Find([string[]]$files.GetRange($offset,$end-$offset+1).ToArray())){[void]$holders.Add($id)}}catch{$scanWarnings.Add($_.Exception.Message)}
 }
 foreach($proc in $all){
  $id=[int]$proc.ProcessId
  if(-not $safe.ContainsKey($id) -and -not $holders.Contains($id)){continue}
  $entry=[ordered]@{pid=$id;name=$proc.Name;created=$proc.CreationDate.ToUniversalTime().ToString('o');association=$safe[$id];fileLockDetected=$holders.Contains($id);canCloseDiagnostic=$safe.ContainsKey($id);protectedReason=$null}
  if(-not $entry.canCloseDiagnostic){$entry.protectedReason=if($proc.Name -eq 'slider-screen-service.exe'){'播放器业务后台：只报告，不自动结束。'}else{'其他软件或身份不明确：只报告，不自动结束。'}}
  $entries[$id]=[pscustomobject]$entry
 }
 $listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -in @(8000,8001)|Select-Object LocalAddress,LocalPort,OwningProcess)
 return @{processes=@($entries.Values);warnings=@($scanWarnings);filesChecked=$files.Count;listeners=$listeners}
}
try {
 if($PSVersionTable.PSEdition -eq 'Core'){throw '请双击start-unlock.bat，使用Windows PowerShell 5.1。'}
 if(-not $TargetDirectory){
  Add-Type -AssemblyName System.Windows.Forms
  $picker=New-Object Windows.Forms.FolderBrowserDialog;$picker.Description='选择删不掉的旧诊断工具最外层文件夹，不是app或reports子文件夹'
  try{if($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){throw '已取消选择。'};$TargetDirectory=$picker.SelectedPath}finally{$picker.Dispose()}
 }
 $TargetDirectory=(Resolve-Path -LiteralPath $TargetDirectory).Path.TrimEnd('\')
 if(-not (Get-Item -LiteralPath $TargetDirectory).PSIsContainer){throw '请选择文件夹。'}
 if(Inside $PSScriptRoot $TargetDirectory){throw '清理工具必须放在旧工具文件夹外面，请重新解压到桌面的另一个文件夹。'}
 foreach($blocked in @('D:\成都理工大学70周年视频播放器','D:\成都理工大学70周年投影播放器','D:\中控软件穿越成理双视频')){if(Inside $TargetDirectory $blocked){throw '不处理70周年系统目录。'}}
 $cursor=Get-Item -LiteralPath $TargetDirectory
 while($cursor){if($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint){throw '目标路径包含目录链接，拒绝自动清理。'};$cursor=$cursor.Parent}
 if(-not (Test-Path -LiteralPath (Join-Path $TargetDirectory 'CdpConnection.cs')) -or -not (@('collect.ps1','compare.ps1','read-compare.ps1')|Where-Object{Test-Path -LiteralPath (Join-Path $TargetDirectory $_)})){throw '未识别为旧诊断工具目录。请选择含CdpConnection.cs和诊断脚本的最外层文件夹。'}
 if((Test-Path -LiteralPath (Join-Path $TargetDirectory '.git')) -or (Test-Path -LiteralPath (Join-Path $TargetDirectory 'config\app.json')) -or (Test-Path -LiteralPath (Join-Path $TargetDirectory 'slider-screen-service.exe'))){throw '不允许把开发仓库或正式运行目录作为清理目标。'}
 if(-not ('RailLockQuery' -as [type])){Add-Type -Path (Join-Path $PSScriptRoot 'LockQuery.cs')}
 $result.target=$TargetDirectory;$result.before=Inspect-Locks
 Write-Host ('检测目标：'+$TargetDirectory) -ForegroundColor Cyan
 $result.before.processes|Select-Object pid,name,association,fileLockDetected,canCloseDiagnostic,protectedReason|Format-Table -AutoSize -Wrap|Out-Host
 foreach($warning in $result.before.warnings){Write-Host $warning -ForegroundColor Yellow}
 $candidates=@($result.before.processes|Where-Object canCloseDiagnostic)
 if($candidates.Count -and -not $ScanOnly){
  Write-Host '优先在旧黑色窗口按Enter正常结束。下面的强制清理可能丢失尚未保存的最后一段诊断数据。' -ForegroundColor Yellow
  Write-Host '只关闭表中canCloseDiagnostic=True的诊断进程，不删除报告、不关闭业务后台、不操作滑轨。'
  if((Read-Host '确认轨道静止、报告已保留且不再采集；输入 YES 清理，直接回车只检测') -ceq 'YES'){
   $ordered=@($candidates|Sort-Object @{Expression={if($_.association -eq '诊断脚本'){0}elseif($_.name -eq 'cmd.exe'){1}else{2}}})
   foreach($item in $ordered){
    $fresh=Get-CimInstance Win32_Process -Filter ('ProcessId='+$item.pid) -ErrorAction SilentlyContinue
    if(-not $fresh){continue}
    if($fresh.Name -ne $item.name -or $fresh.CreationDate.ToUniversalTime().ToString('o') -ne $item.created){$result.actions.Add(@{pid=$item.pid;result='PID已变化，跳过'});continue}
    try{
     $process=Get-Process -Id $item.pid -ErrorAction Stop;[void]$process.Handle
     if([Math]::Abs(($process.StartTime.ToUniversalTime()-$fresh.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1){throw '进程启动时间不匹配，拒绝关闭。'}
     if($item.name -eq 'msedge.exe'){
      [void]$process.CloseMainWindow();[void]$process.WaitForExit(1500)
     }
     if(-not $process.HasExited){Stop-Process -InputObject $process -ErrorAction Stop}
     $result.actions.Add(@{pid=$item.pid;name=$item.name;result='已关闭诊断进程'})
    }catch{$result.actions.Add(@{pid=$item.pid;result='无法关闭，请检查权限或手动退出';detail=$_.Exception.Message})}
   }
   Start-Sleep -Milliseconds 700
  }
 }
 $result.after=Inspect-Locks
 Write-Host '复查结果：' -ForegroundColor Cyan
 $result.after.processes|Select-Object pid,name,association,fileLockDetected,protectedReason|Format-Table -AutoSize -Wrap|Out-Host
 if(-not $result.after.processes.Count){Write-Host '未发现已知占用。关闭旧文件夹窗口、关闭本清理窗口后，再手动删除旧工具目录。' -ForegroundColor Green}
 else{Write-Host '仍有占用，或有关联进程未退出。播放器后台、资源管理器、编辑器等只报告，请正常退出，不要随意结束进程。' -ForegroundColor Yellow}
 if($result.after.listeners.Count){Write-Host '8000/8001仍有监听，可能旧播放器后台没有完整退出。新测试前请正常退出旧后台；本工具不会强制终止它。' -ForegroundColor Yellow;$result.after.listeners|Format-Table|Out-Host}
 Write-Host '注意：仅持有目录的进程不一定被Restart Manager检测到；未发现不等于保证可删除。若仍失败，把unlock-report JSON发回。'
}catch{$result.errors.Add($_.Exception.Message);Write-Host $_.Exception.Message -ForegroundColor Red}
finally{
 [IO.File]::WriteAllText($outputFile,(ConvertTo-Json -InputObject $result -Depth 10),(New-Object Text.UTF8Encoding($false)))
 Write-Host ('检测报告：'+$outputFile)
 Write-Host '没有删除任何文件，也没有发送任何滑轨指令。'
}
