@echo off
set time=%1

ssh benign "cd ~/Desktop/data && echo 'sleep 3; ./benign.sh' | at %time% && rm a.txt && rm a.dat && rm a.csv"