====================
Enabling in Devstack
====================

1. Download DevStack::

    git clone https://github.com/openstack-dev/devstack.git
    cd devstack

2. Add this repo as an external repository::

     > cat local.conf
     [[local|localrc]]
     enable_plugin glare https://github.com/openstack/glare

   .. note::
       To enable installation of glare client from git repo instead of pypi execute
       a shell command:

       .. code-block:: bash

         export LIBS_FROM_GIT+=python-glareclient

3. run ``stack.sh``
