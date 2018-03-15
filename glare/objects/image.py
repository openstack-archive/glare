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


from oslo_versionedobjects import fields

from glare.objects import base
from glare.objects.meta import validators
from glare.objects.meta import wrappers

Field = wrappers.Field.init
Blob = wrappers.BlobField.init


class Image(base.BaseArtifact):

    fields = {
        'container_format': Field(fields.StringField,
                                  validators=[validators.AllowedValues(
                                      ['ami', 'ari', 'aki', 'bare',
                                       'ovf', 'ova', 'docker'])],
                                  description="Image container format."),
        'disk_format': Field(fields.StringField,
                             validators=[validators.AllowedValues(
                                 ['ami', 'ari', 'aki', 'vhd', 'vhdx',
                                  'vmdk', 'raw', 'qcow2', 'vdi', 'iso'])],
                             description="Image disk format."),
        'min_ram': Field(fields.IntegerField, required_on_activate=False,
                         validators=[validators.MinNumberSize(0)],
                         description="Minimal RAM required to boot image."),
        'min_disk': Field(fields.IntegerField, required_on_activate=False,
                          validators=[validators.MinNumberSize(0)],
                          description="Minimal disk space "
                                      "required to boot image."),
        'image': Blob(max_blob_size=1073741824000,
                      required_on_activate=False,
                      description="Image binary."),
        'kernel_id': Field(fields.StringField,
                           required_on_activate=False,
                           validators=[validators.UUID()],
                           description="ID of image stored in Glare that "
                                       "should be used as the kernel when "
                                       "booting an AMI-style image."),
        'ramdisk_id': Field(fields.StringField,
                            required_on_activate=False,
                            validators=[validators.UUID()],
                            description="ID of image stored in Glare that "
                                        "should be used as the ramdisk when "
                                        "booting an AMI-style image."),
        'instance_uuid': Field(fields.StringField,
                               required_on_activate=False,
                               description="Metadata which can be used to "
                                           "record which instance this image "
                                           "is associated with. "
                                           "(Informational only, does not "
                                           "create an instance snapshot.)"),
        'architecture': Field(fields.StringField,
                              required_on_activate=False,
                              description="Operating system architecture as "
                                          "specified in http://docs.openstack."
                                          "org/trunk/openstack-compute/admin/"
                                          "content/adding-images.html"),
        'os_distro': Field(fields.StringField,
                           required_on_activate=False,
                           description="Common name of operating system "
                                       "distribution as specified in "
                                       "http://docs.openstack.org/trunk/"
                                       "openstack-compute/admin/content/"
                                       "adding-images.html"),
        'os_version': Field(fields.StringField,
                            required_on_activate=False,
                            description="Operating system version as "
                                        "specified by the distributor"),
    }

    @classmethod
    def get_type_name(cls):
        return "images"

    @classmethod
    def get_display_type_name(cls):
        return "Images"
