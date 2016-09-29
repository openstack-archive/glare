# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2014 SoftLayer Technologies, Inc.
# Copyright 2015 Mirantis, Inc
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

"""
System-level utilities and helper functions.
"""

import errno

try:
    from eventlet import sleep
except ImportError:
    from time import sleep
from eventlet.green import socket

import functools
import hashlib
import os
import re
import uuid

from OpenSSL import crypto
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from oslo_utils import timeutils
from oslo_versionedobjects import fields
import six
from webob import exc

from glare.common import exception
from glare.i18n import _, _LE, _LW
from glare.objects.meta import fields as glare_fields

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

GLARE_TEST_SOCKET_FD_STR = 'GLARE_TEST_SOCKET_FD'


def chunkreadable(iter, chunk_size=65536):
    """
    Wrap a readable iterator with a reader yielding chunks of
    a preferred size, otherwise leave iterator unchanged.

    :param iter: an iter which may also be readable
    :param chunk_size: maximum size of chunk
    """
    return chunkiter(iter, chunk_size) if hasattr(iter, 'read') else iter


def chunkiter(fp, chunk_size=65536):
    """
    Return an iterator to a file-like obj which yields fixed size chunks

    :param fp: a file-like object
    :param chunk_size: maximum size of chunk
    """
    while True:
        chunk = fp.read(chunk_size)
        if chunk:
            yield chunk
        else:
            break


def cooperative_iter(iter):
    """
    Return an iterator which schedules after each
    iteration. This can prevent eventlet thread starvation.

    :param iter: an iterator to wrap
    """
    try:
        for chunk in iter:
            sleep(0)
            yield chunk
    except Exception as err:
        with excutils.save_and_reraise_exception():
            msg = _LE("Error: cooperative_iter exception %s") % err
            LOG.error(msg)


def cooperative_read(fd):
    """
    Wrap a file descriptor's read with a partial function which schedules
    after each read. This can prevent eventlet thread starvation.

    :param fd: a file descriptor to wrap
    """
    def readfn(*args):
        result = fd.read(*args)
        sleep(0)
        return result
    return readfn


MAX_COOP_READER_BUFFER_SIZE = 134217728  # 128M seems like a sane buffer limit


class CooperativeReader(object):
    """
    An eventlet thread friendly class for reading in blob data.

    When accessing data either through the iterator or the read method
    we perform a sleep to allow a co-operative yield. When there is more than
    one blob being uploaded/downloaded this prevents eventlet thread
    starvation, ie allows all threads to be scheduled periodically rather than
    having the same thread be continuously active.
    """
    def __init__(self, fd):
        """
        :param fd: Underlying blob file object
        """
        self.fd = fd
        self.iterator = None
        # NOTE(markwash): if the underlying supports read(), overwrite the
        # default iterator-based implementation with cooperative_read which
        # is more straightforward
        if hasattr(fd, 'read'):
            self.read = cooperative_read(fd)
        else:
            self.iterator = None
            self.buffer = b''
            self.position = 0

    def read(self, length=None):
        """Return the requested amount of bytes, fetching the next chunk of
        the underlying iterator when needed.

        This is replaced with cooperative_read in __init__ if the underlying
        fd already supports read().
        """
        if length is None:
            if len(self.buffer) - self.position > 0:
                # if no length specified but some data exists in buffer,
                # return that data and clear the buffer
                result = self.buffer[self.position:]
                self.buffer = b''
                self.position = 0
                return str(result)
            else:
                # otherwise read the next chunk from the underlying iterator
                # and return it as a whole. Reset the buffer, as subsequent
                # calls may specify the length
                try:
                    if self.iterator is None:
                        self.iterator = self.__iter__()
                    return next(self.iterator)
                except StopIteration:
                    return ''
                finally:
                    self.buffer = b''
                    self.position = 0
        else:
            result = bytearray()
            while len(result) < length:
                if self.position < len(self.buffer):
                    to_read = length - len(result)
                    chunk = self.buffer[self.position:self.position + to_read]
                    result.extend(chunk)

                    # This check is here to prevent potential OOM issues if
                    # this code is called with unreasonably high values of read
                    # size. Currently it is only called from the HTTP clients
                    # of Glare backend stores, which use httplib for data
                    # streaming, which has readsize hardcoded to 8K, so this
                    # check should never fire. Regardless it still worths to
                    # make the check, as the code may be reused somewhere else.
                    if len(result) >= MAX_COOP_READER_BUFFER_SIZE:
                        raise exception.LimitExceeded()
                    self.position += len(chunk)
                else:
                    try:
                        if self.iterator is None:
                            self.iterator = self.__iter__()
                        self.buffer = next(self.iterator)
                        self.position = 0
                    except StopIteration:
                        self.buffer = b''
                        self.position = 0
                        return bytes(result)
            return bytes(result)

    def __iter__(self):
        return cooperative_iter(self.fd.__iter__())


