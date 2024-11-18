pkill -9 celery
pkill -9 python3
[ ! -d ./log ] && mkdir log

nohup python3 bocloud_worker.py >>log/log.log 2>&1  &
nohup /root/worker/worker/software/python3.6/bin/celery  -A tasks.celery worker -Q celery >>./log/celery.log 2>&1 &

#/root/worker/worker/software/python3.6/bin/celery flower --address=0.0.0.0 --port=5555 --broker=redis://:@0.0.0.0:6379/0 &
