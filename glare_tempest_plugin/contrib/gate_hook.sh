#!/usr/bin/env bash
# Copyright 2017 - Nokia
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

export DEVSTACK_GATE_INSTALL_TESTONLY=1
export DEVSTACK_GATE_TEMPEST=1
export DEVSTACK_GATE_TEMPEST_NOTESTS=1
export KEEP_LOCALRC=1

export DEVSTACK_LOCAL_CONFIG+=$'\n'"GLARE_CUSTOM_MODULES=glare.tests.sample_artifact"
export DEVSTACK_LOCAL_CONFIG+=$'\n'"GLARE_ENABLED_TYPES=heat_templates,heat_environments,murano_packages,tosca_templates,images,sample_artifact"

GATE_DEST=$BASE/new
DEVSTACK_PATH=$GATE_DEST/devstack
$GATE_DEST/devstack-gate/devstack-vm-gate.sh
