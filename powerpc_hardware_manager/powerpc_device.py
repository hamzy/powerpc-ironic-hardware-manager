# Copyright 2016 International Business Machines
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import pyudev
import shlex
import netifaces

from oslo_log import log

from oslo_concurrency import processutils

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent import utils

from ironic_python_agent.hardware import BlockDevice
from ironic_python_agent.hardware import BootInfo
from ironic_python_agent.hardware import CPU
from ironic_python_agent.hardware import Memory
from ironic_python_agent.hardware import NetworkInterface
from ironic_python_agent.hardware import SystemVendorInfo

LOG = log.getLogger()

def _get_device_vendor(dev):
    """Get the vendor name of a given device."""
    try:
        devname = os.path.basename(dev)
        with open('/sys/class/block/%s/device/vendor' % devname, 'r') as f:
            return f.read().strip()
    except IOError:
        LOG.warning("Can't find the device vendor for device %s", dev)

def _udev_settle():
    """Wait for the udev event queue to settle.

    Wait for the udev event queue to settle to make sure all devices
    are detected once the machine boots up.

    """
    try:
        utils.execute('udevadm', 'settle')
    except processutils.ProcessExecutionError as e:
        LOG.warning('Something went wrong when waiting for udev '
                    'to settle. Error: %s', e)
        return

def list_all_block_devices(block_type='disk'):
    """List all physical block devices

    The switches we use for lsblk: P for KEY="value" output, b for size output
    in bytes, d to exclude dependent devices (like md or dm devices), i to
    ensure ascii characters only, and o to specify the fields/columns we need.

    Broken out as its own function to facilitate custom hardware managers that
    don't need to subclass GenericHardwareManager.

    :param block_type: Type of block device to find
    :return: A list of BlockDevices
    """
    _udev_settle()

    columns = ['KNAME', 'MODEL', 'SIZE', 'ROTA', 'TYPE']
    report = utils.execute('lsblk', '-Pbdi', '-o{}'.format(','.join(columns)),
                           check_exit_code=[0])[0]
    lines = report.split('\n')
    context = pyudev.Context()

    devices = []
    for line in lines:
        device = {}
        # Split into KEY=VAL pairs
        vals = shlex.split(line)
        for key, val in (v.split('=', 1) for v in vals):
            device[key] = val.strip()
        # Ignore block types not specified
        if device.get('TYPE') != block_type:
            LOG.debug(
                "TYPE did not match. Wanted: {!r} but found: {!r}".format(
                    block_type, line))
            continue

        # Ensure all required columns are at least present, even if blank
        missing = set(columns) - set(device)
        if missing:
            raise errors.BlockDeviceError(
                '%s must be returned by lsblk.' % ', '.join(sorted(missing)))

        name = '/dev/' + device['KNAME']
        try:
            udev = pyudev.Device.from_device_file(context, name)
        # pyudev started raising another error in 0.18
        except (ValueError, EnvironmentError, pyudev.DeviceNotFoundError) as e:
            LOG.warning("Device %(dev)s is inaccessible, skipping... "
                        "Error: %(error)s", {'dev': name, 'error': e})
            extra = {}
        else:
            # TODO(lucasagomes): Since lsblk only supports
            # returning the short serial we are using
            # ID_SERIAL_SHORT here to keep compatibility with the
            # bash deploy ramdisk
            extra = {key: udev.get('ID_%s' % udev_key) for key, udev_key in
                     [('wwn', 'WWN'), ('serial', 'SERIAL_SHORT'),
                      ('wwn_with_extension', 'WWN_WITH_EXTENSION'),
                      ('wwn_vendor_extension', 'WWN_VENDOR_EXTENSION')]}

        devices.append(BlockDevice(name=name,
                                   model=device['MODEL'],
                                   size=int(device['SIZE']),
                                   rotational=bool(int(device['ROTA'])),
                                   vendor=_get_device_vendor(device['KNAME']),
                                   **extra))
    return devices

