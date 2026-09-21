# Historical external-test files

The obsolete vendored pyca implementation and its vulnerable Rust manifest
have been removed (#590). This directory preserves its original `.github`
files, which are outside the current task's scope, and their original licenses.
It is not an application build input or the external-test implementation.

Use `python3 tools/test-openssl-cryptography.py` from the repository root to
build pinned pyca 50.0.1 against Horos's installed OpenSSL archives and run the
upstream tests. See `docs/openssl-cryptography-validation.md` for provenance,
commands and measured limits. Downloaded sources and fixtures stay local.
