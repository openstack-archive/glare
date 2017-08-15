# Copyright 2011 OpenStack Foundation
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
Base test class for running non-stubbed tests (functional tests)

The FunctionalTest class contains helper methods for starting Glare
server, grabbing the logs of each, cleaning up pidfiles, and spinning down
the server.
"""

import atexit
import datetime
import errno
import os
import platform
import shutil
import signal
import socket
import sys
import tempfile
import time

import eventlet
import fixtures
from oslo_log import log as logging
from oslo_serialization import jsonutils
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
import six.moves.urllib.parse as urlparse
import testtools

from glare.api.v1 import resource
from glare.api.v1 import router
from glare.common import utils
from glare.common import wsgi
from glare.db.sqlalchemy import api as db_api
from glare import tests as glare_tests
from glare.tests import utils as test_utils

execute, get_unused_port = test_utils.execute, test_utils.get_unused_port
tracecmd_osmap = {'Linux': 'strace', 'FreeBSD': 'truss'}

eventlet.patcher.monkey_patch()


class Server(object):
    """Class used to easily manage starting and stopping
    a server during functional test runs.
    """
    def __init__(self, test_dir, port, sock=None):
        """Creates a new Server object.

        :param test_dir: The directory where all test stuff is kept. This is
                         passed from the FunctionalTestCase.
        :param port: The port to start a server up on.
        """
        self.debug = True
        self.no_venv = False
        self.test_dir = test_dir
        self.bind_port = port
        self.conf_file_name = None
        self.conf_base = None
        self.paste_conf_base = None
        self.exec_env = None
        self.deployment_flavor = ''
        self.needs_database = False
        self.log_file = None
        self.sock = sock
        self.fork_socket = True
        self.process_pid = None
        self.server_module = None
        self.stop_kill = False

    def write_conf(self, **kwargs):
        """Writes the configuration file for the server to its intended
        destination.  Returns the name of the configuration file and
        the over-ridden config content (may be useful for populating
        error messages).
        """
        if not self.conf_base:
            raise RuntimeError("Subclass did not populate config_base!")

        conf_override = self.__dict__.copy()
        if kwargs:
            conf_override.update(**kwargs)

        # A config file and paste.ini to use just for this test...we don't want
        # to trample on currently-running Glare servers, now do we?

        conf_dir = os.path.join(self.test_dir, 'etc')
        conf_filepath = os.path.join(conf_dir, "%s.conf" % self.server_name)
        if os.path.exists(conf_filepath):
            os.unlink(conf_filepath)
        paste_conf_filepath = conf_filepath.replace(".conf", "-paste.ini")
        if os.path.exists(paste_conf_filepath):
            os.unlink(paste_conf_filepath)
        test_utils.safe_mkdirs(conf_dir)

        def override_conf(filepath, overridden):
            with open(filepath, 'w') as conf_file:
                conf_file.write(overridden)
                conf_file.flush()
                return conf_file.name

        overridden_core = self.conf_base % conf_override
        self.conf_file_name = override_conf(conf_filepath, overridden_core)

        overridden_paste = ''
        if self.paste_conf_base:
            overridden_paste = self.paste_conf_base % conf_override
            override_conf(paste_conf_filepath, overridden_paste)

        overridden = ('==Core config==\n%s\n==Paste config==\n%s' %
                      (overridden_core, overridden_paste))

        return self.conf_file_name, overridden

    def start(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """Starts the server.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """

        # Ensure the configuration file is written
        self.write_conf(**kwargs)

        self.create_database()

        cmd = ("%(server_module)s --config-file %(conf_file_name)s"
               % {"server_module": self.server_module,
                  "conf_file_name": self.conf_file_name})
        cmd = "%s -m %s" % (sys.executable, cmd)
        # close the sock and release the unused port closer to start time
        if self.exec_env:
            exec_env = self.exec_env.copy()
        else:
            exec_env = {}
        pass_fds = set()
        if self.sock:
            if not self.fork_socket:
                self.sock.close()
                self.sock = None
            else:
                fd = os.dup(self.sock.fileno())
                exec_env[utils.GLARE_TEST_SOCKET_FD_STR] = str(fd)
                pass_fds.add(fd)
                self.sock.close()

        self.process_pid = test_utils.fork_exec(cmd,
                                                logfile=os.devnull,
                                                exec_env=exec_env,
                                                pass_fds=pass_fds)

        self.stop_kill = not expect_exit
        if self.pid_file:
            with open(self.pid_file, 'w') as pf:
                pf.write('%d\n' % self.process_pid)
        if not expect_exit:
            rc = 0
            try:
                os.kill(self.process_pid, 0)
            except OSError:
                raise RuntimeError("The process did not start")
        else:
            rc = test_utils.wait_for_fork(
                self.process_pid,
                expected_exitcode=expected_exitcode)
        # avoid an FD leak
        if self.sock:
            os.close(fd)
            self.sock = None
        return (rc, '', '')

    def reload(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """Start and stop the service to reload

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.stop()
        return self.start(expect_exit=expect_exit,
                          expected_exitcode=expected_exitcode, **kwargs)

    def create_database(self):
        """Create database if required for this server"""
        if self.needs_database:
            conf_dir = os.path.join(self.test_dir, 'etc')
            test_utils.safe_mkdirs(conf_dir)
            conf_filepath = os.path.join(conf_dir, 'glare.conf')

            glare_db_env = 'GLARE_DB_TEST_SQLITE_FILE'
            if glare_db_env in os.environ:
                # use the empty db created and cached as a tempfile
                # instead of spending the time creating a new one
                db_location = os.environ[glare_db_env]
                os.system('cp %s %s/tests.sqlite'
                          % (db_location, self.test_dir))
            else:
                cmd = ('%s -m glare.cmd.db_manage --config-file %s upgrade' %
                       (sys.executable, conf_filepath))
                execute(cmd, no_venv=self.no_venv, exec_env=self.exec_env,
                        expect_exit=True)

                # copy the clean db to a temp location so that it
                # can be reused for future tests
                (osf, db_location) = tempfile.mkstemp()
                os.close(osf)
                os.system('cp %s/tests.sqlite %s'
                          % (self.test_dir, db_location))
                os.environ[glare_db_env] = db_location

                # cleanup the temp file when the test suite is
                # complete
                def _delete_cached_db():
                    try:
                        os.remove(os.environ[glare_db_env])
                    except Exception:
                        glare_tests.logger.exception(
                            "Error cleaning up the file %s" %
                            os.environ[glare_db_env])
                atexit.register(_delete_cached_db)

    def stop(self):
        """Spin down the server."""
        if not self.process_pid:
            raise Exception('why is this being called? %s' % self.server_name)

        if self.stop_kill:
            os.kill(self.process_pid, signal.SIGTERM)
        rc = test_utils.wait_for_fork(self.process_pid, raise_error=False)
        return (rc, '', '')

    def dump_log(self, name):
        log = logging.getLogger(name)
        if not self.log_file or not os.path.exists(self.log_file):
            return
        with open(self.log_file, 'r') as fptr:
            for line in fptr:
                log.info(line.strip())


