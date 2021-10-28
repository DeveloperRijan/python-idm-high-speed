import re
from reprint.reprint import print_line
import requests
import sys
import time
from collections import deque
from datetime import datetime, timedelta
from math import inf
from mmap import mmap
from pathlib import Path
from threading import Thread
from reprint import output

def timestring(sec):
    sec = int(sec)
    a = str(int(sec // 3600)).zfill(2)
    sec = sec % 3600
    b = str(int(sec // 60)).zfill(2)
    c = str(int(sec % 60)).zfill(2)
    return '{0}:{1}:{2}'.format(a, b, c)

class downloader:

    def __init__(self, url, filepath, num_connections=32, overwrite=False):
        self.mm = None
        self.count = 0
        self.recent = deque([0] * 20, maxlen=20)
        self.download(url, filepath, num_connections, overwrite)
    
    def multidown(self, url, start, end):
        r = requests.get(url, headers={'range': 'bytes={0}-{1}'.format(start, end-1)}, stream=True)
        i = start
        for chunk in r.iter_content(1048576):
            if chunk:
                self.mm[i: i+len(chunk)] = chunk
                self.count += len(chunk)
                i += len(chunk)
    
    def singledown(self, url, path):
        with requests.get(url, stream=True) as r:
            with path.open('wb') as file:
                for chunk in r.iter_content(1048576):
                        if chunk:
                            self.count += len(chunk)
                            file.write(chunk)
    
    def download(self, url, filepath, num_connections=32, overwrite=False):
        singlethread = False
        threads = []
        bcontinue = False
        filepath = filepath.replace('\\', '/')
        if (not re.match('^[a-zA-Z]:/(((?![<>:"/|?*]).)+((?<![ .])/)?)*$', filepath) or 
            not Path(filepath[:3]).exists()):
            print('Invalid windows file path has been inputted, process will now stop.')
            return
        path = Path(filepath)
        if not path.exists():
            bcontinue = True
        else:
            if path.is_file():
                if overwrite:
                    bcontinue = True
                else:
                    while True:
                        answer = input(f'`{filepath}` already exists, do you want to overwrite it? \n(Yes, No):').lower()
                        if answer in ['y', 'yes', 'n', 'no']:
                            if answer.startswith('y'):
                                bcontinue = True
                            break
                        else:
                            print('Invalid input detected, retaking input.')
        if not bcontinue:
            print(f'Overwritting {filepath} has been aborted, process will now stop.')
            return
        bcontinue = False
        head = requests.head(url)
        if head.status_code == 200:
            bcontinue = True
        else:
            for i in range(5):
                print(f'Failed to connect server, retrying {i + 1} out of 5')
                head = requests.head(url)
                if head.status_code == 200:
                    print(f'Connection successful on retry {i + 1}, process will now continue.')
                    bcontinue = True
                    break
                else:
                    print(f'Retry {i + 1} out of 5 failed to connect, reattempting in 1 second.')
                    time.sleep(1)
        if not bcontinue:
            print("Connection can't be established, can't download target file, process will now stop.")
            return
        folder = '/'.join(filepath.split('/')[:-1])
        Path(folder).mkdir(parents=True, exist_ok=True)
        headers = head.headers
        total = headers.get('content-length')
        if not total:
            print(f'Cannot find the total length of the content of {url}, the file will be downloaded using a single thread.')
            started = datetime.now()
            print('Task started on %s.' % started.strftime('%Y-%m-%d %H:%M:%S'))
            th = Thread(target=self.singledown, args=(url, path))
            threads.append(th)
            th.start()
            total = inf
            singlethread = True
        else:
            total = int(total)
            code = requests.head(url, headers={'range':'bytes=0-100'}).status_code
            if code != 206:
                print('Server does not support the `range` parameter, the file will be downloaded using a single thread.')
                started = datetime.now()
                print('Task started on %s.' % started.strftime('%Y-%m-%d %H:%M:%S'))
                th = Thread(target=self.singledown, args=(url, path))
                threads.append(th)
                th.start()
                singlethread = True
            else:
                print("Multi downloading starting")
                path.touch()
                file = path.open(mode='wb')
                file.seek(total - 1)
                file.write(b'\0')
                file.close()
                file = path.open(mode='r+b')
                self.mm = mmap(file.fileno(), 0)
                segment = total / num_connections
                started = datetime.now()
                print('Task started on %s.' % started.strftime('%Y-%m-%d %H:%M:%S'))
                for i in range(num_connections):
                    th = Thread(target=self.multidown, args=(url, int(segment * i), int(segment * (i + 1))))
                    threads.append(th)
                    th.start()
        downloaded = 0
        totalMiB = total / 1048576
        speeds = []
        interval = 0.025
        with output(initial_len=4, interval=0) as dynamic_print:
            while True:
                status = sum([i.is_alive() for i in threads])
                downloaded = self.count
                self.recent.append(downloaded)
                done = int(100 * downloaded / total)
                doneMiB = downloaded / 1048576
                gt0 = len([i for i in self.recent if i])
                if not gt0:
                    speed = 0
                else:
                    recent = list(self.recent)[20 - gt0:]
                    if len(recent) == 1:
                        speed = recent[0] / 1048576 / interval
                    else:
                        diff = [b - a for a, b in zip(recent, recent[1:])]
                        speed = sum(diff) / len(diff) / 1048576 / interval
                speeds.append(speed)
                nzspeeds = [i for i in speeds if i]
                if nzspeeds:
                    minspeed = min(nzspeeds)
                else:
                    minspeed = 0
                maxspeed = max(speeds)
                meanspeed = sum(speeds) / len(speeds)
                remaining = totalMiB - doneMiB
                dynamic_print[0] = '[{0}{1}] {2}'.format(
                    '\u2588' * done, '\u00b7' * (100-done), str(done)) + '% completed'
                dynamic_print[1] = '{0:.2f} MiB downloaded, {1:.2f} MiB total, {2:.2f} MiB remaining, download speed: {3:.2f} MiB/s'.format(
                    doneMiB, totalMiB, remaining, speed)
                now = datetime.now()
                elapsed = timestring((now - started).seconds)
                if meanspeed and total != inf:
                    eta = timestring(remaining / meanspeed)
                else:
                    eta = '99:59:59'
                dynamic_print[2] = 'Minimum speed: {0:.2f} MiB/s, average speed: {1:.2f} MiB/s, maximum speed: {2:.2f} MiB/s'.format(minspeed, meanspeed, maxspeed)
                dynamic_print[3] = 'Task started on {0}, {1} elapsed, ETA: {2}'.format(
                    started.strftime('%Y-%m-%d %H:%M:%S'), elapsed, eta)
                if status == 0:
                    ended = datetime.now()
                    if not singlethread:
                        self.mm.close()
                    break
                time.sleep(interval)
        time_spent = (ended - started).seconds
        meanspeed = sum(speeds) / len(speeds)
        print('Task completed on {0}, total time elapsed: {1}, average speed: {2:.2f} MiB/s'.format(
            ended.strftime('%Y-%m-%d %H:%M:%S'), timestring(time_spent), meanspeed))

if __name__ == '__main__':
    fileURL = "http://212.183.159.230/1GB.zip"
    fileSavePath = "C:\\save_file_donwloaded\\testzip2.zip"
    d = downloader(fileURL, fileSavePath)
   