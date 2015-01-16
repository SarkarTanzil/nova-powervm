# Copyright 2013 OpenStack Foundation
# Copyright 2015 IBM Corp.
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

import abc

from oslo.config import cfg
import six

from nova import image
from nova.i18n import _LI, _LE
from nova.openstack.common import log as logging
from pypowervm.jobs import upload_lv
from pypowervm.wrappers import constants as pvm_consts
from pypowervm.wrappers import virtual_io_server as pvm_vios
from pypowervm.wrappers import volume_group as vol_grp

from nova_powervm.virt.powervm import blockdev
from nova_powervm.virt.powervm import vios

localdisk_opts = [
    cfg.StrOpt('volume_group_name',
               default='',
               help='Volume Group to use for block device operations.')
]


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.register_opts(localdisk_opts)
IMAGE_API = image.API()


@six.add_metaclass(abc.ABCMeta)
class AbstractLocalStorageException(Exception):
    def __init__(self, **kwds):
        msg = self.msg_fmt % kwds
        super(AbstractLocalStorageException, self).__init__(msg)


class VGNotFound(AbstractLocalStorageException):
    msg_fmt = _LE('Unable to locate the volume group \'%(vg_name)s\''
                  ' for this operation.')


class IterableToFileAdapter(object):
    """A degenerate file-like so that an iterable could be read like a file.

    As Glance client returns an iterable, but PowerVM requires a file,
    this is the adapter between the two.

    Taken from xenapi/image/apis.py
    """

    def __init__(self, iterable):
        self.iterator = iterable.__iter__()
        self.remaining_data = ''

    def read(self, size):
        chunk = self.remaining_data
        try:
            while not chunk:
                chunk = self.iterator.next()
        except StopIteration:
            return ''
        return_value = chunk[0:size]
        self.remaining_data = chunk[size:]
        return return_value


class LocalStorage(blockdev.StorageAdapter):
    def __init__(self, connection):
        super(LocalStorage, self).__init__(connection)
        self.adapter = connection['adapter']
        self.host_uuid = connection['host_uuid']
        self.vios_name = connection['vios_name']
        self.vios_uuid = connection['vios_uuid']
        self.vg_name = CONF.volume_group_name
        self.vg_uuid = self._get_vg_uuid(self.adapter, self.vios_uuid,
                                         CONF.volume_group_name)
        LOG.info(_LI('Local Storage driver initialized: '
                     'volume group: \'%s\'') % self.vg_name)

    def delete_volume(self, context, volume_info):
        # TODO(IBM):
        pass

    def create_volume_from_image(self, context, instance, image):
        LOG.info(_LI('Create volume.'))

        # Transfer the image
        chunks = IMAGE_API.download(context, image['id'])
        stream = IterableToFileAdapter(chunks)
        vol_name = self._get_disk_name('boot', instance)
        upload_lv.upload_new_vdisk(self.adapter, self.vios_uuid, self.vg_uuid,
                                   stream, vol_name, image['size'])

        return {'device_name': vol_name}

    def connect_volume(self, context, instance, volume_info, **kwds):
        # TODO(IBM): We need the pvm uuid until it's the same as OpenStack
        pvm_uuids = kwds['pvm_uuids']
        lpar_uuid = pvm_uuids.lookup(instance.name)

        vol_name = volume_info['device_name']
        # Create the mapping structure
        scsi_map = pvm_vios.crt_scsi_map_to_vdisk(self.adapter, self.host_uuid,
                                                  lpar_uuid, vol_name)
        # Add the mapping to the VIOS
        vios.add_vscsi_mapping(self.adapter, self.vios_uuid, self.vios_name,
                               scsi_map)

    def _get_disk_name(self, type_, instance):
        return type_[:6] + '_' + instance.uuid[:8]

    def _get_vg_uuid(self, adapter, vios_uuid, name):
        try:
            resp = adapter.read(pvm_consts.VIOS,
                                root_id=vios_uuid,
                                child_type=pvm_consts.VOL_GROUP)
        except Exception as e:
            LOG.exception(e)
            raise e

        # Search the feed for the volume group
        for entry in resp.feed.entries:
            wrapper = vol_grp.VolumeGroup(entry)
            wrap_vg_name = wrapper.get_name()
            LOG.info(_LI('Volume group: %s') % wrap_vg_name)
            if name == wrap_vg_name:
                uuid = entry.properties['id']
                return uuid

        raise VGNotFound(vg_name=name)