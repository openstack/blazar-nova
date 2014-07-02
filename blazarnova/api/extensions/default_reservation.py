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
Default reservation extension may be used if there is need to reserve all
VMs by default (like in the developer clouds: every VM may be not just booted,
but reserved for some amount of time, after which VM should be deleted or
suspended or whatever).
"""

import datetime
import json

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.openstack.common import log as logging
from nova import utils
from oslo.config import cfg
from webob import exc

reservation_opts = [
    cfg.StrOpt('reservation_start_date',
               default='now',
               help='Specify date for all leases to be started for every VM'),
    cfg.IntOpt('reservation_length_days',
               default=30,
               help='Number of days for VM to be reserved.'),
    cfg.IntOpt('reservation_length_hours',
               default=0,
               help='Number of hours for VM to be reserved.'),
    cfg.IntOpt('reservation_length_minutes',
               default=0,
               help='Number of minutes for VM to be reserved.')
]

CONF = cfg.CONF
CONF.register_opts(reservation_opts)

LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('compute', 'default_reservation')


class DefaultReservationController(wsgi.Controller):
    """Add default reservation flags to every VM started."""

    @wsgi.extends
    def create(self, req, body):
        """Add additional hints to the create server request.

        They will be managed by Reservation Extension.
        """

        if not self.is_valid_body(body, 'server'):
            raise exc.HTTPUnprocessableEntity()

        if 'server' in body:
            scheduler_hints = body['server'].get('scheduler_hints', {})
        elif 'os:scheduler_hints' in body:
            scheduler_hints = body['os:scheduler_hints']
        else:
            scheduler_hints = body.get('OS-SCH-HNT:scheduler_hints', {})

        lease_params = json.loads(scheduler_hints.get('lease_params', '{}'))

        delta_days = datetime.timedelta(days=CONF.reservation_length_days)
        delta_hours = datetime.timedelta(hours=CONF.reservation_length_hours)
        delta_minutes = datetime.timedelta(
            minutes=CONF.reservation_length_minutes
        )

        if CONF.reservation_start_date == 'now':
            base = datetime.datetime.utcnow()
        else:
            base = datetime.datetime.strptime(CONF.reservation_start_date,
                                              "%Y-%m-%d %H:%M")

        lease_params.setdefault('name', utils.generate_uid('lease', size=6))
        lease_params.setdefault('start', CONF.reservation_start_date)
        lease_params.setdefault(
            'end', (base + delta_days + delta_hours + delta_minutes).
            strftime('%Y-%m-%d %H:%M'))

        default_hints = {'lease_params': json.dumps(lease_params)}

        if 'server' in body:
            if 'scheduler_hints' in body['server']:
                body['server']['scheduler_hints'].update(default_hints)
            else:
                body['server']['scheduler_hints'] = default_hints
        else:
            attr = 'OS-SCH-HNT:scheduler_hints'
            if 'os:scheduler_hints' in body:
                body['os:scheduler_hints'].update(default_hints)
            elif attr in body and 'lease_params' not in body[attr]:
                body[attr].update(default_hints)
        yield


class Default_reservation(extensions.ExtensionDescriptor):
    """Instance reservation system."""

    name = "DefaultReservation"
    alias = "os-default-instance-reservation"

    def get_controller_extensions(self):
        controller = DefaultReservationController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]
