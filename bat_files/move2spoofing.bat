@echo off

ssh benign "cd ~/Desktop/data && mkdir spoofing && mv a.txt spoofing/ && mv a.dat spoofing/ && mv a.csv spoofing/"
ssh attacker "cd ~/Desktop/'spoofing data' && source venv/bin/activate && python graph_results.py"
ssh attacker "cd ~/Desktop/data && mkdir spoofing && mv ~/Desktop/'spoofing data'/ab_results/ spoofing/ && mv ~/Desktop/'spoofing data'/ab_graphs/ spoofing/"
ssh loadbalancer "sudo systemctl stop haproxy-autoscaler"
ssh loadbalancer "mkdir -p ~/Desktop/data/spoofing && sudo mv /var/log/haproxy-metrics.csv ~/Desktop/data/spoofing/"