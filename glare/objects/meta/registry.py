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

import importlib
import pkgutil
import sys

from oslo_config import cfg
from oslo_config import types
from oslo_log import log as logging
from oslo_versionedobjects import base as vo_base
import six

from glare.common import exception
from glare.i18n import _, _LE
from glare.objects import base

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

registry_options = [
    cfg.ListOpt('enabled_artifact_types',
                default=['heat_templates', 'heat_environments',
                         'murano_packages', 'tosca_templates', 'images'],
                item_type=types.String(),
                help=_("List of enabled artifact types that will be "
                       "available to user")),
    cfg.ListOpt('custom_artifact_types_modules', default=[],
                item_type=types.String(),
                help=_("List of custom user modules with artifact types that "
                       "will be uploaded by Glare dynamically during service "
                       "startup."))
]
CONF.register_opts(registry_options, group='glare')


def import_submodules(module):
    """Import all submodules of a module

    :param module: Package name
    :return list of imported modules
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
            LOG.error(_LE("Cannot import custom artifact type from module "
                          "%(module_name)%s. Error: %(error)s"),
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

    @classmethod
    def register_all_artifacts(cls):
        """Register all artifacts in glare"""
        # get all submodules in glare.objects
        # please note that we registering trusted modules first
        # and applying custom modules after that to allow custom modules
        # to specify custom logic inside
        modules = (import_submodules('glare.objects') +
                   import_modules_list(
                       CONF.glare.custom_artifact_types_modules))
        # get all versioned object classes in module
        supported_types = []
        for module in modules:
            supported_types.extend(get_subclasses(module, base.BaseArtifact))
        for type_name in set(CONF.glare.enabled_artifact_types + ['all']):
            for af_type in supported_types:
                if type_name == af_type.get_type_name():
                    cls._validate_artifact_type(af_type)
                    cls.register(af_type)
                    break
            else:
                raise exception.TypeNotFound(name=type_name)

    @classmethod
    def get_artifact_type(cls, type_name):
        """Return artifact type based on artifact type name

        :param type_name: name of artifact type
        :return: artifact class
        """
        for name, af_type in six.iteritems(cls.obj_classes()):
            if af_type[0].get_type_name() == type_name:
                return af_type[0]
        raise exception.TypeNotFound(name=type_name)

    @classmethod
    def _validate_artifact_type(cls, type_class):
        """Validate artifact type class

        Raises an exception if validation will fail.
        :param type_class: artifact class
        """
        base_classes = [object, base.BaseArtifact, vo_base.VersionedObject]
        base_attributes = set()
        for b_class in base_classes:
            base_attributes.update(set(vars(b_class).keys()))
        class_attributes = set(vars(type_class).keys())
        common_attrs = class_attributes & base_attributes
        allowed_attributes = ('VERSION', 'fields', 'init_db_api',
                              'get_type_name', 'validate_activate',
                              'validate_publish', 'validate_upload',
                              '__doc__', '__module__')
        for attr in common_attrs:
            if attr not in allowed_attributes:
                raise exception.IncorrectArtifactType(
                    explanation=_("attribute %(attr)s not allowed to be "
                                  "redefined in subclass %(class_name)s") % {
                        "attr": attr, "class_name": str(type_class)})
