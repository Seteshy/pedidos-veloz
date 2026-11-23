import json
import os
import socket
import urllib.error
import urllib.request

role = os.environ['SERVICE_ROLE']
target = 'pagamentos' if role == 'pedidos' else 'estoque'
with urllib.request.urlopen(f'http://{target}:8000/health/live', timeout=5) as response:
    assert response.status == 200
result = {'source': role, 'allowed_target': target, 'allowed_status': 200}
if role == 'gateway':
    socket.gethostbyname('pagamentos')
    try:
        urllib.request.urlopen('http://pagamentos:8000/health/live', timeout=3)
    except TimeoutError:
        result['denied_target'] = 'pagamentos'
        result['denied_result'] = 'TIMEOUT'
    except urllib.error.URLError as error:
        if not isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise
        result['denied_target'] = 'pagamentos'
        result['denied_result'] = 'TIMEOUT'
    else:
        raise RuntimeError('Gateway conseguiu acessar pagamentos, contrariando a NetworkPolicy')
result['result'] = 'PASS'
print(json.dumps(result))
