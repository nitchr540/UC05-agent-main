from __future__ import annotations
import io,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from .llm_telemetry import make_telemetry

def _now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
class BufferedResponse:
    def __init__(self,response,body):
        self._response=response; self._buffer=io.BytesIO(body)
        for n in ('status','code','headers','reason','url'):
            setattr(self,n,getattr(response,n,None))
    def read(self,amt=-1): return self._buffer.read(amt)
    def __enter__(self): return self
    def __exit__(self,*args):
        close=getattr(self._response,'close',None)
        if close: close()
        return False
    def __getattr__(self,name): return getattr(self._response,name)
class MetadataRefreshTelemetryCapture:
    def __init__(self):
        self.telemetry={'status':'not_called','workflow':'metadata-refresh','model':os.getenv('LLM_MODEL'),'input_tokens':0,'output_tokens':0,'total_tokens':0,'request_payload_sanitized':{},'response_payload_sanitized':{}}
    def wrap_urlopen(self,original):
        def wrapped(request,*args,**kwargs):
            started=time.perf_counter(); request_time=_now(); raw=getattr(request,'data',None); request_payload={}
            if raw:
                try: request_payload=json.loads(raw.decode() if isinstance(raw,bytes) else raw)
                except Exception: request_payload={'body':raw.decode(errors='replace') if isinstance(raw,bytes) else str(raw)}
            model=request_payload.get('model') if isinstance(request_payload,dict) else os.getenv('LLM_MODEL')
            try:
                response=original(request,*args,**kwargs); body=response.read()
                try: response_payload=json.loads(body.decode())
                except Exception: response_payload={'body':body.decode(errors='replace')}
                choice=(response_payload.get('choices') or [{}])[0] if isinstance(response_payload,dict) else {}
                self.telemetry=make_telemetry(status='completed',model=(response_payload.get('model') if isinstance(response_payload,dict) else None) or model,request_timestamp=request_time,response_timestamp=_now(),latency_ms=round((time.perf_counter()-started)*1000),request_payload=request_payload,response_payload=response_payload,usage=response_payload.get('usage',{}) if isinstance(response_payload,dict) else {},finish_reason=choice.get('finish_reason') if isinstance(choice,dict) else None)
                self.telemetry['workflow']='metadata-refresh'; return BufferedResponse(response,body)
            except Exception as error:
                self.telemetry=make_telemetry(status='failed',model=model or os.getenv('LLM_MODEL'),request_timestamp=request_time,response_timestamp=_now(),latency_ms=round((time.perf_counter()-started)*1000),request_payload=request_payload,response_payload={},error=f'{type(error).__name__}: {error}')
                self.telemetry['workflow']='metadata-refresh'; raise
        return wrapped
    def persist(self):
        t=self.telemetry
        outputs=[('UC_METADATA_LLM_TELEMETRY_JSON','metadata-refresh-telemetry.json',t),('UC_METADATA_LLM_REQUEST_JSON','metadata-refresh-request-sanitized.json',t.get('request_payload_sanitized',{})),('UC_METADATA_LLM_RESPONSE_JSON','metadata-refresh-response-sanitized.json',t.get('response_payload_sanitized',{}))]
        for env,default,payload in outputs: Path(os.getenv(env,default)).write_text(json.dumps(payload,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
        result={'schemaVersion':'1.0','workflow':'metadata-refresh','base_sha':os.getenv('UC_METADATA_BASE_SHA'),'head_sha':os.getenv('UC_METADATA_HEAD_SHA'),'source_pr_number':os.getenv('UC_METADATA_PR_NUMBER'),'source_pr_url':os.getenv('UC_METADATA_PR_URL'),'refreshTelemetry':t}
        Path(os.getenv('UC_METADATA_OUTPUT_JSON','metadata-refresh-result.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
        summary=Path(os.getenv('UC_METADATA_SUMMARY','metadata-refresh-summary.md')); current=summary.read_text(encoding='utf-8') if summary.exists() else '# Metadata refresh\n'
        lines=['','## Metadata Refresh LLM Telemetry','','| Metric | Value |','|---|---|',f"| Status | {t.get('status','unknown')} |",f"| Model | `{t.get('model') or 'not reported'}` |",f"| Input tokens | {t.get('input_tokens',0)} |",f"| Output tokens | {t.get('output_tokens',0)} |",f"| Total tokens | {t.get('total_tokens',0)} |",f"| Latency | {t.get('latency_ms',0)} ms |",f"| Finish reason | {t.get('finish_reason') or 'not reported'} |",'','<details>','<summary>Sanitized metadata-refresh LLM request payload</summary>','','```json',json.dumps(t.get('request_payload_sanitized',{}),indent=2,ensure_ascii=False,sort_keys=True),'```','','</details>','','<details>','<summary>Sanitized metadata-refresh LLM response payload</summary>','','```json',json.dumps(t.get('response_payload_sanitized',{}),indent=2,ensure_ascii=False,sort_keys=True),'```','','</details>','']
        summary.write_text(current.rstrip()+'\n'+'\n'.join(lines),encoding='utf-8')
