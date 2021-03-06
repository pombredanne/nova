# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
"""
Volume manager manages creating, attaching, detaching, and persistent storage.

Persistant storage volumes keep their state independent of instances.  You can
attach to an instance, terminate the instance, spawn a new instance (even
one from a different image) and re-attach the volume with the same data
intact.

**Related Flags**

:volume_topic:  What :mod:`rpc` topic to listen to (default: `volume`).
:volume_manager:  The module name of a class derived from
                  :class:`manager.Manager` (default:
                  :class:`nova.volume.manager.AOEManager`).
:storage_availability_zone:  Defaults to `nova`.
:volume_driver:  Used by :class:`AOEManager`.  Defaults to
                 :class:`nova.volume.driver.AOEDriver`.
:num_shelves:  Number of shelves for AoE (default: 100).
:num_blades:  Number of vblades per shelf to allocate AoE storage from
              (default: 16).
:volume_group:  Name of the group that will contain exported volumes (default:
                `nova-volumes`)
:aoe_eth_dev:  Device name the volumes will be exported on (default: `eth0`).
:num_shell_tries:  Number of times to attempt to run AoE commands (default: 3)

"""

import datetime


from nova import context
from nova import exception
from nova import flags
from nova import log as logging
from nova import manager
from nova import utils


LOG = logging.getLogger('nova.volume.manager')
FLAGS = flags.FLAGS
flags.DEFINE_string('storage_availability_zone',
                    'nova',
                    'availability zone of this service')
flags.DEFINE_string('volume_driver', 'nova.volume.driver.ISCSIDriver',
                    'Driver to use for volume creation')
flags.DEFINE_boolean('use_local_volumes', True,
                     'if True, will not discover local volumes')


class VolumeManager(manager.Manager):
    """Manages attachable block storage devices."""
    def __init__(self, volume_driver=None, *args, **kwargs):
        """Load the driver from the one specified in args, or from flags."""
        if not volume_driver:
            volume_driver = FLAGS.volume_driver
        self.driver = utils.import_object(volume_driver)
        super(VolumeManager, self).__init__(*args, **kwargs)
        # NOTE(vish): Implementation specific db handling is done
        #             by the driver.
        self.driver.db = self.db

    def init_host(self):
        """Do any initialization that needs to be run if this is a
           standalone service."""
        self.driver.check_for_setup_error()
        ctxt = context.get_admin_context()
        volumes = self.db.volume_get_all_by_host(ctxt, self.host)
        LOG.debug(_("Re-exporting %s volumes"), len(volumes))
        for volume in volumes:
            if volume['status'] in ['available', 'in-use']:
                self.driver.ensure_export(ctxt, volume)
            else:
                LOG.info(_("volume %s: skipping export"), volume['name'])

    def create_volume(self, context, volume_id):
        """Creates and exports the volume."""
        context = context.elevated()
        volume_ref = self.db.volume_get(context, volume_id)
        LOG.info(_("volume %s: creating"), volume_ref['name'])

        self.db.volume_update(context,
                              volume_id,
                              {'host': self.host})
        # NOTE(vish): so we don't have to get volume from db again
        #             before passing it to the driver.
        volume_ref['host'] = self.host

        try:
            vol_name = volume_ref['name']
            vol_size = volume_ref['size']
            LOG.debug(_("volume %(vol_name)s: creating lv of"
                    " size %(vol_size)sG") % locals())
            model_update = self.driver.create_volume(volume_ref)
            if model_update:
                self.db.volume_update(context, volume_ref['id'], model_update)

            LOG.debug(_("volume %s: creating export"), volume_ref['name'])
            model_update = self.driver.create_export(context, volume_ref)
            if model_update:
                self.db.volume_update(context, volume_ref['id'], model_update)
        except Exception:
            self.db.volume_update(context,
                                  volume_ref['id'], {'status': 'error'})
            raise

        now = datetime.datetime.utcnow()
        self.db.volume_update(context,
                              volume_ref['id'], {'status': 'available',
                                                 'launched_at': now})
        LOG.debug(_("volume %s: created successfully"), volume_ref['name'])
        return volume_id

    def delete_volume(self, context, volume_id):
        """Deletes and unexports volume."""
        context = context.elevated()
        volume_ref = self.db.volume_get(context, volume_id)
        if volume_ref['attach_status'] == "attached":
            raise exception.Error(_("Volume is still attached"))
        if volume_ref['host'] != self.host:
            raise exception.Error(_("Volume is not local to this node"))

        try:
            LOG.debug(_("volume %s: removing export"), volume_ref['name'])
            self.driver.remove_export(context, volume_ref)
            LOG.debug(_("volume %s: deleting"), volume_ref['name'])
            self.driver.delete_volume(volume_ref)
        except Exception:
            self.db.volume_update(context,
                                  volume_ref['id'],
                                  {'status': 'error_deleting'})
            raise

        self.db.volume_destroy(context, volume_id)
        LOG.debug(_("volume %s: deleted successfully"), volume_ref['name'])
        return True

    def setup_compute_volume(self, context, volume_id):
        """Setup remote volume on compute host.

        Returns path to device."""
        context = context.elevated()
        volume_ref = self.db.volume_get(context, volume_id)
        if volume_ref['host'] == self.host and FLAGS.use_local_volumes:
            path = self.driver.local_path(volume_ref)
        else:
            path = self.driver.discover_volume(context, volume_ref)
        return path

    def remove_compute_volume(self, context, volume_id):
        """Remove remote volume on compute host."""
        context = context.elevated()
        volume_ref = self.db.volume_get(context, volume_id)
        if volume_ref['host'] == self.host and FLAGS.use_local_volumes:
            return True
        else:
            self.driver.undiscover_volume(volume_ref)

    def check_for_export(self, context, instance_id):
        """Make sure whether volume is exported."""
        instance_ref = self.db.instance_get(context, instance_id)
        for volume in instance_ref['volumes']:
            self.driver.check_for_export(context, volume['id'])
