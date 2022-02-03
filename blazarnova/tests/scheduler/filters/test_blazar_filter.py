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

from blazarnova.scheduler.filters import blazar_filter
from nova import objects
from nova import test
from nova.tests.unit.scheduler import fakes
from nova.virt import fake
from oslo_config import cfg

FLAVOR_EXTRA_SPEC = "aggregate_instance_extra_specs:reservation"


class BlazarFilterTestCase(test.TestCase):
    """Filter test case.

    This test case provides tests for the schedule filters available
    on Blazar.
    """
    def setUp(self):
        super(BlazarFilterTestCase, self).setUp()

        # Let's have at hand a brand new blazar filter
        self.f = blazar_filter.BlazarFilter()

        # A fake host state
        self.host = fakes.FakeHostState('host1', 'node1', {})

        # A fake instance (which has a reservation id 'r-fakeres')
        fake.FakeInstance('instance1', 'Running', '123')

        # And a base spec_obj
        self.spec_obj = objects.RequestSpec(
            project_id='fakepj',
            scheduler_hints={},
            flavor=objects.Flavor(flavorid='flavor-id1', extra_specs={})
        )

    def test_blazar_filter_no_pool_available_requested(self):

        # Given the host doesn't belong to any pool
        self.host.aggregates = []

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_no_pool_available_not_requested(self):

        # Given the host doesn't belong to any pool
        self.host.aggregates = []

        # And the filter doesn't require any pool (using filter as in setup())

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall pass
        self.assertTrue(self.host.passes)

    def test_blazar_filter_host_in_freepool_and_none_requested(self):

        # Given the host is in the free pool (named "freepool")
        self.host.aggregates = [
            objects.Aggregate(
                name=cfg.CONF['blazar:physical:host'].aggregate_freepool_name,
                metadata={'availability_zone': 'unknown',
                          self.spec_obj.project_id: True})]

        # And the filter doesn't require any pool (using filter as in setup())

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_host_in_pool_none_requested(self):

        # Given the host belongs to the 'r-fakeres' reservation pool
        self.host.aggregates = [
            objects.Aggregate(
                name='r-fakeres',
                metadata={'availability_zone': (cfg
                                                .CONF['blazar:physical:host']
                                                .blazar_az_prefix) + 'XX',
                          self.spec_obj.project_id: True})]

        # And the filter doesn't require any pool (using filter as in setup())

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_host_in_another_pool(self):

        # Given the host belongs to a pool different to 'r-fakeres'
        self.host.aggregates = [
            objects.Aggregate(
                name='not_the_r-fakeres_pool',
                metadata={'availability_zone': 'unknown',
                          self.spec_obj.project_id: True})]

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_host_not_auth_in_current_tenant(self):

        # Given the host is NOT authorized in the current tenant
        # And thee pool name is NOT 'r-fakeres'
        self.host.aggregates = [
            objects.Aggregate(
                name='r-fackers',
                metadata={'availability_zone': 'unknown',
                          self.spec_obj.project_id: False})]

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_host_auth_in_current_tenant(self):

        # Given the host is authorized in the current tenant
        # And the pool name is 'r-fakeres'
        self.host.aggregates = [
            objects.Aggregate(
                name='r-fakeres',
                metadata={'availability_zone': (cfg
                                                .CONF['blazar:physical:host']
                                                .blazar_az_prefix),
                          self.spec_obj.project_id: True})]

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall pass
        self.assertTrue(self.host.passes)

    def test_blazar_filter_host_authorized_by_owner(self):
        # Given the host blazar owner is the current project id
        # And the pool name is 'r-fakeres'
        self.host.aggregates = [
            objects.Aggregate(
                name='r-fakeres',
                metadata={'availability_zone': (cfg
                                                .CONF['blazar:physical:host']
                                                .blazar_az_prefix),
                          cfg.CONF['blazar:physical:host'].blazar_owner: (
                              self.spec_obj.project_id),
                          self.spec_obj.project_id: False})]

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall pass
        self.assertTrue(self.host.passes)

    def test_blazar_filter_host_not_authorized_by_owner(self):

        # Given the host blazar owner is NOT the current project id
        # And the pool name is 'r-fakeres'
        self.host.aggregates = [
            objects.Aggregate(
                name='r-fakeres',
                metadata={'availability_zone': (cfg
                                                .CONF['blazar:physical:host']
                                                .blazar_az_prefix),
                          cfg.CONF['blazar:physical:host'].blazar_owner: (
                              'another_project_id')})]

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_host_not_in_requested_pools(self):

        # Given the host is in the free pool
        self.host.aggregates = [
            objects.Aggregate(
                name=cfg.CONF['blazar:physical:host'].aggregate_freepool_name,
                metadata={'availability_zone': 'unknown'})]

        # And the 'r-fakeres' pool is requested in the filter
        self.spec_obj.scheduler_hints = {'reservation': ['r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)

    def test_blazar_filter_unicode_requested_pool(self):

        # Given the host is in a pool with unicode characters
        self.host.aggregates = [
            objects.Aggregate(
                name=U'r-fakeres',
                metadata={'availability_zone': (cfg
                                                .CONF['blazar:physical:host']
                                                .blazar_az_prefix),
                          self.spec_obj.project_id: True})]

        # And the filter is requesting for a host with the same name (ucode)
        self.spec_obj.scheduler_hints = {'reservation': [U'r-fakeres']}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(
            self.host,
            self.spec_obj)

        # Then the host shall pass
        self.assertTrue(self.host.passes)

    def test_instance_reservation_requested(self):

        # A host is not in any aggregate
        self.host.aggregates = []

        # And instance-reservation-id1 is requested by an instance
        self.spec_obj.flavor.extra_specs = {
            FLAVOR_EXTRA_SPEC: 'instance-reservation-id1'}
        self.spec_obj.flavor.flavorid = 'instance-reservation-id1'

        self.host.passes = self.f.host_passes(self.host, self.spec_obj)

        self.assertTrue(self.host.passes)

    def test_blazar_filter_host_in_freepool_for_preemptibles(self):

        # Given preemptibles are allowed
        cfg.CONF.set_override('allow_preemptibles', True,
                              group='blazar:physical:host')
        self.addCleanup(cfg.CONF.clear_override, 'allow_preemptibles',
                        group='blazar:physical:host')

        # Given the host is in the free pool
        self.host.aggregates = [
            objects.Aggregate(
                name='freepool',
                metadata={'availability_zone': ''})]

        # And the instance is launched with a flavor marked as preemptible
        self.spec_obj.flavor.extra_specs = {'blazar:preemptible': 'true'}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(self.host, self.spec_obj)

        # Then the host shall pass
        self.assertTrue(self.host.passes)

    def test_blazar_filter_host_in_preemptibles(self):

        # Given preemptibles are allowed and dedicated aggregate is used
        cfg.CONF.set_override('allow_preemptibles', True,
                              group='blazar:physical:host')
        self.addCleanup(cfg.CONF.clear_override, 'allow_preemptibles',
                        group='blazar:physical:host')
        cfg.CONF.set_override('preemptible_aggregate', 'preemptibles',
                              group='blazar:physical:host')
        self.addCleanup(cfg.CONF.clear_override, 'preemptible_aggregate',
                        group='blazar:physical:host')

        # Given the host is in the preemptibles aggregate
        self.host.aggregates = [
            objects.Aggregate(
                name='preemptibles',
                metadata={'availability_zone': ''})]

        # And the instance is launched with a flavor marked as preemptible
        self.spec_obj.flavor.extra_specs = {'blazar:preemptible': 'true'}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(self.host, self.spec_obj)

        # Then the host shall pass
        self.assertTrue(self.host.passes)

    def test_blazar_filter_host_not_in_preemptibles(self):

        # Given preemptibles are allowed and dedicated aggregate is used
        cfg.CONF.set_override('allow_preemptibles', True,
                              group='blazar:physical:host')
        self.addCleanup(cfg.CONF.clear_override, 'allow_preemptibles',
                        group='blazar:physical:host')
        cfg.CONF.set_override('preemptible_aggregate', 'preemptibles',
                              group='blazar:physical:host')
        self.addCleanup(cfg.CONF.clear_override, 'preemptible_aggregate',
                        group='blazar:physical:host')

        # Given the host is in the free pool
        self.host.aggregates = [
            objects.Aggregate(
                name=cfg.CONF['blazar:physical:host'].aggregate_freepool_name,
                metadata={'availability_zone': 'unknown',
                          self.spec_obj.project_id: True})]

        # And the instance is launched with a flavor marked as preemptible
        self.spec_obj.flavor.extra_specs = {'blazar:preemptible': 'true'}

        # When the host goes through the filter
        self.host.passes = self.f.host_passes(self.host, self.spec_obj)

        # Then the host shall NOT pass
        self.assertFalse(self.host.passes)
