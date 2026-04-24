#!/bin/bash

c=$1

cd ~/Desktop/data

/usr/bin/ab -k -r -s 9999 -n 2000 -c $c \
-g a.dat -e a.csv \
-H "Accept-Encoding: gzip" \
http://192.168.100.1:5000/matmul | tee -a a.txt
