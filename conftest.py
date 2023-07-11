"""This program generates an nginx pod latest image and deploys a service route for testing
    To start this program use following commands:
    - oc config view --flatten > kubeconfig
    - export KUBECONFIG=kubeconfig
    - poetry install
    - poetry run pytest -m nginx
"""
import logging
import os
import traceback

import pytest
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from ocp_resources.route import Route
from ocp_resources.service import Service
from ocp_resources.utils import TimeoutExpiredError
from ocp_utilities.infra import cluster_resource
from test_nginx import render_yaml


# Timeout configuration
TIMEOUT_4MIN = 240
LOGGER = logging.getLogger(__name__)


@pytest.mark.nginx
@pytest.fixture(scope="module")
def run_nginx_tests_setup():
    """General wrapper for nginx execution"""
    LOGGER.info("Running tests for nginx pod. Activating setup for resources:\n")
    # LOGGER.info(f"Setting up resources")
    # print(ocm_client_scope_session)
    yield
    LOGGER.info("\nFinished, cleaning up resources:\n")


@pytest.fixture(scope="module")
def webserver_name(run_nginx_tests_setup):
    """Gets username from environment and fill the scheme webserver-<your name>,
    Sets NGINX-WEBSERVER as env var for session usage.
    """
    username = os.getenv("USER")
    LOGGER.info("Environment user name: " + username)
    assert username, "Please configure username for webserver client"
    yield f"webserver-{username}"


@pytest.fixture(scope="module")
def nginx_namespace(webserver_name, admin_client):
    LOGGER.info(f"Creating namespace for - {webserver_name}")
    with cluster_resource(Namespace)(
        client=admin_client, name=webserver_name
    ) as namespace:
        try:
            namespace.wait_for_status(
                status=Namespace.Status.ACTIVE, timeout=TIMEOUT_4MIN
            )
            yield namespace
        except TimeoutExpiredError:
            LOGGER.error(f"Timeout reached while executing {webserver_name}")
            raise


@pytest.fixture(scope="module", params=["tests/nginx_pod"], autouse=True)
def nginx_pod(admin_client, request, nginx_namespace, webserver_name):
    """
    Creates nginx pod, wait for it to be RUNNING and monitor the results.
    :arg:
        client (DynamicClient): openshift dynamic client
        pod_yaml (StringIO): with pod's yaml
    :raise
        TimeoutExpiredError if reached timeout
    :returns nginx pod
    """
    # nodeName, containerPort and protocol attributes are also supported in template, could be used as params
    _dict = {"kind": "Pod", "webserver_namespace": webserver_name}
    pod_yaml = render_yaml(base_path=request.param, _dict=_dict)
    with cluster_resource(Pod)(client=admin_client, yaml_file=pod_yaml) as nginx_pod:
        try:
            nginx_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_4MIN)
            yield nginx_pod
        except TimeoutExpiredError:
            LOGGER.error("Timeout reached while executing pod")
            raise
        except Exception:
            LOGGER.error(
                f"Something went wrong with creating the pod, failed with {traceback.format_exc().splitlines()[-1]}"
            )
            raise


@pytest.fixture(
    scope="module",
    params=[("NodePort", "tests/nginx_pod")],
)
def nginx_service(admin_client, request, webserver_name):
    """
    Get pod relevant yaml to manifest loaded from template, creates a new service to expose via route resource.
    """
    # Port, port type and protocol attributes are also supported in template, could be used as params
    LOGGER.info(f"Executing service with parameters: {request.param}")
    _dict = {
        "kind": "Service",
        "webserver_namespace": webserver_name,
        "type": request.param[0],
    }
    service_yaml = render_yaml(base_path=request.param[1], _dict=_dict)
    try:
        with cluster_resource(Service)(
            client=admin_client, yaml_file=service_yaml
        ) as service:
            yield service
    except Exception:
        LOGGER.error(
            f"Something went wrong with creating the service, failed with {traceback.format_exc().splitlines()[-1]}"
        )
        raise


@pytest.fixture(scope="module")
def nginx_route(admin_client, nginx_service):
    """Exposing nginx service to route"""
    with cluster_resource(Route)(
        client=admin_client,
        name="nginx-route",
        namespace=nginx_service.namespace,
        service=nginx_service.name,
    ) as nginx_route:
        try:
            yield nginx_route
        except Exception:
            LOGGER.error(
                f"Something went wrong with creating the route resource, "
                f"failed with {traceback.format_exc().splitlines()[-1]}"
            )
            raise
