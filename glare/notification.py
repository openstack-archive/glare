# Copyright (c) 2016 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

notifier_opts = [
    cfg.HostAddressOpt('glare_publisher_id', default="artifact.localhost",
                       help='Default publisher_id for outgoing '
                            'Glare notifications.')]
CONF.register_opts(notifier_opts)


def get_transport():
    return oslo_messaging.get_notification_transport(CONF)


def set_defaults(control_exchange='glare'):
    oslo_messaging.set_transport_defaults(control_exchange)


class Notifier(object):
    """Simple interface to receive Glare notifier."""

    SERVICE_NAME = 'artifact'
    GLARE_NOTIFIER = None

    @classmethod
    def _get_notifier(cls):
        if cls.GLARE_NOTIFIER is None:
            cls.GLARE_NOTIFIER = oslo_messaging.Notifier(
                get_transport(),
                publisher_id=CONF.glare_publisher_id)
        return cls.GLARE_NOTIFIER

    @classmethod
    def notify(cls, context, event_type, body, level='INFO'):
        """Notify Glare listeners with some useful info.

        :param context: User request context
        :param event_type: type of event
        :param body: notification payload
        :param level: notification level ("INFO", "WARN", "ERROR", etc)
        """
        af_notifier = cls._get_notifier()
        method = getattr(af_notifier, level.lower())
        if hasattr(body, 'to_notification'):
            body = body.to_notification()
        method({}, "%s.%s" % (cls.SERVICE_NAME, event_type), body)
        LOG.debug('Notification event %(event)s send successfully for '
                  'request %(request)s', {'event': event_type,
                                          'request': context.request_id})
