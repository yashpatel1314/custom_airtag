# Turns the PC's Bluetooth radio ON from a shell (no Settings app needed).
# The BLE listener (server/listener.py, tools/scan_tags.py) errors with
# "Bluetooth radio is not powered on" when it's off — run this first.
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                   $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
$null = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | Where-Object { $_.Kind -eq 'Bluetooth' }
if ($null -eq $bt) { Write-Error 'No Bluetooth radio found'; exit 1 }
if ($bt.State -eq 'On') { 'Bluetooth already on'; exit 0 }
$result = Await ($bt.SetStateAsync('On')) ([Windows.Devices.Radios.RadioAccessStatus])
"Bluetooth: $($bt.State) (SetState: $result)"