class LimitingReader(object):
    """
    Reader designed to fail when reading blob data past the configured
    allowable amount.
    """
    def __init__(self, data, limit):
        """
        :param data: Underlying blob data object
        :param limit: maximum number of bytes the reader should allow
        """
        self.data = data
        self.limit = limit
        self.bytes_read = 0
        self.sha1 = hashlib.sha1()
        self.sha256 = hashlib.sha256()

    def __iter__(self):
        for chunk in self.data:
            self.bytes_read += len(chunk)
            if self.bytes_read > self.limit:
                raise exception.RequestEntityTooLarge()
            else:
                yield chunk

    def read(self, i):
        result = self.data.read(i)
        len_result = len(result)
        self.bytes_read += len_result
        if len_result:
            self.sha1.update(result)
            self.sha256.update(result)
        if self.bytes_read > self.limit:
            raise exception.RequestEntityTooLarge()
        return result


def safe_mkdirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def mutating(func):
    """Decorator to enforce read-only logic"""
    @functools.wraps(func)
    def wrapped(self, req, *args, **kwargs):
        if req.context.read_only:
            msg = "Read-only access"
            LOG.debug(msg)
            raise exc.HTTPForbidden(msg, request=req,
                                    content_type="text/plain")
        return func(self, req, *args, **kwargs)
    return wrapped


def setup_remote_pydev_debug(host, port):
    error_msg = _LE('Error setting up the debug environment. Verify that the'
                    ' option pydev_worker_debug_host is pointing to a valid '
                    'hostname or IP on which a pydev server is listening on'
                    ' the port indicated by pydev_worker_debug_port.')

    try:
        try:
            from pydev import pydevd
        except ImportError:
            import pydevd

        pydevd.settrace(host,
                        port=port,
                        stdoutToServer=True,
                        stderrToServer=True)
        return True
    except Exception:
        with excutils.save_and_reraise_exception():
            LOG.exception(error_msg)


def validate_key_cert(key_file, cert_file):
    try:
        error_key_name = "private key"
        error_filename = key_file
        with open(key_file, 'r') as keyfile:
            key_str = keyfile.read()
        key = crypto.load_privatekey(crypto.FILETYPE_PEM, key_str)

        error_key_name = "certificate"
        error_filename = cert_file
        with open(cert_file, 'r') as certfile:
            cert_str = certfile.read()
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_str)
    except IOError as ioe:
        raise RuntimeError(_("There is a problem with your %(error_key_name)s "
                             "%(error_filename)s.  Please verify it."
                             "  Error: %(ioe)s") %
                           {'error_key_name': error_key_name,
                            'error_filename': error_filename,
                            'ioe': ioe})
    except crypto.Error as ce:
        raise RuntimeError(_("There is a problem with your %(error_key_name)s "
                             "%(error_filename)s.  Please verify it. OpenSSL"
                             " error: %(ce)s") %
                           {'error_key_name': error_key_name,
                            'error_filename': error_filename,
                            'ce': ce})

    try:
        data = str(uuid.uuid4())
        # On Python 3, explicitly encode to UTF-8 to call crypto.sign() which
        # requires bytes. Otherwise, it raises a deprecation warning (and
        # will raise an error later).
        data = encodeutils.to_utf8(data)
        digest = CONF.digest_algorithm
        if digest == 'sha1':
            LOG.warn(
                _LW('The FIPS (FEDERAL INFORMATION PROCESSING STANDARDS)'
                    ' state that the SHA-1 is not suitable for'
                    ' general-purpose digital signature applications (as'
                    ' specified in FIPS 186-3) that require 112 bits of'
                    ' security. The default value is sha1 in Kilo for a'
                    ' smooth upgrade process, and it will be updated'
                    ' with sha256 in next release(L).'))
        out = crypto.sign(key, data, digest)
        crypto.verify(cert, out, data, digest)
    except crypto.Error as ce:
        raise RuntimeError(_("There is a problem with your key pair.  "
                             "Please verify that cert %(cert_file)s and "
                             "key %(key_file)s belong together.  OpenSSL "
                             "error %(ce)s") % {'cert_file': cert_file,
                                                'key_file': key_file,
                                                'ce': ce})


