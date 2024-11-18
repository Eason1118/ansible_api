#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import time

from common.utils import logger


class BaseSqliteDB(object):
    """
    This is a Sqlite3 DB handler class

    The class will handler some base db operation.
    """
    def __init__(self, db, timeout=30, retry_time=3):
        self.db = db
        self.retry_time = retry_time
        self.conn = None
        self.cu = None
        try:
            self.conn = sqlite3.connect(database=self.db,
                                        isolation_level='DEFERRED',
                                        timeout=timeout)
            self.conn.text_factory = str
            self.conn.row_factory = sqlite3.Row
            self.cu = self.conn.cursor()
        except Exception as e:
            logger.error("Sqlite3 db %s init failed: %s" % (self.db, str(e)))
            raise

    @classmethod
    def create_schema(cls, db, init_sql):
        # Create database schema
        try:
            conn = sqlite3.connect(database=db)
            conn.text_factory = str
            conn.row_factory = sqlite3.Row
            cu = conn.cursor()
            with open(init_sql, 'r') as f:
                cu.executescript(f.read())
            logger.debug("Database created successfully.")
        except Exception as ex:
            logger.error('Failed to create database, exception: %s' % str(ex))
            raise
        finally:
            cu.close()
            conn.close()

    def select(self, table_name, column_name=['*'], and_values={}, or_values={},
               association={}, row_num=None):
        select_column = " , ".join(column_name)
        where_clause, args = self._generate_where_clause(and_values, or_values, association)
        # Unicode conversion str
        args = [str(info) for info in args]
        stmt = 'SELECT %s FROM %s %s' % (str(select_column), table_name, where_clause)

        try:
            self.cu.execute(stmt, args)
            if row_num is None:
                data = self.cu.fetchall()
                rows = [dict(row) for row in data]
            elif row_num == 1:
                rows = self.cu.fetchone()
            else:
                data = self.cu.fetchmany(row_num)
                rows = [dict(row) for row in data]
        except Exception as e:
            logger.error('SqliteDB select operation failed: %s' % e.args[0])
            logger.error(stmt.replace('?', '%s') % tuple(args))
            raise

        logger.debug("SqliteDB select succeeded, select result: %s" % str(rows))
        return rows

    def cursor_fetchmany(self, row_num=1000):
        try:
            data = self.cu.fetchmany(row_num)
            rows = [dict(row) for row in data]
        except Exception as e:
            logger.error('SQL operation failed: %s' % e.args[0])
            raise

        logger.debug("fetchmany result: %s" % str(rows))
        return rows

    def insert(self, table_name, key_and_value, commit=True):
        keys = key_and_value.keys()
        args = key_and_value.values()
        # Unicode conversion str
        args = [str(info) for info in args]
        stmt = "INSERT OR IGNORE INTO %s (%s) VALUES (%s)" % \
               (table_name, ",".join(keys), ",".join('?' * len(args)))

        count = 0
        last_autonum = -1
        while True:
            try:
                self.cu.execute(stmt, args)
                if commit:
                    self.commit()
                    last_autonum = self.cu.lastrowid
                break
            except sqlite3.OperationalError as e:
                if e.args[0].find('database is locked') != -1:
                    if count == self.retry_time:
                        logger.error("SqliteDB insert operation failed: " + e.args[0])
                        logger.error(stmt.replace('?', '%s') % tuple(args))
                        raise e
                    else:
                        logger.debug('Database is locked, try again')
                        count = count + 1
                        time.sleep(1)
                        continue
                raise e
            except Exception as e:
                logger.error('SqliteDB insert operation failed: %s' % e.args[0])
                logger.error(stmt.replace('?', '%s') % tuple(args))
                raise e

        logger.debug("SqliteDB insert succeeded.%s" % stmt.replace('?', '%s') % tuple(args))
        if commit:
            logger.debug("Commit to database.")

        return last_autonum

    def update(self, table_name, key_and_value,
               where_and={}, where_or={}, commit=True):
        update_items = key_and_value.items()

        update_clause = ", ".join([x[0] + "=?" for x in update_items])
        where_clause, args = self._generate_where_clause(where_and, where_or)

        stmt = "UPDATE %s SET %s %s" % (table_name, update_clause, where_clause)
        args = [x[1] for x in update_items] + args
        args = [str(info) for info in args]

        count = 0
        while True:
            try:
                self.cu.execute(stmt, args)
                if commit:
                    self.commit()
                break
            except sqlite3.OperationalError as e:
                if e.args[0].find('database is locked') != -1:
                    if count == self.retry_time:
                        logger.error("SqliteDB update operation failed: " + e.args[0])
                        logger.error(stmt.replace('?', '%s') % tuple(args))
                        raise e
                    else:
                        logger.debug('Database is locked, try again')
                        count = count + 1
                        time.sleep(1)
                        continue
                raise e
            except Exception as e:
                logger.error('SqliteDB update operation failed: %s' % e.args[0])
                logger.error(stmt.replace('?', '%s') % tuple(args))
                raise e

        logger.debug("SqliteDB update succeeded. %s " % stmt.replace('?', '%s') % tuple(args))
        if commit:
            logger.debug("Commit to database.")

    def delete(self, table_name, and_values={}, or_values={}, commit=True):
        where_clause, args = self._generate_where_clause(and_values, or_values)
        stmt = "DELETE FROM %s %s" % (table_name, where_clause)
        count = 0

        while True:
            try:
                self.cu.execute(stmt, args)
                if commit:
                    self.commit()
                break
            except sqlite3.OperationalError as e:
                if e.args[0].find('database is locked') != -1:
                    if count == self.retry_time:
                        logger.error("SqliteDB delete operation failed: " + e.args[0])
                        logger.error(stmt.replace('?', '%s') % tuple(args))
                        raise e
                    else:
                        logger.debug('Database is locked, try again')
                        count = count + 1
                        time.sleep(1)
                        continue
                raise e
            except Exception as e:
                logger.error('SqliteDB delete operation failed: %s' % e.args[0])
                logger.error(stmt.replace('?','%s') % tuple(args))
                raise e

        logger.debug("SqliteDB delete succeeded. %s" % stmt.replace('?', '%s') % tuple(args))
        if commit:
            logger.debug("Commit to database.")

    def commit(self):
        count = 0
        while True:
            try:
                self.conn.commit()
                break
            except sqlite3.OperationalError as e:
                if e.args[0].find('database is locked') != -1:
                    if count == self.retry_time:
                        logger.error("SQL operation failed: " + e.args[0])
                        raise e
                    else:
                        logger.debug('Database is locked, try again')
                        count = count + 1
                        time.sleep(1)
                        continue
                raise e
            except Exception as e:
                logger.error("SqliteDB commit failed")
                raise e

        logger.debug("SqliteDB commit succeeded")

    def rollback(self):
        count = 0
        while True:
            try:
                self.conn.rollback()
                break
            except sqlite3.OperationalError as e:
                if e.args[0].find('database is locked') != -1:
                    if count == self.retry_time:
                        logger.error('SQL operation failed: %s' % e.args[0])
                        raise e
                    else:
                        logger.debug('Database is locked, try again')
                        count = count + 1
                        time.sleep(1)
                        continue
                raise e
            except Exception as e:
                logger.error("SqliteDB rollback failed")
                raise e

        logger.debug("SqliteDB rollback succeeded")

    def close(self):
        try:
            if self.cu:
                self.cu.close()
            if self.conn:
                self.conn.close()
        except Exception as e:
            raise e

    def _generate_where_clause(self, and_values={}, or_values={}, association={}):
        and_list = [k[0] + "=?" for k in and_values.items()]
        and_args = [k[1] for k in and_values.items()]

        or_list = []
        or_args = []
        for k in or_values.items():
            or_list = or_list + [k[0] + '=?'] * len(k[1])
        for k in or_values.items():
            or_args = or_args + k[1]

        for k in association:
            and_list += [k + "=" + association[k]]

        if len(and_list) == 0 and len(or_list) == 0:
            return "", []
        elif len(and_list) == 0:
            where_clause = " WHERE " + \
                           " OR ".join(or_list)
            args = or_args
        elif len(or_list) == 0:
            where_clause = " WHERE " + \
                           " AND ".join(and_list)
            args = and_args
        else:
            where_clause = " WHERE " + \
                           " AND ".join(and_list) + \
                           " AND " + \
                           " OR ".join(or_list)
            args = and_args + or_args

        return where_clause, args
