to turn off autoscaling:

systemctl stop haproxy-autoscaler
systemctl disable haproxy-autoscaler


to turn it back on: 

systemctl enable --now haproxy-autoscaler


to see the servers usage on haproxy: 

journalctl -fu haproxy-autoscaler


Run these commands on each backend server:

**CPU cores (for context)**
```bash
nproc
lscpu | grep "Model name"
```

**Disk max speed — run a quick benchmark**
```bash
# Test write speed
sudo dd if=/dev/zero of=/tmp/test bs=1M count=1024 oflag=direct 2>&1 | grep copied

# Test read speed
sudo dd if=/tmp/test of=/dev/null bs=1M iflag=direct 2>&1 | grep copied

# Clean up
rm /tmp/test
```

**Network interface max speed**
```bash
# Shows speed in Mbps — divide by 8 to get MB/s
cat /sys/class/net/$(ip route | grep default | awk '{print $5}')/speed
```

**Max connections your server can handle**
```bash
# System max
cat /proc/sys/net/core/somaxconn

# Current open files limit (each connection = 1 file descriptor)
ulimit -n
```

---

## Example output interpretation

```
dd write:     450 MB/s  → DISK_MAX_MB_S = 450
dd read:      480 MB/s  → use 480 but 450 is safe
NIC speed:    1000 Mbps → NET_MAX_MB_S  = 125   (1000/8)
maxconn:      1000      → CONN_MAX      = 1000  (matches haproxy.cfg)
```

Run this on all three servers — if they differ, use the **lowest** value across all of them so the normalization is consistent and no single server gets unfairly penalized.

One thing to note — your ulimit -n is only 1024 which means each server can only hold 1024 open file descriptors total (connections + open files). You should raise this otherwise the server hits its own limit before HAProxy's maxconn 1000 does:
bash# Raise it permanently
```
echo "* soft nofile 65535" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65535" | sudo tee -a /etc/security/limits.conf
```
Then log out and back in and verify with ulimit -n — should show 65535.


check for the time taken for one request without any attack: 

```
time curl http://192.168.100.1:5000/matmul
```