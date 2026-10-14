#!/usr/bin/env python3
"""R2 combined static + Gemini judge API server + shared gallery"""
import http.server, json, os, urllib.request, base64, time, datetime, glob
HERE = os.path.dirname(os.path.abspath(__file__))

# Load GEMINI_API_KEY from ~/.gemini_env (format: export GEMINI_API_KEY=xxxx)
def load_key():
    k = os.environ.get('GEMINI_API_KEY')
    if k: return k
    try:
        with open(os.path.expanduser('~/.gemini_env')) as f:
            for line in f:
                if 'GEMINI_API_KEY' in line and '=' in line:
                    return line.split('=',1)[1].strip().strip('"').strip("'")
    except Exception as e:
        print('key load err', e)
    return None

GEMINI_KEY = load_key()
print('Gemini key loaded:', 'yes' if GEMINI_KEY else 'NO')

class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()

    def do_POST(self):
        if self.path == '/api/judge':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length))
                target_expr = data.get('target_expr', 'happy')
                target_jp = data.get('target_jp', 'わらう')
                image_b64 = data.get('image', '')
                prompt = (f"画像に人の顔は写っていますか? はい か いいえ だけで答えてください。")
                body = json.dumps({
                    'contents': [{'parts': [
                        {'text': prompt},
                        {'inline_data': {'mime_type': 'image/jpeg', 'data': image_b64}}
                    ]}],
                    'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 10}
                }).encode()
                url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_KEY}'
                req = urllib.request.Request(url, data=body, headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    resp = json.loads(r.read())
                text = resp.get('candidates',[{}])[0].get('content',{}).get('parts',[{}])[0].get('text','').strip()
                text_l = text.lower()
                # 激甘: 「はい」または「yes」で100、「いいえ」「no」なら0、不明なら100
                if 'いいえ' in text or text_l.startswith('no') or 'いない' in text:
                    score = 0
                else:
                    score = 100
                is_match = (score==100)
                out = {'match': is_match, 'score': score, 'text': text}
                print(f'[judge] target={target_jp} score={score} text={text!r}')
            except Exception as e:
                # API失敗時も激甘: 100点で通す
                out = {'match': True, 'score': 100, 'text': '', 'error': str(e)}
                print(f'[judge] API ERROR (fallback 100): {e}')
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/api/save':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length))
                color = data.get('color', 'unknown')
                expr = data.get('expr', 'unknown')
                label = data.get('label', '')
                image_b64 = data.get('image', '')
                img_bytes = base64.b64decode(image_b64)
                os.makedirs(os.path.join(HERE, 'captures'), exist_ok=True)
                ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                fn = f'{ts}_{color}_{expr}.jpg'
                path = os.path.join(os.path.join(HERE, 'captures'), fn)
                with open(path, 'wb') as f: f.write(img_bytes)
                out = {'ok': True, 'url': '/captures/' + fn, 'filename': fn}
            except Exception as e:
                out = {'ok': False, 'error': str(e)}
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_GET(self):
        if self.path == '/api/gallery' or self.path.startswith('/api/gallery?'):
            try:
                today = datetime.datetime.now().strftime('%Y%m%d')
                files = sorted(glob.glob(f'{HERE}/captures/{today}_*.jpg'))
                items = []
                for f in files[-200:]:  # 最新200枚
                    base = os.path.basename(f)
                    parts = base.replace('.jpg','').split('_')
                    # parts: YYYYMMDD, HHMMSS, micros, color, expr
                    color = parts[3] if len(parts)>3 else ''
                    expr = parts[4] if len(parts)>4 else ''
                    ts = parts[1] if len(parts)>1 else ''
                    items.append({'url':'/captures/'+base,'color':color,'expr':expr,'timestamp':ts})
                out = {'items': items}
            except Exception as e:
                out = {'items': [], 'error': str(e)}
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass  # silent

if __name__ == '__main__':
    os.chdir(HERE)
    port = 8766
    print(f'Serving {HERE} on 0.0.0.0:{port} with /api/judge')
    http.server.HTTPServer(('0.0.0.0', port), H).serve_forever()
