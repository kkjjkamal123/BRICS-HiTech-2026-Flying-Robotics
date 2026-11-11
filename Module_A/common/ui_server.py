"""
Operator web UI - standard library only (works on the Orange Pi without installing anything).

  ui = UIServer(state, port=8090).start()
  open http://10.42.0.1:8090  (drone)  or  http://localhost:8090  (laptop / mock)

`state` is a dict shared with the mission (protected by state['_lock']):
  status, phase, battery, pos, detections (list), counts, log (list of str), report (path), frame_jpg (bytes)
Buttons write state['command'] = 'start' | 'return' | 'land' | 'abort'.
  RETURN = fly home, then land.  LAND / ABORT = land where it is now.
Python 3.8 compatible.
"""
import json
import math
import os
import socket
import threading
import time

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except ImportError:  # pragma: no cover
    from http.server import BaseHTTPRequestHandler, HTTPServer as ThreadingHTTPServer

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#111;color:#eee}
header{background:#1d3557;padding:10px 16px;font-size:20px;font-weight:bold}
.wrap{display:flex;flex-wrap:wrap;gap:14px;padding:14px}
.card{background:#222;border-radius:8px;padding:12px;min-width:280px;flex:1}
button{font-size:18px;padding:12px 22px;margin:4px;border:0;border-radius:6px;cursor:pointer;color:#fff}
.start{background:#2a9d8f}.ret{background:#457b9d}.land{background:#e9c46a;color:#000}.abort{background:#e63946}
#phase{font-size:26px;font-weight:bold}.k{color:#999}
table{border-collapse:collapse;width:100%%}td,th{border-bottom:1px solid #333;padding:4px;text-align:left}
#log{font-family:monospace;font-size:12px;height:200px;overflow-y:auto;white-space:pre-wrap;background:#000;padding:6px}
img{max-width:100%%;border-radius:6px}
.alert{background:#e63946;color:#fff;padding:8px;border-radius:6px;margin-top:6px;display:none;font-weight:bold}
</style></head><body><header>%(title)s</header><div class="wrap">
<div class="card"><div class="k">Mission phase</div><div id="phase">-</div>
<div id="status" class="k"></div><div id="alert" class="alert"></div>
<p><span class="k">Battery:</span> <b id="bat">-</b> &nbsp; <span class="k">Position:</span> <b id="pos">-</b></p>
<button class="start" onclick="cmd('start')">START MISSION</button>
<button class="ret" onclick="cmd('return')" title="fly home, then land">RETURN HOME</button>
<button class="land" onclick="cmd('land')" title="land where it is now">LAND</button>
<button class="abort" onclick="cmd('abort')">ABORT</button>
<p id="report"></p>
<h3>Counts</h3><table id="counts"></table></div>
<div class="card"><div class="k">Live camera (detections)</div><img id="frame" src="/stream.mjpg" onerror="window.poll=1;this.onerror=null;this.src='/frame.jpg?'+Date.now()"></div>
<div class="card"><div class="k">Live map (metres, aruco_map) &nbsp; <span id="fps"></span></div>
<svg id="map" viewBox="0 0 400 400" style="width:100%%;max-width:420px;background:#0b1a2a;border-radius:6px"></svg></div>
<div class="card"><h3>Detected objects</h3><table id="det"><tr><th>#</th><th>Class</th><th>X</th><th>Y</th><th>Conf</th><th>Time</th></tr></table></div>
<div class="card" style="min-width:100%%"><div class="k">Log</div><div id="log"></div></div></div>
<script>
let lastN=0;
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const COL={fire:'#ff4d4d',flame:'#ff4d4d',hotspot:'#ff4d4d',smoke:'#bbbbbb',car:'#4dabf7',truck:'#4dabf7'};
function drawMap(s){
 // world bounds = mission area + home + everything seen, 0.5 m margin; x right, y up
 const pts=[]; const a=s.area; if(a&&a.length===4){pts.push([a[0],a[1]],[a[2],a[3]]);}
 if(s.home) pts.push(s.home); if(s.xy) pts.push(s.xy);
 (s.detections||[]).forEach(d=>{if(typeof d.x==='number') pts.push([d.x,d.y]);});
 if(!pts.length) pts.push([0,0],[1,1]);
 let x0=Math.min(...pts.map(p=>p[0]))-0.5,x1=Math.max(...pts.map(p=>p[0]))+0.5,y0=Math.min(...pts.map(p=>p[1]))-0.5,y1=Math.max(...pts.map(p=>p[1]))+0.5;
 const sc=380/Math.max(x1-x0,y1-y0,1), X=x=>10+(x-x0)*sc, Y=y=>390-(y-y0)*sc;
 let g='';
 for(let gx=Math.ceil(x0);gx<=x1;gx++) g+=`<line x1="${X(gx)}" y1="0" x2="${X(gx)}" y2="400" stroke="#1f3b57"/><text x="${X(gx)+2}" y="398" fill="#5a7a99" font-size="10">${gx}</text>`;
 for(let gy=Math.ceil(y0);gy<=y1;gy++) g+=`<line x1="0" y1="${Y(gy)}" x2="400" y2="${Y(gy)}" stroke="#1f3b57"/><text x="2" y="${Y(gy)-2}" fill="#5a7a99" font-size="10">${gy}</text>`;
 if(a&&a.length===4) g+=`<rect x="${X(Math.min(a[0],a[2]))}" y="${Y(Math.max(a[1],a[3]))}" width="${Math.abs(a[2]-a[0])*sc}" height="${Math.abs(a[3]-a[1])*sc}" fill="none" stroke="#2a9d8f" stroke-dasharray="6 4"/>`;
 if(s.track&&s.track.length>1) g+=`<polyline fill="none" stroke="#8ecae6" stroke-width="1.5" opacity="0.7" points="${s.track.map(p=>X(p[0])+','+Y(p[1])).join(' ')}"/>`;
 if(s.home) g+=`<rect x="${X(s.home[0])-6}" y="${Y(s.home[1])-6}" width="12" height="12" fill="none" stroke="#e9c46a" stroke-width="2"/><text x="${X(s.home[0])+8}" y="${Y(s.home[1])+4}" fill="#e9c46a" font-size="11">H</text>`;
 (s.detections||[]).forEach(d=>{ if(typeof d.x!=='number') return; const c=COL[d.name]||'#f4a261';
  g+=`<circle cx="${X(d.x)}" cy="${Y(d.y)}" r="7" fill="${c}" stroke="#fff"/><text x="${X(d.x)+9}" y="${Y(d.y)-6}" fill="#fff" font-size="11">#${d.id} ${esc(d.name)} ${esc(d.time||'')}</text>`;});
 if(s.xy) g+=`<polygon points="${X(s.xy[0])},${Y(s.xy[1])-8} ${X(s.xy[0])-6},${Y(s.xy[1])+6} ${X(s.xy[0])+6},${Y(s.xy[1])+6}" fill="#ffffff"/>`;
 document.getElementById('map').innerHTML=g;
}
function cmd(c){ if(c==='abort' && !confirm('ABORT and land now?')) return; fetch('/cmd?c='+c,{method:'POST'}).catch(()=>alert('No connection to the drone - use the RC transmitter!')); }
async function tick(){
 try{ const s=await (await fetch('/status')).json();
  document.getElementById('phase').textContent=s.phase||'-';
  document.getElementById('status').textContent=s.status||'';
  document.getElementById('bat').textContent=s.battery||'-';
  document.getElementById('pos').textContent=s.pos||'-';
  let r='<tr><th>#</th><th>Class</th><th>X</th><th>Y</th><th>Conf</th><th>Time</th></tr>';
  const f=v=>(typeof v==='number')?v.toFixed(2):'?';
  (s.detections||[]).forEach(d=>{r+=`<tr><td>${d.id}</td><td><b>${esc(d.name)}</b></td><td>${f(d.x)}</td><td>${f(d.y)}</td><td>${f(d.conf||0)}</td><td>${esc(d.time||'')}</td></tr>`});
  document.getElementById('det').innerHTML=r;
  drawMap(s);
  let fp=''; for(const k in (s.fps||{})) fp+=`${esc(k)} ${s.fps[k].toFixed(1)} FPS &nbsp;`;
  document.getElementById('fps').innerHTML=fp;
  let c=''; for(const k in (s.counts||{})) c+=`<tr><td>${esc(k)}</td><td><b>${s.counts[k]}</b></td></tr>`;
  document.getElementById('counts').innerHTML=c;
  const n=(s.detections||[]).length, a=document.getElementById('alert');
  if(n>lastN){ a.style.display='block'; a.textContent='NEW OBJECT: '+s.detections[n-1].name+' at ('+f(s.detections[n-1].x)+', '+f(s.detections[n-1].y)+')'; }
  lastN=n;
  document.getElementById('log').textContent=(s.log||[]).join('\\n');
  document.getElementById('report').innerHTML=s.report?'<a style="color:#8ecae6" href="/report" target="_blank">Open mission report</a>':'';
  if(window.poll) document.getElementById('frame').src='/frame.jpg?'+Date.now();
 }catch(e){}
}
setInterval(tick,700); tick();
</script></body></html>"""


def _finite(o):
    """NaN / inf are not valid JSON (the browser would reject the whole status) -> None."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


class UIServer(object):
    def __init__(self, state, port=8090, title="UAV Mission Control", host="0.0.0.0"):
        self.state, self.port, self.title, self.host = state, port, title, host
        state.setdefault("_lock", threading.Lock())

    def start(self):
        state, title = self.state, self.title

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                p = self.path.split("?")[0]
                if p == "/":
                    if state.get("_web_page", True):
                        self._send(200, (PAGE % {"title": title}).encode(), "text/html; charset=utf-8")
                    else:                       # `ui.web_page: false`: no website, the BRICS Dashboard app is the UI
                        self._send(200, b"BRICS mission link: no web page. Open the BRICS Dashboard app.\n", "text/plain; charset=utf-8")
                elif p == "/status":
                    with state["_lock"]:
                        s = {k: v for k, v in state.items() if not k.startswith("_") and k != "frame_jpg"}
                        s["log"] = list(state.get("log", []))[-80:]
                    self._send(200, json.dumps(_finite(s), default=str).encode(), "application/json")
                elif p == "/frame.jpg":
                    with state["_lock"]:
                        jpg = state.get("frame_jpg")
                    if jpg:
                        self._send(200, jpg, "image/jpeg")
                    else:
                        self._send(404, b"", "text/plain")
                elif p == "/stream.mjpg":
                    self._stream()
                elif p == "/report" and state.get("report") and os.path.exists(state["report"]):
                    self._send(200, open(state["report"], "rb").read(), "text/html; charset=utf-8")
                else:
                    self._send(404, b"not found", "text/plain")

            def _stream(self):
                """Low-latency live view: every new frame is pushed over one open connection (MJPEG).
                A slow link skips frames instead of queueing them, so the picture never falls behind."""
                try:
                    self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024)
                    self.connection.settimeout(5.0)
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    last, t_sent = None, 0.0
                    while True:
                        with state["_lock"]:
                            jpg = state.get("frame_jpg")
                        now = time.time()
                        if jpg and (jpg is not last or now - t_sent > 1.0):     # resend every 1 s = keep-alive
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode()
                                             + b"\r\n\r\n" + jpg + b"\r\n")
                            self.wfile.flush()
                            last, t_sent = jpg, now
                        else:
                            time.sleep(0.008)
                except Exception:
                    pass                    # viewer closed the page / link dropped

            def do_POST(self):
                if self.path.startswith("/cmd"):
                    c = self.path.split("c=")[-1]
                    if c in ("start", "return", "abort", "land"):
                        with state["_lock"]:
                            state["command"] = c
                            state.setdefault("log", []).append("[ui] operator pressed %s" % c.upper())
                    self._send(200, b"ok", "text/plain")
                else:
                    self._send(404, b"", "text/plain")

        # On the TECHNIC image port 8080 belongs to web_video_server. If our port is taken, use the next free
        # one instead of crashing the mission, and say so loudly.
        first, err = self.port, None
        for p in range(first, first + 10):
            try:
                self.httpd = ThreadingHTTPServer((self.host, p), H)
                self.port = p
                break
            except OSError as e:
                err = e
        else:
            raise OSError("operator UI: ports %d-%d all in use (%s)" % (first, first + 9, err))
        if self.port != first:
            print("[ui] WARNING: port %d is in use - operator page moved to port %d" % (first, self.port))
        with state["_lock"]:
            state["ui_port"] = self.port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        print("[ui] operator page: http://<drone-ip>:%d  (drone Wi-Fi: http://10.42.0.1:%d)" % (self.port, self.port))
        return self

    def stop(self):
        self.httpd.shutdown()
