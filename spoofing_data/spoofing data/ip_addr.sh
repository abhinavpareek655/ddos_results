#!/bin/bash

for i in {10..109}; do 
	ip addr add 192.168.100.$i/24 dev enp0s8
done
