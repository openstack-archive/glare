#!/usr/bin/env bash
# Plugin file for Glare services
# -------------------------------

# Dependencies:
# ``functions`` file
# ``DEST``, ``DATA_DIR``, ``STACK_USER`` must be defined

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set -o xtrace

echo_summary "glare's plugin.sh was called..."
# create_glare_accounts() - Set up common required glare accounts
#
# Tenant      User       Roles
# ------------------------------
# service     glare     admin
function create_glare_accounts() {
    create_service_user "glare"

    # required for swift access
    if is_service_enabled s-proxy; then
        create_service_user "glare-swift" "ResellerAdmin"
    fi

    get_or_create_service "glare" "artifact" "Artifact repository"
    get_or_create_endpoint "artifact" \
        "$REGION_NAME" \
        "$GLARE_SERVICE_PROTOCOL://$GLARE_SERVICE_HOST:$GLARE_SERVICE_PORT" \
        "$GLARE_SERVICE_PROTOCOL://$GLARE_SERVICE_HOST:$GLARE_SERVICE_PORT" \
        "$GLARE_SERVICE_PROTOCOL://$GLARE_SERVICE_HOST:$GLARE_SERVICE_PORT"
}


function mkdir_chown_stack {
    if [[ ! -d "$1" ]]; then
        sudo mkdir -p "$1"
    fi
    sudo chown $STACK_USER "$1"
}


