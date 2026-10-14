#!/usr/bin/env python3
"""まねっこバルーン v2 サーバー
   - 静的配信(~/r2/v2)
   - /api/classify : ベロ出し等、幾何で取れない表情だけVLM(Gemini)で yes/no 分類(採点でなく分類=安定)
   - /api/save, /api/gallery : v1と同じ写真共有(captures/ を共用)
"""
import http.server, json, os, urllib.request, base64, datetime, glob

ROOT = os.path.expanduser('~/r2/v2')
CAPDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'captures')

def load_key():
    k = os.environ.get('GEMINI_API_KEY')
    if k: return k
    try:
        with open(os.path.expanduser('~/.gemini_env')) as f:
            for line in f:
                if 'GEMINI_API_KEY' in line and '=' in line:
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except Exception as e:
        print('key load err', e)
    return None

GEMINI_KEY = load_key()
print('Gemini key loaded:', 'yes' if GEMINI_KEY else 'NO')

# 幾何で取れない表情 → VLMへの自然文の問い(「はい/いいえ」分類)
VLM_QUESTION = {
    'tongue': 'この画像の人物は舌を出していますか?',
    'disgusted': 'この画像の人物は「うえっ」という嫌悪の表情をしていますか?',
}

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == '/api/classify':
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                expr = data.get('expr', 'tongue')
                q = VLM_QUESTION.get(expr, f'この画像の人物は{expr}の表情をしていますか?')
                prompt = q + ' はい か いいえ だけで答えてください。'
                body = json.dumps({
                    'contents': [{'parts': [
                        {'text': prompt},
                        {'inline_data': {'mime_type': 'image/jpeg', 'data': data.get('image', '')}}
                    ]}],
                    'generationConfig': {'temperature': 0.0, 'maxOutputTokens': 8}
                }).encode()
                url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                       f'gemini-2.5-flash-lite:generateContent?key={GEMINI_KEY}')
                # 503/タイムアウトは一時的に起きるので最大3回リトライ
                resp = None
                for attempt in range(3):
                    try:
                        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
                        with urllib.request.urlopen(req, timeout=30) as r:
                            resp = json.loads(r.read())
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise
                        print(f'[classify] retry {attempt+1} after {e}')
                text = resp.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()
                tl = text.lower()
                match = not ('いいえ' in text or tl.startswith('no') or 'いない' in text or 'していません' in text)
                print(f'[classify] expr={expr} match={match} text={text!r}')
                self._json({'match': match, 'text': text})
            except Exception as e:
                # 失敗時は通す(イベント運用優先): 公平で安定だが、止めない
                print(f'[classify] ERROR (fallback match): {e}')
                self._json({'match': True, 'text': '', 'error': str(e)})
            return

        if self.path == '/api/save':
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                os.makedirs(CAPDIR, exist_ok=True)
                ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                fn = f"{ts}_{data.get('color','x')}_{data.get('expr','x')}.jpg"
                with open(os.path.join(CAPDIR, fn), 'wb') as f:
                    f.write(base64.b64decode(data.get('image', '')))
                self._json({'ok': True, 'url': '/captures/' + fn})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return
        self.send_error(404)

    def do_GET(self):
        if self.path.startswith('/api/gallery'):
            try:
                today = datetime.datetime.now().strftime('%Y%m%d')
                items = []
                for f in sorted(glob.glob(f'{CAPDIR}/{today}_*.jpg'))[-200:]:
                    p = os.path.basename(f).replace('.jpg', '').split('_')
                    items.append({'url': '/captures/' + os.path.basename(f),
                                  'color': p[3] if len(p) > 3 else '',
                                  'expr': p[4] if len(p) > 4 else ''})
                self._json({'items': items})
            except Exception as e:
                self._json({'items': [], 'error': str(e)})
            return
        # captures/ は v1 と共用
        if self.path.startswith('/captures/'):
            fp = os.path.join(CAPDIR, os.path.basename(self.path))
            if os.path.exists(fp):
                self.send_response(200); self.send_header('Content-Type', 'image/jpeg')
                self.end_headers()
                with open(fp, 'rb') as f: self.wfile.write(f.read())
                return
        return super().do_GET()

    def log_message(self, *a):
        pass

if __name__ == '__main__':
    port = 8767
    print(f'まねっこバルーン v2 → http://localhost:{port}/  (root={ROOT})')
    http.server.HTTPServer(('0.0.0.0', port), H).serve_forever()
