# Copyright 2017 - Nokia Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import sys
import time

from oslo_serialization import jsonutils
from six.moves import range

from glare.tests import functional
from glare.tests.functional import base
from glare.tests.utils import execute


class TestScrubber(base.TestArtifact):

    """Test that delayed_delete works and the scrubber deletes"""

    def setUp(self):
        functional.FunctionalTest.setUp(self)

        self.include_scrubber = True
        self.set_user('user1')
        self.glare_server.deployment_flavor = 'noauth'

        self.glare_server.enabled_artifact_types = ','.join(
            self.enabled_types)
        self.glare_server.custom_artifact_types_modules = (
            'glare.tests.sample_artifact')

    def _create_sample_artifact(self):
        art = self.create_artifact({'name': 'test_art',
                                    'version': '1.0'})

        url = '/sample_artifact/%s' % art['id']
        headers = {'Content-Type': 'application/octet-stream'}

        # upload data to blob
        self.put(url=url + '/small_blob', data='aaaaaa',
                 headers=headers)

        # upload a couple of blobs to dict_of_blobs
        self.put(url + '/dict_of_blobs/blob1', data='bbbb',
                 headers=headers)
        self.put(url + '/dict_of_blobs/blob2', data='cccc',
                 headers=headers)

        # add external location
        body = jsonutils.dumps(
            {'url': self._url(url + '/small_blob'),
             'md5': "fake", 'sha1': "fake_sha", "sha256": "fake_sha256"})
        headers = {'Content-Type':
                   'application/vnd+openstack.glare-custom-location+json'}
        self.put(url=url + '/blob', data=body, status=200,
                 headers=headers)

        return url

    def test_scrubber_delayed_delete(self):
        """
        Test that artifacts don't get deleted immediately and that the scrubber
        scrubs them.
        """
        self.start_servers(delayed_delete=True, daemon=True,
                           **self.__dict__.copy())

        url = self._create_sample_artifact()

        # create another artifact
        art2 = self.create_artifact({'name': 'test_art', 'version': '2.0'})

        # delete sample artifact
        self.delete(url=url)
        art = self.get(url)
        self.assertEqual('deleted', art['status'])

        self.wait_for_scrub(url)

        # check that the second artifact wasn't removed
        art = self.get('/sample_artifact/%s' % art2['id'])
        self.assertEqual('drafted', art['status'])

    def test_scrubber_app(self):
        """
        Test that the scrubber script runs successfully when not in
        daemon mode.
        """
        self.start_servers(delayed_delete=True,
                           **self.__dict__.copy())

        url = self._create_sample_artifact()

        # wait for the scrub time on the artifacts to pass
        time.sleep(self.scrubber_daemon.scrub_time)

        # create another artifact
        art2 = self.create_artifact({'name': 'test_art', 'version': '2.0'})

        # delete sample artifact
        self.delete(url=url)
        art = self.get(url)
        self.assertEqual('deleted', art['status'])

        # scrub artifacts and make sure they are deleted
        exe_cmd = "%s -m glare.cmd.scrubber" % sys.executable
        cmd = ("%s --config-file %s" %
               (exe_cmd, self.scrubber_daemon.conf_file_name))
        exitcode, out, err = execute(cmd, raise_error=False)
        self.assertEqual(0, exitcode)

        self.wait_for_scrub(url)

        # check that the second artifact wasn't removed
        art = self.get('/sample_artifact/%s' % art2['id'])
        self.assertEqual('drafted', art['status'])

    def wait_for_scrub(self, url):
        """
        The build servers sometimes take longer than 15 seconds
        to scrub. Give it up to 5 min, checking every 5 seconds.
        When/if it flips to deleted, bail immediately.
        """
        wait_for = 300    # seconds
        check_every = 5  # seconds
        for _ in range(wait_for // check_every):
            time.sleep(check_every)
            try:
                self.get(url, status=404)
                return
            except Exception:
                pass
        else:
            self.fail("Artifact wasn't scrubbed")
