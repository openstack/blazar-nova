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

import mock

from blazarnova.api.extensions import reservation
from blazarnova.tests.api import extensions
from nova.api.openstack import wsgi
from oslo_serialization import jsonutils


class BlazarReservationTestCase(extensions.BaseExtensionTestCase):
    """Blazar API extensions test case.

    This test case provides tests for Reservation extension working
    together with Reservation extension passing hints to Nova and
    sending lease creation request to Blazar.
    """

    def setUp(self):
        """Set up testing environment."""
        super(BlazarReservationTestCase, self).setUp()
        self.controller = reservation.ReservationController()

    @mock.patch('blazarnova.api.extensions.reservation.blazar_client')
    def test_create(self, mock_module):
        """Test extension work with passed lease parameters."""

        mock_module.Client.return_value = self.mock_client

        body = {
            'server': {
                'name': 'server_test',
                'imageRef': 'cedef40a-ed67-4d10-800e-17455edce175',
                'flavorRef': '1',
            },
            'os:scheduler_hints': {
                'lease_params': '{"name": "some_name", '
                                '"start": "2014-02-09 12:00", '
                                '"end": "2014-02-10 12:00"}'}
        }

        self.req.body = jsonutils.dumps(body)
        resp_obj = wsgi.ResponseObject({'server': {'id': 'fakeId'}})
        self.controller.create(self.req, resp_obj, body)

        mock_module.Client.assert_called_once_with(climate_url='fake',
                                                   auth_token='fake_token')

        self.lease_controller.create.assert_called_once_with(
            reservations=[
                {'resource_type': 'virtual:instance',
                 'resource_id': 'fakeId'}],
            end='2014-02-10 12:00',
            events=[],
            start='2014-02-09 12:00',
            name='some_name')
