import os
import subprocess

from flask import Response


class ProcessWrapper:
    def __init__(self, process, done):
        self.process = process
        self.done = done
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.done()
        if self.process.poll() is not None:
            return
        self.process.stdout.close()
        self.process.terminate()
        self.process.wait()

    def __iter__(self):
        return self

    def __del__(self):
        self.close()

    def __next__(self):
        try:
            data = self.process.stdout.readline()
        except Exception:
            self.close()
            raise StopIteration()
        if data:
            return data
        self.close()
        raise StopIteration()


def send_process(args, pid_file):
    def tear_down_proc():
        try:
            os.unlink(pid_file)
        except OSError:
            pass

    if os.path.exists(pid_file):
        with open(pid_file) as f:
            pid = f.read().strip()
        if pid and os.path.exists("/proc/%s/status" % pid):
            return Response("Scanner is already running.\n", mimetype="text/plain")
    process = subprocess.Popen(
        args, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    with open(pid_file, "w") as f:
        f.write(str(process.pid))
    return Response(ProcessWrapper(process, tear_down_proc), direct_passthrough=True, mimetype="text/plain")
