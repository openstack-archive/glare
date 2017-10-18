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

import collections
import importlib
import pkgutil
import sys

from oslo_config import cfg
from oslo_config import types as conf_types
from oslo_log import log as logging
from oslo_versionedobjects import base as vo_base

from glare.common import exception
from glare.i18n import _
from glare.objects import base

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

registry_options = [
    cfg.ListOpt('enabled_artifact_types',
                default=['heat_templates', 'heat_environments',
                         'murano_packages', 'tosca_templates', 'images'],
                item_type=conf_types.String(),
                help=_("List of enabled artifact types that will be "
                       "available to user")),
    cfg.ListOpt('custom_artifact_types_modules', default=[],
                item_type=conf_types.String(),
                help=_("List of custom user modules with artifact types that "
                       "will be uploaded by Glare dynamically during service "
                       "startup."))
]
CONF.register_opts(registry_options)


def import_submodules(module):
    """Import all submodules of a module.

    :param module: Package name
    :return: list of imported modules
    """
    package = sys.modules[module]
    return [
        importlib.import_module(module + '.' + name)
        for loader, name, is_pkg in pkgutil.walk_packages(package.__path__)]


def import_modules_list(modules):
    custom_module_list = []
    for module_name in modules:
        try:
            custom_module_list.append(importlib.import_module(module_name))
        except Exception as e:
            LOG.exception(e)
            LOG.error("Cannot import custom artifact type from module "
                      "%(module_name)%s. Error: %(error)s",
                      {'module_name': module_name, 'error': str(e)})
    return custom_module_list


def get_subclasses(module, base_class):
    subclasses = []
    for name in dir(module):
        obj = getattr(module, name)
        try:
            if issubclass(obj, base_class) and obj != base_class:
                subclasses.append(obj)
        except TypeError:
            pass
    return subclasses


class ArtifactRegistry(vo_base.VersionedObjectRegistry):
    """Artifact Registry is responsible for registration of artifacts and
    returning appropriate artifact types based on artifact type name.
    """

    enabled_types = {}

    @classmethod
    def register_all_artifacts(cls):
        """Register all artifacts in Glare."""
        # get all submodules in glare.objects
        # please note that we registering trusted modules first
        # and applying custom modules after that to allow custom modules
        # to specify custom logic inside
        modules = (import_submodules('glare.objects') +
                   import_modules_list(
                       CONF.custom_artifact_types_modules))
        # get all versioned object classes in module
        supported_types = []
        for module in modules:
            supported_types.extend(get_subclasses(module, base.BaseArtifact))

        for type_name in set(CONF.enabled_artifact_types + ['all']):
            for af_type in supported_types:
                if type_name == af_type.get_type_name():
                    if af_type != 'all':
                        CONF.register_opts(
                            af_type.list_artifact_type_opts(),
                            group='artifact_type:' + type_name)
                    cls.register(af_type)
                    break
            else:
                raise exception.TypeNotFound(name=type_name)

            # Fill enabled_types
            for name, af_type in cls.obj_classes().items():
                cls.enabled_types[af_type[0].get_type_name()] = af_type[0]

    @classmethod
    def get_artifact_type(cls, type_name):
        """Return artifact type based on artifact type name.

        :param type_name: name of artifact type
        :return: artifact class
        """
        if type_name not in cls.enabled_types:
            raise exception.TypeNotFound(name=type_name)
        return cls.enabled_types[type_name]

    @classmethod
    def reset_registry(cls):
        """Resets all registered artifact type classes."""
        cls._registry._obj_classes = collections.defaultdict(list)
