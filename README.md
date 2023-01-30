# speedtest-cli-faster

Faster command line SpeedTest.net client

This is a Python implementation of the older speedtest.net protocol for testing download and upload speeds. In order to achieve good performance on less powerful devices (e.g. Raspberry PI), it does not use 3rd party HTTP libraries, but implements the HTTP client itself. 1 GB/sec on a Raspberry Pi 4 works just fine with this implementation.

The official [speedtest-cli](https://www.speedtest.net/apps/cli) can't even max out my 1 GB/sec connection on a PC connected directly to the internet.

## Comparison

CPU: Intel Pentium Silver N6005. Link speed: 1000 Mb/s

Same speedtest server was used.

### Official speedtest-cli: 

```
Testing download speed................................................................................
Download: 698.30 Mbit/s
Testing upload speed......................................................................................................
Upload: 370.45 Mbit/s
```

### My speedtest-cli-faster:

```
Download: 927.4 mbit/sec
Upload: 938.0 mbit/sec
```
