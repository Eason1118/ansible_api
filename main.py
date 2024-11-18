#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

from common.db.bocloud_worker_db import BocloudWorkerDB
from common.threads_monitor import ThreadsMonitor
from common.utils import BOCLOUD_WORKER_CONFIG, ZOOKEEPER_CONFIG
from common.utils import BOCLOUD_WORKER_SQLITEDB
from common.utils import logger
from zookeeper_handler.node_register import NodeRegister
# from bocloud_worker import _reset_tps

os.environ["PYTHONOPTIMIZE"] = "1"

ansible_result = {}
tps = 0
start_time = None
reset_thread = None
is_daemon = False


def main():

    logger.info("Threads monitor thread is start.")
    monitor = ThreadsMonitor()
    monitor.setDaemon(True)
    monitor.start()

    zk = NodeRegister(ZOOKEEPER_CONFIG["zk_server"])
    try:
        worker_db = BOCLOUD_WORKER_SQLITEDB
        logger.debug("The worker db is local at %s" % worker_db)
        init_sql = BOCLOUD_WORKER_CONFIG["init_sql"]
        logger.debug("The initialization database is %s" % init_sql)
        BocloudWorkerDB.create_bocloud_worker_schema(worker_db, init_sql)

        zk.service()
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


if __name__ == '__main__':
    main()