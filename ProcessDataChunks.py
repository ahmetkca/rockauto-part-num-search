import json
import pathlib
from typing import Generator, List
import csv
import xlsxwriter
import httpx
from tqdm import tqdm
import os
from stem import Signal
from stem.control import Controller
import socket
import socks
from config import TOR_PORT, TOR_PASSWORD, SOCKS5_PORT, NO_CONCURRENT
import time
import asyncio
controller = Controller.from_port(port=TOR_PORT)
pn_with_problem = []
results = []

async def connect_tor():
	socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', SOCKS5_PORT, True)
	socket.socket = socks.socksocket


async def renew_tor():
	controller.authenticate(TOR_PASSWORD)
	delay = controller.get_newnym_wait() * 2
	if delay < 15:
			delay = 15
	if not controller.is_newnym_available():
		print(f"Waiting {delay} seconds for new ip.")
		await asyncio.sleep(delay)
		controller.signal(Signal.NEWNYM)
	else:
		print(f"Waiting 1 seconds for new ip.")
		await asyncio.sleep(1)
		controller.signal(Signal.NEWNYM)
	return delay

FOLDER_NAME = "Butun_Bilgiler_COMPLETE"
try:
	os.mkdir(FOLDER_NAME)
except OSError as error:
    print(error)

def get_next_year(year_range: str) -> int:
	if len(year_range.split("-")) == 1:
		yield int(year_range.split("-")[0])
	else:
		from_year, to_year = (int(year) for year in year_range.split("-"))
		for year in range(from_year, to_year+1):
			yield year


def get_next_make_model_year(part_number, make_model_year_table: List[List[str]]) -> List[str]:
	for make, model, year_range in make_model_year_table:
		for year in get_next_year(year_range):
			yield (make, model, year)


async def download_image(client, url, part_number, index):
	ext = url.split(".")[-1]
	try:
		os.mkdir(f"{FOLDER_NAME}/{part_number}")
	except OSError as error:
		pass
	# print(f"Downloading {part_number}_{index}.{ext}...")
	try:
		with open(f"{FOLDER_NAME}/{part_number}/{part_number}_{index}.{ext}", 'wb') as download_file:
			async with client.stream("GET", url) as response:
				total = int(response.headers["Content-Length"])

				with tqdm(desc=f"{part_number}_{index}.{ext}", total=total, unit_scale=True, unit_divisor=1024, unit="B") as progress:
					num_bytes_downloaded = response.num_bytes_downloaded
					async for chunk in response.aiter_bytes():
						download_file.write(chunk)
						progress.update(response.num_bytes_downloaded - num_bytes_downloaded)
						num_bytes_downloaded = response.num_bytes_downloaded
	except httpx.HTTPError as err:
		pn_with_problem.append((url, part_number, index))
		# print(f"\nCouldn't download {part_number}_{index}.{ext}\n")
		return err
	else:
		# print(f"\n{part_number}_{index}.{ext} successfully downloaded.\n")
		results.append(f"{part_number}_{index}.{ext}")
		return f"{part_number}_{index}.{ext}"
	



async def main(loop, all_part_numbers_g):
	await renew_tor()
	await connect_tor()
	await asyncio.sleep(10)
	
	tasks = set()
	async with httpx.AsyncClient() as client:
		x = 0
		for part_number, part_info in all_part_numbers_g:
			for index, image_url in enumerate(part_info["images"]):
				if x != 0 and x % 20 == 0:
					await renew_tor()
					await connect_tor()
				if len(tasks) >= NO_CONCURRENT:
					done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
					# for task in done:
					# 	try:
					# 		task.result()
					# 	except Exception as e:
					# 		print(task.exception())
					# 	else:
					# 		print(task.result())
				tasks.add(loop.create_task(download_image(client, image_url, part_number, index)))
				x+=1
		done, pending = await asyncio.wait(tasks)
		# for task in done:
		# 	try:
		# 		task.result()
		# 	except Exception as e:
		# 		results.append(task.exception())
		# 	else:
		# 		results.append(task.result())
		with open(f"{FOLDER_NAME}/Image_Results.json", 'w') as outfile:
			json.dump(results, outfile, ensure_ascii=False, indent=4)
		with open(f"{FOLDER_NAME}/Images_Couldnt_Downloaded.json", 'w') as outfile:
			json.dump(pn_with_problem, outfile, ensure_ascii=False,  indent=4)

