import copy

import eventlet
from oslo_config import cfg
from oslo_log import log as logging
import six

from murano.common import auth_utils
from murano.common.i18n import _LW
from murano.common import utils
from murano.dsl import dsl
from murano.dsl import helpers
from murano.dsl import session_local_storage

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


import novaclient.client as n_client
from novaclient.v2 import servers as nova_servers

import cinderclient.client as c_client

@dsl.name('io.murano.system.Openstack')
class Openstack(object):
    def __init__(self, this):
        self._owner = this.find_owner('io.murano.Environment')

    @staticmethod
    def _create_client(session, region_name):
        parameters = auth_utils.get_session_client_parameters(
            service_type='compute', region=region_name,
            conf=CONF.heat, session=session)
        return n_client.Client('2', **parameters)

    @staticmethod
    def c_create_client(session, region_name):
        parameters = auth_utils.get_session_client_parameters(
            service_type='volume', region=region_name,
            conf=CONF.heat, session=session)
        return c_client.Client('2', **parameters)

    @property
    def _client(self):
        region = None if self._owner is None else self._owner['region']
        return self._get_client(region)

    @property
    def c_client(self):
        region = None if self._owner is None else self._owner['region']
        return self.c_get_client(region)

    @staticmethod
    @session_local_storage.execution_session_memoize
    def _get_client(region_name):
        session = auth_utils.get_client_session(conf=CONF.heat)
        return Openstack._create_client(session, region_name)

    @staticmethod
    @session_local_storage.execution_session_memoize
    def c_get_client(region_name):
        session = auth_utils.get_client_session(conf=CONF.heat)
        return Openstack._create_client(session, region_name)

    def _get_token_client(self):
        ks_session = auth_utils.get_token_client_session(conf=CONF.heat)
        region = None if self._owner is None else self._owner['region']
        return self._create_client(ks_session, region)

    def c_get_token_client(self):
        ks_session = auth_utils.get_token_client_session(conf=CONF.heat)
        region = None if self._owner is None else self._owner['region']
        return self.c_create_client(ks_session, region)

    def service_enable(self, host, binary):
        return self._client.services.enable(host, binary)

    def create(self, definition):
        return self._client.servers.create(
            definition['name'],
            definition['image'],
            definition['flavor'],
            key_name=definition['key_name'],
            userdata=definition.get('userdata', None),
            security_groups=definition.get('security_groups', None),
            availability_zone=definition.get('availability_zone', None),
            block_device_mapping=definition.get('block_device_mapping', None),
            block_device_mapping_v2=definition.get('block_device_mapping_v2', None),
            nics=definition.get('nics', None),
            min_count=definition.get('instance_count', 1),
            admin_pass=definition.get('admin_pass', None),
            disk_config=definition.get('disk_config', None),
            config_drive=definition.get('config_drive', None),
            meta=definition.get('meta', None)).to_dict()

    def delete(self, instance_id):
        self._client.servers.delete(instance_id)

    def reboot(self, instance_id, soft_reboot=False):
        if soft_reboot:
            hardness = nova_servers.REBOOT_SOFT
        else:
            hardness = nova_servers.REBOOT_HARD
        self._client.servers.reboot(instance_id, hardness)

    def get(self, instance_id):
        return self._client.servers.get(instance_id).to_dict()

    def wait(self, instance_id):
        self.n_wait_state(instance_id, lambda status: status == 'ACTIVE')

    def start(self, instance_id):
        server = self._client.servers.get(instance_id)
        if getattr(server, "OS-EXT-STS:power_state", 0) != 1:
            self._client.servers.start(instance_id)

    def stop(self, instance_id):
        server = self._client.servers.get(instance_id)
        if getattr(server, "OS-EXT-STS:power_state", 0) != 4:
            self._client.servers.stop(instance_id)

    def attach(self, instance_id, volume_id, device=None):
        self.c_wait_state(volume_id, lambda status: status == 'available')
        self._client.volumes.create_server_volume(instance_id, volume_id, device)

    def detach(self, volume_id):
        info = self.c_client.volumes.get(volume_id)
        for attachment in info.attachments:
            self._client.volumes.delete_server_volume(attachment.get('server_id', None), volume_id)

    def volume_get(self, volume_id):
        return self.c_client.volumes.get(volume_id).to_dict()

    def volume_create(self, size, data):
        volume = self.c_client.volumes.create(size, **data)
        return volume.to_dict()

    def volume_delete(self, volume_id):
        self.c_client.volumes.delete(volume_id)

    def volume_wait(self, volume_id):
        self.c_wait_state(volume_id, lambda status: status == 'available')

    def n_wait_state(self, instance_id, status_func):
        tries = 4
        delay = 1

        while tries > 0:
            while True:
                try:
                    info = self._client.servers.get(instance_id)
                    status = info.status
                    tries = 4
                    delay = 1
                except Exception:
                    tries -= 1
                    delay *= 2
                    if not tries:
                        raise
                    eventlet.sleep(delay)
                    break

                if 'BUILD' in status:
                    eventlet.sleep(5)
                    continue

                if not status_func(status):
                    raise EnvironmentError("Unexpected server state {0}".format(status))

                return
        return

    def c_wait_state(self, volume_id, status_func):
        tries = 4
        delay = 1

        while tries > 0:
            while True:
                try:
                    info = self.c_client.volumes.get(volume_id)
                    status = info.status
                    tries = 4
                    delay = 1
                except Exception:
                    tries -= 1
                    delay *= 2
                    if not tries:
                        raise
                    eventlet.sleep(delay)
                    break

                if 'creating' in status:
                    eventlet.sleep(2)
                    continue

                if 'downloading' in status:
                    eventlet.sleep(2)
                    continue

                if not status_func(status):
                    raise EnvironmentError("Unexpected volume state {0}".format(status))

                return
        return
