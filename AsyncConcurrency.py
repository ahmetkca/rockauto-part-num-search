import asyncio
import socket
import socks
import json
import time
from asyncio import Task
from typing import List, Set
import sys

import httpx
from stem import Signal
from stem.control import Controller

from config import NO_CONCURRENT, TOR_PASSWORD, TOR_PORT, SOCKS5_PORT, STEP_LIMIT
import csv

from copy_main import AutoPart, logging
import os
FROM = int(sys.argv[1])
TO = int(sys.argv[2])
FOLDER_NAME = "Butun_Bilgiler"
FILE_FRONT = "CHECKING_AGAIN"
FILE_NAME = f"{FILE_FRONT}_{FROM}-{TO}"
os.mkdir(f"{FOLDER_NAME}/{FILE_NAME}")
logging.basicConfig(
	format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
	datefmt='%Y-%m-%d,%H:%M:%S',
	level=logging.INFO,
	handlers=[
		logging.FileHandler(filename=f"{FOLDER_NAME}/{FILE_NAME}/rockauto_{FROM}-{TO}.log", mode="w"),
		logging.StreamHandler()
	],
	encoding='utf-8'
)
controller = Controller.from_port(port=TOR_PORT)


async def connect_tor():
	await asyncio.sleep(0.1)
	socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', SOCKS5_PORT, True)
	socket.socket = socks.socksocket


async def renew_tor():
	logging.info("LOOKING FOR NEW IP...")
	controller.authenticate(TOR_PASSWORD)
	delay = controller.get_newnym_wait() * 2
	if not controller.is_newnym_available():
		if delay < 10:
			delay = 15
		_d = await asyncio.sleep(delay, result=True)
		logging.info(f"New ip address is not available yet. Waiting for {delay} seconds.")
		if _d:
			controller.signal(Signal.NEWNYM)
	else:
		logging.info("New ip address is available.")
		controller.signal(Signal.NEWNYM)
	return delay


async def current_ip_address(session, delay):
	logging.info(f"Waited {delay} seconds.")
	try:
		res = await session.get("https://api.ipify.org/")
		res.raise_for_status()
	except httpx.HTTPError as e:
		logging.error("Unable to display ip...")
		return "Unable to get ip address"
	else:
		return res.text


# async def test_ip_rotatio():
# 	ua: UserAgent = UserAgent()
# 	headers = {"User-Agent": ua.random}
# 	session = httpx.AsyncClient(trust_env=True, headers=headers)
# 	for i in range(5):
# 		await renew_tor()
# 		await connect_tor()
# 		ip_addr = await current_ip_address(session)
# 		print(ip_addr)
# 	await session.aclose()
# asyncio.run(test_ip_rotatio())
# exit()


async def main(loop: asyncio.AbstractEventLoop):
	results = []
	not_founds = []
	tasks: Set = set()
	part_numbers: List[AutoPart] = []
	with open(f"{FOLDER_NAME}_Not_Founds.json", 'r') as jsonfile:
		data = json.loads(jsonfile.read())
		for part_num in data:
			part_numbers.append(AutoPart(part_num))
	# exit()
	
	# with open("Butun_Bilgiler.csv") as csvfile:
	# 	logging.info(f"Reading part numbers...")
	# 	data = csv.DictReader(csvfile)
	# 	for row in data:
	# 		part_numbers.append(AutoPart(row["Part Noi "].strip()))
	
	part_numbers = [*part_numbers[FROM: TO]]
	
	logging.info(f"{len(part_numbers)} part numbers found...")
	current_index: int = 0
	limits = httpx.Limits(max_keepalive_connections=None, max_connections=None)
	async with httpx.AsyncClient(limits=limits) as session:
		delay = await renew_tor()
		await asyncio.wait({loop.create_task(connect_tor())})
		ip_addr = await current_ip_address(session, delay)
		logging.info(f"... NEW IP ADDRESS IS ... ({ip_addr})")
		while current_index < len(part_numbers):
			if len(tasks) >= NO_CONCURRENT:
				done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
				# task: Task = next(iter(_done))
				for task in done:
					try:
						task.result()
					except Exception as e:
						logging.error(f"Error: occured while processing finished tasks. {e}")
						results.append(task.exception())
					else:
						results.append(task.result())
				# excp = task.exception()
				# if excp is not None:
				# 	results.append(excp)
				# 	not_founds.append(part_numbers[current_index].part_number)
				# else:
				# 	results.append(task.result())
			tasks.add(loop.create_task(part_numbers[current_index].get_all_info(session)))
			logging.info(f"""{part_numbers[current_index].part_number} has been added to the task list.
							So far ({current_index + 1}) Part Number has been added to the task list.""")
			if current_index != 0 and current_index % 18 == 0:
				# logging.info(f"... BLOCKING PROCESS FOR 10 seconds ...")
				# time.sleep(10)
				delay = await renew_tor()
				await asyncio.wait({loop.create_task(connect_tor())})
				ip_addr = await current_ip_address(session, delay)
				# ip_addr = await current_ip_address(session)
				logging.info(f"NEW IP ADDRESS IS ... ({ip_addr})")
			current_index += 1
		if len(tasks) <= 0:
			return results
		done, pending = await asyncio.wait(tasks)
		t: Task
		for t in done:
			try:
				t.result()
			except Exception as e:
				logging.error(f"Error: occured while processing finished tasks. {e}")
				results.append(t.exception())
			else:
				results.append(t.result())
			# excp = t.exception()
			# if excp is not None:
			# 	results.append(excp)
			# else:
			# 	results.append(t.result())
		# await session.aclose()
		with open(f"{FOLDER_NAME}/{FILE_NAME}/NOT_FOUNDS_{FROM}-{TO}.json", "w", encoding="utf-8") as outfilex:
			logging.info(f"Writing to json file...")
			json.dump(not_founds, outfilex, ensure_ascii=False, indent=4)
		return results
	


if __name__ == '__main__':
	start_time = time.time()
	my_loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

	try:
		
		my_results = my_loop.run_until_complete(main(my_loop))
		# to_Json = []
		to_Json = {}
		for result in my_results:
			tojson = getattr(result, "toJSON", None)
			if callable(tojson):
				to_Json = {**to_Json, **result.toJSON()}
			else:
				print(result)
				logging.info("Result from Tasks returned is neither AutoPart or PartNumberNotFound ConnError")
		# to_Json.append(result.toJSON())
		with open(f"{FOLDER_NAME}/{FILE_NAME}/{FILE_FRONT}_{FOLDER_NAME}_{FROM}-{TO}.json", "w", encoding="utf-8") as outfile:
			logging.info(f"Writing to json file...")
			json.dump(to_Json, outfile, ensure_ascii=False, indent=4)
		
		# with open("next_from_to.json", 'w') as outfile:
		# 	json.dump({"from": TO, "to": TO + STEP_LIMIT}, outfile, ensure_ascii=False, indent=4)
	except ValueError as e:
		print(e)
		logging.error(e)
	finally:
		logging.info("--- %s seconds ---" % (time.time() - start_time))
		my_loop.close()
