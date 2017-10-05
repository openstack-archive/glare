# Copyright 2010-2011 OpenStack Foundation
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

"""Common utilities used in testing"""
import errno
import functools
import os
import shlex
import shutil
import six
import socket
import subprocess

import fixtures
from oslo_config import cfg
from oslo_config import fixture as cfg_fixture
from oslo_log import log
import requests
import testtools

from glare.common import config

CONF = cfg.CONF
try:
    CONF.debug
except cfg.NoSuchOptError:
    # NOTE(sigmavirus24): If we run the entire test suite, the logging options
    # will be registered appropriately and we do not need to re-register them.
    # However, when we run a test in isolation (or use --debug), those options
    # will not be registered for us. In order for a test in a class that
    # inherits from BaseTestCase to even run, we will need to register them
    # ourselves.  BaseTestCase.config will set the debug level if something
    # calls self.config(debug=True) so we need these options registered
    # appropriately.
    # See bug 1433785 for more details.
    log.register_options(CONF)


class BaseTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseTestCase, self).setUp()

        self._config_fixture = self.useFixture(cfg_fixture.Config())

        # NOTE(bcwaldon): parse_args has to be called to register certain
        # command-line options - specifically we need config_dir for
        # the following policy tests
        config.parse_args(args=[])
        self.addCleanup(CONF.reset)
        self.test_dir = self.useFixture(fixtures.TempDir()).path
        self.conf_dir = os.path.join(self.test_dir, 'etc')
        safe_mkdirs(self.conf_dir)
        self.set_policy()

    def set_policy(self):
        conf_file = "policy.json"
        self.policy_file = self._copy_data_file(conf_file, self.conf_dir)
        self.config(policy_file=self.policy_file, group='oslo_policy')

    def _copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glare/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def config(self, **kw):
        """Override some configuration values.

        The keyword arguments are the names of configuration options to
        override and their values.
        If a group argument is supplied, the overrides are applied to
        the specified configuration option group.
        All overrides are automatically cleared at the end of the current
        test by the fixtures cleanup process.
        """
        self._config_fixture.config(**kw)


class requires(object):
    """Decorator that initiates additional test setup/teardown."""
    def __init__(self, setup=None, teardown=None):
        self.setup = setup
        self.teardown = teardown

    def __call__(self, func):
        def _runner(*args, **kw):
            if self.setup:
                self.setup(args[0])
            func(*args, **kw)
            if self.teardown:
                self.teardown(args[0])
        _runner.__name__ = func.__name__
        _runner.__doc__ = func.__doc__
        return _runner


class depends_on_exe(object):
    """Decorator to skip test if an executable is unavailable"""
    def __init__(self, exe):
        self.exe = exe

    def __call__(self, func):
        def _runner(*args, **kw):
            cmd = 'which %s' % self.exe
            exitcode, out, err = execute(cmd, raise_error=False)
            if exitcode != 0:
                args[0].disabled_message = 'test requires exe: %s' % self.exe
                args[0].disabled = True
            func(*args, **kw)
        _runner.__name__ = func.__name__
        _runner.__doc__ = func.__doc__
        return _runner


def skip_if_disabled(func):
    """Decorator that skips a test if test case is disabled."""
    @functools.wraps(func)
    def wrapped(*a, **kwargs):
        func.__test__ = False
        test_obj = a[0]
        message = getattr(test_obj, 'disabled_message',
                          'Test disabled')
        if getattr(test_obj, 'disabled', False):
            test_obj.skipTest(message)
        func(*a, **kwargs)
    return wrapped


def fork_exec(cmd,
              exec_env=None,
              logfile=None,
              pass_fds=None):
    """Execute a command using fork/exec.

    This is needed for programs system executions that need path
    searching but cannot have a shell as their parent process, for
    example: glare.  When glare starts it sets itself as
    the parent process for its own process group.  Thus the pid that
    a Popen process would have is not the right pid to use for killing
    the process group.  This patch gives the test env direct access
    to the actual pid.

    :param cmd: Command to execute as an array of arguments.
    :param exec_env: A dictionary representing the environment with
                     which to run the command.
    :param logfile: A path to a file which will hold the stdout/err of
                   the child process.
    :param pass_fds: Sequence of file descriptors passed to the child.
    """
    env = os.environ.copy()
    if exec_env is not None:
        for env_name, env_val in exec_env.items():
            if callable(env_val):
                env[env_name] = env_val(env.get(env_name))
            else:
                env[env_name] = env_val

    pid = os.fork()
    if pid == 0:
        if logfile:
            fds = [1, 2]
            with open(logfile, 'r+b') as fptr:
                for desc in fds:  # close fds
                    try:
                        os.dup2(fptr.fileno(), desc)
                    except OSError:
                        pass
        if pass_fds and hasattr(os, 'set_inheritable'):
            # os.set_inheritable() is only available and needed
            # since Python 3.4. On Python 3.3 and older, file descriptors are
            # inheritable by default.
            for fd in pass_fds:
                os.set_inheritable(fd, True)

        args = shlex.split(cmd)
        os.execvpe(args[0], args, env)
    else:
        return pid


def wait_for_fork(pid,
                  raise_error=True,
                  expected_exitcode=0):
    """Wait for a process to complete

    This function will wait for the given pid to complete.  If the
    exit code does not match that of the expected_exitcode an error
    is raised.
    """

    rc = 0
    try:
        (pid, rc) = os.waitpid(pid, 0)
        rc = os.WEXITSTATUS(rc)
        if rc != expected_exitcode:
            raise RuntimeError('The exit code %d is not %d'
                               % (rc, expected_exitcode))
    except Exception:
        if raise_error:
            raise

    return rc


