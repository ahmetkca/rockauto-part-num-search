import abc
from asyncio.tasks import current_task
import json
import logging
import pathlib
from typing import Generator, List
import csv
from fake_useragent.fake import UserAgent
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
import sys
from bs4 import BeautifulSoup
NO_CONCURRENT = 50
ua: UserAgent = UserAgent()

class IpChanger:
	def __init__(self):
		self.counter = 0
		self.controller = Controller.from_port(port=TOR_PORT)
		self.is_changing = False

	async def connect_tor(self):
		socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', SOCKS5_PORT, True)
		socket.socket = socks.socksocket


	async def renew_tor(self):
		await asyncio.sleep(0.00001)
		if self.is_changing:
			return
		self.is_changing = True
		self.controller.authenticate(TOR_PASSWORD)
		delay = self.controller.get_newnym_wait() * 2
		if delay < 15:
				delay = 15
		if not self.controller.is_newnym_available():
			print(f"\nWaiting {delay} seconds for new ip.\n")
			await asyncio.sleep(delay)
			self.controller.signal(Signal.NEWNYM)
		else:
			print(f"\nWaiting 1 seconds for new ip.\n")
			await asyncio.sleep(1)
			self.controller.signal(Signal.NEWNYM)
		self.is_changing = False
		return delay

	async def increment_counter(self):
		await asyncio.sleep(0)
		self.counter+=1

	async def change_ip(self):
		if self.counter % 1000 != 0:
			await asyncio.sleep(0)
			return
		print("\n... CHANGING IP ...\n")
		await self.renew_tor()
		await self.connect_tor()
# global_ip_changer = IpChanger()


class ImageDownloadManager:
	BASE_URL = "https://www.showmethepartsdb3.com/BIN/images/"
	BASE_IMAGE_URL = "https://www.showmethepartsdb3.com"

	def __init__(self, local_folder_name):
		self.local_folder_name = local_folder_name
		try:
			os.mkdir(local_folder_name)
		except OSError as e:
			print(e)

	@abc.abstractclassmethod
	def get_part_number_from_image_name(self, image_name):
		# raise Exception("This is a abstract method you need to implement this.")
		...

	async def get_image_names(self, client):
		"""Get all image names from folder url where all the images lives"""
		headers = {"User-Agent": ua.random}
		print(f"Fetching all images for {self.local_folder_name}")
		res = await client.get(f"{ImageDownloadManager.BASE_URL}{self.local_folder_name}", timeout=120, headers=headers)
		print(f"Successfully fetched all images for {self.local_folder_name}")
		soup: BeautifulSoup = BeautifulSoup(res.text, 'html.parser')
		pre = soup.find("pre")
		print(f"There are {len(pre.findAll('a'))-1} images for {self.local_folder_name}")
		self.total_length = len(pre.findAll('a'))-1
		input("Enter any key to continue...")
		current_tag = pre.findNext("a")
		c = 1
		while current_tag is not None:
			# if current_tag.name != "a" or current_tag.text == "[To Parent Directory]":
			# 	continue
			image_name = current_tag.text
			part_number = self.get_part_number_from_image_name(image_name)
			href = current_tag.get("href")
			yield (part_number, image_name, href, c)
			c+=1
			await asyncio.sleep(0)
			current_tag = current_tag.findNext("a")
			
		

	async def download_image(self, client, image_url, image_name, part_number, index):
		"""Download image based on given url (image_url) and save it as given name (file_name)
        """
		part_number_folder_path = f"{self.local_folder_name}/{part_number}"
		try:
			os.mkdir(part_number_folder_path)
		except OSError as error:
			pass
		image_path = f"{part_number_folder_path}/{image_name}"
		headers = {"User-Agent": ua.random}
		try:
			with open(image_path, 'wb') as download_file:
				async with client.stream("GET", f"{ImageDownloadManager.BASE_IMAGE_URL}{image_url}", headers=headers) as response:
					total = int(response.headers["Content-Length"])
					response.raise_for_status()
					with tqdm(desc=f"Status={response.status_code}:{index}/{self.total_length}#{part_number}:{image_name}", total=total, unit_scale=True, unit_divisor=1024, unit="B") as progress:
						num_bytes_downloaded = response.num_bytes_downloaded
						async for chunk in response.aiter_bytes():
							download_file.write(chunk)
							progress.update(response.num_bytes_downloaded - num_bytes_downloaded)
							num_bytes_downloaded = response.num_bytes_downloaded
		except httpx.HTTPError as err:
			return (self.local_folder_name, part_number, image_url)
		else:
			return (self.local_folder_name, part_number, image_url)

	async def download_all(self, loop):
		successfulls, failures = [], []
		tasks = set()
		limits = httpx.Limits(max_keepalive_connections=int(NO_CONCURRENT/2)+5, max_connections=NO_CONCURRENT+5)
		async with httpx.AsyncClient(limits=limits) as client:
			async for part_number, image_name, href, index in self.get_image_names(client):
				# await global_ip_changer.change_ip()
				if len(tasks) >= NO_CONCURRENT:
					done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
					for task in done:
						try:
							task.result()
						except Exception as e:
							print(e)
							failures.append(task.exception())
						else:
							successfulls.append(task.result())
				tasks.add(loop.create_task(self.download_image(
					client=client, 
					image_url=href,
					image_name=image_name,
					part_number=part_number,
					index=index)))
				# await global_ip_changer.increment_counter()
			done, tasks = await asyncio.wait(tasks)
			for task in done:
				try:
					task.result()
				except Exception as e:
					failures.append(task.exception())
				else:
					successfulls.append(task.result())
			return (self.local_folder_name, successfulls, failures)
			


