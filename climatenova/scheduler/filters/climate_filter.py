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

import six

from oslo.config import cfg

from nova import db
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging
from nova.scheduler import filters

LOG = logging.getLogger(__name__)

opts = [
    cfg.StrOpt('aggregate_freepool_name',
               default='freepool',
               help='Name of the special aggregate where all hosts '
                    'are candidate for physical host reservation'),
    cfg.StrOpt('tenant_id_key',
               default='climate:tenant',
               help='Aggregate metadata value for key matching tenant_id'),
    cfg.StrOpt('climate_owner',
               default='climate:owner',
               help='Aggregate metadata key for knowing owner tenant_id'),
    cfg.StrOpt('climate_az_prefix',
               default='climate:',
               help='Prefix for Availability Zones created by Climate'),
]

cfg.CONF.register_opts(opts, 'climate:physical:host')


class ClimateFilter(filters.BaseHostFilter):
    """Climate Filter for nova-scheduler."""

    run_filter_once_per_request = True

    def host_passes(self, host_state, filter_properties):
        """Check if a host in a pool can be used for a request

        A host is in a pool if it is a member of an aggregate that has
        a metadata item with a key value of "climate:owner"

        If the user does not pass "reservation=<id>" as a hint then only
        hosts which are not in a pool (including freepool) pass.

        If the user does pass "reservation=<id>" as a hint then the host only
        passes if it is a member of the specified pool and that pool
        has a metadata key of either :
            - "climate:owner=tenant_id (which grants automatically all the
                users from the tenant from which the request came from)
            - or, "tenant_id=climate:tenant" (which grants extra tenants for
                the reservation)
        """

        context = filter_properties['context'].elevated()

        # Find which Pools the user wants to use (if any)
        scheduler_hints = filter_properties.get('scheduler_hints') or {}
        requested_pools = scheduler_hints.get('reservation', [])
        if isinstance(requested_pools, six.text_type):
            requested_pools = [requested_pools]

        # Get any reservation pools this host is part of
        # Note this include possibly the freepool

        aggregates = db.aggregate_get_by_host(context, host_state.host)
        pools = []
        for agg in aggregates:
            if agg['availability_zone'].startswith(
                    cfg.CONF['climate:physical:host'].climate_az_prefix):
                pools.append(agg)
            if agg['name'] == (
                    cfg.CONF['climate:physical:host'].aggregate_freepool_name):
                pools.append(agg)

        if pools:
            if not requested_pools:
                # Host is in a Pool and none requested
                LOG.audit(_("In a user pool or in the freepool"))
                return False

            # Find aggregate which matches Pool
            for pool in pools:
                if pool['name'] in requested_pools:

                    # Check tenant is allowed to use this Pool

                    # NOTE(sbauza): Currently, the key is only the project_id,
                    #  but later will possibly be climate:tenant:{project_id}
                    key = context.project_id
                    access = pool['metadetails'].get(key)
                    if access:
                        return True
                    # NOTE(sbauza): We also need to check the climate:owner key
                    #  until we modify the reservation pool for including the
                    #  project_id key as for any other extra project
                    owner = cfg.CONF['climate:physical:host'].climate_owner
                    owner_project_id = pool['metadetails'].get(owner)
                    if owner_project_id == context.project_id:
                        return True
                    LOG.info(_("Unauthorized request to use Pool "
                               "%(pool_id)s by tenant %(tenant_id)s"),
                             {'pool_id': pool['name'],
                             'tenant_id': context.project_id})
                    return False

            # Host not in requested Pools
            return False

        else:

            if requested_pools:
                # Host is not in a Pool and Pool requested
                return False
            return True
