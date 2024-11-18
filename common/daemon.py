"""
Provide a class to help to write python daemon
"""

import atexit
import os
import signal
import sys

from common.utils import logger


class Daemon(object):
    """
    A generic daemon class.
    """
    STDINOUTERR = '/dev/null'
    PIDLOCK_HOME = '/var/run'

    def __init__(self):
        self.name = os.path.basename(sys.argv[0]).split('.')[0]
        self.pidfile = os.path.join(self.PIDLOCK_HOME, '%s.pid' % self.name)
        self.shall_quit = False

    def daemonize(self):
        """
        daemonize the process
        """
        # Break away from parent process
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("failed to fork with %d, %s\n" %
                             (e.errno, e.strerror))
            sys.exit(e.errno)

        os.chdir("/")
        # Break away from terminal
        os.setsid()
        # Reset the file access permission
        os.umask(0)

        # 2 fork needed. Forbid process reopen terminal again.
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("failed to fork with %d, %s\n" %
                             (e.errno, e.strerror))
            sys.exit(e.errno)

        stdin = open(self.STDINOUTERR, 'r')
        os.dup2(stdin.fileno(), sys.stdin.fileno())

        sys.stdout.flush()
        stdout = open(self.STDINOUTERR, 'a+')
        os.dup2(stdout.fileno(), sys.stdout.fileno())

        sys.stderr.flush()
        stderr = open(self.STDINOUTERR, 'a+', 0)
        os.dup2(stderr.fileno(), sys.stderr.fileno())

        atexit.register(self.cleanup)
        pid = str(os.getpid())
        f = open(self.pidfile, 'w+')
        f.write("%s\n" % pid)
        f.close()

    def cleanup(self):
        """
        Clean up when exit. This function is registed with atexit,
        so it will get executed in most of the time.
        """
        os.remove(self.pidfile)

    def sig_handler(self, sig, frame):
        """
        Signal handler. Shall always override this one to
        handle in your own way
        """
        if sig == signal.SIGTERM:
            self.shall_quit = True
            sys.exit(0)

    def register_signal_handler(self):
        """
        Register signal handler for common signals
        """
        signal.signal(signal.SIGTERM, self.sig_handler)
        signal.signal(signal.SIGHUP, self.sig_handler)
        signal.signal(signal.SIGINT, self.sig_handler)

    def work(self):
        """
        Actual work of the class.
        This shall be always overrided
        """
        logger.info('do nothing. life is good')
        return 0

    def run(self):
        """
        This is to provide a sequence which is good for most of daemons.
        you can certainly override it with own customization.
        """
        self.daemonize()
        self.register_signal_handler()
        try:
            return_code = self.work()
        except Exception as e:
            logger.exception(e)
            # bad number but what to use?
            return_code = 1
        sys.exit(return_code)
