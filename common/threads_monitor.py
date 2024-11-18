#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import time

from common.utils import global_dict_update
from common.utils import logger

threads_pool = {}
threads_pool_lock = threading.Lock()


class ThreadsMonitor(threading.Thread):
    '''
    The class monitor all bocloud_worker threads. It regularly check
    threads status. If a thread don't response long time that expire
    the configured timeout, it will force terminate the thread.
    '''

    def __init__(self):
        super(ThreadsMonitor, self).__init__()
        self.stop = False

    def run(self):
        while not self.stop:
            time.sleep(5)
            self.force_stop_thread()

        # stop some threads that are appended after stop main process.
        if self.stop:
            logger.info("Terminate the monitor thread. \
                         Final force cleanup the unfinished threads")
            self.force_stop_thread()

    def force_stop_thread(self):
        global threads_pool
        for thread in threads_pool.keys():
            if not thread.isAlive():
                global_dict_update(threads_pool,
                                   thread,
                                   lock=threads_pool_lock,
                                   operate="pop")
            else:
                duration = time.time() - threads_pool[thread]
                if self.stop or duration >= thread.timeout:
                    if self.stop:
                        message = "BOCLOUD_worker service stop. Job %s is stopped." % \
                                  thread.getName()
                    else:
                        message = "Job %s execute timeout." % thread.getName()
                    logger.info(message)
                    thread.terminate()
                    global_dict_update(threads_pool,
                                       thread,
                                       lock=threads_pool_lock,
                                       operate="pop")

    def terminate(self):
        self.stop = True
