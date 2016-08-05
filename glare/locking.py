# Copyright 2016 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import inspect
import six

from oslo_log import log as logging

from glare.i18n import _LI

LOG = logging.getLogger(__name__)


class LockApiBase(object):
    """Lock Api Base class that responsible for acquiring/releasing locks
    """

    def create_lock(self, context, lock_key):
        """Acquire lock for current user

        :param context user context
        :param lock_key: unique lock identifier that defines lock scope
        :return lock internal identifier
        """
        raise NotImplementedError()

    def delete_lock(self, context, lock_id):
        """Delete acquired user lock

        :param context: user context
        :param lock_id: lock internal identifier
        :return:
        """
        raise NotImplementedError()


class Lock(object):
    """Object that stores lock context for users. This class is internal
    and used only for Lock Engine. So users shouldn't use this class directly
    """

    def __init__(self, context, lock_id, lock_key, release_method):
        """Initialize lock context"""
        self.context = context
        self.lock_id = lock_id
        self.lock_key = lock_key
        self.release = release_method

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # TODO(kairat) catch all exceptions here
        self.release(self)


class LockEngine(object):
    """Glare lock engine.
    Defines how artifact updates must be synchronized with each other. When
    some user obtains lock  for the same piece of data then other user cannot
    request that lock and get Conflict error.
    This little engine also allows to encapsulate lock logic in one place so
    we can potentially add tooz functionality in future to Glare. Right now
    there are troubles with locks in Galera (especially in mysql) and zookeeper
    requires additional work from IT engineers. So we need support production
    ready DB locks in our implementation.
    """

    MAX_LOCK_LENGTH = 255

    def __init__(self, lock_api):
        """Initialize lock engine with some lock api

        :param lock_api: api that allows to create/delete locks. It must be
        db_api but it might be replaced with DLM in near future.
        """
        self.lock_api = lock_api

    def acquire(self, context, lock_key):
        """Acquire lock to update whole artifact

        Acquire lock to update artifact. If there is some other
        lock for the same artifact then raise Conflict Error.

        :param context: user context
        :param lock_key: lock key
        :return: lock definition
        """
        if lock_key is not None and len(lock_key) < self.MAX_LOCK_LENGTH:
            lock_id = self.lock_api.create_lock(context, lock_key)
            LOG.info(_LI("Lock %(lock_id)s acquired for lock_key "
                         "%(lock_key)s"),
                     {'lock_id': lock_id, 'lock_key': lock_key})
        else:
            lock_id = None
            LOG.info(_LI("No lock for lock_key %s"), lock_key)

        return Lock(context, lock_id, lock_key, self.release)

    def release(self, lock):
        if lock.lock_id is not None:
            self.lock_api.delete_lock(lock.context, lock.lock_id)
            LOG.info(_LI("Lock %(lock_id)s released for lock_key %(key)s"),
                     {'lock_id': lock.lock_id, 'key': lock.lock_key})

    def locked(self, lock_name_parameters):
        """Synchronization decorator.
        :param list lock_name_parameters: List of parameters that will be used
        as part of lock name
        :returns: function that locks artifact by specified parameters
        """
        def wrap(f):
            @six.wraps(f)
            def wrapped(*a, **k):
                call_args = inspect.getcallargs(f, *a, **k)
                lock_key = ''
                for param in lock_name_parameters:
                    lock_key += str(call_args[param]) + ':'
                context = call_args.get('context')
                with self.acquire(context, lock_key):
                    res = f(*a, **k)
                return res
            return wrapped
        return wrap
