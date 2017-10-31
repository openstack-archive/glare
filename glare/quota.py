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

from oslo_config import cfg

from glare.common import exception
from glare.db.sqlalchemy import api
from glare.i18n import _

CONF = cfg.CONF


def verify_artifact_count(context, type_name):
    """Verify if user can upload data based on his quota limits.

    :param context: user context
    :param type_name: name of artifact type
    """
    global_limit = CONF.max_artifact_number
    type_limit = getattr(
        CONF, 'artifact_type:' + type_name).max_artifact_number

    # update limits if they were reassigned for project
    project_id = context.project_id
    quotas = list_quotas(project_id).get(project_id, {})
    if 'max_artifact_number' in quotas:
        global_limit = quotas['max_artifact_number']
    if 'max_artifact_number:' + type_name in quotas:
        type_limit = quotas['max_artifact_number:' + type_name]

    session = api.get_session()

    if global_limit != -1:
        # the whole amount of created artifacts
        whole_number = api.count_artifact_number(context, session)

        if whole_number >= global_limit:
            msg = _("Can't create artifact because of global quota "
                    "limit is %(global_limit)d artifacts. "
                    "You have %(whole_number)d artifact(s).") % {
                'global_limit': global_limit, 'whole_number': whole_number}
            raise exception.Forbidden(msg)

    if type_limit != -1:
        # the amount of artifacts for specific type
        type_number = api.count_artifact_number(
            context, session, type_name)

        if type_number >= type_limit:
            msg = _("Can't create artifact because of quota limit for "
                    "artifact type '%(type_name)s' is %(type_limit)d "
                    "artifacts. You have %(type_number)d artifact(s) "
                    "of this type.") % {
                'type_name': type_name,
                'type_limit': type_limit,
                'type_number': type_number}
            raise exception.Forbidden(msg)


def verify_uploaded_data_amount(context, type_name, data_amount=None):
    """Verify if user can upload data based on his quota limits.

    :param context: user context
    :param type_name: name of artifact type
    :param data_amount: number of bytes user wants to upload. Value None means
     that user hasn't specified data amount. In this case don't raise an
     exception, but just return the amount of data he is able to upload.
    :return: number of bytes user can upload if data_amount isn't specified
    """
    global_limit = CONF.max_uploaded_data
    type_limit = getattr(CONF, 'artifact_type:' + type_name).max_uploaded_data

    # update limits if they were reassigned for project
    project_id = context.project_id
    quotas = list_quotas(project_id).get(project_id, {})
    if 'max_uploaded_data' in quotas:
        global_limit = quotas['max_uploaded_data']
    if 'max_uploaded_data:' + type_name in quotas:
        type_limit = quotas['max_uploaded_data:' + type_name]

    session = api.get_session()
    res = -1

    if global_limit != -1:
        # the whole amount of created artifacts
        whole_number = api.calculate_uploaded_data(context, session)
        if data_amount is None:
            res = global_limit - whole_number
        elif whole_number + data_amount > global_limit:
            msg = _("Can't upload %(data_amount)d byte(s) because of global "
                    "quota limit: %(global_limit)d. "
                    "You have %(whole_number)d bytes uploaded.") % {
                'data_amount': data_amount,
                'global_limit': global_limit,
                'whole_number': whole_number}
            raise exception.RequestEntityTooLarge(msg)

    if type_limit != -1:
        # the amount of artifacts for specific type
        type_number = api.calculate_uploaded_data(
            context, session, type_name)
        if data_amount is None:
            available = type_limit - type_number
            res = available if res == -1 else min(res, available)
        elif type_number + data_amount > type_limit:
            msg = _("Can't upload %(data_amount)d byte(s) because of "
                    "quota limit for artifact type '%(type_name)s': "
                    "%(type_limit)d. You have %(type_number)d bytes "
                    "uploaded for this type.") % {
                'data_amount': data_amount,
                'type_name': type_name,
                'type_limit': type_limit,
                'type_number': type_number}
            raise exception.RequestEntityTooLarge(msg)
    return res


def set_quotas(values):
    session = api.get_session()
    api.set_quotas(values, session)


def list_quotas(project_id=None):
    session = api.get_session()
    return api.get_all_quotas(session, project_id)
