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
try:
    from eventlet import sleep
except ImportError:
    from time import sleep
from eventlet.green import socket

import hashlib
import os
import re

from OpenSSL import crypto
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from oslo_utils import timeutils
from oslo_utils import uuidutils
from oslo_versionedobjects import fields
import six

from glare.common import exception
from glare.i18n import _
from glare.objects.meta import fields as glare_fields

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

GLARE_TEST_SOCKET_FD_STR = 'GLARE_TEST_SOCKET_FD'


def cooperative_iter(iter):
    """Return an iterator which schedules after each
    iteration. This can prevent eventlet thread starvation.

    :param iter: an iterator to wrap
    """
    try:
        for chunk in iter:
            sleep(0)
            yield chunk
    except Exception as err:
        with excutils.save_and_reraise_exception():
            LOG.error("Error: cooperative_iter exception %s", err)


def cooperative_read(fd):
    """Wrap a file descriptor's read with a partial function which schedules
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
    """An eventlet thread friendly class for reading in blob data.

    When accessing data either through the iterator or the read method
    we perform a sleep to allow a co-operative yield. When there is more than
    one blob being uploaded/downloaded this prevents eventlet thread
    starvation, ie allows all threads to be scheduled periodically rather than
    having the same thread be continuously active.
    """
    def __init__(self, fd):
        """:param fd: Underlying blob file object
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
                        raise exception.RequestEntityTooLarge()
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
    """Reader designed to fail when reading blob data past the configured
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
        self.md5 = hashlib.md5()
        self.sha1 = hashlib.sha1()
        self.sha256 = hashlib.sha256()

    def __iter__(self):
        for chunk in self.data:
            self.bytes_read += len(chunk)
            if self.bytes_read > self.limit:
                raise exception.RequestEntityTooLarge()
            else:
                yield chunk

    def read(self, length=None):
        res = self.data.read() if length is None else self.data.read(length)
        len_result = len(res)
        self.bytes_read += len_result
        if len_result:
            self.md5.update(res)
            self.sha1.update(res)
            self.sha256.update(res)
        if self.bytes_read > self.limit:
            message = _("The server is refusing to process a request because"
                        " the request entity is larger than the server is"
                        " willing or able to process - %s bytes.") % self.limit
            raise exception.RequestEntityTooLarge(message=message)
        return res


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
        data = uuidutils.generate_uuid()
        # On Python 3, explicitly encode to UTF-8 to call crypto.sign() which
        # requires bytes. Otherwise, it raises a deprecation warning (and
        # will raise an error later).
        data = encodeutils.to_utf8(data)
        digest = CONF.digest_algorithm
        if digest == 'sha1':
            LOG.warning(
                'The FIPS (FEDERAL INFORMATION PROCESSING STANDARDS)'
                ' state that the SHA-1 is not suitable for'
                ' general-purpose digital signature applications (as'
                ' specified in FIPS 186-3) that require 112 bits of'
                ' security. The default value is sha1 in Kilo for a'
                ' smooth upgrade process, and it will be updated'
                ' with sha256 in next release(L).')
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
    """Checks that no 4 byte unicode characters are allowed
    in dicts' keys/values and string's parameters.
    """
    def wrapper(*args, **kwargs):

        def _is_match(some_str):
            return (isinstance(some_str, six.text_type) and
                    REGEX_4BYTE_UNICODE.findall(some_str) != [])

        def _check_dict(data_dict):
            # a dict of dicts has to be checked recursively
            for key, value in data_dict.items():
                if isinstance(value, dict):
                    _check_dict(value)
                else:
                    if _is_match(key):
                        msg = _("Property names can't contain 4 byte unicode.")
                        raise exception.BadRequest(msg)
                    if _is_match(value):
                        msg = (_("%s can't contain 4 byte unicode characters.")
                               % key.title())
                        raise exception.BadRequest(msg)

        for data_dict in [arg for arg in args if isinstance(arg, dict)]:
            _check_dict(data_dict)
        # now check args for str values
        for arg in args:
            if _is_match(arg):
                msg = _("Param values can't contain 4 byte unicode.")
                raise exception.BadRequest(msg)
        # check kwargs as well, as params are passed as kwargs via
        # registry calls
        _check_dict(kwargs)
        return f(*args, **kwargs)
    return wrapper


def stash_conf_values():
    """Make a copy of some of the current global CONF's settings.
    Allows determining if any of these values have changed
    when the config is reloaded.
    """
    conf = {
        'bind_host': CONF.bind_host,
        'bind_port': CONF.bind_port,
        'tcp_keepidle': CONF.cert_file,
        'backlog': CONF.backlog,
        'key_file': CONF.key_file,
        'cert_file': CONF.cert_file,
        'enabled_artifact_types': CONF.enabled_artifact_types,
        'custom_artifact_types_modules': CONF.custom_artifact_types_modules
    }

    return conf


def split_filter_op(expression):
    """Split operator from threshold in an expression.
    Designed for use on a comparative-filtering query field.
    When no operator is found, default to an equality comparison.

    :param expression: the expression to parse
    :return: a tuple (operator, threshold) parsed from expression
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


