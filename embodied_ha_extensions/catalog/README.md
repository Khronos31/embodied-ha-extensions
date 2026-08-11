# Bundled catalog

Only reviewed `*.json` manifests stored in this directory are loaded. A manifest ID must match its filename and a same-ID directory under `/app/apps`. Its entrypoint is one executable filename inside that directory; shell expressions and paths are not accepted.

The development skeleton intentionally ships an empty catalog. Test manifests live only in temporary pytest directories.
