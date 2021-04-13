import argparse
import asyncio
import re
import time
import urllib.parse
from collections import deque
from functools import partial

import requests
from lxml import etree as xml


class SlidingWindow:
    def __init__(self, window=1.0):
        self._data = deque()
        self.sum = 0
        self.window = window

    def _purge(self):
        cutoff = time.monotonic() - self.window
        while self._data and self._data[0][0] < cutoff:
            self.sum -= self._data.popleft()[1]

    def value(self):
        self._purge()
        return self.sum / self.window

    def add(self, value):
        self.sum += value
        self._data.append((time.monotonic(), value))
        self._purge()


class Monitor:
    def __init__(self, context, duration):
        self._context = context
        self._report_interval = 0.1
        self._runtime = duration
        self._next_report = time.monotonic() + self._report_interval
        self._end_time = time.monotonic() + self._runtime
        self._bytes_received = 0
        self.running = True
        self._sliding_window = SlidingWindow()

    def add(self, n):
        now = time.monotonic()
        self._sliding_window.add(n)
        if now >= self._end_time:
            if self.running:
                self.running = False  # Signal to shut down
                print()
        elif now >= self._next_report:
            print(
                f"\r{self._context}: {self._sliding_window.value()*8/1e6:.1f} mbit/sec", end="", flush=True)
            self._next_report += self._report_interval
        self._bytes_received += n


class DownloadSpeedProtocol(asyncio.Protocol):
    def __init__(self, url, monitor):
        self.monitor = monitor
        self.complete = asyncio.Future()
        self.url = url
        self.rx_buffer = bytearray()
        self.header_received = False
        self.content_length = None
        self.bytes_received = 0
        self.content_bytes_received = 0

    def connection_made(self, transport):
        self._transport = transport
        self.request()

    def request(self):
        req = f'GET {self.url.path}?{self.url.query} HTTP/1.1\r\nHost: {self.url.netloc}\r\nUser-Agent: x/1.0\r\n\r\n'.encode()
        self._transport.write(req)
        self.header_received = False

    def data_received(self, data):
        self.bytes_received += len(data)
        self.monitor.add(len(data))
        if self.header_received:
            self.content_bytes_received += len(data)
        else:
            if self.rx_buffer:
                self.rx_buffer.extend(data)
            else:
                self.rx_buffer = data
            crlfcrlf = self.rx_buffer.find(b'\r\n\r\n')
            if crlfcrlf > -1:
                self.header_received = True
                self.header = self.rx_buffer[0:crlfcrlf+2]
                content_length_match = re.search(
                    rb'Content-Length: (\d+)', self.header)
                if content_length_match:
                    self.content_length = int(content_length_match[1])
                else:
                    self.content_length = 0
                self.content_bytes_received = len(
                    self.rx_buffer) - crlfcrlf - 4

        if self.content_bytes_received == self.content_length:
            self.rx_buffer = bytearray()
            if self.monitor.running:
                self.request()
            else:
                self._transport.close()

    def eof_received(self):
        return False  # Let transport close itself

    def connection_lost(self, err):
        self._transport = None
        self.complete.set_result(self.bytes_received)


class UploadSpeedProtocol(asyncio.Protocol):
    def __init__(self, url, monitor):
        self.url = url
        self.complete = asyncio.Future()
        self._data = bytes(65536)
        self.bytes_sent = 0
        self.monitor = monitor
        self.header_received = False
        self.rx_buffer = bytearray()

    def connection_made(self, transport):
        self._transport = transport
        self.request()

    def request(self):
        req = f'POST {self.url.path} HTTP/1.1\r\nHost: {self.url.netloc}\r\nContent-Length: {len(self._data)}\r\nUser-Agent: x/1.0\r\n\r\n'.encode(
        )
        self._transport.write(req)
        self._transport.write(self._data)
        self.bytes_sent += len(req) + len(self._data)
        self.monitor.add(len(req) + len(self._data))
        self.header_received = False

    def data_received(self, data):
        if self.header_received:
            self.content_bytes_received += len(data)
        else:
            if self.rx_buffer:
                self.rx_buffer.extend(data)
            else:
                self.rx_buffer = data
            crlfcrlf = self.rx_buffer.find(b'\r\n\r\n')
            if crlfcrlf > -1:
                self.header_received = True
                self.header = self.rx_buffer[0:crlfcrlf+2]
                content_length_match = re.search(
                    rb'Content-Length: (\d+)', self.header)
                if content_length_match:
                    self.content_length = int(content_length_match[1])
                else:
                    self.content_length = 0
                self.content_bytes_received = len(
                    self.rx_buffer) - crlfcrlf - 4

        if self.content_bytes_received == self.content_length:
            self.rx_buffer = bytearray()
            if self.monitor.running:
                self.request()
            else:
                self._transport.close()

    def connection_lost(self, err):
        self._transport = None
        self.complete.set_result(self.bytes_sent)

    def eof_received(self):
        return False  # Let transport close itself


