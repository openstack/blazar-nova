# Copyright (c) 2013 Bull.
#
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

from blazarnova.i18n import _

from nova.scheduler import filters
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils.strutils import bool_from_string

LOG = logging.getLogger(__name__)

FLAVOR_EXTRA_SPEC = "aggregate_instance_extra_specs:reservation"
FLAVOR_PREEMPTIBLE = "blazar:preemptible"

opts = [
    cfg.StrOpt('aggregate_freepool_name',
               default='freepool',
               help='Name of the special aggregate where all hosts '
                    'are candidate for physical host reservation'),
    cfg.BoolOpt('allow_preemptibles',
                default=False,
                help='Whether to allow preemptible instances to be scheduled '
                     'on hosts in the preemptible aggregate'),
    cfg.StrOpt('preemptible_aggregate',
               default='freepool',
               help='Name of the aggregate where hosts can run preemptible '
                    'instances'),
    cfg.StrOpt('project_id_key',
               default='blazar:tenant',
               help='Aggregate metadata value for key matching project_id'),
    cfg.StrOpt('blazar_owner',
               default='blazar:owner',
               help='Aggregate metadata key for knowing owner project_id'),
    cfg.StrOpt('blazar_az_prefix',
               default='blazar_',
               help='Prefix for Availability Zones created by Blazar')
]

cfg.CONF.register_opts(opts, 'blazar:physical:host')


class BlazarFilter(filters.BaseHostFilter):
    """Blazar Filter for nova-scheduler."""

    run_filter_once_per_request = True

    def fetch_blazar_pools(self, host_state):
        # Get any reservation pools this host is part of
        # Note this include possibly the freepool
        aggregates = host_state.aggregates
        pools = []
        for agg in aggregates:
            if (agg.availability_zone and
                    str(agg.availability_zone).startswith(
                        cfg.CONF['blazar:physical:host'].blazar_az_prefix)
                    # NOTE(hiro-kobayashi): following 2 lines are for keeping
                    # backward compatibility
                    or str(agg.availability_zone).startswith('blazar:')):
                pools.append(agg)

            if agg.name in [
                    cfg.CONF['blazar:physical:host'].aggregate_freepool_name,
                    cfg.CONF['blazar:physical:host'].preemptible_aggregate]:
                pools.append(agg)

        return pools

    def host_reservation_request(self, host_state, spec_obj, requested_pools):

        pools = self.fetch_blazar_pools(host_state)

        for pool in [p for p in pools if p.name in requested_pools]:
            # Check tenant is allowed to use this Pool

            # NOTE(sbauza): Currently, the key is only the project_id,
            #  but later will possibly be blazar:tenant:{project_id}
            key = spec_obj.project_id
            access = pool.metadata.get(key)
            if access:
                return True
            # NOTE(sbauza): We also need to check the blazar:owner key
            #  until we modify the reservation pool for including the
            #  project_id key as for any other extra project
            owner = cfg.CONF['blazar:physical:host'].blazar_owner
            owner_project_id = pool.metadata.get(owner)
            if owner_project_id == spec_obj.project_id:
                return True
            LOG.info(_("Unauthorized request to use Pool "
                       "%(pool_id)s by tenant %(tenant_id)s"),
                     {'pool_id': pool.name,
                      'tenant_id': spec_obj.project_id})
            return False
        return False

    def host_passes(self, host_state, spec_obj):
        """Check if a host in a pool can be used for a request

        A host is in a pool if it is a member of an aggregate that has
        a metadata item with a key value of "blazar:owner"

        If the user does not pass "reservation=<id>" as a hint then only
        hosts which are not in a pool (including freepool) pass.

        If the user does pass "reservation=<id>" as a hint then the host only
        passes if it is a member of the specified pool and that pool
        has a metadata key of either :
            - "blazar:owner=tenant_id (which grants automatically all the
                users from the tenant from which the request came from)
            - or, "tenant_id=blazar:tenant" (which grants extra tenants for
                the reservation)
        """

        # Find which Pools the user wants to use (if any)
        requested_pools = spec_obj.get_scheduler_hint('reservation')
        if isinstance(requested_pools, str):
            requested_pools = [requested_pools]

        # the request is host reservation
        if requested_pools:
            return self.host_reservation_request(host_state, spec_obj,
                                                 requested_pools)

        extra_specs = spec_obj.flavor.extra_specs
        # the request is instance reservation
        if FLAVOR_EXTRA_SPEC in extra_specs.keys():
            # Scheduling requests for instance reservation are processed by
            # other Nova filters: AggregateInstanceExtraSpecsFilter,
            # AggregateMultiTenancyIsolation, and
            # ServerGroupAntiAffinityFilter. What BlazarFilter needs to
            # do is just pass the host if the request has an instance
            # reservation key.
            return True

        allow_preempt = cfg.CONF['blazar:physical:host'].allow_preemptibles
        preemptible = bool_from_string(
            extra_specs.get(FLAVOR_PREEMPTIBLE, False))
        blazar_pools = self.fetch_blazar_pools(host_state)
        # If the request is for a preemptible instance and they are allowed
        if allow_preempt and preemptible:
            if (len(blazar_pools) == 1 and blazar_pools[0].name ==
                    cfg.CONF['blazar:physical:host'].preemptible_aggregate):
                # Pass host if it only belongs to the preemptibles aggregate
                LOG.info("Host %s allowed for preemptibles" % host_state)
                return True
            return False

        if blazar_pools:
            # Host is in a blazar pool and non reservation request
            LOG.info("Host is in a reservation aggregate or in the freepool")
            return False

        return True
