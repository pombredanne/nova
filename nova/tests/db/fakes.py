# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

"""Stubouts, mocks and fixtures for the test suite"""

import time

from nova import db
from nova import test
from nova import utils


def stub_out_db_instance_api(stubs):
    """ Stubs out the db API for creating Instances """

    INSTANCE_TYPES = {
        'm1.tiny': dict(memory_mb=512,
                        vcpus=1,
                        local_gb=0,
                        flavorid=1,
                        rxtx_cap=1),
        'm1.small': dict(memory_mb=2048,
                         vcpus=1,
                         local_gb=20,
                         flavorid=2,
                         rxtx_cap=2),
        'm1.medium':
            dict(memory_mb=4096,
                 vcpus=2,
                 local_gb=40,
                 flavorid=3,
                 rxtx_cap=3),
        'm1.large': dict(memory_mb=8192,
                         vcpus=4,
                         local_gb=80,
                         flavorid=4,
                         rxtx_cap=4),
        'm1.xlarge':
            dict(memory_mb=16384,
                 vcpus=8,
                 local_gb=160,
                 flavorid=5,
                 rxtx_cap=5)}

    class FakeModel(object):
        """ Stubs out for model """
        def __init__(self, values):
            self.values = values

        def __getattr__(self, name):
            return self.values[name]

        def __getitem__(self, key):
            if key in self.values:
                return self.values[key]
            else:
                raise NotImplementedError()

    def fake_instance_type_get_all(context, inactive=0):
        return INSTANCE_TYPES

    def fake_instance_type_get_by_name(context, name):
        return INSTANCE_TYPES[name]

    def fake_instance_create(values):
        """ Stubs out the db.instance_create method """

        type_data = INSTANCE_TYPES[values['instance_type']]

        base_options = {
            'name': values['name'],
            'id': values['id'],
            'reservation_id': utils.generate_uid('r'),
            'image_id': values['image_id'],
            'kernel_id': values['kernel_id'],
            'ramdisk_id': values['ramdisk_id'],
            'state_description': 'scheduling',
            'user_id': values['user_id'],
            'project_id': values['project_id'],
            'launch_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'instance_type': values['instance_type'],
            'memory_mb': type_data['memory_mb'],
            'mac_address': values['mac_address'],
            'vcpus': type_data['vcpus'],
            'local_gb': type_data['local_gb'],
            'os_type': values['os_type']}

        return FakeModel(base_options)

    def fake_network_get_by_instance(context, instance_id):
        fields = {
            'bridge': 'xenbr0',
            }
        return FakeModel(fields)

    stubs.Set(db, 'instance_create', fake_instance_create)
    stubs.Set(db, 'network_get_by_instance', fake_network_get_by_instance)
    stubs.Set(db, 'instance_type_get_all', fake_instance_type_get_all)
    stubs.Set(db, 'instance_type_get_by_name', fake_instance_type_get_by_name)
