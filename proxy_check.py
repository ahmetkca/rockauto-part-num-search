import requests
import time
from stem import Signal
from stem.control import Controller
import socks
import socket

controller = Controller.from_port(port=9051)

def connect_tor():
	socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', 9050, True)
	socket.socket = socks.socksocket


def renew_tor():
	controller.authenticate("987654321Krpnr")
	delay = controller.get_newnym_wait() * 2
	print(f"Delay {delay} seconds")
	if not controller.is_newnym_available():
		if delay < 10:
			delay = 15
		_d = time.sleep(delay)
		if _d:
			controller.signal(Signal.NEWNYM)
	else:
		controller.signal(Signal.NEWNYM)
	return delay


def current_ip_address(session, delay):
	try:
		res = session.get("https://httpbin.org/ip")
		res.raise_for_status()
	except ResponseError as e:
		return "Unable to get ip address"
	else:
		return res.text
for i in range(10):
    delay = renew_tor()
    connect_tor()
    print(current_ip_address(requests, delay))