class GlareServer(Server):

    """Server object that starts/stops/manages Glare server"""

    def __init__(self, test_dir, port, policy_file, delayed_delete=False,
                 pid_file=None, sock=None, **kwargs):
        super(GlareServer, self).__init__(test_dir, port, sock=sock)
        self.server_name = 'glare'
        self.server_module = 'glare.cmd.api'
        self.default_store = kwargs.get("default_store", "file")
        self.key_file = ""
        self.cert_file = ""
        self.blob_dir = os.path.join(self.test_dir, "artifacts")
        self.pid_file = pid_file or os.path.join(self.test_dir, "glare.pid")
        self.log_file = os.path.join(self.test_dir, "glare.log")
        self.delayed_delete = delayed_delete
        self.workers = 1
        self.policy_file = policy_file
        self.policy_default_rule = 'default'
        self.disable_path = None

        self.needs_database = True
        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLARE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.lock_path = self.test_dir

        self.enabled_artifact_types = ''
        self.custom_artifact_types_modules = ''
        self.max_uploaded_data = '1099511627776'
        self.max_artifact_number = '100'
        self.artifact_type_section = ''

        self.conf_base = """[DEFAULT]
debug = %(debug)s
default_log_levels = eventlet.wsgi.server=DEBUG
bind_host = 127.0.0.1
bind_port = %(bind_port)s
key_file = %(key_file)s
cert_file = %(cert_file)s
log_file = %(log_file)s
delayed_delete = %(delayed_delete)s
workers = %(workers)s
lock_path = %(lock_path)s
enabled_artifact_types = %(enabled_artifact_types)s
custom_artifact_types_modules = %(custom_artifact_types_modules)s
max_uploaded_data = %(max_uploaded_data)s
max_artifact_number = %(max_artifact_number)s
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
[paste_deploy]
flavor = %(deployment_flavor)s
[glance_store]
filesystem_store_datadir=%(blob_dir)s
default_store = %(default_store)s
[database]
connection = %(sql_connection)s
%(artifact_type_section)s
"""
        self.paste_conf_base = """[pipeline:glare-api]
pipeline = faultwrapper versionnegotiation trustedauth glarev1api

[pipeline:glare-api-noauth]
pipeline = faultwrapper versionnegotiation context glarev1api

[app:glarev1api]
paste.app_factory =
 glare.tests.functional:TestRouter.factory

[filter:faultwrapper]
paste.filter_factory =
 glare.api.middleware.fault:GlareFaultWrapperFilter.factory

[filter:versionnegotiation]
paste.filter_factory =
 glare.api.middleware.version_negotiation:
   GlareVersionNegotiationFilter.factory

[filter:context]
paste.filter_factory = glare.api.middleware.context:ContextMiddleware.factory

[filter:trustedauth]
paste.filter_factory =
 glare.api.middleware.context:TrustedAuthMiddleware.factory
"""


