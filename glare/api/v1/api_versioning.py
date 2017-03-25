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

import functools

from glare.api.v1 import api_version_request as api_version
from glare.common import exception as exc
from glare.i18n import _


class VersionedMethod(object):

    def __init__(self, name, start_version, end_version, func):
        """Versioning information for a single method.

        :param name: Name of the method
        :param start_version: Minimum acceptable version
        :param end_version: Maximum acceptable_version
        :param func: Method to call
        """
        # NOTE(kairat): minimums and maximums are inclusive
        self.name = name
        self.start_version = start_version
        self.end_version = end_version
        self.func = func

    def __str__(self):
        return ("Version Method %s: min: %s, max: %s"
                % (self.name, self.start_version, self.end_version))


class VersionedResource(object):
    """Versioned mixin that provides ability to define versioned methods and
    return appropriate methods based on user request.
    """

    # prefix for all versioned methods in class
    VER_METHODS_ATTR_PREFIX = 'versioned_methods_'

    @staticmethod
    def check_for_versions_intersection(func_list):
        """Determines whether function list contains version intervals
        intersections or not. General algorithm:
        https://en.wikipedia.org/wiki/Intersection_algorithm

        :param func_list: list of VersionedMethod objects
        :return: boolean
        """
        pairs = []
        counter = 0
        for f in func_list:
            pairs.append((f.start_version, 1, f))
            pairs.append((f.end_version, -1, f))

        def compare(x):
            return x[0]

        pairs.sort(key=compare)
        for p in pairs:
            counter += p[1]
            if counter > 1:
                return True
        return False

    @classmethod
    def supported_versions(cls, min_ver, max_ver=None):
        """Decorator for versioning api methods.

        Add the decorator to any method which takes a request object
        as the first parameter and belongs to a class which inherits from
        wsgi.Controller. The implementation inspired by Nova.

        :param min_ver: string representing minimum version
        :param max_ver: optional string representing maximum version
        """

        def decorator(f):
            obj_min_ver = api_version.APIVersionRequest(min_ver)
            if max_ver:
                obj_max_ver = api_version.APIVersionRequest(max_ver)
            else:
                obj_max_ver = api_version.APIVersionRequest.max_version()

            # Add to list of versioned methods registered
            func_name = f.__name__
            new_func = VersionedMethod(func_name, obj_min_ver, obj_max_ver, f)

            versioned_attr = cls.VER_METHODS_ATTR_PREFIX + cls.__name__
            func_dict = getattr(cls, versioned_attr, {})
            if not func_dict:
                setattr(cls, versioned_attr, func_dict)

            func_list = func_dict.get(func_name, [])
            if not func_list:
                func_dict[func_name] = func_list
                func_list.append(new_func)

            # Ensure the list is sorted by minimum version (reversed)
            # so later when we work through the list in order we find
            # the method which has the latest version which supports
            # the version requested.
            is_intersect = cls.check_for_versions_intersection(
                func_list)

            if is_intersect:
                raise exc.ApiVersionsIntersect(
                    name=new_func.name,
                    min_ver=new_func.start_version,
                    max_ver=new_func.end_version,
                )

            func_list.sort(key=lambda vf: vf.start_version, reverse=True)

            return f

        return decorator

    def __getattribute__(self, key):
        def version_select(*args, **kwargs):
            """Look for the method which matches the name supplied and version
            constraints and calls it with the supplied arguments.

            :returns: Returns the result of the method called
            :raises: VersionNotFoundForAPIMethod if there is no method which
             matches the name and version constraints
            """
            # versioning is used in 3 classes: request deserializer and
            # controller have request as first argument
            # response serializer has response as first argument
            # we must respect all three cases
            if hasattr(args[0], 'api_version_request'):
                ver = args[0].api_version_request
            elif hasattr(args[0], 'request'):
                ver = args[0].request.api_version_request
            else:
                raise exc.VersionNotFoundForAPIMethod(
                    message=_("Api version not found in the request."))

            func_list = self.versioned_methods[key]
            for func in func_list:
                if ver.matches(func.start_version, func.end_version):
                    # Update the version_select wrapper function so
                    # other decorator attributes like wsgi.response
                    # are still respected.
                    functools.update_wrapper(version_select, func.func)
                    return func.func(self, *args, **kwargs)

            # No version match
            raise exc.VersionNotFoundForAPIMethod(version=ver)

        class_obj = object.__getattribute__(self, '__class__')
        prefix = object.__getattribute__(self, 'VER_METHODS_ATTR_PREFIX')
        attr_name = prefix + object.__getattribute__(class_obj, '__name__')
        try:
            if key in object.__getattribute__(self, attr_name):
                return version_select
        except AttributeError:
            # No versioning on this class
            pass

        return object.__getattribute__(self, key)
