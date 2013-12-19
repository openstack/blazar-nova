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

"""
Reservation extension parses instance creation request to find hints referring
to use Climate. If finds, create instance, shelve it not to use compute
capacity while instance is not used and sent lease creation request to Climate.
"""

import json
import time
import traceback

try:
    from climateclient import client as climate_client
except ImportError:
    climate_client = None

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import compute
from nova import exception
from nova.openstack.common.gettextutils import _  # noqa
from nova.openstack.common import log as logging


LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('compute', 'reservation')


class ReservationController(wsgi.Controller):
    """Reservation controller to support VMs wake up."""
    def __init__(self, *args, **kwargs):
        super(ReservationController, self).__init__(*args, **kwargs)
        self.compute_api = compute.API()

    @wsgi.extends
    def create(self, req, resp_obj, body):
        """Support Climate usage for Nova VMs."""

        scheduler_hints = body.get('server', {}).get('scheduler_hints', {})
        lease_params = scheduler_hints.get('lease_params')

        if lease_params:
            try:
                lease_params = json.loads(lease_params)
            except ValueError:
                raise ValueError(_('Wrong JSON format for lease parameters '
                                   'passed %s') % lease_params)

            if 'events' not in lease_params:
                lease_params.update({'events': []})

            instance_id = resp_obj.obj['server']['id']
            lease_params.update({
                'reservations': [{'resource_id': instance_id,
                                  'resource_type': 'virtual:instance'}],
            })

            service_catalog = json.loads(req.environ['HTTP_X_SERVICE_CATALOG'])
            user_roles = req.environ['HTTP_X_ROLES'].split(',')
            auth_token = req.environ['HTTP_X_AUTH_TOKEN']
            nova_ctx = req.environ["nova.context"]
            instance = self.compute_api.get(nova_ctx, instance_id,
                                            want_objects=True)

            lease_transaction = LeaseTransaction()

            with lease_transaction:
                while instance.vm_state != 'active':
                    if instance.vm_state == 'error':
                        raise exception.InstanceNotRunning(
                            _("Instance %s responded with error state") %
                            instance_id
                        )
                    instance = self.compute_api.get(nova_ctx, instance_id,
                                                    want_objects=True)
                    time.sleep(1)
                self.compute_api.shelve(nova_ctx, instance)

                # shelve instance
                while instance.vm_state != 'shelved_offloaded':
                    instance = self.compute_api.get(nova_ctx, instance_id,
                                                    want_objects=True)
                    time.sleep(1)

                # send lease creation request to Climate
                # this operation should be last, because otherwise Climate
                # Manager may try unshelve instance when it's still active
                climate_cl = self.get_climate_client(service_catalog,
                                                     user_roles, auth_token)
                lease_transaction.set_params(instance_id, climate_cl, nova_ctx)
                lease = climate_cl.lease.create(**lease_params)

                try:
                    lease_transaction.set_lease_id(lease['id'])
                except Exception:
                    raise exception.InternalError(
                        _('Lease creation request failed.')
                    )

    def get_climate_client(self, catalog, user_roles, auth_token):

        if not climate_client:
            raise ImportError(_('No Climate client installed to the '
                                'environment. Please install it to use '
                                'reservation for Nova instances.'))

        climate_endpoints = None
        for service in catalog:
            if service['type'] == 'reservation':
                climate_endpoints = service['endpoints'][0]
        if not climate_endpoints:
            raise exception.NotFound(_('No Climate endpoint found in service '
                                       'catalog.'))

        climate_url = None
        if 'admin' in user_roles:
            climate_url = climate_endpoints.get('adminURL')
        if climate_url is None:
            climate_url = climate_endpoints.get('publicURL')
        if climate_url is None:
            raise exception.NotFound(_('No Climate URL found in service '
                                       'catalog.'))

        climate_cl = climate_client.Client(climate_url=climate_url,
                                           auth_token=auth_token)
        return climate_cl


class LeaseTransaction(object):
    def __init__(self):
        self.lease_id = None
        self.instance_id = None
        self.climate_cl = None
        self.nova_ctx = None

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type and self.instance_id:
            msg = '\n'.join(traceback.format_exception(
                exc_type, exc_value, exc_traceback))
            LOG.error(_('Error occurred while lease creation. '
                        'Traceback: \n%s') % msg)
            if self.lease_id:
                self.climate_cl.lease.delete(self.lease_id)

            api = compute.API()
            api.delete(self.nova_ctx, api.get(self.nova_ctx, self.instance_id,
                                              want_objects=True))

    def set_lease_id(self, lease_id):
        self.lease_id = lease_id

    def set_params(self, instance_id, climate_cl, nova_ctx):
        self.instance_id = instance_id
        self.climate_cl = climate_cl
        self.nova_ctx = nova_ctx


class Reservation(extensions.ExtensionDescriptor):
    """Instance reservation system."""

    name = "Reservation"
    alias = "os-instance-reservation"

    def get_controller_extensions(self):
        controller = ReservationController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]