class error_handler(object):
    def __init__(self, error_map, default_exception=None):
        """Init method of the class.

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
        self.error_map = error_map
        self.default_exception = default_exception

    def __call__(self, f):
        """Decorator that catches exception that came from func or method.

        :param f: target func
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
    if isinstance(attr, fields.IntegerField) or attr is fields.Integer:
        return 'integer'
    elif isinstance(attr, fields.FloatField) or attr is fields.Float:
        return 'number'
    elif isinstance(attr, fields.FlexibleBooleanField) \
            or attr is fields.FlexibleBoolean:
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


class BlobIterator(object):
    """Reads data from a blob, one chunk at a time.
    """

    def __init__(self, data, chunk_size=65536):
        self.chunk_size = chunk_size
        self.data = data

    def __iter__(self):
        bytes_left = len(self.data)
        i = 0
        while bytes_left > 0:
            data = self.data[i * self.chunk_size:(i + 1) * self.chunk_size]
            bytes_left -= len(data)
            yield data
        raise StopIteration()


def validate_status_transition(af, from_status, to_status):
    if from_status == 'deleted':
        msg = _("Cannot change status if artifact is deleted.")
        raise exception.Forbidden(msg)
    if to_status == 'active':
        if from_status == 'drafted':
            for name, type_obj in af.fields.items():
                if type_obj.required_on_activate and getattr(af, name) is None:
                    msg = _("'%s' field value must be set before "
                            "activation.") % name
                    raise exception.Forbidden(msg)
    elif to_status == 'drafted':
        if from_status != 'drafted':
            msg = _("Cannot change status to 'drafted'") % from_status
            raise exception.Forbidden(msg)
    elif to_status == 'deactivated':
        if from_status not in ('active', 'deactivated'):
            msg = _("Cannot deactivate artifact if it's not active.")
            raise exception.Forbidden(msg)
    elif to_status == 'deleted':
        msg = _("Cannot delete artifact with PATCH requests. Use special "
                "API to do this.")
        raise exception.Forbidden(msg)
    else:
        msg = _("Unknown artifact status: %s.") % to_status
        raise exception.BadRequest(msg)


def validate_visibility_transition(af, from_visibility, to_visibility):
    if to_visibility == 'private':
        if from_visibility != 'private':
            msg = _("Cannot make artifact private again.")
            raise exception.Forbidden()
    elif to_visibility == 'public':
        if af.status != 'active':
            msg = _("Cannot change visibility to 'public' if artifact"
                    " is not active.")
            raise exception.Forbidden(msg)
    else:
        msg = _("Unknown artifact visibility: %s.") % to_visibility
        raise exception.BadRequest(msg)


def validate_change_allowed(af, field_name):
    """Validate if fields can be set for the artifact."""
    if field_name not in af.fields:
        msg = _("Cannot add new field '%s' to artifact.") % field_name
        raise exception.BadRequest(msg)
    if af.status not in ('active', 'drafted'):
        msg = _("Forbidden to change fields "
                "if artifact is not active or drafted.")
        raise exception.Forbidden(message=msg)
    if af.fields[field_name].system is True:
        msg = _("Forbidden to specify system field %s. It is not "
                "available for modifying by users.") % field_name
        raise exception.Forbidden(msg)
    if af.status == 'active' and not af.fields[field_name].mutable:
        msg = (_("Forbidden to change field '%s' after activation.")
               % field_name)
        raise exception.Forbidden(message=msg)
