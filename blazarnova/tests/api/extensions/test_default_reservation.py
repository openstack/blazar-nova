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
from nova.openstack.common import jsonutils

from blazarnova.tests.api import extensions


class BlazarDefaultReservationTestCase(extensions.BaseExtensionTestCase):
    """Blazar API extensions test case.

    This test case provides tests for Default_reservation extension working
    together with Reservation extension passing hints to Nova and
    sending lease creation request to Blazar.
    """

    def setUp(self):
        """Set up testing environment."""
        super(BlazarDefaultReservationTestCase, self).setUp()

    @mock.patch('blazarnova.api.extensions.reservation.blazar_client')
    def test_create_with_default(self, mock_module):
        """Test extension work with default lease parameters."""

        mock_module.Client.return_value = self.mock_client

        # here we set no Blazar related hints, so all lease info should be
        # default one - dates got from CONF and auto generated name
        body = {
            'server': {
                'name': 'server_test',
                'imageRef': 'cedef40a-ed67-4d10-800e-17455edce175',
                'flavorRef': '1',
            }
        }

        self.req.body = jsonutils.dumps(body)
        res = self.req.get_response(self.app)

        mock_module.Client.assert_called_once_with(climate_url='fake',
                                                   auth_token='fake_token')
        self.lease_controller.create.assert_called_once_with(
            reservations=[
                {'resource_type': 'virtual:instance',
                 'resource_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'}],
            end=self.default_lease_end,
            events=[],
            start='now',
            name='lease_123')

        self.assertEqual(202, res.status_int)

    @mock.patch('blazarnova.api.extensions.reservation.blazar_client')
    def test_create_with_passed_args(self, mock_module):
        """Test extension work if some lease param would be passed."""
        # here we pass non default lease name to Nova
        # Default_reservation extension should not rewrite it,
        # Reservation extension should pass it to Blazar

        mock_module.Client.return_value = self.mock_client

        body = {
            'server': {
                'name': 'server_test',
                'imageRef': 'cedef40a-ed67-4d10-800e-17455edce175',
                'flavorRef': '1',
            },
            'os:scheduler_hints': {'lease_params': '{"name": "other_name"}'},
        }

        self.req.body = jsonutils.dumps(body)
        res = self.req.get_response(self.app)

        mock_module.Client.assert_called_once_with(climate_url='fake',
                                                   auth_token='fake_token')
        self.lease_controller.create.assert_called_once_with(
            reservations=[
                {'resource_type': 'virtual:instance',
                 'resource_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'}],
            end=self.default_lease_end,
            events=[],
            start='now',
            name='other_name')

        self.assertEqual(202, res.status_int)