class GSP(ImageDownloadManager):
	def __init__(self, local_folder_name):
		super().__init__(local_folder_name)

	def get_part_number_from_image_name(self, image_name):
		part_number = image_name.split(".")[0].replace("_", "|").replace(" ", "|")
		part_number = part_number.replace("-", "|")
		part_number = part_number.split("|")[0]
		return part_number


class FCS(ImageDownloadManager):
	def __init__(self, local_folder_name):
		super().__init__(local_folder_name)

	def get_part_number_from_image_name(self, image_name):
		part_number = image_name.replace('.', "|").replace('_', "|").replace('+', "|").split("|")[0]
		if part_number[-1] == "L" or part_number[-1] == "R":
			return part_number[:-1]
		return part_number



class Centric(ImageDownloadManager):
	def __init__(self, local_folder_name, centric_part_numbers_file):
		super().__init__(local_folder_name)
		self.centric_part_numbers_file = centric_part_numbers_file

	async def get_image_names_from_image_links(self, image_links):
		for image_link in image_links:
			yield image_link.split('/')[-1]
			await asyncio.sleep(0)

	async def get_image_names(self, client=None):
		with open(f"{self.centric_part_numbers_file}.json", 'r') as jfile:
			centric_parts = json.load(jfile)
			self.total_length = len(centric_parts.items())
			for _, part_info in centric_parts.items():
				self.total_length += len(part_info["images"])
			print(f"There are total {self.total_length} images to download.")
			input("Enter any key to continue...")
			centric_parts = ((part_number, part_info["images"]) for part_number, part_info in centric_parts.items())
			c = 1
			for part_number, image_links in centric_parts:
				async for image_name in self.get_image_names_from_image_links(image_links):
					# print(f"{part_number} : {image_name} : {f'/BIN/images/Centric/{image_name}'} : {c}")
					yield (part_number, image_name, f"/BIN/images/Centric/{image_name}", c)
					await asyncio.sleep(0)
					c+=1




async def main(loop):
	# gsp = GSP("GSP")
	# fcs = FCS("FCS")
	centric = Centric("Centric", "Centric_Part_Numbers")
	# await centric.get_image_names()
	# exit()
	tasks = set()
	
	
	# tasks.add(loop.create_task(gsp.download_all(loop)))
	# tasks.add(loop.create_task(fcs.download_all(loop)))
	tasks.add(loop.create_task(centric.download_all(loop)))
	done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
	for task in done:
		try:
			print("1 Task finished.")
			task.result()
		except Exception as e:
			print(e)
			print(task.exception())
		else:
			brand_name, successfulls, failures = task.result()
			print(f"{brand_name} has been finished.")
			with open(f"{brand_name}/results.json", 'w') as outfile:
				json.dump({"successfulls": successfulls, "failures": failures}, outfile, ensure_ascii=False, indent=4)
		
if __name__ == '__main__':
	# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	loop = asyncio.get_event_loop()
	try:
		my_results = loop.run_until_complete(main(loop))
	except Exception as e:
		print(e)
	finally:
		# loop.close()
		pass
		# exit()