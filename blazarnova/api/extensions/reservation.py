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
to use Blazar. If finds, create instance, shelve it not to use compute
capacity while instance is not used and sent lease creation request to Blazar.
"""

import json
import time
import traceback

try:
    from climateclient import client as blazar_client
except ImportError:
    blazar_client = None

from blazarnova.i18n import _  # noqa

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import compute
from nova import exception
from oslo_log import log as logging


LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('compute', 'reservation')


class ReservationController(wsgi.Controller):
    """Reservation controller to support VMs wake up."""
    def __init__(self, *args, **kwargs):
        super(ReservationController, self).__init__(*args, **kwargs)
        self.compute_api = compute.API()

    @wsgi.extends
    def create(self, req, resp_obj, body):
        """Support Blazar usage for Nova VMs."""

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

                # send lease creation request to Blazar
                # this operation should be last, because otherwise Blazar
                # Manager may try unshelve instance when it's still active
                blazar_cl = self.get_blazar_client(service_catalog,
                                                   user_roles, auth_token)
                lease_transaction.set_params(instance_id, blazar_cl, nova_ctx)
                lease = blazar_cl.lease.create(**lease_params)

                try:
                    lease_transaction.set_lease_id(lease['id'])
                except Exception:
                    raise exception.InternalError(
                        _('Lease creation request failed.')
                    )

    def get_blazar_client(self, catalog, user_roles, auth_token):
        if not blazar_client:
            raise ImportError(_('No Blazar client installed to the '
                                'environment. Please install it to use '
                                'reservation for Nova instances.'))

        blazar_endpoints = None
        for service in catalog:
            if service['type'] == 'reservation':
                blazar_endpoints = service['endpoints'][0]
        if not blazar_endpoints:
            raise exception.NotFound(_('No Blazar endpoint found in service '
                                       'catalog.'))

        blazar_url = None
        if 'admin' in user_roles:
            blazar_url = blazar_endpoints.get('adminURL')
        if blazar_url is None:
            blazar_url = blazar_endpoints.get('publicURL')
        if blazar_url is None:
            raise exception.NotFound(_('No Blazar URL found in service '
                                       'catalog.'))

        blazar_cl = blazar_client.Client(climate_url=blazar_url,
                                         auth_token=auth_token)
        return blazar_cl


class LeaseTransaction(object):
    def __init__(self):
        self.lease_id = None
        self.instance_id = None
        self.blazar_cl = None
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
                self.blazar_cl.lease.delete(self.lease_id)

            api = compute.API()
            api.delete(self.nova_ctx, api.get(self.nova_ctx, self.instance_id,
                                              want_objects=True))

    def set_lease_id(self, lease_id):
        self.lease_id = lease_id

    def set_params(self, instance_id, blazar_cl, nova_ctx):
        self.instance_id = instance_id
        self.blazar_cl = blazar_cl
        self.nova_ctx = nova_ctx


class Reservation(extensions.ExtensionDescriptor):
    """Instance reservation system."""

    name = "Reservation"
    alias = "os-instance-reservation"
    updated = "2015-09-29T00:00:00Z"
    namespace = "blazarnova"

    def get_controller_extensions(self):
        controller = ReservationController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]
