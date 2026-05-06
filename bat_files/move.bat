@echo off

set c=%1
ssh benign "cd ~/Desktop/data && rm -rf c%c% && mkdir c%c% && mv a.txt c%c% && mv a.dat c%c% && mv a.csv c%c%"
ssh attacker "cd ~/Desktop/data && rm -rf c%c% && mkdir c%c% && mv a.txt c%c% && mv a.dat c%c% && mv a.csv c%c%"
ssh loadbalancer "sudo systemctl stop haproxy-autoscaler"
ssh loadbalancer "rm -rf ~/Desktop/data/c%c% && mkdir -p ~/Desktop/data/c%c% && sudo mv /var/log/haproxy-metrics.csv ~/Desktop/data/c%c%/"
ssh server1 "rm -rf ~/Desktop/data/c%c% && mkdir -p ~/Desktop/data/c%c% && mv ~/Desktop/scripts/request_log.csv ~/Desktop/data/c%c%/"
ssh server2 "rm -rf ~/Desktop/data/c%c% && mkdir -p ~/Desktop/data/c%c% && mv ~/Desktop/MatMul/request_log.csv ~/Desktop/data/c%c%/"
ssh server3 "rm -rf ~/Desktop/data/c%c% && mkdir -p ~/Desktop/data/c%c% && mv ~/Desktop/MatMul/request_log.csv ~/Desktop/data/c%c%/"