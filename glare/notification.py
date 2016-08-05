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
from oslo_messaging import serializer

_ALIASES = {
    'glare.openstack.common.rpc.impl_kombu': 'rabbit',
    'glare.openstack.common.rpc.impl_qpid': 'qpid',
    'glare.openstack.common.rpc.impl_zmq': 'zmq',
}

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def get_transport():
    return oslo_messaging.get_notification_transport(CONF, aliases=_ALIASES)


class RequestSerializer(serializer.Serializer):

    def serialize_entity(self, context, entity):
        return entity.to_notification()

    def deserialize_entity(self, context, entity):
        return entity

    def serialize_context(self, context):
        return context.to_dict()

    def deserialize_context(self, context):
        return context.from_dict(context)


class Notifier(object):
    """Simple interface to receive Glare notifier

    """

    SERVICE_NAME = 'artifact'
    GLARE_NOTIFIER = None

    @classmethod
    def _get_notifier(cls):
        if cls.GLARE_NOTIFIER is None:
            notifier_opts = [
                cfg.StrOpt('glare_publisher_id', default="artifact",
                           help='Default publisher_id for outgoing '
                                'Glare notifications.')]
            CONF.register_opts(notifier_opts)
            cls.GLARE_NOTIFIER = oslo_messaging.Notifier(
                get_transport(),
                publisher_id=CONF.glare_publisher_id,
                serializer=RequestSerializer())
        return cls.GLARE_NOTIFIER

    @classmethod
    def notify(cls, context, event_type, body, level='INFO'):
        """Notify Glare listeners with some useful info

        :param context: User request context
        :param event_type: type of event
        :param body: notification payload
        :param level: notification level ("INFO", "WARN", "ERROR", etc)
        """
        af_notifier = cls._get_notifier()
        method = getattr(af_notifier, level.lower())
        method(context, "%s.%s" % (cls.SERVICE_NAME, event_type), body)
        LOG.debug('Notification event %(event)s send successfully for '
                  'request %(request)s', {'event': event_type,
                                          'request': context.request_id})
