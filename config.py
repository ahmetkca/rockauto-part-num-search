import random

PART_NUMBER_SEARCH_URL: str = "https://www.rockauto.com/en/partsearch/?partnum={}"
ROCKAUTO_IMG_URL_BASE = "https://www.rockauto.com{}"
MAKE_MODEL_YEAR_URL = "https://www.rockauto.com/catalog/catalogapi.php"
PROXY = None
NO_CONCURRENT = 2
SLEEP = lambda : random.choices(
	[0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08],
	weights=(5, 5, 10, 15, 50, 5, 5, 5),
	k=1)[0]
PROXIES = {
	"http://": "socks5://127.0.0.1:9050",
	"https://": "socks5://127.0.0.1:9050"
}
TOR_PASSWORD = "987654321Krpnr"
TOR_PORT = 9051
SOCKS5_PORT = 9050

STEP_LIMIT = 25