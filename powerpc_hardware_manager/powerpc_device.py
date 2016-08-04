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

from oslo_log import log

from oslo_concurrency import processutils

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent import utils

from ironic_python_agent.hardware import BlockDevice
from ironic_python_agent.hardware import BootInfo
from ironic_python_agent.hardware import CPU
from ironic_python_agent.hardware import Memory
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
#       hardware_info['interfaces'] = self.list_network_interfaces()
        hardware_info['cpu'] = self.get_cpus()
        hardware_info['disks'] = self.list_block_devices()
        hardware_info['memory'] = self.get_memory()
        hardware_info['bmc_address'] = self.get_bmc_address()
        hardware_info['system_vendor'] = self.get_system_vendor_info()
        hardware_info['boot'] = self.get_boot_info()
        return hardware_info

    def get_cpus(self):
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

        LOG.debug("PowerPCHardwareManager.get_cpus: model_name = %s", model_name)
        LOG.debug("PowerPCHardwareManager.get_cpus: frequency = %s", frequency)
        LOG.debug("PowerPCHardwareManager.get_cpus: count = %s", count)
        LOG.debug("PowerPCHardwareManager.get_cpus: architecturecount = %s", architecture)
        LOG.debug("PowerPCHardwareManager.get_cpus: flags = %s", flags)

        return CPU(model_name=model_name,
                   frequency=frequency,
                   # this includes hyperthreading cores
                   count=count,
                   architecture=architecture,
                   flags=flags)

    def list_block_devices(self):
        return list_all_block_devices()

    def get_memory(self):
        try:
            out, _ = utils.execute("lshw -c memory -short -quiet 2>/dev/null"
                                   "|grep -i 'system memory'",
                                   shell=True)

            physical_mb = 0

            for line in out.split('\n'):

                if len(line.strip ()) == 0:
                    continue

                try:
                    # /0/5                           memory     8165MiB System memory
                    # /0/1                         memory     255GiB System memory
                    (_, _, memory, _, _) = line[0].split()
                except ValueError:
                    LOG.debug("PowerPCHardwareManager.get_memory: \'%s\' bad line",
                              line)
                    raise

                if memory.endswith('GiB'):
                     physical_mb += int(memory[0:-3])*1024
                elif memory.endswith('MiB'):
                     physical_mb += int(memory[0:-3])
                else:
                    LOG.warning("PowerPCHardwareManager.get_memory: %s bad memory",
                                memory)
                    LOG.warning("PowerPCHardwareManager.get_memory: line = \'%s\'",
                                line)

            LOG.debug("PowerPCHardwareManager.get_memory: physical_mb = %s",
                      physical_mb)

            return Memory(total=physical_mb, physical_mb=physical_mb)
        except (processutils.ProcessExecutionError, OSError) as e:
            LOG.warning("Cannot execute lshw -c momeory -short -quiet: %s", e)

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
        product_name = None
        serial_number = None
        manufacturer = "IBM"
        try:
            out, _ = utils.execute("lshw -quiet | egrep '^    (product|serial):'",
                                   shell=True)
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

        LOG.debug ("PowerPCHardwareManager.get_system_vendor_info: product_name = %s", product_name)
        LOG.debug ("PowerPCHardwareManager.get_system_vendor_info: serial_number = %s", serial_number)
        LOG.debug ("PowerPCHardwareManager.get_system_vendor_info: manufacturer = %s", manufacturer)

        return SystemVendorInfo(product_name=product_name,
                                serial_number=serial_number,
                                manufacturer=manufacturer)

    def get_boot_info(self):
        boot_mode = 'uefi' if os.path.isdir('/sys/firmware/efi') else 'bios'
        LOG.debug("PowerPCHardwareManager.get_boot_info: The current boot mode is %s", boot_mode)
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

        return []

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
