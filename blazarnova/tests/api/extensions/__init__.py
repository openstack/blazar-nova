# Copyright (c) 2013 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime

import mock

from nova.api.openstack import compute
from nova.compute import api as compute_api
from nova import context
from nova import test
from nova.tests.unit.api.openstack import fakes
from nova import utils
from oslo_config import cfg


UUID = fakes.FAKE_UUID
CONF = cfg.CONF
CONF.import_opt('reservation_start_date',
                'blazarnova.api.extensions.default_reservation')
CONF.import_opt('reservation_length_hours',
                'blazarnova.api.extensions.default_reservation')
CONF.import_opt('reservation_length_days',
                'blazarnova.api.extensions.default_reservation')
CONF.import_opt('reservation_length_minutes',
                'blazarnova.api.extensions.default_reservation')


class InstanceWrapper(object):
    # this wrapper is needed to make dict look like object with fields and
    # dictionary at the same time

    def __init__(self, dct):
        self._dct = dct

    def __getattr__(self, item):
        return self._dct.get(item)

    __getitem__ = __getattr__


class BaseExtensionTestCase(test.TestCase):

    def setUp(self):
        """Set up testing environment."""
        super(BaseExtensionTestCase, self).setUp()
        self.fake_instance = fakes.stub_instance(1, uuid=UUID)

        self.lease_controller = mock.MagicMock()
        self.mock_client = mock.MagicMock()
        self.mock_client.lease = self.lease_controller

        self.req = fakes.HTTPRequestV21.blank('/fake/servers')
        self.req.method = 'POST'
        self.req.content_type = 'application/json'
        self.req.environ.update({
            'HTTP_X_SERVICE_CATALOG': '[{"type": "reservation", '
                                      '"endpoints": [{"publicURL": "fake"}]}]',
            'HTTP_X_ROLES': '12,34',
            'HTTP_X_AUTH_TOKEN': 'fake_token',
            'nova.context': context.RequestContext('fake', 'fake'),
        })

        self.l_name = 'lease_123'
        self.app = compute.APIRouterV21()
        self.stubs.Set(utils, 'generate_uid', lambda name, size: self.l_name)
        self.stubs.Set(compute_api.API, 'get', self._fake_get)
        self.stubs.Set(compute_api.API, 'shelve', self._fake_shelve)

        delta_days = datetime.timedelta(days=CONF.reservation_length_days)
        delta_hours = datetime.timedelta(hours=CONF.reservation_length_hours)
        delta_minutes = datetime.timedelta(
            minutes=CONF.reservation_length_minutes)
        self.delta = delta_days + delta_hours + delta_minutes
        lease_end = datetime.datetime.utcnow() + self.delta
        self.default_lease_end = lease_end.strftime('%Y-%m-%d %H:%M')
        self.default_lease_start = 'now'

    def _fake_get(self, *args, **kwargs):
        self.fake_instance['vm_state'] = 'active'
        return InstanceWrapper(self.fake_instance)

    def _fake_shelve(self, *args):
        self.fake_instance['vm_state'] = 'shelved_offloaded'
