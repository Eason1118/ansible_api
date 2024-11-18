#!/usr/bin/env python
# -*- coding: utf-8 -*-


class bocloud_logger(object):
    def __init__(self, logger):
        self.logger = logger

    def _transfer_unicode(self, target):
        return str(target).replace('u\'', '\'').decode("unicode-escape")

    def info(self, msg):
        self.logger.info(self._transfer_unicode(msg))

    def debug(self, msg):
        self.logger.debug(self._transfer_unicode(msg))

    def warning(self, msg):
        self.logger.warning(self._transfer_unicode(msg))

    def error(self, msg):
        self.logger.error(self._transfer_unicode(msg))

    def exception(self, msg):
        self.logger.exception(self._transfer_unicode(msg))
