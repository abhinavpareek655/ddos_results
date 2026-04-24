ab -q -k -r -s 9999 -n 100 -c 1 -g a.dat -e a.csv -H "Accept-Encoding: gzip, default" http://192.168.100.1:5000/matmul | tee -a a.txt
