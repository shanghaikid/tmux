#!/usr/bin/env python3
"""Isolated tmux/PTTY protocol, lifetime, client rendering and memory acceptance."""
import base64
import json
import os
from pathlib import Path
import pty
import select
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import tty


def child(path):
    server = socket.socket(socket.AF_UNIX)
    server.bind(path)
    server.listen()
    while True:
        conn, _ = server.accept()
        with conn:
            request = json.loads(conn.makefile('rb').readline())
            raw = base64.b64decode(request['bytes'])
            if request.get('query'):
                settings = termios.tcgetattr(0)
                tty.setraw(0)
                try:
                    os.write(1, raw)
                    response = b''
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        if select.select([0], [], [], .1)[0]:
                            response += os.read(0, 8192)
                            if response.endswith((b'\x1b\\', b'\x07')): break
                    response = base64.b64encode(response).decode()
                finally:
                    termios.tcsetattr(0, termios.TCSANOW, settings)
            else:
                for offset in range(0, len(raw), 65536):
                    view = memoryview(raw)[offset:offset+65536]
                    while view:
                        view = view[os.write(1, view):]
                response = 'ok'
            conn.sendall(json.dumps(response).encode()+b'\n')


def main(binary):
    with tempfile.TemporaryDirectory(prefix='tmux-osc7501-') as directory:
        root = Path(directory)
        server_socket, control = root/'tmux.sock', root/'child.sock'
        client = None
        env = dict(os.environ, TERM='xterm-256color')
        env.pop('TMUX', None)
        def command(*args):
            return subprocess.check_output([binary, '-S', str(server_socket), *args], env=env, text=True).strip()
        def status(target='acceptance:0.0'):
            return command('display-message', '-p', '-t', target, '#{pane_program_status}')
        def send(raw, query=False):
            with socket.socket(socket.AF_UNIX) as conn:
                conn.settimeout(20)
                conn.connect(str(control))
                conn.sendall(json.dumps({'bytes':base64.b64encode(raw).decode(), 'query':query}).encode()+b'\n')
                return json.loads(conn.makefile('rb').readline())
        def wait(expected):
            deadline = time.monotonic()+3
            while time.monotonic() < deadline:
                actual = status()
                if actual == expected: return
                time.sleep(.01)
            raise AssertionError((expected, actual))
        def rss():
            pid = command('display-message', '-p', '#{pid}')
            return int(subprocess.check_output(['ps', '-o', 'rss=', '-p', pid], text=True))
        try:
            command('-f', '/dev/null', 'new-session', '-d', '-s', 'acceptance', sys.executable, __file__, '--child', str(control))
            command('set-option', '-w', 'remain-on-exit', 'on')
            command('set-option', '-w', 'window-status-current-format', '#{pane_program_status} #{pane_id} acceptance')
            for _ in range(100):
                if control.exists(): break
                time.sleep(.03)
            assert control.exists()
            client, master = pty.fork()
            if client == 0:
                os.execve(binary, [binary, '-S', str(server_socket), 'attach-session', '-t', 'acceptance'], env)
            time.sleep(.1)
            send(b'\x1b]7501;state=working:app=build:progress=42\x1b\\')
            wait('[working 42%]')
            rendered = b''
            deadline = time.monotonic()+2
            while time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]: rendered += os.read(master, 65536)
                if b'[working 42%]' in rendered: break
            assert b'[working 42%]' in rendered, repr(rendered)
            for end in (b'\x1b\\', b'\x07'):
                reply = base64.b64decode(send(b'\x1b]7501;?'+end, True))
                assert reply == b'\x1b]7501;?:states=idle,working,done,blocked,error:kinds=permission,question,auth'+end, repr(reply)
            send(b'\x1b]7501;state=blocked:id=child:kind=permission\x07'); wait('[permission]')
            send(b'\x1b]7501;state=clear:id=child\x07'); wait('[working 42%]')
            send(b'\x1b]7501;state=done:id=result\x07\x1b]133;A\x07'); wait('[done]')
            send(b'\x1b[?1049h\x1b[?1049l\x1b[!p'); wait('[done]')
            send(b'\x1b]7501;state=error:msg=____\x07\x1b]7501;state=error\x18\x1b]7501;state=error\x1bX')
            time.sleep(.1); wait('[done]')
            before = rss()
            send(b'\x1b]7501;state=working:x='+b'x'*32_000_000+b'\x1b\\')
            wait('[done]')
            growth = rss()-before
            assert growth < 4096, f'server RSS grew {growth} KiB on discarded report'
            send(b'\x1bc'); wait('')
            send(b'\x1b]7501;state=done\x07'); wait('[done]')
            pane_pid = int(command('display-message', '-p', '-t', 'acceptance:0.0', '#{pane_pid}'))
            os.kill(pane_pid, signal.SIGTERM)
            time.sleep(.15); wait('[done]')
            print(json.dumps({'result':'PASS', 'checks':['raw reports','both query replies','real client status rendering','hierarchy/clear','screen independence','soft/full reset','prompt/exit lifetime','invalid/cancelled/oversized reports'], 'discarded_report_bytes':32_000_000, 'server_rss_growth_kib':growth}, indent=2))
        finally:
            try: command('kill-server')
            except subprocess.CalledProcessError: pass
            if client:
                os.close(master)
                try: os.waitpid(client, 0)
                except ChildProcessError: pass

if __name__ == '__main__':
    if sys.argv[1:2] == ['--child']: child(sys.argv[2])
    else: main(os.path.abspath(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'tmux'))