class ScrubberDaemon(Server):
    """
    Server object that starts/stops/manages the Scrubber server
    """

    def __init__(self, test_dir, policy_file, daemon=False, **kwargs):
        # NOTE(jkoelker): Set the port to 0 since we actually don't listen
        super(ScrubberDaemon, self).__init__(test_dir, 0)
        self.server_name = 'scrubber'
        self.server_module = 'glare.cmd.%s' % self.server_name
        self.daemon = daemon

        self.blob_dir = os.path.join(self.test_dir, "artifacts")
        self.scrub_time = 5
        self.pid_file = os.path.join(self.test_dir, "scrubber.pid")
        self.log_file = os.path.join(self.test_dir, "scrubber.log")
        self.lock_path = self.test_dir

        default_sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        self.sql_connection = os.environ.get('GLARE_TEST_SQL_CONNECTION',
                                             default_sql_connection)
        self.policy_file = policy_file
        self.policy_default_rule = 'default'

        self.conf_base = """[DEFAULT]
debug = %(debug)s
log_file = %(log_file)s
[scrubber]
daemon = %(daemon)s
wakeup_time = 2
scrub_time = %(scrub_time)s
[glance_store]
filesystem_store_datadir=%(blob_dir)s
[oslo_policy]
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s
[database]
connection = %(sql_connection)s
idle_timeout = 3600
"""

    def start(self, expect_exit=True, expected_exitcode=0, **kwargs):
        if 'daemon' in kwargs:
            expect_exit = False
        return super(ScrubberDaemon, self).start(
            expect_exit=expect_exit,
            expected_exitcode=expected_exitcode,
            **kwargs)


