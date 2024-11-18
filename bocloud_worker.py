#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import sqlite3
import sys
import threading
import time
import traceback
import importlib
import flask_restful
from flask import Flask
from flask import abort
from flask import request

from ansible_handler.ansible_handler import AnsibleHandler
from common.base_handler import BaseHandler
from common.daemon import Daemon
from common.db.bocloud_worker_db import ASYNC_TASK_STATUS_COMPLETE
from common.db.bocloud_worker_db import ASYNC_TASK_STATUS_RUNNING
from common.db.bocloud_worker_db import BocloudWorkerDB
from common.rabbitmq_handler import intergrate_send_result_to_rabbitmq
from common.status import get_status
from common.threads_monitor import ThreadsMonitor
from common.threads_monitor import threads_pool
from common.threads_monitor import threads_pool_lock
from common.utils import BOCLOUD_WORKER_CONFIG, ZOOKEEPER_CONFIG
from common.utils import BOCLOUD_WORKER_SQLITEDB
from common.utils import check_white_blacklist
from common.utils import global_dict_update
from common.utils import logger
from common.utils import get_file_content
from zookeeper_handler.node_register import NodeRegister
from celery.exceptions import TimeoutError


importlib.reload(sys)

os.environ["PYTHONOPTIMIZE"] = "1"
app = Flask(__name__)
api = flask_restful.Api(app)
ansible_result = {}
tps = 0
start_time = None
reset_thread = None
is_daemon = False
# celery

# app.config.from_object(settings)
# celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
# celery.conf.update(app.config)


@app.before_request
def init_request():
    """Check whether or not the ip have permession to access the BOCLOUD_worker service.
    """
    ip = request.remote_addr
    logger.debug("The IP of requestment is %s", ip)
    # write every request to sqlite3 DB
    if BOCLOUD_WORKER_CONFIG["is_not_db"] is False:
        db = None
        try:
            logger.debug("insert a request to sqlite DB")
            db = BocloudWorkerDB(BOCLOUD_WORKER_SQLITEDB)
            request_id = db.insert_task_requests(request)
            logger.debug("The request id in task_requests table is %d" % request_id)
            request.task_request_id = request_id
        except sqlite3.Error as e:
            logger.error("Failed to insert request with sqlite3 exception: %s" % str(e))
            abort(500)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to insert request with unknown exception: %s" % str(e))
            abort(500)
        finally:
            if db:
                db.close()

    result = check_white_blacklist(ip)
    if not result:
        logger.error("The IP %s don't have the permission to access the BOCLOUD_Worker service", ip)
        abort(403)


@app.after_request
def after_request(response):
    # the response of request update to sqlite3 DB
    status_code = response.status_code
    if not hasattr(request, 'task_request_id') and BOCLOUD_WORKER_CONFIG["is_not_db"] is False:
        abort(400)
        return
    queue = None
    db = None
    if request.json and "queue" in request.json:
        queue = request.json["queue"]
    tr_values = dict()
    aos_values = dict()
    tr_values["respond_code"] = status_code
    if status_code == 200:
        message = json.loads(response.data)
        # async job can't success running
        if "success" in message and message["success"] is False:
            tr_values["error_message"] = message.get("message", "")
            aos_values["status"] = ASYNC_TASK_STATUS_COMPLETE
    else:
        tr_values["error_message"] = response.data

    if BOCLOUD_WORKER_CONFIG["is_not_db"] is False:
        request_id = request.task_request_id
        try:
            logger.debug("update DB before send response to server")
            db = BocloudWorkerDB(BOCLOUD_WORKER_SQLITEDB)
            db.update_task_requests(request_id, tr_values)
            if queue and len(aos_values) > 0:
                db.update_async_task_status(queue, aos_values)
        except sqlite3.Error as e:
            logger.error("Failed to update request result with sqlite3 exception: %s" % str(e))
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to update request result with unknown exception: %s" % str(e))
        finally:
            if db:
                db.close()

    return response


