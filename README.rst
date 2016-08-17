Installation
============

Download diskimage-builder
--------------------------

Download disk image builder into a directory and then check out a released version such as 1.17.0::

   ubuntu@hamzy-baby-utopic:~$ git clone git://git.openstack.org/openstack/diskimage-builder diskimage-builder.git.hm
   ubuntu@hamzy-baby-utopic:~$ cd diskimage-builder.git.hm/
   ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git checkout 1.17.0
   ...
   HEAD is now at c621c5c... Merge "Release notes for 1.17.0"

Optionally, install patches for diskimage-builder
-------------------------------------------------

If you want to checkout unapproved patches, you can do the following::

    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git config user.name "Mark Hamzy"; git config user.email hamzy@us.ibm.com
    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git fetch https://git.openstack.org/openstack/diskimage-builder refs/changes/32/333932/3 && git cherry-pick FETCH_HEAD
    From https://git.openstack.org/openstack/diskimage-builder
     * branch            refs/changes/32/333932/3 -> FETCH_HEAD
    [detached HEAD b8e8771] dmidecode does not exist for ppc64/ppc64el
     Date: Fri Jun 24 09:31:43 2016 -0500
     3 files changed, 29 insertions(+), 5 deletions(-)

Install Ironic Python Agent
---------------------------

You can work on a local copy of the Ironic python agent (IPA) by using the source-repository feature::

    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git clone https://git.openstack.org/openstack/ironic-python-agent
    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ (PWD=$(pwd); echo ${PWD}; sed -i -r -e 's,^([^ ]*) ([^ ]*) ([^ ]*) ([^ ]*)$,\1 \2 \3 '${PWD}/ironic-python-agent/',' ./elements/ironic-agent/source-repository-ironic-agent)
    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ cd ironic-python-agent/

Optionally, install patches for Ironic Python Agent
---------------------------------------------------

With a local copy, you can also apply unapproved patches by doing the following::

    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm/ironic-python-agent$ git config user.name "Mark Hamzy"; git config user.email hamzy@us.ibm.com
    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm/ironic-python-agent$ git fetch git://git.openstack.org/openstack/ironic-python-agent refs/changes/18/347518/1 && git cherry-pick FETCH_HEAD
    From git://git.openstack.org/openstack/ironic-python-agent
     * branch            refs/changes/18/347518/1 -> FETCH_HEAD
    [master bff8b61] Support use_insecure_erase_with_wipefs option
     Date: Tue Jul 26 13:43:57 2016 -0500
     1 file changed, 11 insertions(+), 1 deletion(-)

Add in the PowerPC Hardware Manager
-----------------------------------

After you have your local copy of IPA installed, you can then add another source repository line to get the git project installed inside of the boot image.::

    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ echo "ironic-agent git /usr/share/ipa-powerpc-hardware-manager /home/ubuntu/powerpc-hardware-manager" >> ./elements/ironic-agent/source-repository-ironic-agent

Then run the installation command. Note, you actually have to install it inside of the virtual python environment inside of the boot image.  Sigh.::

    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ vi ./elements/ironic-agent/install.d/ironic-agent-source-install/60-ironic-agent-install
    ...
    (
    # Fix: /usr/share/ironic-python-agent/venv/bin/activate: line 57: PS1: unbound variable
    export VIRTUAL_ENV_DISABLE_PROMPT=1
    source $IPADIR/venv/bin/activate
    cd /usr/share/ipa-powerpc-hardware-manager/
    python setup.py install
    )
    ...

Install diskimage-builder
-------------------------

After everything is setup and configured, you then install the DIB requirements and then install DIB to the system.::

    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ sudo pip install --upgrade --force-reinstall --requirement requirements.txt
    ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ sudo python setup.py install

Create the disk image
---------------------

Creating a IPA boot image is as follows::

    ubuntu@hamzy-baby-utopic:~$ (disk-image-create -a ppc64el -u ubuntu ironic-agent dhcp-all-interfaces source-repositories -o ~/ci-images/ipa-hm-ppc64el 2>&1 | tee output.dib; sudo chown -R ubuntu:ubuntu ~/ci-images/ipa-hm-ppc64el*)


Debugging
---------

If there is a syntax error, you will see it in the output of /opt/stack/logs/screen-ir-cond.log::

    2016-08-17 14:55:23.432 1949 ERROR stevedore.extension [-] Could not load 'powerpc_device': invalid syntax (powerpc_device.py, line 338)

However, it is easier to test your code for syntax errors in a virtual environment.  You can do this as follows::

    ubuntu@hamzy-baby-utopic:~$ (rm -rf test-stevedore/; mkdir test-stevedore; cd test-stevedore/; virtualenv --no-site-packages --distribute venv; source venv/bin/activate; pip install -U stevedore; pip install -U oslo.log; pip install -U ironic_python_agent; cd ~/powerpc-hardware-manager/; python setup.py install; python)
    >>> import logging
    >>> console = logging.StreamHandler()
    >>> console.setLevel(logging.DEBUG)
    >>> logging.getLogger('').addHandler(console)
    >>> from powerpc_hardware_manager import powerpc_device
    >>> obj = powerpc_device.PowerPCHardwareManager()
    >>> print obj.get_cpus()
    Failed to get CPU flags
    <ironic_python_agent.hardware.CPU object at 0x3fff8e790c50>
    >>> import stevedore
    >>> extension_manager = stevedore.ExtensionManager(namespace='ironic_python_agent.hardware_managers', invoke_on_load=True)
    >>> [ n.name for n in extension_manager.extensions ]
    ['powerpc_device', 'generic']
