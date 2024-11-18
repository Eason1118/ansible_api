#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import time

from common.utils import logger


class ZkThread(threading.Thread):
    def __init__(self, register):
        threading.Thread.__init__(self)
        self.register = register

    def run(self):
        time.sleep(0.1)
        if self.register.zk_node is None:
            logger.warn("must call register method first")
            return
        check_result = self.register.zk.exists(self.register.zk_node)
        if check_result is None:
            # redo the register
            logger.warn("redo register {}".format(self.register.zk_node))
            self.register.register()
        else:
            logger.debug("{} path remain exists".format(self.register.zk_node))
