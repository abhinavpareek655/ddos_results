@echo off
set time=%1

ssh loadbalancer "sudo rm /var/log/haproxy-metrics.csv"
ssh loadbalancer "sudo systemctl start haproxy-autoscaler"
ssh loadbalancer "echo 'sudo systemctl restart haproxy-autoscaler' | at %time%"