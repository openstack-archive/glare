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

sudo chmod -R a+rw /opt/stack/
DEVSTACK_PATH="$BASE/new"
(cd $DEVSTACK_PATH/glare/; sudo virtualenv .venv)
. $DEVSTACK_PATH/glare/.venv/bin/activate

(cd $DEVSTACK_PATH/tempest/; sudo pip install -r requirements.txt -r test-requirements.txt)

sudo cp $DEVSTACK_PATH/tempest/etc/logging.conf.sample $DEVSTACK_PATH/tempest/etc/logging.conf

(cd $DEVSTACK_PATH/glare/; sudo pip install -r requirements.txt -r test-requirements.txt)
(cd $DEVSTACK_PATH/glare/; sudo python setup.py install)

(cd $DEVSTACK_PATH/tempest/; sudo rm -rf .testrepository)
(cd $DEVSTACK_PATH/tempest/; sudo testr init)
echo "running glare tests"
(cd $BASE/new/tempest/; sudo -E tox -eall-plugin glare)
