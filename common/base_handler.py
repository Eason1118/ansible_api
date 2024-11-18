#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ctypes
import inspect
import sqlite3
import threading
import traceback

from common.db.bocloud_worker_db import BocloudWorkerDB
from common.utils import logger, BOCLOUD_WORKER_SQLITEDB


class BaseHandler(threading.Thread):
    '''
    This is a base class for operator handler.
    It will run as alone thread
    '''
    api_request = {'/job/submit': {"necessary": (("queue", "response", "taskNodeId"), {"targets": {"necessary": ("host",)}}),
                                   "opt_sole": {"module": ("name", "args"),
                                                "script": ("type",
                                                           "content")}, },
                   '/server/status/scan': {"necessary": ("queue", "targets"), },
                   '/logview': {"necessary": ("filepath", "target"), }, }

    def __init__(self, name=None, timeout=None):
        super(BaseHandler, self).__init__(name=name)
        self.timeout = timeout

    @classmethod
    def check_request(cls, request, route):
        '''Check request whether or not is valid.

           Args:
             - request: request reveive from restful api
             - route: restful api route
           Return:
             If the request is valid, return True. Otherwise, False
        '''
        if request is None:
            logger.error("Restfule api miss request.")
            return False

        if cls.check_queue_exist(request.get("queue", None), BOCLOUD_WORKER_SQLITEDB):
            logger.error("queue already exists.")
            return False

        def check_request_items(rule, request_items, request_parent):
            # check whether or not request miss the necessary parameters
            if "necessary" in rule:
                for arg in rule["necessary"]:
                    # if the rule item of necessary is a dictory, we need to check recursively
                    if isinstance(arg, dict):
                        for rule_name, child_rule in arg.items():
                            item = rule_name
                            if request_parent:
                                item = "%s -> %s" % (request_parent, rule_name)

                            if rule_name not in request_items:
                                logger.error("%s is necessary for restful api %s" %
                                             (item, route))
                                return False

                            if not isinstance(request_items[rule_name], list):
                                logger.debug("continue to check %s, rule is %s",
                                             request_items[rule_name], child_rule)
                                return check_request_items(child_rule, request_items[rule_name], item)
                            # if child requirements are list, check per item in the list
                            for req_list in request_items[rule_name]:
                                logger.debug("continue to check %s, rule is %s", req_list, child_rule)
                                if not check_request_items(child_rule, req_list, item):
                                    logger.error("%s don't accord with rule %s, %s" % (req_list, child_rule, item))
                                    return False
                    # if the rule item is tuple, this mean that the least one of item is necessary
                    elif isinstance(arg, tuple):
                        flag = False
                        for sub in arg:
                            if sub in request_items:
                                flag = True
                                break

                        if flag is False:
                            logger.error("At least one of %s is necessary for restful api %s" %
                                         (arg, route))
                            return False
                    elif arg not in request_items:
                        item = arg
                        if request_parent:
                            item = "%s -> %s" % (request_parent, arg)
                        logger.error("%s is necessary for restful api %s" %
                                     (item, route))
                        return False

            # check whether or not value is in scope
            if "value_scope" in rule:
                for req, val in rule["value_scope"].items():
                    if req in request_items and request_items[req] not in val:
                        item = request_items[req]
                        if request_parent:
                            item = "%s -> %s" % (request_parent, request_items[req])
                        logger.error("%s value scope is not valid for %s" % (item, req))
                        return False

            # check whether or not just exist a option for one more options
            if "opt_sole" in rule:
                exist_req = []
                for req, val in rule["opt_sole"].items():
                    if req in request_items:
                        if len(exist_req) is not 0:
                            logger.error("%s and %s can't exist at the same time" %
                                         (req, exist_req))
                            return False

                        exist_req.append(req)
                        # check whether or not its value is valid.
                        for its_req in val:
                            if its_req not in request_items[req]:
                                logger.error("%s is necessary for %s option" %
                                             (its_req, req))
                                return False

                if len(exist_req) is 0:
                    logger.error("must give a option for %s" %
                                 [k for k, v in rule["opt_sole"].items()])
                    return False

            return True

        request_rule = cls.api_request.get(route, None)
        if not request_rule:
            logger.debug("The request %s don't need to check whether or not is valid", route)
            return True

        return check_request_items(request_rule, request, None)

    @classmethod
    def check_queue_exist(cls, queue, worker_db):
        try:
            db = BocloudWorkerDB(worker_db)
            return db.check_queue_exist(queue)
        except sqlite3.Error as e:
            logger.error("Failed to check if queue exist with sqlite3 exception: %s" % str(e))
            return False
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to check if queue exist with unknown exception: %s" % str(e))
            return False
        finally:
            db.close()

    def check_targets_category(self, targets):
        '''whether or not targets list includes both windows and linux machines
           We only support all linux targets and all windows targets
           Args:
             - targets: machines list, pre machine value is dictory type
           Return:
             - True: include both mahcine type
             - False: don't include
        '''
        try:
            category_list = [host.get('category', 'Linux') for host in targets]
            win_category = ['Windows' for host in targets]
            # one windows, must all windows
            if 'Windows' in category_list and category_list != win_category:
                logger.info("Don't support to operate windows and linux machines in a requirement")
                return False
        except:
            logger.error("check machines type exception")
            return False
        return True

    def _get_thread_id(self):
        '''
        determines this (self's) thread id
        '''
        if not self.isAlive():
            raise threading.ThreadError("the thread is not active")
        # do we have it cached?
        if hasattr(self, "_thread_id"):
            return self._thread_id
        # no, look for it in the _active dict
        for tid, tobj in threading._active.items():
            if tobj is self:
                self._thread_id = tid
                return tid
        raise AssertionError("could not determine the thread's id")

    def _raise_exc(self, exctype):
        '''
        raises the exception, thread cleanup if needed
        '''
        tid = ctypes.c_long(self._get_thread_id())
        logger.info("The thread id that try to terminate is %s." % tid)
        if not inspect.isclass(exctype):
            exctype = type(exctype)
        func_ptr = ctypes.py_object(exctype)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, func_ptr)
        if res == 0:
            raise ValueError("invalid thread id")
        elif res != 1:
            # if it returns a number greater than one, you're in trouble,
            # and you should call it again with exc=NULL to revert the effect
            ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
            raise SystemError("PyThreadState_SetAsyncExc failed")

    def terminate(self):
        '''
        raises SystemExit in the context of the given thread, which should
        cause the thread to exit silently (unless caught)
        '''
        logger.debug("Stop threading...")
        self._raise_exc(SystemExit)

    def run(self):
        pass