def get_test_suite_socket():
    global GLARE_TEST_SOCKET_FD_STR
    if GLARE_TEST_SOCKET_FD_STR in os.environ:
        fd = int(os.environ[GLARE_TEST_SOCKET_FD_STR])
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        if six.PY2:
            sock = socket.SocketType(_sock=sock)
        sock.listen(CONF.backlog)
        del os.environ[GLARE_TEST_SOCKET_FD_STR]
        os.close(fd)
        return sock
    return None


try:
    REGEX_4BYTE_UNICODE = re.compile(u'[\U00010000-\U0010ffff]')
except re.error:
    # UCS-2 build case
    REGEX_4BYTE_UNICODE = re.compile(u'[\uD800-\uDBFF][\uDC00-\uDFFF]')


def no_4byte_params(f):
    """
    Checks that no 4 byte unicode characters are allowed
    in dicts' keys/values and string's parameters
    """
    def wrapper(*args, **kwargs):

        def _is_match(some_str):
            return (isinstance(some_str, six.text_type) and
                    REGEX_4BYTE_UNICODE.findall(some_str) != [])

        def _check_dict(data_dict):
            # a dict of dicts has to be checked recursively
            for key, value in six.iteritems(data_dict):
                if isinstance(value, dict):
                    _check_dict(value)
                else:
                    if _is_match(key):
                        msg = _("Property names can't contain 4 byte unicode.")
                        raise exception.Invalid(msg)
                    if _is_match(value):
                        msg = (_("%s can't contain 4 byte unicode characters.")
                               % key.title())
                        raise exception.Invalid(msg)

        for data_dict in [arg for arg in args if isinstance(arg, dict)]:
            _check_dict(data_dict)
        # now check args for str values
        for arg in args:
            if _is_match(arg):
                msg = _("Param values can't contain 4 byte unicode.")
                raise exception.Invalid(msg)
        # check kwargs as well, as params are passed as kwargs via
        # registry calls
        _check_dict(kwargs)
        return f(*args, **kwargs)
    return wrapper


def stash_conf_values():
    """
    Make a copy of some of the current global CONF's settings.
    Allows determining if any of these values have changed
    when the config is reloaded.
    """
    conf = {
        'bind_host': CONF.bind_host,
        'bind_port': CONF.bind_port,
        'tcp_keepidle': CONF.cert_file,
        'backlog': CONF.backlog,
        'key_file': CONF.key_file,
        'cert_file': CONF.cert_file
    }

    return conf


def split_filter_op(expression):
    """Split operator from threshold in an expression.
    Designed for use on a comparative-filtering query field.
    When no operator is found, default to an equality comparison.

    :param expression: the expression to parse

    :returns: a tuple (operator, threshold) parsed from expression
    """
    left, sep, right = expression.partition(':')
    if sep:
        # If the expression is a date of the format ISO 8601 like
        # CCYY-MM-DDThh:mm:ss+hh:mm and has no operator, it should
        # not be partitioned, and a default operator of eq should be
        # assumed.
        try:
            timeutils.parse_isotime(expression)
            op = 'eq'
            threshold = expression
        except ValueError:
            op = left
            threshold = right
    else:
        op = 'eq'  # default operator
        threshold = left

    # NOTE stevelle decoding escaped values may be needed later
    return op, threshold


def validate_quotes(value):
    """Validate filter values

    Validation opening/closing quotes in the expression.
    """
    open_quotes = True
    for i in range(len(value)):
        if value[i] == '"':
            if i and value[i - 1] == '\\':
                continue
            if open_quotes:
                if i and value[i - 1] != ',':
                    msg = _("Invalid filter value %s. There is no comma "
                            "before opening quotation mark.") % value
                    raise exception.InvalidParameterValue(message=msg)
            else:
                if i + 1 != len(value) and value[i + 1] != ",":
                    msg = _("Invalid filter value %s. There is no comma "
                            "after closing quotation mark.") % value
                    raise exception.InvalidParameterValue(message=msg)
            open_quotes = not open_quotes
    if not open_quotes:
        msg = _("Invalid filter value %s. The quote is not closed.") % value
        raise exception.InvalidParameterValue(message=msg)


def split_filter_value_for_quotes(value):
    """Split filter values

    Split values by commas and quotes for 'in' operator, according api-wg.
    """
    validate_quotes(value)
    tmp = re.compile(r'''
        "(                 # if found a double-quote
           [^\"\\]*        # take characters either non-quotes or backslashes
           (?:\\.          # take backslashes and character after it
            [^\"\\]*)*     # take characters either non-quotes or backslashes
         )                 # before double-quote
        ",?                # a double-quote with comma maybe
        | ([^,]+),?        # if not found double-quote take any non-comma
                           # characters with comma maybe
        | ,                # if we have only comma take empty string
        ''', re.VERBOSE)
    return [val[0] or val[1] for val in re.findall(tmp, value)]


