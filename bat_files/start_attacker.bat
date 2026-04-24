@echo off
set c=%1
set time=%2

ssh attacker "cd ~/Desktop/data && echo 'sleep 4; ./attacker.sh %c%' | at %time% && rm a.txt && rm a.dat && rm a.csv"