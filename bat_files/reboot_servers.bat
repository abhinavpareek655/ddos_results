@echo off

ssh server1 "sudo reboot"
@REM ssh server2 "sudo reboot"
@REM ssh server3 "sudo reboot"
ssh loadbalancer "sudo reboot"
ssh attacker "sudo reboot"
ssh benign "sudo reboot"