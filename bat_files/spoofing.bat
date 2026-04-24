@echo off

set time=%1

call start_server.bat
call start_monitoring.bat %time%
call restart_haproxy.bat
call start_benign.bat %time%
@REM ssh abhinav@10.48.145.221 "cd ~/Desktop/'spoofing data' && sudo ./ip_addr.sh"
ssh attacker "cd ~/Desktop/'spoofing data' && echo 'sleep 4; ./attacker.sh' | at %time%" 

pause