@echo off

set name=%1

ssh benign "cd ~/Desktop/data && mkdir spoofing && mv a.txt spoofing/ && mv a.dat spoofing/ && mv a.csv spoofing/"
ssh attacker "cd ~/Desktop/'spoofing data' && source venv/bin/activate && python graph_results.py"
ssh attacker "cd ~/Desktop/data && mkdir spoofing && mv ~/Desktop/'spoofing data'/ab_results/ spoofing/ && mv ~/Desktop/'spoofing data'/ab_graphs/ spoofing/"
ssh loadbalancer "sudo systemctl stop haproxy-autoscaler"
ssh loadbalancer "mkdir -p ~/Desktop/data/spoofing && sudo mv /var/log/haproxy-metrics.csv ~/Desktop/data/spoofing/"
ssh server1 "mkdir -p ~/Desktop/data/spoofing && mv ~/Desktop/scripts/request_log.csv ~/Desktop/data/spoofing/"
ssh server2 "mkdir -p ~/Desktop/data/spoofing && mv ~/Desktop/MatMul/request_log.csv ~/Desktop/data/spoofing/"
ssh server3 "mkdir -p ~/Desktop/data/spoofing && mv ~/Desktop/MatMul/request_log.csv ~/Desktop/data/spoofing/"

ssh benign "cd ~/Desktop/data && rm -rf %name% && mkdir %name% && mv c*/ %name%/ && mv spoofing/ %name%/"
ssh attacker "cd ~/Desktop/data && rm -rf %name% && mkdir %name% && mv c*/ %name%/ && mv spoofing/ %name%/"
ssh loadbalancer "cd ~/Desktop/data && rm -rf %name% && mkdir %name% && mv c*/ %name%/ && mv spoofing/ %name%/"
ssh server1 "cd ~/Desktop/data && rm -rf %name% && mkdir %name% && mv c*/ %name%/ && mv spoofing/ %name%/"
ssh server2 "cd ~/Desktop/data && rm -rf %name% && mkdir %name% && mv c*/ %name%/ && mv spoofing/ %name%/"
ssh server3 "cd ~/Desktop/data && rm -rf %name% && mkdir %name% && mv c*/ %name%/ && mv spoofing/ %name%/"