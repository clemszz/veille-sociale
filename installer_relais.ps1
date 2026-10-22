# Installe (ou met à jour) la tâche planifiée Windows du relais ameli sur ce PC.
# Elle lance relais_local.py sans fenêtre chaque matin à 8 h 45 et à chaque
# ouverture de session (rattrapage si le PC était éteint à 8 h 45).
# Désinstaller : Unregister-ScheduledTask -TaskName "Veille AIPALS - relais ameli" -Confirm:$false
$projet = $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "$projet\.venv\Scripts\pythonw.exe" -Argument "`"$projet\relais_local.py`"" -WorkingDirectory $projet
$matin = New-ScheduledTaskTrigger -Daily -At "08:45"
$session = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$session.Delay = "PT5M"
$reglages = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Veille AIPALS - relais ameli" -Description "Relève les actualités ameli pour la veille juridique sociale AIPALS (dépôt clemszz/veille-sociale)." -Action $action -Trigger $matin, $session -Settings $reglages -Force | Out-Null
Write-Output "Tâche « Veille AIPALS - relais ameli » installée."
