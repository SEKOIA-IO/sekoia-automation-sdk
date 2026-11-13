import base64
import re

import requests


def check_image_on_registry(
    docker_image: str, version: str, registry: str, namespace: str, registry_pat: str
) -> bool:
    """Checks if a Docker image exists on a registry

    An image name with at least 2 `/` (e.g. my_registry.com/sekoia-io/image) carries
    its own registry and namespace; otherwise the defaults are used.

    Args:
        docker_image (str): Docker image name as specified in the manifest
        version (str): Docker image version
        registry (str): Default registry, used if the image name has none
        namespace (str): Default namespace, used if the image name has none
        registry_pat (str): Token used to authenticate on the registry

    Returns:
        bool: True if the image exists on the registry or if we don't have access
            to a registry
              False otherwise
    """
    if match := re.match(r"(.*?)/(.*)/(.*)", docker_image):
        registry = match[1]
        namespace = match[2]
        image_name = match[3]
    else:
        image_name = docker_image

    token = base64.b64encode(registry_pat.encode()).decode()
    response = requests.get(
        f"https://{registry}/v2/{namespace}/{image_name}/manifests/{version}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.index.v1+json",
        },
    )

    return response.status_code == 200
