"""
>       available fixtures: admin_client, cache, capfd, capfdbinary, caplog,
        capsys, capsysbinary, cluster, cluster_name, doctest_namespace, junitxml_plugin,
        monkeypatch, nodes, ocm_client_scope_class, ocm_client_scope_session, ocm_token,
        pytestconfig, record_property, record_testsuite_property, record_xml_attribute, recwarn,
        set_webserver_name, tmp_path, tmp_path_factory, tmpdir, tmpdir_factory
>       use 'pytest --fixtures [testpath]' for help on them.
"""
import io
import logging
import os
import traceback
from http.client import responses

import pytest
import requests
from jinja2 import (  # <- Temp # TODO push Jinja2_templates to ocp_utils and change imports
    Environment,
    FileSystemLoader,
)
from ocp_resources.namespace import Namespace
from ocp_utilities.infra import assert_pods_failed_or_pending


PORT = 80
LOGGER = logging.getLogger(__name__)


@pytest.mark.nginx
def test_namespace(nginx_namespace):
    assert nginx_namespace.status == Namespace.Status.ACTIVE, "Namespace is tackled"


@pytest.mark.nginx(depends=["test_namespace"])
def test_pod_status(nginx_pod):
    """Checks that pod is running, using 'assert_pods_failed_or_pending' for nginx.
    ---
    assert_pods_failed_or_pending:
    Validates all pods are not in failed nor pending phase
    Args:
         pods: List of pod objects
    Raises:
        PodsFailedOrPendingError: if there are failed or pending pods
    """
    check_result = assert_pods_failed_or_pending(pods=[nginx_pod])
    LOGGER.info(f"Pod status: {nginx_pod.status}")
    assert check_result is None, "Failed with pod checkups"


@pytest.mark.nginx
def test_pod_logs(nginx_pod):
    """We get pod given logs with unconditional execute status, logs used from ocp_resources/pod"""
    LOGGER.info(f"-----Pod Logs:\n{nginx_pod.log()}")
    # TODO compress into file?


@pytest.mark.nginx(depends=["test_pod_status"])
def test_nginx_service(nginx_service):
    LOGGER.info(
        f"Created service for nginx pod with port named nginx-service-port,"
        f" service type: {nginx_service.instance.spec.type}, using {nginx_service.instance.spec.ipFamilies}"
    )
    assert nginx_service, "Service is unavailable"


@pytest.mark.nginx(depends=["test_nginx_service"])
def test_nginx_route(nginx_route):
    LOGGER.info(
        f"Route nginx-route (ocp_resources Resource object) is exposing service on host {nginx_route.host}"
    )
    assert nginx_route, "Route is unavailable"


@pytest.mark.nginx(depends=["test_nginx_route"])
def test_get_request(nginx_route):
    """
    Checks response from GET request from webserver (exposed service) host.
    """
    url = f"http://{nginx_route.host}:{PORT}"
    LOGGER.info(f"Using GET request in : \n{url}")
    request_result = requests.get(url=url)
    assert request_result.status_code in [requests.codes.OK, requests.codes.ACCEPTED], (
        f"Failed with status code {request_result.status_code}:"
        f" {responses[request_result.status_code]}\nURL used: {request_result.url}"
    )
    LOGGER.info(f"Success - result returned {request_result}")


@pytest.mark.nginx(depends=["test_pod_status"])
def test_core_v1_api_get_request(nginx_pod):
    """connect GET requests to proxy of Pod  # noqa: E501
    This method makes a synchronous HTTP request by default."""
    request_result = nginx_pod._kube_v1_api.connect_get_namespaced_pod_proxy(
        name=nginx_pod.name, namespace=nginx_pod.namespace
    )
    assert request_result, "Failed with connect_get_namespaced_pod_proxy"
    LOGGER.info(f"Check connect_get_namespaced_pod_proxy: \n{request_result}")


# TODO: Edit once 'Jinja2_template.py' added to openshift-python-utilities
def render_yaml(
    base_path=os.getcwd(), template_file_path="nginx_pod_template.j2", _dict=None
):
    """
    This is temporary until generic file 'Jinja2_template.py' will be merged into ocp_utilities
    ------
    Reads j2
    template file name from templates under base dir & Render a yaml file from dict Args: template_file_name (str):
    template name base_dir_path (str): templates base directory, default value is current dir <- implemented as
    fixture input, since its local parameter (could be changed dynamically).
    _dict (dict): used to populate template with values Returns: StringIO
    with yaml rendered from template
    """
    if not _dict:
        _dict = {}
    try:
        env = Environment(
            loader=FileSystemLoader(base_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(name=template_file_path)
        return io.StringIO(template.render(_dict))
    # except (TypeError,TemplateNotFound,TemplateError,BlockingIOError) as exc:
    except Exception:
        LOGGER.error(
            f"Something went wrong with loading {template_file_path}, "
            f"failed with {traceback.format_exc().splitlines()[-1]}"
        )
        raise
