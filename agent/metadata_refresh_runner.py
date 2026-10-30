from __future__ import annotations
import runpy,urllib.request
from .metadata_refresh_telemetry import MetadataRefreshTelemetryCapture
def main():
    capture=MetadataRefreshTelemetryCapture(); original=urllib.request.urlopen; urllib.request.urlopen=capture.wrap_urlopen(original); code=0
    try: runpy.run_module('agent.metadata_updater',run_name='__main__')
    except SystemExit as error: code=int(error.code or 0)
    finally: urllib.request.urlopen=original; capture.persist()
    return code
if __name__=='__main__': raise SystemExit(main())
