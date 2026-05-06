@echo off

ssh benign "cd ~/Desktop/data && rm a.txt && rm a.dat && rm a.csv"
ssh attacker "cd ~/Desktop/data && rm a.txt && rm a.dat && rm a.csv"