# Занимает порты 8000-8014 и поднимает app.py на 8015 (свободный поиск 8000+).
import socket, subprocess, sys, time, urllib.request, os
socks=[]
for p in range(8000,8015):
    s=socket.socket()
    try: s.bind(("127.0.0.1",p)); s.listen(1); socks.append(s)
    except OSError: pass
env=dict(os.environ); pass  # локально без пароля
proc=subprocess.Popen([sys.executable,"app.py"],cwd="/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип/ui",env=env)
print("PID",proc.pid,flush=True)
for i in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:8015/api/ping",timeout=1); break
    except Exception: time.sleep(0.5)
print("up",flush=True)
proc.wait()