def execute(cmd,
            raise_error=True,
            no_venv=False,
            exec_env=None,
            expect_exit=True,
            expected_exitcode=0,
            context=None):
    """Executes a command in a subprocess.

    Returns a tuple of (exitcode, out, err), where out is the string
    output from stdout and err is the string output from stderr when
    executing the command.

    :param cmd: Command string to execute
    :param raise_error: If returncode is not 0 (success), then
                        raise a RuntimeError? Default: True)
    :param no_venv: Disable the virtual environment
    :param exec_env: Optional dictionary of additional environment
                     variables; values may be callables, which will
                     be passed the current value of the named
                     environment variable
    :param expect_exit: Optional flag true iff timely exit is expected
    :param expected_exitcode: expected exitcode from the launcher
    :param context: additional context for error message
    """

    env = os.environ.copy()
    if exec_env is not None:
        for env_name, env_val in exec_env.items():
            if callable(env_val):
                env[env_name] = env_val(env.get(env_name))
            else:
                env[env_name] = env_val

    # If we're asked to omit the virtualenv, and if one is set up,
    # restore the various environment variables
    if no_venv and 'VIRTUAL_ENV' in env:
        # Clip off the first element of PATH
        env['PATH'] = env['PATH'].split(os.pathsep, 1)[-1]
        del env['VIRTUAL_ENV']

    # Make sure that we use the programs in the
    # current source directory's bin/ directory.
    path_ext = [os.path.join(os.getcwd(), 'bin')]

    # Also jack in the path cmd comes from, if it's absolute
    args = shlex.split(cmd)
    executable = args[0]
    if os.path.isabs(executable):
        path_ext.append(os.path.dirname(executable))

    env['PATH'] = ':'.join(path_ext) + ':' + env['PATH']
    process = subprocess.Popen(args,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               env=env)
    if expect_exit:
        result = process.communicate()
        (out, err) = result
        exitcode = process.returncode
    else:
        out = ''
        err = ''
        exitcode = 0

    if exitcode != expected_exitcode and raise_error:
        msg = ("Command %(cmd)s did not succeed. Returned an exit "
               "code of %(exitcode)d."
               "\n\nSTDOUT: %(out)s"
               "\n\nSTDERR: %(err)s" % {'cmd': cmd, 'exitcode': exitcode,
                                        'out': out, 'err': err})
        if context:
            msg += "\n\nCONTEXT: %s" % context
        raise RuntimeError(msg)
    return exitcode, out, err


def find_executable(cmdname):
    """Searches the path for a given cmdname.

    Returns an absolute filename if an executable with the given
    name exists in the path, or None if one does not.

    :param cmdname: The bare name of the executable to search for
    """

    # Keep an eye out for the possibility of an absolute pathname
    if os.path.isabs(cmdname):
        return cmdname

    # Get a list of the directories to search
    path = ([os.path.join(os.getcwd(), 'bin')] +
            os.environ['PATH'].split(os.pathsep))

    # Search through each in turn
    for elem in path:
        full_path = os.path.join(elem, cmdname)
        if os.access(full_path, os.X_OK):
            return full_path

    # No dice...
    return None


def get_unused_port():
    """Returns an unused port on localhost.
    """
    port, s = get_unused_port_and_socket()
    s.close()
    return port


def get_unused_port_and_socket():
    """Returns an unused port on localhost and the open socket
    from which it was created.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    addr, port = s.getsockname()
    return (port, s)


def xattr_writes_supported(path):
    """Returns True if the we can write a file to the supplied
    path and subsequently write a xattr to that file.
    """
    try:
        import xattr
    except ImportError:
        return False

    def set_xattr(path, key, value):
        xattr.setxattr(path, "user.%s" % key, value)

    # We do a quick attempt to write a user xattr to a temporary file
    # to check that the filesystem is even enabled to support xattrs
    fake_filepath = os.path.join(path, 'testing-checkme')
    result = True
    with open(fake_filepath, 'wb') as fake_file:
        fake_file.write(b"XXX")
        fake_file.flush()
    try:
        set_xattr(fake_filepath, 'hits', b'1')
    except IOError as e:
        if e.errno == errno.EOPNOTSUPP:
            result = False
    else:
        # Cleanup after ourselves...
        if os.path.exists(fake_filepath):
            os.unlink(fake_filepath)

    return result


def safe_mkdirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


class FakeHTTPResponse(object):
    def __init__(self, status=200, headers=None, data=None, *args, **kwargs):
        data = data or b'some_data'
        self.data = six.BytesIO(data)
        self.read = self.data.read
        self.status = status
        self.headers = headers or {'content-length': len(data)}
        if not kwargs.get('no_response_body', False):
            self.body = None

    def getheader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def getheaders(self):
        return self.headers or {}

    def read(self, amt):
        self.data.read(amt)

    def release_conn(self):
        pass

    def close(self):
        self.data.close()


def fake_response(status_code=200, headers=None, content=None, **kwargs):
    r = requests.models.Response()
    r.status_code = status_code
    r.headers = headers or {}
    r.raw = FakeHTTPResponse(status_code, headers, content, kwargs)
    return r
