# Copyright 2016 Openstack Foundation.
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

import re

from glare.common import exception
from glare.i18n import _


REST_API_VERSION_HISTORY = """REST API Version History:

    * 1.1 Added dynamic quotas API request. Added a possibility to delete blobs
    with external locations. Added a possibility to define system locations to
    blobs.

    * 1.0 - First stable API version that supports microversion. If API version
    is not specified in the request then API v1.0 is used as default API
    version.
"""


class APIVersionRequest(object):
    """This class represents an API Version Request with convenience
    methods for manipulation and comparison of version
    numbers that we need to do to implement microversions.
    """

    _MIN_API_VERSION = "1.0"
    _MAX_API_VERSION = "1.1"
    _DEFAULT_API_VERSION = "1.0"

    def __init__(self, version_string):
        """Create an API version request object.

        :param version_string: String representation of APIVersionRequest.
         Correct format is 'X.Y', where 'X' and 'Y' are int values.
        """
        match = re.match(r"^([1-9]\d*)\.([1-9]\d*|0)$", version_string)
        if match:
            self.ver_major = int(match.group(1))
            self.ver_minor = int(match.group(2))
        else:
            msg = _("API version string %s is not valid. "
                    "Cannot determine API version.") % version_string
            raise exception.BadRequest(msg)

    def __str__(self):
        """Debug/Logging representation of object."""
        return ("API Version Request Major: %s, Minor: %s"
                % (self.ver_major, self.ver_minor))

    def _format_type_error(self, other):
        return TypeError(_("'%(other)s' should be an instance of '%(cls)s'") %
                         {"other": other, "cls": self.__class__})

    def __lt__(self, other):
        if not isinstance(other, APIVersionRequest):
            raise self._format_type_error(other)

        return ((self.ver_major, self.ver_minor) <
                (other.ver_major, other.ver_minor))

    def __eq__(self, other):
        if not isinstance(other, APIVersionRequest):
            raise self._format_type_error(other)

        return ((self.ver_major, self.ver_minor) ==
                (other.ver_major, other.ver_minor))

    def __gt__(self, other):
        if not isinstance(other, APIVersionRequest):
            raise self._format_type_error(other)

        return ((self.ver_major, self.ver_minor) >
                (other.ver_major, other.ver_minor))

    def __le__(self, other):
        return self < other or self == other

    def __ne__(self, other):
        return not self.__eq__(other)

    def __ge__(self, other):
        return self > other or self == other

    def matches(self, min_version, max_version):
        """Returns whether the version object represents a version
        greater than or equal to the minimum version and less than
        or equal to the maximum version.

        :param min_version: Minimum acceptable version.
        :param max_version: Maximum acceptable version.
        :returns: boolean
        """
        return min_version <= self <= max_version

    def get_string(self):
        """Converts object to string representation which is used to create
        an APIVersionRequest object results in the same version request.
        """
        return "%s.%s" % (self.ver_major, self.ver_minor)

    @classmethod
    def min_version(cls):
        """Minimal allowed api version."""
        return APIVersionRequest(cls._MIN_API_VERSION)

    @classmethod
    def max_version(cls):
        """Maximal allowed api version."""
        return APIVersionRequest(cls._MAX_API_VERSION)

    @classmethod
    def default_version(cls):
        """Default api version if no version in request."""
        return APIVersionRequest(cls._DEFAULT_API_VERSION)