class FunctionalTest(test_utils.BaseTestCase):

    """Base test class for any test that wants to test the actual
    servers and clients and not just the stubbed out interfaces
    """

    inited = False
    disabled = False
    launched_servers = []

    def setUp(self):
        super(FunctionalTest, self).setUp()
        self.test_dir = self.useFixture(fixtures.TempDir()).path

        self.api_protocol = 'http'
        self.glare_port, glare_sock = test_utils.get_unused_port_and_socket()

        self.include_scrubber = False

        self.tracecmd = tracecmd_osmap.get(platform.system())

        conf_dir = os.path.join(self.test_dir, 'etc')
        test_utils.safe_mkdirs(conf_dir)
        self.copy_data_file('policy.json', conf_dir)
        self.policy_file = os.path.join(conf_dir, 'policy.json')

        self.glare_server = GlareServer(self.test_dir,
                                        self.glare_port,
                                        self.policy_file,
                                        sock=glare_sock)

        self.scrubber_daemon = ScrubberDaemon(self.test_dir, self.policy_file)

        self.pid_files = [self.glare_server.pid_file,
                          self.scrubber_daemon.pid_file]
        self.files_to_destroy = []
        self.launched_servers = []

    def tearDown(self):
        if not self.disabled:
            self.cleanup()
            # We destroy the test data store between each test case,
            # and recreate it, which ensures that we have no side-effects
            # from the tests
            self._reset_database(self.glare_server.sql_connection)
        super(FunctionalTest, self).tearDown()

        self.glare_server.dump_log('glare_server')
        self.scrubber_daemon.dump_log('scrubber_daemon')

    def set_policy_rules(self, rules):
        with open(self.policy_file, 'w') as fap:
            fap.write(jsonutils.dumps(rules))

    def _reset_database(self, conn_string):
        conn_pieces = urlparse.urlparse(conn_string)
        if conn_string.startswith('sqlite'):
            # We leave behind the sqlite DB for failing tests to aid
            # in diagnosis, as the file size is relatively small and
            # won't interfere with subsequent tests as it's in a per-
            # test directory (which is blown-away if the test is green)
            pass
        elif conn_string.startswith('mysql'):
            # We can execute the MySQL client to destroy and re-create
            # the MYSQL database, which is easier and less error-prone
            # than using SQLAlchemy to do this via MetaData...trust me.
            database = conn_pieces.path.strip('/')
            loc_pieces = conn_pieces.netloc.split('@')
            host = loc_pieces[1]
            auth_pieces = loc_pieces[0].split(':')
            user = auth_pieces[0]
            password = ""
            if len(auth_pieces) > 1:
                if auth_pieces[1].strip():
                    password = "-p%s" % auth_pieces[1]
            sql = ("drop database if exists %(database)s; "
                   "create database %(database)s;") % {'database': database}
            cmd = ("mysql -u%(user)s %(password)s -h%(host)s "
                   "-e\"%(sql)s\"") % {'user': user, 'password': password,
                                       'host': host, 'sql': sql}
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)

    def cleanup(self):
        """Makes sure anything we created or started up in the
        tests are destroyed or spun down
        """

        # NOTE(jbresnah) call stop on each of the servers instead of
        # checking the pid file.  stop() will wait until the child
        # server is dead.  This eliminates the possibility of a race
        # between a child process listening on a port actually dying
        # and a new process being started
        servers = [self.glare_server,
                   self.scrubber_daemon]
        for s in servers:
            try:
                s.stop()
            except Exception:
                pass

        for f in self.files_to_destroy:
            if os.path.exists(f):
                os.unlink(f)

    def start_server(self,
                     server,
                     expect_launch,
                     expect_exit=True,
                     expected_exitcode=0,
                     **kwargs):
        """Starts a server on an unused port.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the server.

        :param server: the server to launch
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        :param expected_exitcode: expected exitcode from the launcher
        """
        self.cleanup()

        # Start up the requested server
        exitcode, out, err = server.start(expect_exit=expect_exit,
                                          expected_exitcode=expected_exitcode,
                                          **kwargs)
        if expect_exit:
            self.assertEqual(expected_exitcode, exitcode,
                             "Failed to spin up the requested server. "
                             "Got: %s" % err)

        self.launched_servers.append(server)

        launch_msg = self.wait_for_servers([server], expect_launch)
        self.assertTrue(launch_msg is None, launch_msg)

    def start_with_retry(self, server, port_name, max_retries,
                         expect_launch=True,
                         **kwargs):
        """Starts a server, with retries if the server launches but
        fails to start listening on the expected port.

        :param server: the server to launch
        :param port_name: the name of the port attribute
        :param max_retries: the maximum number of attempts
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        """
        launch_msg = None
        for i in range(max_retries):
            exitcode, out, err = server.start(expect_exit=not expect_launch,
                                              **kwargs)
            name = server.server_name
            self.assertEqual(0, exitcode,
                             "Failed to spin up the %s server. "
                             "Got: %s" % (name, err))
            launch_msg = self.wait_for_servers([server], expect_launch)
            if launch_msg:
                server.stop()
                server.bind_port = get_unused_port()
                setattr(self, port_name, server.bind_port)
            else:
                self.launched_servers.append(server)
                break
        self.assertTrue(launch_msg is None, launch_msg)

    def start_servers(self, **kwargs):
        """Starts the Glare server on unused port.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.cleanup()

        self.start_with_retry(self.glare_server, 'glare_port', 3, **kwargs)

        if self.include_scrubber:
            exitcode, out, err = self.scrubber_daemon.start(**kwargs)
            self.assertEqual(0, exitcode,
                             "Failed to spin up the Scrubber daemon. "
                             "Got: %s" % err)

    def ping_server(self, port):
        """Simple ping on the port. If responsive, return True, else
        return False.

        :note We use raw sockets, not ping here, since ping uses ICMP and
        has no concept of ports...
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except socket.error:
            return False
        finally:
            s.close()

    def wait_for_servers(self, servers, expect_launch=True, timeout=30):
        """Tight loop, waiting for the given server port(s) to be available.
        Returns when all are pingable. There is a timeout on waiting
        for the servers to come up.

        :param servers: Glare server ports to ping
        :param expect_launch: Optional, true iff the server(s) are
                              expected to successfully start
        :param timeout: Optional, defaults to 30 seconds
        :returns: None if launch expectation is met, otherwise an
                 assertion message
        """
        now = datetime.datetime.now()
        timeout_time = now + datetime.timedelta(seconds=timeout)
        replied = []
        while (timeout_time > now):
            pinged = 0
            for server in servers:
                if self.ping_server(server.bind_port):
                    pinged += 1
                    if server not in replied:
                        replied.append(server)
            if pinged == len(servers):
                msg = 'Unexpected server launch status'
                return None if expect_launch else msg
            now = datetime.datetime.now()
            time.sleep(0.05)

        failed = list(set(servers) - set(replied))
        msg = 'Unexpected server launch status for: '
        for f in failed:
            msg += ('%s, ' % f.server_name)
            if os.path.exists(f.pid_file):
                pid = f.process_pid
                trace = f.pid_file.replace('.pid', '.trace')
                if self.tracecmd:
                    cmd = '%s -p %d -o %s' % (self.tracecmd, pid, trace)
                    try:
                        execute(cmd, raise_error=False, expect_exit=False)
                    except OSError as e:
                        if e.errno == errno.ENOENT:
                            raise RuntimeError('No executable found for "%s" '
                                               'command.' % self.tracecmd)
                        else:
                            raise
                    time.sleep(0.5)
                    if os.path.exists(trace):
                        msg += ('\n%s:\n%s\n' % (self.tracecmd,
                                                 open(trace).read()))

        self.add_log_details(failed)

        return msg if expect_launch else None

    def stop_server(self, server):
        """Called to stop a single server in a normal fashion.

        :param server: the server to stop
        """
        # Spin down the requested server
        server.stop()

    def stop_servers(self):
        self.stop_server(self.glare_server)

        if self.include_scrubber:
            self.stop_server(self.scrubber_daemon)

        self._reset_database(self.glare_server.sql_connection)

    def run_sql_cmd(self, sql):
        """Provides a crude mechanism to run manual SQL commands
        for backend DB verification within the functional tests.
        The raw result set is returned.
        """
        engine = db_api.get_engine()
        return engine.execute(sql)

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glare/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def add_log_details(self, servers=None):
        logs = [s.log_file for s in (servers or self.launched_servers)]
        for log in logs:
            if os.path.exists(log):
                testtools.content.attach_file(self, log)


class TestRouter(router.API):
    def _get_artifacts_resource(self):
        deserializer = resource.RequestDeserializer()
        serializer = resource.ResponseSerializer()
        controller = resource.ArtifactsController()
        return wsgi.Resource(controller, deserializer, serializer)
