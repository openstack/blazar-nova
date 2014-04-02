# Copyright (c) 2013 Julien Danjou <julien@danjou.info>
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

import mock

from climatenova.scheduler.filters import climate_filter
from nova import context
from nova.openstack.common import log as logging
from nova import test
from nova.tests.scheduler import fakes
from oslo.config import cfg

LOG = logging.getLogger(__name__)


class ClimateFilterTestCase(test.TestCase):
    """Filter test case.

    This test case provides tests for the schedule filters available
    on Climate.
    """
    def setUp(self):
        super(ClimateFilterTestCase, self).setUp()

        #Let's have at hand a brand new climate filter
        self.f = climate_filter.ClimateFilter()

        #A fake host state
        self.host = fakes.FakeHostState('host1', 'node1', {})

        #A fake context
        self.fake_context = context.RequestContext('fake', 'fake')

        #A fake instance (which has a reservation id 'r-fakeres')
        fakes.FakeInstance(self.fake_context)

        #And a base filter properties
        self.filter_properties = {
            "context": self.fake_context,
            "scheduler_hints": {}
        }

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_no_pool_available_requested(self, fake_nova_db):

        #Given the host doesn't belong to any pool
        fake_nova_db.aggregate_get_by_host.return_value = []

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_no_pool_available_not_requested(
            self,
            fake_nova_db):

        #Given the host doesn't belong to any pool
        fake_nova_db.aggregate_get_by_host.return_value = []

        #And the filter doesn't require any pool (using filter as in setup())

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall pass
        self.assertTrue(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_in_freepool_and_none_requested(
            self,
            fake_nova_db):

        #Given the host is in the free pool (named "freepool")
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name':
              cfg.CONF['climate:physical:host'].aggregate_freepool_name,
              'availability_zone': 'unknown',
              'metadetails': {self.fake_context.project_id: True}}]

        #And the filter doesn't require any pool (using filter as in setup())

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_in_pool_none_requested(self, fake_nova_db):

        #Given the host belongs to the 'r-fakeres' reservation pool
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': 'r-fakeres',
              'availability_zone':
              cfg.CONF['climate:physical:host'].climate_az_prefix + 'XX',
              'metadetails': {self.fake_context.project_id: True}}]

        #And the filter doesn't require any pool (using filter as in setup())

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_not_in_ant_pool(self, fake_nova_db):

        #Given the host belongs to a pool different to 'r-fakeres'
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': 'not_the_r-fackers_pool',
              'availability_zone': 'unknown',
              'metadetails': {self.fake_context.project_id: True}}]

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_not_auth_in_current_tenant(
            self,
            fake_nova_db):

        #Given the host is NOT authorized in the current tenant
        #And thee pool name is NOT 'r-fakeres'
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': 'r-fackers',
              'availability_zone': 'unknown',
              'metadetails': {self.fake_context.project_id: False}}]

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_auth_in_current_tenant(self, fake_nova_db):

        #Given the host is authorized in the current tenant
        #And thee pool name is 'r-fakeres'
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': 'r-fakeres',
              'availability_zone':
              cfg.CONF['climate:physical:host'].climate_az_prefix,
              'metadetails': {self.fake_context.project_id: True}}]

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall pass
        self.assertTrue(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_authorized_by_owner(self, fake_nova_db):

        #Given the host climate owner is the current project id
        #And thee pool name is 'r-fakeres'
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': 'r-fakeres',
              'availability_zone':
              cfg.CONF['climate:physical:host'].climate_az_prefix,
              'metadetails': {self.fake_context.project_id: False,
                              cfg.CONF['climate:physical:host'].
                              climate_owner: self.fake_context.project_id}}]

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall pass
        self.assertTrue(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_not_authorized_by_owner(self, fake_nova_db):

        #Given the host climate owner is NOT the current project id
        #And thee pool name is 'r-fakeres'
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': 'r-fakeres',
              'availability_zone':
              cfg.CONF['climate:physical:host'].climate_az_prefix,
              'metadetails': {self.fake_context.project_id: False,
                              cfg.CONF['climate:physical:host'].
                              climate_owner: 'another_project_id'}}]

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_host_not_in_requested_pools(self, fake_nova_db):

        #Given the host is in the free pool
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': cfg.CONF['climate:physical:host'].
                aggregate_freepool_name,
              'availability_zone': 'unknown'}]

        #And the 'r-fakeres' pool is requested in the filter
        self.filter_properties['scheduler_hints']['reservation'] = 'r-fakeres'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    @mock.patch('climatenova.scheduler.filters.climate_filter.db')
    def test_climate_filter_unicode_requested_pool(self, fake_nova_db):

        #Given the host is in a pool with unicode characters
        fake_nova_db.aggregate_get_by_host.return_value = \
            [{'name': U'r-fake~es',
              'availability_zone':
              cfg.CONF['climate:physical:host'].climate_az_prefix,
             'metadetails': {self.fake_context.project_id: True}}]

        #And the filter is requesting for a host with the same name (ucode)
        self.filter_properties['scheduler_hints']['reservation'] = U'r-fake~es'

        #When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.filter_properties)

        #Then the host shall pass
        self.assertTrue(self.host.passes)