class PowerPCHardwareManager(hardware.HardwareManager):
    """ """
    HARDWARE_MANAGER_NAME = "PowerPCHardwareManager"
    HARDWARE_MANAGER_VERSION = "1"
    SYSTEM_FIRMWARE_VERSION = "IBM-habanero-ibm-OP8_v1.7_1.62"
    SYSTEM_FIRMWARE_FILE = "/root/8348_810.1603.20160310b_update.hpm"

    def __init__(self):
        self.sys_path = '/sys'

    def evaluate_hardware_support(self):
        """Declare level of hardware support provided.
        Since this example covers a case of supporting a specific device,
        this method is where you would do anything needed to initalize that
        device, including loading drivers, and then detect if one exists.
        In some cases, if you expect the hardware to be available on any node
        running this hardware manager, or it's undetectable, you may want to
        return a static value here.
        Be aware all managers' loaded in IPA will run this method before IPA
        performs a lookup or begins heartbeating, so the time needed to
        execute this method will make cleaning and deploying slower.
        :returns: HardwareSupport level for this manager.
        """
        LOG.debug("PowerPCHardwareManager.evaluate_hardware_support:")

        return hardware.HardwareSupport.SERVICE_PROVIDER

    def list_hardware_info(self):
        """Return full hardware inventory as a serializable dict.

        This inventory is sent to Ironic on lookup and to Inspector on
        inspection.

        :return: a dictionary representing inventory
        """
        hardware_info = {}
        hardware_info['interfaces'] = self.list_network_interfaces()
        hardware_info['cpu'] = self.get_cpus()
        hardware_info['disks'] = self.list_block_devices()
        hardware_info['memory'] = self.get_memory()
        hardware_info['bmc_address'] = self.get_bmc_address()
        hardware_info['system_vendor'] = self.get_system_vendor_info()
        hardware_info['boot'] = self.get_boot_info()

        return hardware_info

    def list_network_interfaces(self):
        iface_names = os.listdir('{0}/class/net'.format(self.sys_path))
        iface_names = [name for name in iface_names if self._is_device(name)]

        return [self._get_interface_info(name) for name in iface_names]

    def get_cpus(self):
        func = "PowerPCHardwareManager.get_cpus"

        lines = utils.execute('lscpu')[0]
        cpu_info = {k.strip().lower(): v.strip() for k, v in
                    (line.split(':', 1)
                     for line in lines.split('\n')
                     if line.strip())}
        # Current CPU frequency can be different from maximum one on modern
        # processors
        frequency = cpu_info.get('cpu max mhz', cpu_info.get('cpu mhz'))

        flags = []
        out = utils.try_execute('grep', '-Em1', '^flags', '/proc/cpuinfo')
        if out:
            try:
                # Example output (much longer for a real system):
                # flags           : fpu vme de pse
                flags = out[0].strip().split(':', 1)[1].strip().split()
            except (IndexError, ValueError):
                LOG.warning('Malformed CPU flags information: %s', out)
        else:
            LOG.warning('Failed to get CPU flags')

        model_name = cpu_info.get('model name')
        count = int(cpu_info.get('cpu(s)'))
        architecture = cpu_info.get('architecture')

        LOG.debug("%s: model_name = %s", func, model_name)
        LOG.debug("%s: frequency = %s", func, frequency)
        LOG.debug("%s: count = %s", func, count)
        LOG.debug("%s: architecturecount = %s", func, architecture)
        LOG.debug("%s: flags = %s", func, flags)

        return CPU(model_name=model_name,
                   frequency=frequency,
                   # this includes hyperthreading cores
                   count=count,
                   architecture=architecture,
                   flags=flags)

    def list_block_devices(self):
        return list_all_block_devices()

    def get_memory(self):
        func = "PowerPCHardwareManager.get_memory"
        cmd = ("lshw -c memory -short -quiet 2>/dev/null"
               "|grep -i 'system memory'")

        try:
            out, _ = utils.execute(cmd, shell=True)

            physical_mb = 0

            for line in out.split('\n'):

                if len(line.strip ()) == 0:
                    continue

                try:
                    # /0/5                   memory     8165MiB System memory
                    # /0/1                 memory     255GiB System memory
                    (_, _, memory, _, _) = line.split()
                except ValueError:
                    LOG.debug("%s: \'%s\' bad line", func, line)
                    raise

                if memory.endswith('GiB'):
                     physical_mb += int(memory[0:-3])*1024
                elif memory.endswith('MiB'):
                     physical_mb += int(memory[0:-3])
                else:
                    LOG.warning("%s: %s bad memory", func, memory)
                    LOG.warning("%s: line = \'%s\'", func, line)

            LOG.debug("%s: physical_mb = %s", func, physical_mb)

            return Memory(total=physical_mb, physical_mb=physical_mb)
        except (processutils.ProcessExecutionError, OSError) as e:
            LOG.warning("%s: Cannot execute %s: %s", cmd, e)

        return None

    def get_bmc_address(self):
        # These modules are rarely loaded automatically
        utils.try_execute('modprobe', 'ipmi_msghandler')
        utils.try_execute('modprobe', 'ipmi_devintf')
        utils.try_execute('modprobe', 'ipmi_si')

        try:
            out, _ = utils.execute(
                "ipmitool lan print | grep -e 'IP Address [^S]' "
                "| awk '{ print $4 }'", shell=True)
        except (processutils.ProcessExecutionError, OSError) as e:
            # Not error, because it's normal in virtual environment
            LOG.warning("Cannot get BMC address: %s", e)
            return

        return out.strip()

    def get_system_vendor_info(self):
        func = "PowerPCHardwareManager.get_system_vendor_info"
        cmd = "lshw -quiet | egrep '^    (product|serial):'"
        product_name = None
        serial_number = None
        manufacturer = "IBM"
        try:
            out, _ = utils.execute(cmd, shell=True)
        except (processutils.ProcessExecutionError, OSError) as e:
            LOG.warning("Cannot get system vendor information: %s", e)
        else:
            for line in out.split('\n'):
                line_arr = line.split(':', 1)
                if len(line_arr) != 2:
                    continue
                if line_arr[0].strip() == 'product':
                    product_name = line_arr[1].strip()
                elif line_arr[0].strip() == 'serial':
                    serial_number = line_arr[1].strip()

        LOG.debug ("%s: product_name = %s", func, product_name)
        LOG.debug ("%s: serial_number = %s", func, serial_number)
        LOG.debug ("%s: manufacturer = %s", func, manufacturer)

        return SystemVendorInfo(product_name=product_name,
                                serial_number=serial_number,
                                manufacturer=manufacturer)

    def get_boot_info(self):
        func = "PowerPCHardwareManager.get_boot_info"

        boot_mode = 'uefi' if os.path.isdir('/sys/firmware/efi') else 'bios'
        LOG.debug("%s: The current boot mode is %s", func, boot_mode)

        pxe_interface = utils.get_agent_params().get('BOOTIF')

        return BootInfo(current_boot_mode=boot_mode,
                        pxe_interface=pxe_interface)

    def get_clean_steps(self, node, ports):
        """Get a list of clean steps with priority.
        Define any clean steps added by this manager here. These will be mixed
        with other loaded managers that support this hardware, and ordered by
        priority. Higher priority steps run earlier.
        Note that out-of-band clean steps may also be provided by Ironic.
        These will follow the same priority ordering even though they are not
        executed by IPA.
        There is *no guarantee whatsoever* that steps defined here will be
        executed by this HardwareManager. When it comes time to run these
        steps, they'll be called using dispatch_to_managers() just like any
        other IPA HardwareManager method. This means if they are unique to
        your hardware, they should be uniquely named. For example,
        upgrade_firmware would be a bad step name. Whereas
        upgrade_foobar_device_firmware would be better.
        :param node: The node object as provided by Ironic.
        :param ports: Port objects as provided by Ironic.
        :returns: A list of cleaning steps, as a list of dicts.
        """
        LOG.debug("PowerPCHardwareManager.get_clean_steps:")

        return [{
                 "step": "upgrade_powerpc_firmware",
                 "priority": 17,
                 # Should always be the deploy interface
                 "interface": "deploy",
                 # If you need Ironic to coordinate a reboot after this step
                 # runs, but before continuing cleaning, this should be true.
                 "reboot_requested": True,
                 # If it's safe for Ironic to abort cleaning while this step
                 # runs, this should be true.
                 "abortable": False
               }]

    def get_version(self):
        """Get a name and version for this hardware manager.

        In order to avoid errors and make agent upgrades painless, cleaning
        will check the version of all hardware managers during get_clean_steps
        at the beginning of cleaning and before executing each step in the
        agent.

        The agent isn't aware of the steps being taken before or after via
        out of band steps, so it can never know if a new step is safe to run.
        Therefore, we default to restarting the whole process.

        :returns: a dictionary with two keys: `name` and
            `version`, where `name` is a string identifying the hardware
            manager and `version` is an arbitrary version string.
        """
        LOG.debug("PowerPCHardwareManager.get_version:")

        return {
            'name': self.HARDWARE_MANAGER_NAME,
            'version': self.HARDWARE_MANAGER_VERSION
        }

    def get_ipv4_addr(self, interface_id):
        try:
            addrs = netifaces.ifaddresses(interface_id)
            return addrs[netifaces.AF_INET][0]['addr']
        except (ValueError, IndexError, KeyError):
            # No default IPv4 address found
            return None

    def _is_device(self, interface_name):
        device_path = '{0}/class/net/{1}/device'.format(self.sys_path,
                                                        interface_name)
        return os.path.exists(device_path)

    def _get_interface_info(self, interface_name):
        addr_path = '{0}/class/net/{1}/address'.format(self.sys_path,
                                                       interface_name)
        with open(addr_path) as addr_file:
            mac_addr = addr_file.read().strip()

        return NetworkInterface(
            interface_name,
            mac_addr,
            ipv4_address=self.get_ipv4_addr(interface_name),
            has_carrier=self._interface_has_carrier(interface_name),
            lldp=None)

    def _interface_has_carrier(self, interface_name):
        path = '{0}/class/net/{1}/carrier'.format(self.sys_path,
                                                  interface_name)
        try:
            with open(path, 'rt') as fp:
                return fp.read().strip() == '1'
        except EnvironmentError:
            LOG.debug('No carrier information for interface %s',
                      interface_name)
            return False

    def upgrade_powerpc_firmware (self, node, ports):
        """Upgrade firmware on a PowerPC computer"""
        # Any commands needed to perform the firmware upgrade should go here.
        # If you plan on actually flashing firmware every cleaning cycle, you
        # should ensure your device will not experience flash exhaustion. A
        # good practice in some environments would be to check the firmware
        # version against a constant in the code, and noop the method if an
        # upgrade is not needed.
        func = "PowerPCHardwareManager.upgrade_powerpc_firmware"
        LOG.debug("%s: node = %s", func, node)
        LOG.debug("%s: ports = %s", func, ports)

        if self._is_latest_firmware_ipmi(node, ports):
            LOG.debug('Latest firmware already flashed, skipping')
            # Return values are ignored here on success
            return True
        else:
            LOG.debug('Firmware version X found, upgrading to Y')
            # Perform firmware upgrade.
            try:
                self._upgrade_firmware_ipmi(node, ports)
            except Exception as e:
                # Log and pass through the exception so cleaning will fail
                LOG.exception(e)
                raise
        return True

    def _is_latest_firmware_ipmi(self, node, ports):
        """Detect if device is running latest firmware."""
        func = "PowerPCHardwareManager._is_latest_firmware_ipmi"
        ipmi_username = node["driver_info"]["ipmi_username"]
        ipmi_address = node["driver_info"]["ipmi_address"]
        ipmi_password = node["driver_info"]["ipmi_password"]

        version = None

        try:
            cmd = ("sudo ipmitool "
                   "-I lanplus "
                   "-H %s "
                   "-U %s "
                   "-P %s "
                   "fru") % (ipmi_address,
                             ipmi_username,
                             ipmi_password, )

            out, _ = utils.execute(cmd, shell=True)

            fInSection = False

            for line in out.split('\n'):

                if len(line.strip ()) == 0:
                    fInSection = False
                    continue

                if line.find("FRU Device Description : System Firmware") > -1:
                    LOG.debug("%s: Found System Firmware section", func)
                    fInSection = True
                    continue

                if not fInSection:
                    continue

                if line.find("Product Version") > -1:
                    version = line.split(':')[1].strip()

        except (processutils.ProcessExecutionError, OSError) as e:
            LOG.warning("%s: Cannot execute %s: %s", cmd, e)

        LOG.debug("%s: version = %s", func, version)

        if version is None:
            return False
        # http://stackoverflow.com/a/29247821/5839258
        elif version.upper().lower() == self.SYSTEM_FIRMWARE_VERSION.upper().lower():
            return True
        else:
            return False

    def _upgrade_firmware_ipmi(self, node, ports):
        """Upgrade firmware on device."""
        func = "PowerPCHardwareManager._upgrade_firmware_ipmi"

        try:
            cmd = ("sudo ipmitool "
                   "-I lanplus "
                   "-H %s "
                   "-U %s "
                   "-P %s "
                   "-z 30000 "
                   "hpm upgrade %s "
                   "force") % (ipmi_address,
                             ipmi_username,
                             ipmi_password,
                             self.SYSTEM_FIRMWARE_FILE)

            out, _ = utils.execute(cmd, shell=True)

            return True

        except (processutils.ProcessExecutionError, OSError) as e:
            LOG.warning("%s: Cannot execute %s: %s", cmd, e)

            return False

    def _MarkMark(self):
        # Ironic powers off the computer before the entire debug log has
        # been flushed out. Hack that here. :(
        LOG.debug("MARKMARK")
        import time
        time.sleep (30)
