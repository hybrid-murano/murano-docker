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


from novaclient.v2 import servers as nova_servers

import novaclient.client as compute
import cinderclient.client as volume
import ceilometerclient.client as metering
import neutronclient.client as network

@dsl.name('io.murano.system.Openstack')
class Openstack(object):
    def __init__(self, this):
        _owner = this.find_owner('io.murano.Environment')
        self.region = None if _owner is None else _owner['region']

    @staticmethod
    def _get_parameters(service_type, region):
        session = auth_utils.get_client_session(conf=CONF.heat)
        return auth_utils.get_session_client_parameters(service_type=service_type, region=region, conf=CONF.heat, session=session)

    @staticmethod
    @session_local_storage.execution_session_memoize
    def _compute(region):
        parameters = Openstack._get_parameters('compute', region)
        return compute.Client('2', **parameters)

    @staticmethod
    @session_local_storage.execution_session_memoize
    def _volume(region):
        parameters = Openstack._get_parameters('volume', region)
        return volume.Client('2', **parameters)

    @staticmethod
    @session_local_storage.execution_session_memoize
    def _network(region):
        parameters = Openstack._get_parameters('network', region)
        return network.Client('2', **parameters)

    @staticmethod
    @session_local_storage.execution_session_memoize
    def _metering(region):
        parameters = Openstack._get_parameters('metering', region)
        return metering.Client('2', **parameters)

    def statistic_list(self, meter_name, query=None, period=None):
        statistics = self._metering(self.region).statistics.list(meter_name=meter_name, q=query, period=period)
        return [Statistic(s) for s in statistics]

    def compute_service_enable(self, host, binary):
        return self._compute(self.region).services.enable(host, binary)

    def compute_service_disable(self, host, binary):
        return self._compute(self.region).services.disable(host, binary)

    def server_create(self, definition):
        return self._compute(self.region).servers.create(
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

    def server_delete(self, instance_id):
        self._compute(self.region).servers.delete(instance_id)

    def server_reboot(self, instance_id, soft_reboot=False):
        if soft_reboot:
            hardness = nova_servers.REBOOT_SOFT
        else:
            hardness = nova_servers.REBOOT_HARD
        self._compute(self.region).servers.reboot(instance_id, hardness)

    def server_show(self, instance_id):
        return self._compute(self.region).servers.get(instance_id).to_dict()

    def server_start(self, instance_id):
        server = self._compute(self.region).servers.get(instance_id)
        if getattr(server, "OS-EXT-STS:power_state", 0) != 1:
            self._compute(self.region).servers.start(instance_id)

    def server_stop(self, instance_id):
        server = self._compute(self.region).servers.get(instance_id)
        if getattr(server, "OS-EXT-STS:power_state", 0) != 4:
            self._compute(self.region).servers.stop(instance_id)

    def server_add_volume(self, instance_id, volume_id, device=None):
        self.c_wait_state(volume_id, lambda status: status == 'available')
        self._compute(self.region).volumes.create_server_volume(instance_id, volume_id, device)

    def server_remove_volume(self, volume_id):
        info = self._volume(self.region).volumes.get(volume_id)
        for attachment in info.attachments:
            self._compute(self.region).volumes.delete_server_volume(attachment.get('server_id', None), volume_id)

    def volume_show(self, volume_id):
        return self._volume(self.region).volumes.get(volume_id).to_dict()

    def volume_create(self, size, data):
        volume = self._volume(self.region).volumes.create(size, **data)
        return volume.to_dict()

    def volume_delete(self, volume_id):
        self._volume(self.region).volumes.delete(volume_id)

    def server_wait(self, instance_id, timeout=600):
        tries = 4
        delay = 1

        end = time.time() + timeout
        while tries > 0:
            while True:
                try:
                    info = self._compute(self.region).servers.get(instance_id)
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

                if time.time() >= end:
                    raise EnvironmentError("Unexpected compute timeout")

                if status in {'BUILD'}:
                    eventlet.sleep(5)
                    continue

                if status != 'ACTIVE':
                    raise EnvironmentError("Unexpected server state {0}".format(status))

                return
        return

    def volume_wait(self, volume_id, timeout=600):
        tries = 4
        delay = 1

        end = time.time() + timeout
        while tries > 0:
            while True:
                try:
                    status = self._volume(self.region).volumes.get(volume_id).status
                    tries = 4
                    delay = 1
                except Exception:
                    tries -= 1
                    delay *= 2
                    if not tries:
                        raise
                    eventlet.sleep(delay)
                    break

                if time.time() >= end:
                    raise EnvironmentError("Unexpected volume timeout")

                if status in {'creating', 'downloading'}:
                    eventlet.sleep(2)
                    continue

                if status != 'available':
                    raise EnvironmentError("Unexpected volume state {0}".format(status))

                return
        return
