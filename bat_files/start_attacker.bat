@echo off
set c=%1

ssh attacker "cd ~/Desktop/data && ./attacker.sh %c%"