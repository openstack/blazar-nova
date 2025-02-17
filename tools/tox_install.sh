#!/usr/bin/env bash

# The blazar-nova repo suffers from the problem of depending on nova, which
# does not exist on PyPI.

# This wrapper for tox's package installer will use the existing package
# if it exists, else use zuul-cloner if that program exists, else grab it
# from nova master via a hard-coded URL. That last case should only
# happen with devs running unit tests locally.

# From the tox.ini config page:
# install_command=ARGV
# default:
# pip install {opts} {packages}

BRANCH_NAME=${NOVA_BRANCH:-master}
nova_installed=$(echo "import nova" | python 2>/dev/null ; echo $?)
NOVA_DIR=$HOME/nova

set -e
set -x

# Use .gitreview as the key to determine the appropriate branch to clone for
# tests. Inspired by OSA code.
PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${PARENT}/../.gitreview" ]; then
  BRANCH_NAME=$(awk -F'=' '/defaultbranch/ {print $2}' "${PARENT}/../.gitreview")
  if [[ "${BRANCH_NAME}" == "" ]]; then
    BRANCH_NAME="master"
  fi
fi

install_cmd="pip install -c$1"
shift

# The devstack based functional tests have nova checked out in
# $NOVA_DIR on the test systems - with the change to test in it.
# Use this directory if it exists, so that this script installs the
# nova version to test here.
# Note that the functional tests use sudo to run tox and thus
# variables used for zuul-cloner to check out the correct version are
# lost.
if [ -d "$NOVA_DIR" ]; then
    echo "FOUND Nova code at $NOVA_DIR - using"
    $install_cmd -U -e $NOVA_DIR
elif [ $nova_installed -eq 0 ]; then
    echo "ALREADY INSTALLED" > /tmp/tox_install.txt
    location=$(python -c "import nova; print(nova.__file__)")
    echo "ALREADY INSTALLED at $location"

    echo "Nova already installed; using existing package"
elif [ -d "/opt/git/opendev.org/openstack/nova" ]; then
    echo "PIP LOCAL" > /tmp/tox_install.txt
    if [ -z "$NOVA_PIP_LOCATION" ]; then
        NOVA_PIP_LOCATION="git+file:///opt/git/opendev.org/openstack/nova@$BRANCH_NAME#egg=nova"
    fi
    $install_cmd -U -e ${NOVA_PIP_LOCATION}
else
    echo "PIP HARDCODE" > /tmp/tox_install.txt
    if [ -z "$NOVA_PIP_LOCATION" ]; then
        NOVA_PIP_LOCATION="git+https://opendev.org/openstack/nova@$BRANCH_NAME#egg=nova"
    fi
    $install_cmd -U -e ${NOVA_PIP_LOCATION}
fi

$install_cmd -U $*
exit $?
