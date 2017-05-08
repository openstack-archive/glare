Glare Client Installation Guide
===============================

To install ``python-glareclient``, it is required to have ``pip``
(in most cases). Make sure that ``pip`` is installed. Then type::

    $ pip install python-glareclient

Or, if it is needed to install ``python-glareclient`` from master branch,
type::

    $ pip install git+https://github.com/openstack/python-glareclient.git

After ``python-glareclient`` is installed you will see command ``glare``
in your environment.

Glare client also provides a plugin ``openstack artifact`` to OpenStack client.
If glare client is supposed to be used with OpenStack cloud then additionally
``python-openstackclient`` has to be installed::

    $ pip install python-openstackclient


Configure authentication against Keystone
-----------------------------------------

If Keystone is used for authentication in Glare, then the interraction has to
be organized with openstackclient plugin ``openstack artifact`` and the
environment should have auth variables::

    $ export OS_AUTH_URL=http://<Keystone_host>:5000/v3
    $ export OS_TENANT_NAME=tenant
    $ export OS_USERNAME=admin
    $ export OS_PASSWORD=secret
    $ export OS_GLARE_URL=http://<Glare host>:9494  (optional, by default URL=http://localhost:9494/)

And in the case when you are authenticating against keystone over https::

    $ export OS_CACERT=<path_to_ca_cert>

.. note:: In client, we can use both Keystone auth versions - v2.0 and v3. But server supports only v3.

You can see the list of available commands by typing::

    $ openstack artifact --help

To make sure Glare client works, type::

    $ openstack artifact type-list

Configure authentication against Keycloak
-----------------------------------------

Glare also supports authentication against Keycloak server via OpenID Connect protocol.
In this case ``glare`` command must be used.
In order to use it on the client side the environment should look as follows::

    $ export KEYCLOAK_AUTH_URL=https://<Keycloak-server-host>:<Keycloak-server-port>/auth
    $ export KEYCLOAK_REALM_NAME=my_keycloak_realm
    $ export KEYCLOAK_USERNAME=admin
    $ export KEYCLOAK_PASSWORD=secret
    $ export OPENID_CLIENT_ID=my_keycloak_client
    $ export OS_GLARE_URL=http://<GLARE host>:9494  (optional, by default URL=http://localhost:9494)

.. note:: If KEYCLOAK_AUTH_URL is set then authentication against KeyCloak will be used

You can see the list of available commands by typing::

    $ glare --help

To make sure Glare client works, type::

    $ glare type-list

Send tokens directly without authentication
-------------------------------------------

Glare has a possibility to send tokens directly.
In order to use it on the client side the environment should look as follows::

    $ export OS_GLARE_URL=http://<GLARE host>:9494  (optional, by default URL=http://localhost:9494)
    $ export AUTH_TOKEN=secret_token

.. note:: It's more convenient to specify token as a command parameter in format ``--auth-token``,
   for example, ``glare --auth-token secret_token type-list``
