import json, os, http.server, urllib.parse
ROOT=os.path.dirname(os.path.abspath(__file__)); LIB=os.path.expanduser("~/describesong/mulan-trial/library"); LAB=os.path.join(ROOT,"labels.json")
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*a,**k): super().__init__(*a,directory=ROOT,**k)
    def do_GET(self):
        if self.path.startswith("/library/"):
            p=os.path.join(LIB, urllib.parse.unquote(self.path[len("/library/"):]))
            if not os.path.isfile(p): self.send_error(404); return
            size=os.path.getsize(p); rng=self.headers.get("Range")
            start,end=0,size-1
            if rng and rng.startswith("bytes="):
                a,_,b=rng[6:].partition("-"); start=int(a or 0); end=int(b) if b else size-1; end=min(end,size-1)
            with open(p,"rb") as f: f.seek(start); data=f.read(end-start+1)
            self.send_response(206 if rng else 200); self.send_header("Content-Type","audio/mpeg"); self.send_header("Accept-Ranges","bytes")
            if rng: self.send_header("Content-Range","bytes %d-%d/%d"%(start,end,size))
            self.send_header("Content-Length",str(len(data))); self.end_headers()
            try: self.wfile.write(data)
            except BrokenPipeError: pass
            return
        if self.path=="/labels.json":
            body=open(LAB,"rb").read() if os.path.exists(LAB) else b"{}"; self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        super().do_GET()
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0)); d=json.loads(self.rfile.read(n)); labels=json.load(open(LAB)) if os.path.exists(LAB) else {}
        labels[str(d["id"])]=d["label"]; json.dump(labels, open(LAB,"w")); self.send_response(204); self.end_headers()
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(("127.0.0.1",8099),H).serve_forever()
