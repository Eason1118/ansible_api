#!/usr/bin/env python
import random
from kombu import serialization
from kombu import Exchange, Queue
from common.utils import CELERY_CONFIG

serialization.registry._decoders.pop("application/x-python-serialize")

celery_queue = CELERY_CONFIG['celery_queue']
SECRET_KEY = CELERY_CONFIG['secret_key']
BROKER_URL = CELERY_CONFIG['broker_url']
CELERY_RESULT_BACKEND = CELERY_CONFIG['celery_result_backend']
CELERY_TASK_RESULT_EXPIRES = CELERY_CONFIG['celery_task_result_expires']
CELERYD_PREFETCH_MULTIPLIER = CELERY_CONFIG['celery_prefetch_multiplier']
CELERYD_CONCURRENCY = CELERY_CONFIG['celery_concurrency']
CELERY_TASK_SERIALIZER = CELERY_CONFIG['celery_task_serializer']
#CELERYD_MAX_TASKS_PER_CHILD = CELERY_CONFIG['celeryd_max_tasks_per_child']
#CELERY_TIMEZONE = CELERY_CONFIG['celery_timezone']
#CELERY_ACCEPT_CONTENT = ['json']
#CELERY_RESULT_SERIALIZER = 'json'
CELERY_QUEUES = (
    Queue(celery_queue, Exchange(celery_queue), routing_key=celery_queue),
)

#CELERY_IGNORE_RESULT = True
#CELERY_SEND_EVENTS = False
#CELERY_EVENT_QUEUE_EXPIRES = CELERY_CONFIG['celery_event_queue_expires']