@app.route('/job/submit', methods=['POST'])
def handle_job():
    """this interface is used to execute jobs
    the rest instant response means the jobs is sent to worker successfully
    after worker finish all jobs, send job results to rabbitmq.
    :return:
    {
        "message": "The 123 job is sent to worker successful.",
        "success": true
    }
    """
    logger.info("The /job/submit request is %s" % json.dumps(request.json, ensure_ascii=False))
    global tps
    tps += 1
    if not BaseHandler.check_request(request.json,
                                     "/job/submit"):
        abort(400)

    result = True
    queue = request.json.get("queue", "job_submit" + str(time.time()))
    message = "The job is sent to worker successful. Queue is %s" % queue

    context = None
    try:
        from tasks import async_job_exec

        job_result = async_job_exec.apply_async(args=(json.dumps(request.json), queue, ))
        if request.json.get("response", "") == "sync":
            timeout = request.json.get('timeout', BOCLOUD_WORKER_CONFIG["job_timeout"])
            context = job_result.get(timeout=timeout)
    except TimeoutError:
        logger.error(traceback.format_exc())
        message = "The task is timeout!"
        logger.error(message)
        result = False

    except Exception as ex:
        logger.error(traceback.format_exc())
        message = "The job is failure to operate. Queue is %s. %s" % (queue, ex)
        logger.error(message)
        result = False

    if not context:
        context = {"success": result,
                   "message": message}

    return json.dumps(context)


@app.route('/job/recovery', methods=['POST'])
def recovery_job():
    """
    this interface is used to recovery offline worker jobs
    :return:
    {
        "message": "ok",
        "success": true
    }
    """
    logger.info("The /job/recovery request is %s" % json.dumps(request.json))
    result = {"success": True,
              "message": "ok"}
    try:
        recovery_exec(request.json['host'], request.json['port'])
    except Exception as e:
        logger.error(traceback.format_exc())
        result = {"success": False,
                  "message": str(e)}

    return json.dumps(result)


@app.route('/server/status/scan', methods=['POST'])
def machines_scan():
    """this interface is used to get server status
    :return:
    {
        "message": "Finished the job 123",
        "data": [
            {
                "status": "online",
                "host": "192.168.2.73"
            }
        ],
        "success": true
    }
    """
    logger.debug("The /server/status/scan request is %s" % json.dumps(request.json))

    if not BaseHandler.check_request(request.json,
                                     "/server/status/scan"):
        abort(400)

    result = True
    queue = request.json["queue"]
    message = "The %s job is sent to worker successful." % queue
    context = None
    try:
        request_json = request.json
        request_json["module"] = {}
        request_json["module"]["name"] = "ping"
        context = job_exec(request.json, queue)
    except Exception as ex:
        logger.error(traceback.format_exc())
        logger.error("Failure operate job %s. %s" % (queue, ex))
        result = False
        message = "The %s job is failure to operate. %s" % (queue, ex)

    if not context:
        context = {"success": result,
                   "message": message}
    return json.dumps(context)


@app.route('/status', methods=['GET'])
def status():
    """this interface is used to get worker status
    :return: json string
    {
        "data": {
            "cpu.worker.usage": 0.0,
            "ip": "192.168.200.128",
            "memory.system.free": 74,
            "memory.system.total": 977,
            "memory.worker.memory": 796,
            "memory.worker.resident": 34,
            "memory.worker.stacksize": 0,
            "memory.worker.threads": 7,
            "os.arch": "x86_64",
            "os.cpu.number": 1,
            "os.name": "Linux-3.10.0-327.el7.x86_64-x86_64-with-centos-7.2.1511-Core",
            "tps": 0,
            "uptime.worker": 53
        },
        "message": "ok",
        "success": true
    }
    """
    return json.dumps(dict(data=get_status(tps, start_time),
                           success=True,
                           message='ok'))


