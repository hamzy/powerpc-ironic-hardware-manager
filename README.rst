Installation
============

Download diskimage-builder
--------------------------

ubuntu@hamzy-baby-utopic:~$ git clone git://git.openstack.org/openstack/diskimage-builder diskimage-builder.git.hm
ubuntu@hamzy-baby-utopic:~$ cd diskimage-builder.git.hm/
ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git checkout 1.17.0
...
HEAD is now at c621c5c... Merge "Release notes for 1.17.0"

Optionally, install patches for diskimage-builder
-------------------------------------------------

ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git config user.name "Mark Hamzy"; git config user.email hamzy@us.ibm.com
ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git fetch https://git.openstack.org/openstack/diskimage-builder refs/changes/32/333932/3 && git cherry-pick FETCH_HEAD
From https://git.openstack.org/openstack/diskimage-builder
 * branch            refs/changes/32/333932/3 -> FETCH_HEAD
[detached HEAD b8e8771] dmidecode does not exist for ppc64/ppc64el
 Date: Fri Jun 24 09:31:43 2016 -0500
 3 files changed, 29 insertions(+), 5 deletions(-)

Install Ironic Python Agent
---------------------------

ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ git clone https://git.openstack.org/openstack/ironic-python-agent
ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ (PWD=$(pwd); echo ${PWD}; sed -i -r -e 's,^([^ ]*) ([^ ]*) ([^ ]*) ([^ ]*)$,\1 \2 \3 '${PWD}/ironic-python-agent/',' ./elements/ironic-agent/source-repository-ironic-agent)
ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ cd ironic-python-agent/

Optionally, install patches for Ironic Python Agent
---------------------------------------------------

ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm/ironic-python-agent$ git config user.name "Mark Hamzy"; git config user.email hamzy@us.ibm.com
ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm/ironic-python-agent$ git fetch git://git.openstack.org/openstack/ironic-python-agent refs/changes/18/347518/1 && git cherry-pick FETCH_HEAD
From git://git.openstack.org/openstack/ironic-python-agent
 * branch            refs/changes/18/347518/1 -> FETCH_HEAD
[master bff8b61] Support use_insecure_erase_with_wipefs option
 Date: Tue Jul 26 13:43:57 2016 -0500
 1 file changed, 11 insertions(+), 1 deletion(-)

Add in the PowerPC Hardware Manager
-----------------------------------

First, add a source repository line to get the git project installed inside of the boot image.

ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ echo "ironic-agent git /usr/share/ipa-powerpc-hardware-manager /home/ubuntu/powerpc-hardware-manager" >> ./elements/ironic-agent/source-repository-ironic-agent

Then run the installation command. Note, you actually have to install it inside of the virtual python environment inside of the boot image.  Sigh.

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

ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ sudo pip install --upgrade --force-reinstall --requirement requirements.txt
ubuntu@hamzy-baby-utopic:~/diskimage-builder.git.hm$ sudo python setup.py install

Create the disk image
---------------------

ubuntu@hamzy-baby-utopic:~$ (disk-image-create -a ppc64el -u ubuntu ironic-agent dhcp-all-interfaces source-repositories -o ~/ci-images/ipa-hm-ppc64el 2>&1 | tee output.dib; sudo chown -R ubuntu:ubuntu ~/ci-images/ipa-hm-ppc64el*)
