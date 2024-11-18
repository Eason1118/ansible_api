#!/usr/bin/env python
# -*- coding: utf-8 -*-
import subprocess
import os
import platform
import time
from multiprocessing import cpu_count

from common.utils import get_ip

_mem_info = '/proc/meminfo'
_proc_status = '/proc/%d/status' % os.getpid()

_scale = {'kB': 1024.0, 'mB': 1024.0 * 1024.0,
          'KB': 1024.0, 'MB': 1024.0 * 1024.0}


def _vmb(vm_key, runtime=True):
    """Private.
    """
    global _proc_status, _scale, _mem_info

    _file = _proc_status if runtime else _mem_info
    # get pseudo file  /proc/<pid>/status
    try:
        t = open(_file)
        v = t.read()
        t.close()
    except:
        return 0.0  # non-Linux?
    # get VmKey line e.g. 'VmRSS:  9999  kB\n ...'
    i = v.index(vm_key)
    v = v[i:].split(None, 3)  # whitespace
    if len(v) < 3:
        return 0.0  # invalid format?
    # convert Vm value to bytes
    return float(v[1]) * _scale[v[2]]


def memory(since=0.0):
    """Return memory usage in bytes.
    """
    return _vmb('VmSize:') - since


def resident(since=0.0):
    """Return resident memory usage in bytes.
    """
    return _vmb('VmRSS:') - since


def stacksize(since=0.0):
    """Return stack size in bytes.
    """
    return _vmb('VmStk:') - since


def threads():
    global _proc_status, _scale
    # get pseudo file  /proc/<pid>/status
    try:
        t = open(_proc_status)
        v = t.read()
        t.close()
    except:
        return 0.0  # non-Linux?
    # get Threads line
    i = v.index('Threads:')
    v = v[i:].split(None, 3)  # whitespace
    if len(v) < 3:
        return 0.0  # invalid format?
    return v[1]


def system_total(since=0.0):
    """Return stack size in bytes.
    """
    return _vmb('MemTotal:', False) - since


def system_free(since=0.0):
    """Return stack size in bytes.
    """
    return _vmb('MemFree:', False) - since


def worker_cpu_usage():
    return subprocess.run(
        "top -b -n 1 -p %d| awk -v pid=%d '{if ($1 == pid) print $9}'" % (os.getpid(), os.getpid()))


def get_status(tps, start_time):
    status = dict()
    status['os.name'] = platform.platform()
    status['os.arch'] = platform.machine()
    status['os.cpu.number'] = cpu_count()
    status['tps'] = tps
    status['ip'] = get_ip()
    status['uptime.worker'] = float('%.3f' % (time.time() - start_time))
    status['memory.system.total'] = int(system_total() / (1024 * 1024))
    status['memory.system.free'] = int(system_free() / (1024 * 1024))
    status['memory.worker.stacksize'] = int(stacksize() / (1024 * 1024))
    status['memory.worker.memory'] = int(memory() / (1024 * 1024))
    status['memory.worker.resident'] = int(resident() / (1024 * 1024))
    status['memory.worker.threads'] = int(threads())
    status['cpu.worker.usage'] = float(worker_cpu_usage())
    return status