@app.route('/logview', methods=['POST'])
def log_view():
    """this interface is used to get remote log file content
    file content return immediately
    :return: json object
    {
        "message": "55555\n666666\n7777777\n88888888\n",  # 文件内容或是错误信息
        "filesize": 65,      # 读取了返回的文件内容后，文件最后的位置
        "success": true      # API是否执行成功
    }
    """
    logger.debug("The /logview request is %s" % json.dumps(request.json))

    if not BaseHandler.check_request(request.json,
                                     "/logview"):
        abort(400)

    position = request.json.get("position", 0)
    presize = request.json.get("presize", 1024)
    # presize is 0, use default presize 1024
    if presize == 0:
        presize = 1024

    # if just want to see itself log of worker, don't suggest to call ansible.
    # this maybe cause worker can't normal worker and crash.
    if BOCLOUD_WORKER_CONFIG['host'] == request.json['target']:
        file_name = request.json['filepath']
        if file_name == "":
            file_name = BOCLOUD_WORKER_CONFIG['log']['file']

        success, content, curr_position = get_file_content(file_name, position, presize)
        context = {"success": success,
                   "message": content,
                   "filesize": curr_position}
        return json.dumps(context)

    new_request = dict()
    target = dict(host=request.json['target'])
    for optional in ['user', 'pasd', 'port']:
        if optional in request.json:
            target[optional] = request.json[optional]
    new_request['targets'] = [target]
    new_request['module'] = dict()
    new_request['module']['name'] = 'bocloud_logview'
    new_request['module']['args'] = dict()
    if BOCLOUD_WORKER_CONFIG['host'] == request.json['target'] and request.json['filepath'] == "":
        new_request['module']['args']['log_file'] = BOCLOUD_WORKER_CONFIG['log']['file']
    else:
        new_request['module']['args']['log_file'] = request.json['filepath']
    new_request['module']['args']['position'] = position

    new_request['module']['args']['presize'] = presize
    thread_name = "logview" + str(time.time())
    result_signal = threading.Event()
    ansible_thread = AnsibleHandler(new_request, thread_name, result_signal=result_signal)
    logger.info("the new logview request is %s" % new_request)
    ansible_thread.start()
    global_dict_update(threads_pool,
                       ansible_thread,
                       lock=threads_pool_lock,
                       value=time.time(),
                       operate="append")

    if result_signal.wait(timeout=60):
        if ansible_thread.ansible_result["success"]:
            msg = ansible_thread.ansible_result["data"][0]["message"]["bocloud_worker_msg"].get("content", "")
            position = ansible_thread.ansible_result["data"][0]["message"]["bocloud_worker_msg"]["curr_position"]
        else:
            msg = ansible_thread.ansible_result["data"][0]["message"]["msg"]
            position = 0

        context = {"success": ansible_thread.ansible_result["success"],
                   "message": msg,
                   "filesize": position}
    else:
        context = {"success": False,
                   "message": "Get special log content failure. please check requestment"}
    return json.dumps(context)


def job_exec(request_json, queue, recovery=False, worker_db=BOCLOUD_WORKER_SQLITEDB):
    """exec jobs using ansible
    :param request_json:
    :param queue:
    :param recovery:
    :param worker_db:db路径
    :return:
    """
    node_id = request_json.get("taskNodeId")
    size = len(request_json["targets"])
    response_type = request_json.get("response", "async_result")
    is_async = False if response_type == "sync" else True
    db = None
    # update task status and mark the job is running
    # just insert async task to DB
    if recovery is False and is_async is True and BOCLOUD_WORKER_CONFIG["is_not_db"] is False:
        try:
            db = BocloudWorkerDB(worker_db)
            values = dict()
            values["status"] = ASYNC_TASK_STATUS_RUNNING
            values["total_count"] = size
            db.update_async_task_status(queue, values)
        except sqlite3.Error as e:
            logger.error("Failed to update task status with sqlite3 exception: %s" % str(e))
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to update task status with unknown exception: %s" % str(e))
        finally:
            if db:
                db.close()

    result_signal = None
    # if response type is sync, we generate an event to wait result.
    if is_async is False:
        result_signal = threading.Event()
    ansible_thread = AnsibleHandler(request_json, queue, node_id,
                                    result_signal=result_signal, db=worker_db)
    ansible_thread.start()
    global_dict_update(threads_pool,
                       ansible_thread,
                       lock=threads_pool_lock,
                       value=time.time(),
                       operate="append")

    content = None
    # wait the result if this is sync request
    if result_signal:
        if result_signal.wait(timeout=60):
            return ansible_thread.ansible_result
        else:
            content = {"success": False,
                       "taskNodeId": node_id,
                       "message": "The task is timeout."}
    else:
        time_out = request_json.get('timeout', BOCLOUD_WORKER_CONFIG["job_timeout"])
        ansible_thread.join(time_out)
    return content


