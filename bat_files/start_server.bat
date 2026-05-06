@echo off

start /b ssh server1 "cd ~/Desktop/scripts && source venv/bin/activate && nohup ./server.sh > /dev/null 2>&1 &"
@REM start /b ssh server2 "cd ~/Desktop/MatMul && source .venv/bin/activate && nohup ./server.sh > /dev/null 2>&1 &"
@REM start /b ssh server3 "cd ~/Desktop/MatMul && source .venv/bin/activate && nohup ./server.sh > /dev/null 2>&1 &"

echo All servers starting...