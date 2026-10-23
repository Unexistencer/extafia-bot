"""Fail a container build if known vulnerable Python CA bundles remain."""
import importlib.metadata
import os
from pathlib import Path
import ssl

import certifi
from pip._vendor import certifi as pip_certifi


def check_bundle(label, path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(path))
    roots = context.get_ca_certs()
    assert roots, f"{label}: empty CA store"
    for root in roots:
        for rdn in root["subject"]:
            for key, value in rdn:
                assert not (key == "commonName" and value == "emSign ECC Root CA - G3"), (
                    f"{label}: distrusted emSign ECC Root CA - G3 remains"
                )
    print(f"PASS {label}: {len(roots)} certificates; G3 absent")


assert tuple(map(int, importlib.metadata.version("pip").split("."))) >= (26, 2, 2)
assert tuple(map(int, importlib.metadata.version("certifi").split("."))) >= (2026, 10, 19)
check_bundle("certifi", certifi.where())
check_bundle("pip vendored certifi", pip_certifi.where())
system_bundle = ssl.get_default_verify_paths().cafile
assert system_bundle, "System CA bundle not found"
check_bundle("system", system_bundle)
try:
    import grpc
except ImportError:
    pass
else:
    grpc_roots = Path(os.environ.get("GRPC_DEFAULT_SSL_ROOTS_FILE_PATH") or (
        Path(grpc.__file__).parent / "_cython" / "_credentials" / "roots.pem"
    ))
    assert grpc_roots.is_file(), "Locate and verify this gRPC build's embedded roots"
    check_bundle("gRPC effective", grpc_roots)
