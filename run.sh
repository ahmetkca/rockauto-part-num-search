#!/bin/sh
#echo "Starting 1000 to 1100"
#python3.9 AsyncConcurrency.py 1000 1100
for i in $(seq 1000 50 3400)
do
  from=$i
  to=$(($i + 50))
  echo "Starting ... $from to $to"
  python3.9 AsyncConcurrency.py $from $to
  echo "Waiting for 30 seconds"
  sleep 30
done

