@echo off


call stop_server.bat
call start_server.bat
timeout /t 5 /nobreak
call start_monitoring.bat
call restart_haproxy.bat
call clear.bat
timeout /t 5 /nobreak
start "BENIGN" cmd /k start_benign.bat
start "ATTACKER" cmd /k spoofed_attacker.bat

pause