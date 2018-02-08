# Copyright 2011-2016 OpenStack Foundation
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

"""Glare policy operations inspired by Nova implementation."""

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import policy

from glare.common import exception

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

_ENFORCER = None


artifact_policy_rules = [
    policy.RuleDefault('context_is_admin', 'role:admin'),
    policy.RuleDefault('admin_or_owner',
                       'is_admin:True or project_id:%(owner)s'),
    policy.RuleDefault("artifact:type_list", "",
                       "Policy to request list of artifact types"),
    policy.RuleDefault("artifact:create", "", "Policy to create artifact."),
    policy.RuleDefault("artifact:update_public",
                       "'public':%(visibility)s and rule:context_is_admin "
                       "or not 'public':%(visibility)s",
                       "Policy to update public artifact"),
    policy.RuleDefault("artifact:update", "rule:admin_or_owner and "
                                          "rule:artifact:update_public",
                       "Policy to update artifact"),
    policy.RuleDefault("artifact:activate", "rule:admin_or_owner",
                       "Policy to activate artifact"),
    policy.RuleDefault("artifact:reactivate", "rule:context_is_admin",
                       "Policy to reactivate artifact"),
    policy.RuleDefault("artifact:deactivate", "rule:context_is_admin",
                       "Policy to update artifact"),
    policy.RuleDefault("artifact:publish", "rule:context_is_admin",
                       "Policy to publish artifact"),
    policy.RuleDefault("artifact:get", "",
                       "Policy to get artifact definition"),
    policy.RuleDefault("artifact:get_any_artifact", "rule:context_is_admin",
                       "Policy to get artifact from any project"),
    policy.RuleDefault("artifact:list", "",
                       "Policy to list artifacts"),
    policy.RuleDefault("artifact:list_all_artifacts",
                       "rule:context_is_admin",
                       "Policy to list artifacts from all projects"),
    policy.RuleDefault("artifact:delete_public",
                       "'public':%(visibility)s and rule:context_is_admin "
                       "or not 'public':%(visibility)s",
                       "Policy to delete public artifacts"),
    policy.RuleDefault("artifact:delete_deactivated",
                       "'deactivated':%(status)s and rule:context_is_admin "
                       "or not 'deactivated':%(status)s",
                       "Policy to delete deactivated artifacts"),
    policy.RuleDefault("artifact:delete", "rule:admin_or_owner and "
                                          "rule:artifact:delete_public and "
                                          "rule:artifact:delete_deactivated",
                       "Policy to delete artifacts"),
    policy.RuleDefault("artifact:set_location", "rule:admin_or_owner",
                       "Policy to set custom location for artifact blob"),
    policy.RuleDefault("artifact:set_internal_location",
                       "rule:context_is_admin",
                       "Policy to set internal location for artifact blob"),
    policy.RuleDefault("artifact:upload", "rule:admin_or_owner",
                       "Policy to upload blob for artifact"),
    policy.RuleDefault("artifact:download_deactivated",
                       "'deactivated':%(status)s and rule:context_is_admin "
                       "or not 'deactivated':%(status)s",
                       "Policy to download blob from deactivated artifact"),
    policy.RuleDefault("artifact:download",
                       "rule:admin_or_owner and "
                       "rule:artifact:download_deactivated",
                       "Policy to download blob from artifact"),
    policy.RuleDefault("artifact:download_from_any_artifact",
                       "rule:context_is_admin",
                       "Policy to download blob from any artifact"
                       " in any project"
                       ),
    policy.RuleDefault("artifact:delete_blob", "rule:admin_or_owner",
                       "Policy to delete blob with external location "
                       "from artifact"),
    policy.RuleDefault("artifact:set_quotas", "rule:context_is_admin",
                       "Policy to set quotas for projects"),
    policy.RuleDefault("artifact:list_all_quotas", "rule:context_is_admin",
                       "Policy to list all quotas for all projects"),
    policy.RuleDefault("artifact:list_project_quotas",
                       "project_id:%(project_id)s or rule:context_is_admin",
                       "Policy to get info about project quotas"),
]


def list_rules():
    return artifact_policy_rules


def init(use_conf=True):
    """Init an Enforcer class.
    """

    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer(CONF, use_conf=use_conf)
        _ENFORCER.register_defaults(list_rules())
    return _ENFORCER


def reset():
    global _ENFORCER
    if _ENFORCER:
        _ENFORCER.clear()
        _ENFORCER = None


def authorize(policy_name, target, context, do_raise=True):
    """Method checks that user action can be executed according to policies.

    :param policy_name: policy name
    :param target:
    :param do_raise
    :param context:
    :return: True if check passed
    """
    creds = context.to_policy_values()
    result = init().authorize(
        policy_name, target, creds, do_raise=do_raise,
        exc=exception.PolicyException, policy_name=policy_name)
    LOG.debug("Policy %(policy)s check %(result)s for request %(request_id)s",
              {'policy': policy_name,
               'result': 'passed' if result else 'failed',
               'request_id': context.request_id})
    return result


def check_is_admin(context):
    """Whether or not roles contains 'admin' role according to policy setting.
    """
    return authorize('context_is_admin', {}, context, do_raise=False)
