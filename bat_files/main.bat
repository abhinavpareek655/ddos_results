@echo off

set time=%1
set c=%2

call start_server.bat
call start_monitoring.bat %time%
call restart_haproxy.bat
call start_benign.bat %time%
call start_attacker.bat %c% %time%

pause