#!/usr/bin/env python
# -*- coding: utf-8 -*-
import traceback
import time
import os
import json

from common.utils import logger
from celery import Celery
from bocloud_worker import job_exec
from celery.exceptions import SoftTimeLimitExceeded
os.environ["PYTHONOPTIMIZE"] = "1"

celery = Celery()
celery.config_from_object("celery_config")


@celery.task(bind=True, default_retry_delay=300, max_retries=1, soft_time_limit=3600)
def async_job_exec(self, request_json, queue):
    """异步方法"""
    result = None
    start = time.time()
    logger.info("==============【开始】异步执行任务=============== ")
    try:
        result = job_exec(json.loads(request_json), queue)
    except SoftTimeLimitExceeded as e:
        logger.error(traceback.format_exc())
        logger.error("==queue:{}=异步执行任务超时：{}".format(queue, e))
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("==queue:{}=异步执行任务失败：{}".format(queue, e))
    logger.info("==============【结束】异步执行任务，耗时：{}============= ".format((time.time() - start)))

    return result