def evaluate_filter_op(value, operator, threshold):
    """Evaluate a comparison operator.
    Designed for use on a comparative-filtering query field.

    :param value: evaluated against the operator, as left side of expression
    :param operator: any supported filter operation
    :param threshold: to compare value against, as right side of expression

    :raises: InvalidFilterOperatorValue if an unknown operator is provided

    :returns: boolean result of applied comparison

    """
    if operator == 'gt':
        return value > threshold
    elif operator == 'gte':
        return value >= threshold
    elif operator == 'lt':
        return value < threshold
    elif operator == 'lte':
        return value <= threshold
    elif operator == 'neq':
        return value != threshold
    elif operator == 'eq':
        return value == threshold

    msg = _("Unable to filter on a unknown operator.")
    raise exception.InvalidFilterOperatorValue(msg)


class error_handler(object):
    def __init__(self, error_map, default_exception=None):
        self.error_map = error_map
        self.default_exception = default_exception

    def __call__(self, f):
        """Decorator that catches exception that came from func or method
            :param f: targer func
            :param error_map: dict of exception that can be raised
            in func and exceptions that must be raised for these exceptions.
            For example, if sqlalchemy NotFound might be raised and we need
            re-raise it as glare NotFound exception then error_map must
            contain {"catch": SQLAlchemyNotFound,
                     "raise": exceptions.NotFound}
            :param default_exception: default exception that must be raised if
            exception that cannot be found in error map was raised
            :return: func
        """

        def new_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                for map_record in self.error_map:
                    if isinstance(e, map_record['catch']):
                        raise map_record['raise'](str(e))
                else:
                    if self.default_exception:
                        raise self.default_exception(str(e))
                    else:
                        raise
        return new_function


def get_schema_type(attr):
    if isinstance(attr, fields.IntegerField):
        return 'integer'
    elif isinstance(attr, fields.FloatField):
        return 'number'
    elif isinstance(attr, fields.BooleanField):
        return 'boolean'
    elif isinstance(attr, glare_fields.List):
        return 'array'
    elif isinstance(attr, (glare_fields.Dict, glare_fields.BlobField)):
        return 'object'
    return 'string'


def get_glare_type(attr):
    if isinstance(attr, fields.IntegerField):
        return 'Integer'
    elif isinstance(attr, fields.FloatField):
        return 'Float'
    elif isinstance(attr, fields.FlexibleBooleanField):
        return 'Boolean'
    elif isinstance(attr, fields.DateTimeField):
        return 'DateTime'
    elif isinstance(attr, glare_fields.BlobField):
        return 'Blob'
    elif isinstance(attr, glare_fields.Link):
        return 'Link'
    elif isinstance(attr, glare_fields.List):
        return _get_element_type(attr.element_type) + 'List'
    elif isinstance(attr, glare_fields.Dict):
        return _get_element_type(attr.element_type) + 'Dict'
    return 'String'


def _get_element_type(element_type):
    if element_type is fields.FlexibleBooleanField:
        return 'Boolean'
    elif element_type is fields.Integer:
        return 'Integer'
    elif element_type is fields.Float:
        return 'Float'
    elif element_type is glare_fields.BlobFieldType:
        return 'Blob'
    elif element_type is glare_fields.LinkFieldType:
        return 'Link'
    return 'String'


class DictDiffer(object):
    """
    Calculate the difference between two dictionaries as:
    (1) items added
    (2) items removed
    (3) keys same in both but changed values
    (4) keys same in both and unchanged values
    """

    def __init__(self, current_dict, past_dict):
        self.current_dict, self.past_dict = current_dict, past_dict
        self.current_keys, self.past_keys = [
            set(d.keys()) for d in (current_dict, past_dict)]
        self.intersect = self.current_keys.intersection(
            self.past_keys)

    def added(self):
        return self.current_keys - self.intersect

    def removed(self):
        return self.past_keys - self.intersect

    def changed(self):
        return set(o for o in self.intersect
                   if self.past_dict[o] != self.current_dict[o])

    def unchanged(self):
        return set(o for o in self.intersect
                   if self.past_dict[o] == self.current_dict[o])

    def __str__(self):
        msg = "\nResult output:\n"
        msg += "\tAdded keys: %s\n" % ', '.join(self.added())
        msg += "\tRemoved keys: %s\n" % ', '.join(self.removed())
        msg += "\tChanged keys: %s\n" % ', '.join(self.changed())
        msg += "\tUnchanged keys: %s\n" % ', '.join(self.unchanged())
        return msg