if __name__ == '__main__':
	part_numbers_from_csv = []
	with open("Butun_Bilgiler.csv") as csvfile:
		data = csv.DictReader(csvfile)
		for row in data:
			part_numbers_from_csv.append(row["Part Noi "].strip())
	all_part_numbers = {}
	i = 0
	script_path = pathlib.Path(__file__).parent.resolve()
	butun_bilgiler = script_path.joinpath("Butun_Bilgiler")
	chunks: List[pathlib.Path] = [x for x in butun_bilgiler.iterdir() if x.is_dir()]
	for chunk in chunks:
		for file in chunk.iterdir():
			if file.is_file() and file.suffix == '.json' and file.name.split(".")[0].split("_")[0] != "NOT":
				# print(file.absolute())
				with open(file.absolute(), 'r') as chunk_file:
					try:
						
						chunk_data_as_json = json.loads(chunk_file.read())
						i += len(chunk_data_as_json.keys())
						_from, _to = [int(_) for _ in file.name.split('.')[0].split('_')[-1].split("-")]
						print(f"{file.name} - {len(chunk_data_as_json.keys())} keys. Expected {(_to-1)-_from}")
						all_part_numbers = {**all_part_numbers, **chunk_data_as_json}
					except TypeError as e:
						print(e)
						print(file.name)
	not_founds = []
	for part_number_from_csv in part_numbers_from_csv:
		try:
			all_part_numbers[part_number_from_csv]
		except KeyError as e:
			print(f"{part_number_from_csv} ... Not Found")
			not_founds.append(part_number_from_csv)
		else:
			if type(all_part_numbers[part_number_from_csv]) is str and all_part_numbers[part_number_from_csv] == "Not Found":
				print(f"{part_number_from_csv} ... Not Found")
				del all_part_numbers[part_number_from_csv]
				not_founds.append(part_number_from_csv)
	
	with open("Butun_Bilgiler_Not_Founds.json", "w") as outfile:
		json.dump(not_founds, outfile, ensure_ascii=False, indent=4)
	print(f"Successfully processed part numbers {len(all_part_numbers.keys())}")
	with open("Centric_Part_Numbers.json", 'w') as outfile:
		json.dump(all_part_numbers, outfile, ensure_ascii=False, indent=4)
	exit()

	workbook = xlsxwriter.Workbook(f'{FOLDER_NAME}/{FOLDER_NAME}.xlsx')
	worksheet = workbook.add_worksheet()
	row = 0
	print(f"Successfully processed part numbers {len(all_part_numbers.keys())}")
	print(f"Number of unsuccessful part numbers {len(not_founds)}")
	exit()
	all_part_numbers_g = ((part_number, part_info) for part_number, part_info in all_part_numbers.items())
	del all_part_numbers
	loop = asyncio.get_event_loop()
	try:
		my_results = loop.run_until_complete(main(loop, all_part_numbers_g))
	except Exception as e:
		print(e)
	finally:
		loop.close()
		exit()
	x = 0
	
	for part_number, part_info in all_part_numbers_g:
		if x != 0 and x % 25 == 0:
			renew_tor()
			connect_tor()
		for i, image_url in enumerate(part_info["images"], 1):
			download_image(image_url, part_number, i)
			x+=1
		# if type(part_info["make_model_year"]) is str:
		# 	print(f"{part_number}\t\t{len(part_info['images'])}\t\t\t\t\t\t\t\t{part_info['oem_numbers']}")
		# 	worksheet.write(row, 0, part_number)
		# 	# worksheet.write(row, 1, make)
		# 	# worksheet.write(row, 2, model)
		# 	# worksheet.write(row, 3, year)
		# 	if part_info["oem_numbers"] != f"No OEM Number found for => ({part_number})":
		# 		worksheet.write(row, 4, part_info["oem_numbers"])
		# 	worksheet.write(row, 5, "VAR" if len(part_info["images"]) > 0 else "YOK")
		# 	row+=1
		# else:
		# 	for make, model, year in get_next_make_model_year(part_number, part_info["make_model_year"]):
		# 		print(f"{part_number}\t\t{len(part_info['images'])}\t\t{make}\t\t{model}\t\t{year}\t\t{part_info['oem_numbers']}")
		# 		worksheet.write(row, 0, part_number)
		# 		worksheet.write(row, 1, make)
		# 		worksheet.write(row, 2, model)
		# 		worksheet.write(row, 3, year)
		# 		if part_info["oem_numbers"] != f"No OEM Number found for => ({part_number})":
		# 			worksheet.write(row, 4, part_info["oem_numbers"])
		# 		worksheet.write(row, 5, "VAR" if len(part_info["images"]) > 0 else "YOK")
		# 		row+=1
	workbook.close()