async def create_downloader(server, monitor):
    url = f'http://{server.host}/speedtest/random350x350.jpg?x={time.time()}'
    url = urllib.parse.urlparse(url)
    loop = asyncio.get_running_loop()
    _, protocol = await loop.create_connection(partial(DownloadSpeedProtocol, url, monitor), host=url.hostname, port=url.port)
    return protocol.complete


async def create_uploader(server, monitor):
    url = urllib.parse.urlparse(server.url)
    loop = asyncio.get_running_loop()
    c, t = await loop.create_connection(partial(UploadSpeedProtocol, url, monitor), host=url.hostname, port=url.port)
    return t.complete


async def main(server, duration):
    monitor = Monitor('Download', duration)
    downloaders = [await create_downloader(server, monitor) for _ in range(32)]
    return sum(await asyncio.gather(*downloaders))


async def upload_main(server, duration):
    monitor = Monitor('Upload', duration)
    downloaders = [await create_uploader(server, monitor) for _ in range(32)]
    return sum(await asyncio.gather(*downloaders))


def upload(server, duration):
    print(f"Connecting to {server.sponsor} ({server.name}, {server.country})")
    bytes_received = asyncio.run(upload_main(server, duration))


def download(server, duration):
    print(f"Connecting to {server.sponsor} ({server.name}, {server.country})")
    bytes_received = asyncio.run(main(server, duration))


class Server:
    def __init__(self, etree):
        self.url = etree.get('url')
        self.lat = etree.get('lat')
        self.lon = etree.get('lon')
        self.name = etree.get('name')
        self.country = etree.get('country')
        self.cc = etree.get('cc')
        self.id = int(etree.get('id'))
        self.host = etree.get('host')
        self.sponsor = etree.get('sponsor')


def retrieve_servers():
    text = requests.get(
        'http://c.speedtest.net/speedtest-servers.php', stream=True).text
    tree = xml.fromstring(text.encode())
    return [Server(node) for node in tree.xpath('//server')]


def list_servers():
    for server in retrieve_servers():
        print(f"{server.id}: {server.sponsor} ({server.name}, {server.country})")


def get_server(server_id=None):
    servers = retrieve_servers()
    if server_id:
        for server in servers:
            if server.id == server_id:
                return server
    else:
        return servers[0]


def real_main():
    parser = argparse.ArgumentParser(description='Test network speed')
    parser.set_defaults(command=None)
    parser.add_argument('--server', type=int, help='Server ID', default=None)
    parser.add_argument('--duration', type=float,
                        help='Duration of test', default=20.0)
    subparser = parser.add_subparsers()
    list_servers_parser = subparser.add_parser('list')
    list_servers_parser.set_defaults(command='list')
    download_parser = subparser.add_parser('download')
    download_parser.set_defaults(command='download')
    upload_parser = subparser.add_parser('upload')
    upload_parser.set_defaults(command='upload')
    opts = parser.parse_args()
    if opts.command == 'list':
        list_servers()
    elif opts.command == 'download':
        download(get_server(opts.server), opts.duration)
    elif opts.command == 'upload':
        upload(get_server(opts.server), opts.duration)
    elif opts.command is None:
        server = get_server(opts.server)
        download(server, opts.duration)
        upload(server, opts.duration)


if __name__ == '__main__':
    real_main()
