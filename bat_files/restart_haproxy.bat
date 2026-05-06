@echo off
ssh loadbalancer "sudo systemctl restart haproxy-autoscaler"
ssh loadbalancer "sudo systemctl restart haproxy"