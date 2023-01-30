# speedtest-cli-faster

Faster command line SpeedTest.net client

This is a Python implementation of the older speedtest.net protocol for testing download and upload speeds. In order to achieve good performance on less powerful devices (e.g. Raspberry PI), it does not use 3rd party HTTP libraries, but implements the HTTP client itself. 1 GiB/sec on a Raspberry Pi 4 works just fine with this implementation.
