"""Tests for K8sConnector — mock subprocess.run."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.k8s import K8sConnector, K8sResult


@pytest.fixture
def connector():
    return K8sConnector(
        kubeconfig="apiVersion: v1\nclusters: []",
        context=None,
        namespace="default",
        timeout=30,
    )


@pytest.fixture
def connector_with_context():
    return K8sConnector(
        kubeconfig="apiVersion: v1\nclusters: []",
        context="my-context",
        namespace="production",
        timeout=30,
    )


def _mock_subprocess(returncode=0, stdout="output", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


@patch("subprocess.run")
async def test_execute_success(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="NAME   READY   STATUS\nnginx  1/1     Running")

    result = await connector.execute("get pods")

    assert isinstance(result, K8sResult)
    assert result.exit_code == 0
    assert "nginx" in result.stdout
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "kubectl" in cmd
    assert "-n default" in cmd
    assert "get pods" in cmd


@patch("subprocess.run")
async def test_execute_adds_namespace(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="ok")

    await connector.execute("get deployments")

    cmd = mock_run.call_args[0][0]
    assert "-n default" in cmd


@patch("subprocess.run")
async def test_execute_all_namespaces_no_extra_namespace(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="ok")

    await connector.execute("get pods --all-namespaces")

    cmd = mock_run.call_args[0][0]
    assert "--all-namespaces" in cmd
    assert "-n default" not in cmd


@patch("subprocess.run")
async def test_execute_strips_kubectl_prefix(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="ok")

    await connector.execute("kubectl get nodes")

    cmd = mock_run.call_args[0][0]
    # Should not have double "kubectl kubectl"
    assert "kubectl kubectl" not in cmd
    assert "get nodes" in cmd


@patch("subprocess.run")
async def test_execute_with_context(mock_run, connector_with_context: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="ok")

    await connector_with_context.execute("get pods")

    cmd = mock_run.call_args[0][0]
    assert "--context=my-context" in cmd
    assert "-n production" in cmd


@patch("subprocess.run")
async def test_execute_timeout(mock_run, connector: K8sConnector):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=30)

    result = await connector.execute("get pods")

    assert result.exit_code == 1
    assert "timed out" in result.stderr.lower()


@patch("subprocess.run")
async def test_test_connection_success(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="Kubernetes control plane is running")

    ok = await connector.test_connection()
    assert ok is True


@patch("subprocess.run")
async def test_test_connection_failure(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(returncode=1, stderr="connection refused")

    ok = await connector.test_connection()
    assert ok is False


@patch("subprocess.run")
async def test_kubeconfig_written_to_tempfile(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="ok")

    await connector.execute("get pods")

    cmd = mock_run.call_args[0][0]
    assert "KUBECONFIG=" in cmd


@patch("subprocess.run")
async def test_execute_with_explicit_namespace_flag(mock_run, connector: K8sConnector):
    mock_run.return_value = _mock_subprocess(stdout="ok")

    await connector.execute("get pods -n kube-system")

    cmd = mock_run.call_args[0][0]
    # Should not add default namespace when -n is already specified
    assert "-n default" not in cmd
    assert "-n kube-system" in cmd