def recovery_exec(worker_host, worker_port):
    kv = dict()
    kv["nfs_path"] = BOCLOUD_WORKER_CONFIG["nfs_path"]
    kv["host"] = worker_host
    kv["port"] = worker_port
    # worker_db = "{0[nfs_path]}/{0[host]}_{0[port]}/bocloud_worker.db".format(kv)
    worker_db = "{0[nfs_path]}/bocloud_worker_db/bocloud_worker.db".format(kv)
    logger.debug("Start to recovery uncompleted tasks. database is %s" % worker_db)
    recovery_request = dict()
    db = None
    try:
        # get all not running async tasks
        db = BocloudWorkerDB(worker_db)
        tasks = db.get_new_tasks()
        for task in tasks:
            logger.debug("recocery new task: %s" % task)
            request_data = task["request_data"]
            recovery_request = json.loads(request_data, encoding='utf-8')
            sync = recovery_request.get("response", None)
            if sync:
                # mark the task as finished
                db.set_task_as_finished(recovery_request["queue"])
                continue
            job_exec(recovery_request, recovery_request["queue"], worker_db=worker_db)

        # get all uncompleted async tasks
        db = BocloudWorkerDB(worker_db)
        tasks = db.get_uncompleted_tasks()
        for task in tasks:
            request_data = json.loads(task["request_data"], encoding='utf-8')
            request_id = task['request_id']
            # filter out completed targets from the request
            db.refresh_request_data_for_uncompleted_target(request_id,
                                                           request_data)
            logger.debug("recovery uncompleted task %d, request data is %s" % (request_id, request_data))
            if len(request_data["targets"]) == 0:
                # don't have tasks need ansible to do, just intergrate the exist result
                # and send the result to rabbitmq
                queue = request_data["queue"]
                _, results = db.get_task_all_result(queue)
                intergrate_send_result_to_rabbitmq(queue, results)
                db.set_task_as_finished(queue)
            else:
                sync = recovery_request.get("response", None)
                if sync:
                    # mark the task as finished
                    db.set_task_as_finished(recovery_request["queue"])
                    continue
                job_exec(request_data, request_data["queue"], recovery=True, worker_db=worker_db)
    except sqlite3.Error as e:
        logger.error("Failed to operate sqlite3 exception: %s" % str(e))
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("Failed to operate sqlite3 with unknown exception: %s" % str(e))
    finally:
        if db:
            db.close()


def _reset_tps():
    """
    this is a timer to reset tps
    :return:
    """
    global tps
    tps = 0
    global reset_thread
    reset_thread = threading.Timer(1.0, _reset_tps)
    reset_thread.start()


def main():
    global start_time
    start_time = time.time()
    host = BOCLOUD_WORKER_CONFIG["host"]
    port = BOCLOUD_WORKER_CONFIG["port"]

    zk = NodeRegister(ZOOKEEPER_CONFIG["zk_server"])
    zk_thread = threading.Thread(target=zk.service)
    zk_thread.setName("zk-thread")
    zk_thread.setDaemon(True)
    zk_thread.start()

    # reset tps per second
    global reset_thread
    reset_thread = threading.Timer(1.0, _reset_tps)
    reset_thread.daemon = True
    reset_thread.start()

    logger.info("Threads monitor thread is start.")
    monitor = ThreadsMonitor()
    monitor.setDaemon(True)
    monitor.start()

    flask_debug = BOCLOUD_WORKER_CONFIG["flask_debug"]
    try:
        # create bocloud_worker database if it is not existing
        # worker_db = "{0[nfs_path]}/{0[host]}_{0[port]}/bocloud_worker.db".format(BOCLOUD_WORKER_CONFIG)
        worker_db = BOCLOUD_WORKER_SQLITEDB
        logger.debug("The worker db is local at %s" % worker_db)
        init_sql = BOCLOUD_WORKER_CONFIG["init_sql"]
        logger.debug("The initialization database is %s" % init_sql)
        BocloudWorkerDB.create_bocloud_worker_schema(worker_db, init_sql)
        app.run(debug=flask_debug, host=host, port=port, use_reloader=False)
    except KeyboardInterrupt as err:
        logger.info("Close BOCLOUD worker with Ctrl+c")
    except Exception as err:
        logger.error("Close BOCLOUD worker, Unknown error: %s" % str(err))
    except SystemExit as err:
        logger.error("BOCLOUD_worker exit, code status is: %s" % str(err))
    finally:
        logger.info("BOCLOUD worker exit. cleanup used source")
        monitor.terminate()
        logger.info("try to terminate all threads. Please wait ...")
        monitor.join(10)
        zk.close()
        sys.exit(0)


# create a new daemon class to override work function in base class.
class BOCLOUDWorker(Daemon):
    def work(self):
        main()


if __name__ == "__main__":
    if is_daemon:
        # run bocloud_worder as daemon process
        bocloud_worker = BOCLOUDWorker()
        bocloud_worker.run()
    else:
        main()
