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


from oslo_log import log as logging
import six

from glare.i18n import _

LOG = logging.getLogger(__name__)


class GlareException(Exception):
    """Base Glare Exception class.

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.
    """
    message = _("An unknown exception occurred")

    def __init__(self, message=None, **kwargs):
        if message:
            self.message = message
        self.kwargs = kwargs
        if self.kwargs:
            self.message = self.message % kwargs
        LOG.error(self.message)
        super(GlareException, self).__init__(self.message)

    def __unicode__(self):
        return six.text_type(self.message)


class BadRequest(GlareException):
    message = _("Bad request")


class InvalidParameterValue(BadRequest):
    message = _("Invalid filter value ")


class InvalidFilterOperatorValue(BadRequest):
    msg = _("Unable to filter by unknown operator.")


class InvalidVersion(GlareException):
    message = _("Provided version is invalid")


class NotAcceptable(GlareException):
    message = _("Not acceptable")


class InvalidGlobalAPIVersion(NotAcceptable):
    message = _("Version %(req_ver)s is not supported by the API. Minimum "
                "is %(min_ver)s and maximum is %(max_ver)s.")


class VersionNotFoundForAPIMethod(GlareException):
    message = _("API version %(version)s is not supported on this method.")


class ApiVersionsIntersect(GlareException):
    message = _("Version of %(name)s %(min_ver)s %(max_ver)s intersects "
                "with another versions.")


class Unauthorized(GlareException):
    message = _('You are not authenticated')


class Forbidden(GlareException):
    message = _("You are not authorized to complete this action.")


class PolicyException(Forbidden):
    message = _("Policy check for %(policy_name)s "
                "failed with user credentials.")


class NotFound(GlareException):
    message = _("An object with the specified identifier was not found.")


class TypeNotFound(NotFound):
    message = _("Glare type with name '%(name)s' was not found.")


class IncorrectArtifactType(GlareException):
    message = _("Artifact type is incorrect: %(explanation)s")


class ArtifactNotFound(NotFound):
    message = _("Artifact with type name '%(type_name)s' and id '%(id)s' was "
                "not found.")


class RequestTimeout(GlareException):
    message = _("The client did not produce a request within the time "
                "that the server was prepared to wait.")


class Conflict(GlareException):
    message = _("The request could not be completed due to a conflict "
                "with the current state of the resource.")


class Gone(GlareException):
    message = _("The requested resource is no longer available at the "
                "server and no forwarding address is known.")


class PreconditionFailed(GlareException):
    message = _("The precondition given in one or more of the request-header "
                "fields evaluated to false when it was tested on the server.")


class RequestEntityTooLarge(GlareException):
    message = _("The server is refusing to process a request because the "
                "request entity is larger than the server is willing or "
                "able to process.")


class RequestRangeNotSatisfiable(GlareException):
    message = _("The request included a Range request-header field, and none "
                "of the range-specifier values in this field overlap the "
                "current extent of the selected resource, and the request "
                "did not include an If-Range request-header field.")


class Locked(GlareException):
    message = _('The resource is locked.')


class FailedDependency(GlareException):
    message = _('The method could not be performed because the requested '
                'action depended on another action and that action failed.')


class UnsupportedMediaType(GlareException):
    message = _("Unsupported media type.")


class SIGHUPInterrupt(GlareException):
    message = _("System SIGHUP signal received.")


class WorkerCreationFailure(GlareException):
    message = _("Server worker creation failed: %(reason)s.")


class DBNotAllowed(GlareException):
    msg_fmt = _('This operation is not allowed with current DB')