function configure_glare {

    # create and clean up auth cache dir
    mkdir_chown_stack "$GLARE_AUTH_CACHE_DIR"
    rm -f "$GLARE_AUTH_CACHE_DIR"/*

    mkdir_chown_stack "$GLARE_CONF_DIR"

    # Generate Glare configuration file and configure common parameters.
    oslo-config-generator --config-file $GLARE_DIR/etc/oslo-config-generator/glare.conf --output-file $GLARE_CONF_FILE

    # Glare Configuration
    #-------------------------

    iniset $GLARE_CONF_FILE DEFAULT debug $GLARE_DEBUG

    # Specify additional modules with external artifact types
    if [ -n "$GLARE_CUSTOM_MODULES" ]; then
        iniset $GLARE_CONF_FILE DEFAULT custom_artifact_types_modules $GLARE_CUSTOM_MODULES
    fi

    # Specify a list of enabled artifact types
    if [ -n "$GLARE_ENABLED_TYPES" ]; then
        iniset $GLARE_CONF_FILE DEFAULT enabled_artifact_types $GLARE_ENABLED_TYPES
    fi

    oslopolicy-sample-generator --namespace=glare --output-file=$GLARE_POLICY_FILE
    sed -i 's/^#"//' $GLARE_POLICY_FILE

    cp -p $GLARE_DIR/etc/glare-paste.ini $GLARE_CONF_DIR

    iniset $GLARE_CONF_FILE paste_deploy flavor $GLARE_FLAVOR

    # Setup keystone_authtoken section
    configure_auth_token_middleware $GLARE_CONF_FILE glare $GLARE_AUTH_CACHE_DIR

    # Setup RabbitMQ credentials
    iniset $GLARE_CONF_FILE oslo_messaging_rabbit rabbit_userid $RABBIT_USERID
    iniset $GLARE_CONF_FILE oslo_messaging_rabbit rabbit_password $RABBIT_PASSWORD

    # Enable notifications support
    iniset $GLARE_CONF_FILE oslo_messaging_notifications driver messaging

    # Configure the database.
    iniset $GLARE_CONF_FILE database connection `database_connection_url glare`
    iniset $GLARE_CONF_FILE database max_overflow -1
    iniset $GLARE_CONF_FILE database max_pool_size 1000

    # Path of policy.yaml file.
    iniset $GLARE_CONF_FILE oslo_policy policy_file $GLARE_POLICY_FILE

    if [ "$LOG_COLOR" == "True" ] && [ "$SYSLOG" == "False" ]; then
        setup_colorized_logging $GLARE_CONF_FILE DEFAULT tenant user
    fi

    if [ "$GLARE_RPC_IMPLEMENTATION" ]; then
        iniset $GLARE_CONF_FILE DEFAULT rpc_implementation $GLARE_RPC_IMPLEMENTATION
    fi

    # Configuring storage
    iniset $GLARE_CONF_FILE glance_store filesystem_store_datadir $GLARE_ARTIFACTS_DIR

    # Store the artifacts in swift if enabled.
    if is_service_enabled s-proxy; then
        GLARE_SWIFT_STORE_CONF=$GLARE_CONF_DIR/glare-swift-store.conf
        cp -p $GLARE_DIR/etc/glare-swift.conf.sample $GLARE_CONF_DIR

        iniset $GLARE_CONF_FILE glance_store default_store swift
        iniset $GLARE_CONF_FILE glance_store swift_store_create_container_on_put True

        iniset $GLARE_CONF_FILE glance_store swift_store_config_file $GLARE_SWIFT_STORE_CONF
        iniset $GLARE_CONF_FILE glance_store default_swift_reference ref1
        iniset $GLARE_CONF_FILE glance_store stores "file, http, swift"

        iniset $GLARE_SWIFT_STORE_CONF ref1 user $SERVICE_PROJECT_NAME:glare-swift

        iniset $GLARE_SWIFT_STORE_CONF ref1 key $SERVICE_PASSWORD
        iniset $GLARE_SWIFT_STORE_CONF ref1 auth_address $KEYSTONE_SERVICE_URI/v3
        iniset $GLARE_SWIFT_STORE_CONF ref1 user_domain_name $SERVICE_DOMAIN_NAME
        iniset $GLARE_SWIFT_STORE_CONF ref1 project_domain_name $SERVICE_DOMAIN_NAME
        iniset $GLARE_SWIFT_STORE_CONF ref1 auth_version 3

        # commenting is not strictly necessary but it's confusing to have bad values in conf
        inicomment $GLARE_CONF_FILE glance_store swift_store_user
        inicomment $GLARE_CONF_FILE glance_store swift_store_key
        inicomment $GLARE_CONF_FILE glance_store swift_store_auth_address
    fi
}


# init_glare - Initialize the database
function init_glare {
    # Delete existing artifacts
    rm -rf $GLARE_ARTIFACTS_DIR
    mkdir -p $GLARE_ARTIFACTS_DIR

    # (re)create Glare database
    recreate_database glare utf8

    # Migrate glare database
    $GLARE_BIN_DIR/glare-db-manage --config-file $GLARE_CONF_FILE upgrade
}


# install_glare - Collect source and prepare
function install_glare {
    setup_develop $GLARE_DIR
}


function install_glare_pythonclient {
    if use_library_from_git "python-glareclient"; then
        git_clone $GLARE_PYTHONCLIENT_REPO $GLARE_PYTHONCLIENT_DIR $GLARE_PYTHONCLIENT_BRANCH
        setup_develop $GLARE_PYTHONCLIENT_DIR
    else
        # nothing actually "requires" glareclient, so force installation from pypi
        pip_install_gr python-glareclient
    fi
}


# start_glare - Start running processes, including screen
function start_glare {
    run_process glare "$GLARE_BIN_DIR/glare-api --config-file $GLARE_CONF_DIR/glare.conf"
}


# stop_glare - Stop running processes
function stop_glare {
    # Kill the Glare screen windows
    for serv in glare-api; do
        stop_process $serv
    done
}


function cleanup_glare {
    sudo rm -rf $GLARE_ARTIFACTS_DIR $GLARE_AUTH_CACHE_DIR
}


if is_service_enabled glare; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing glare"
        install_glare
        install_glare_pythonclient
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configuring glare"
        create_glare_accounts
        configure_glare
    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        echo_summary "Initializing glare"
        init_glare
        echo_summary "Starting Glare process"
        start_glare
    fi

    if [[ "$1" == "unstack" ]]; then
        echo_summary "Shutting down glare"
        stop_glare
    fi

    if [[ "$1" == "clean" ]]; then
        echo_summary "Cleaning glare"
        cleanup_glare
    fi
fi


# Restore xtrace
$XTRACE

# Local variables:
# mode: shell-script
# End:
