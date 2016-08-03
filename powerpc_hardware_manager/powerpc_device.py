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

from oslo_log import log

from ironic_python_agent import hardware
from ironic_python_agent import utils

from ironic_python_agent.hardware import Memory

LOG = log.getLogger()

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

    def get_memory(self):
        try:
            out, _ = utils.execute("lshw -c memory -short -quiet 2>/dev/null | grep -i 'system memory'",
                                   shell=True)

            lines = out.split('\n')

            # We only expect one line back!
            if len(lines) != 1:
                LOG.warning("PowerPCHardwareManager.get_memory: lines = \'%s\'", lines)
                return None

            # /0/5                           memory     8165MiB System memory
            # /0/1                         memory     255GiB System memory
            (_, _, memory, _, _) = lines[0].split()

            if memory.endswith('GiB'):
                 physical_mb = int(memory[0:-3])*1024
            elif memory.endswith('MiB'):
                 physical_mb = int(memory[0:-3])
            else:
                physical_mb = 0
                LOG.warning("PowerPCHardwareManager.get_memory: %s bad memory", memory)
                LOG.warning("PowerPCHardwareManager.get_memory: lines = \'%s\'", lines)

            if physical_mb > 0:
                LOG.debug("PowerPCHardwareManager.get_memory: physical_mb = ", physical_mb)

                return hardware.Memory(total=physical_mb, physical_mb=physical_mb)
        except (processutils.ProcessExecutionError, OSError) as e:
            LOG.warning("Cannot execute lshw -c momeory -short -quiet: %s", e)

        return None

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
