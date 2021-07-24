import pprint
from abc import abstractmethod
from typing import List, Optional
import bs4
from bs4 import BeautifulSoup, ResultSet
import re
import json
from config import PART_NUMBER_SEARCH_URL, ROCKAUTO_IMG_URL_BASE, MAKE_MODEL_YEAR_URL, PROXY
import asyncio
from aiohttp import ClientSession, ClientConnectorError, ClientResponseError, TCPConnector
import logging

logging.basicConfig(
	format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
	datefmt='%Y-%m-%d,%H:%M:%S',
	level=logging.INFO,
	handlers=[
		logging.FileHandler(filename="rockauto.log", mode="w"),
		logging.StreamHandler()
	],
	encoding='utf-8'
)

Url = str


class MyToJson:
	@abstractmethod
	def toJSON(self):
		pass


class NotFoundList:
	def __init__(self):
		self.not_found_part_numbers = set()
	
	def add(self, part_number):
		self.not_found_part_numbers.add(part_number)
	
	def toJSON(self):
		to_dict = {}
		for part_num in self.not_found_part_numbers:
			to_dict[part_num] = "Not Found"


class PartNumberNotFound(Exception, MyToJson):
	def __init__(self, value):
		self.value = value
		message = f"Part number {value} is NOT Found."
		super().__init__(message)
	
	def toJSON(self):
		return {
			self.value: "Not Found"
		}


class FormDataError(Exception):
	def __init__(self):
		message = f"Form data couldn't processed thus can't make post request for Make Model Year"
		super().__init__(message)


'''
    Checks given attribute before going forward with the given function
    
    if given attribute is not found or is not a list and its length is 0 then
        raises PartNumberNotFound exception
'''


def check_part_number(attr):
	def _check_part_number(f):
		def wrapper(self, *args, **kwargs):
			try:
				if getattr(self, attr) is None or (type(getattr(self, attr)) is list and len(getattr(self, attr)) == 0):
					logging.error(
						f"No HTML tag found for ... ({self.part_number}) thus can't get make model year, images or oem numbers!!!")
					raise PartNumberNotFound(getattr(self, "part_number"))
			except AttributeError:
				raise PartNumberNotFound(getattr(self, "part_number"))
			return f(self, *args, **kwargs)
		
		return wrapper
	
	return _check_part_number


'''
    Make sure to call get_make_model_year function before calling given function

    if form_data can't be processed then
        raises FormDataError exception
'''


def make_sure_form_data():
	def _make_sure_form_data(f):
		def wrapper(self, *args, **kwargs):
			logging.info(f"Form data is processing ... ({self.part_number})")
			form_data = self.get_make_model_year_form_data()
			if form_data is None or len(form_data.to_dict().keys()) == 0:
				logging.error(f"No form data created for ... ({self.part_number}) thus can't get make mode year!!!")
				raise FormDataError
			return f(self, *args, **kwargs)
		
		return wrapper
	
	return _make_sure_form_data


class AutoPart(MyToJson):
	def __init__(self, part_number: str):
		self.part_number: str = part_number
	
	async def get_part_number(self, session: ClientSession):
		try:
			async with session.get(url=PART_NUMBER_SEARCH_URL.format(self.part_number)) as response:
				try:
					response.raise_for_status()
				except ClientResponseError as e:
					logging.error(
						f"Error: occurred. status: ({response.status}) ({response.real_url}) ({self.part_number}) ..... {e}")
					raise PartNumberNotFound(self.part_number)
				else:
					res_text = await response.text()
					self.soup: BeautifulSoup = BeautifulSoup(res_text, 'html.parser')
					self.part_tbody_list: Optional[List[bs4.element.Tag]] = self.soup.findAll('tbody', id=lambda
						x: x and x.startswith('listingcontainer['))
					self.listing_container_id_num: Optional[int] = None
					if self.part_tbody_list is None or (
							type(self.part_tbody_list) is list and len(self.part_tbody_list) == 0):
						logging.error(
							f"Error: occurred while trying to get part's listing id number. ({self.part_number})")
						raise PartNumberNotFound(self.part_number)
					self.part_tbody_tag: bs4.element.Tag = self.part_tbody_list[0]
					if self.part_tbody_tag is None:
						logging.error(
							f"Error: occurred while trying to get part's listing id number. ({self.part_number})")
						raise PartNumberNotFound(self.part_number)
					self.regex_result = re.search('listingcontainer\\[(.*)\\]', self.part_tbody_tag.get("id"))
					self.listing_container_id_num = self.regex_result.group(1)
					if self.listing_container_id_num is None or len(self.listing_container_id_num) == 0:
						logging.error(
							f"Error: occurred while trying to get part's listing id number. ({self.part_number})")
						raise PartNumberNotFound(self.part_number)
					logging.info(f"{self.part_number} successfully found")
					return self.listing_container_id_num
		except ClientConnectorError as e:
			logging.error(
				f"Error: occurred while trying to get part number's listing tag id. ({self.part_number}) ..... {e}")
			raise PartNumberNotFound(self.part_number)
	
	@check_part_number("listing_container_id_num")
	def get_make_model_year_form_data(self):
		self.option_choice_tag: bs4.element.Tag = self.part_tbody_tag.find("input", id="optionchoice[{}]".format(
			self.listing_container_id_num))
		if self.option_choice_tag is None:
			# self.select_option_choice_tag: bs4.element.Tag = self.part_tbody_tag.find("select", id="optionchoice[{}]".format(self.listing_container_id_num))
			# self.option_under_select_tag: ResultSet[bs4.element.Tag] = self.select_option_choice_tag.findAll("option")
			# self.last_option_tag: bs4.element.Tag = self.option_under_select_tag[len(self.option_under_select_tag)]
			self.option_choice_value = ""
			print(f"{self.part_number} => id:{self.listing_container_id_num}")
		else:
			self.option_choice_value: str = self.option_choice_tag.get("value")
		self.listing_data_essential_tag: bs4.element.Tag = self.part_tbody_tag.find("input",
		                                                                            id="listing_data_essential[{}]".format(
			                                                                            self.listing_container_id_num))
		self.listing_data_essential_value: dict = json.loads(self.listing_data_essential_tag.get("value"))
		self.listing_data_supplemental_tag: bs4.element.Tag = self.part_tbody_tag.find("input",
		                                                                               id="listing_data_supplemental[{}]".format(
			                                                                               self.listing_container_id_num))
		self.listing_data_supplemental_value: dict = json.loads(self.listing_data_supplemental_tag.get("value"))
		self.form_data = FormData(func="getbuyersguide", api_json_request="1", sctchecked="1", scbeenloaded="true",
		                          curCartGroupID="_maincart")
		self.partData = json.dumps(
			{
				"partData": {
					"groupindex": self.listing_container_id_num,
					"listing_data_essential": self.listing_data_essential_value,
					"listing_data_supplemental": self.listing_data_supplemental_value,
					"OptKey": self.option_choice_value
				}
			}
		)
		self.form_data.update_attr(payload=self.partData)
		logging.info(f"Successfully created form data for Make Model Year post request ... ({self.part_number})")
		return self.form_data
	
	@check_part_number("listing_container_id_num")
	@make_sure_form_data()
	async def get_make_model_year(self, session):
		logging.info(f"Getting Make Model Year for ... ({self.part_number})")
		# "72.142.14.234:80"
		# "http://132.226.36.165:3128"
		await asyncio.sleep(0.25)
		async with session.post(url=MAKE_MODEL_YEAR_URL, data=self.form_data.to_dict()) as response:
			res_json = await response.json()
			soup: BeautifulSoup = BeautifulSoup(res_json["buyersguidepieces"]["body"], 'html.parser')
			table: bs4.element.Tag = soup.find("table", {"class": "nobmp"})
			trs: ResultSet[bs4.element.Tag] = table.findAll("tr")
			make_model_year = []
			for tr in trs:
				tds: bs4.element.Tag = tr.findAll("td")
				current_make_model_year = []
				for td in tds:
					current_make_model_year.append(td.text)
				make_model_year.append(current_make_model_year)
			logging.info(f"Successfully gathered Make Model Year info ... ({self.part_number})")
			return make_model_year
	
	@check_part_number("listing_container_id_num")
	async def get_images(self):
		logging.info(f"Getting images for ... ({self.part_number})")
		image_urls = []
		js_inline_image = self.part_tbody_tag.find("input", id="jsninlineimg[{}]".format(self.listing_container_id_num))
		images = json.loads(js_inline_image.get("value"))["Slots"]
		for image in images:
			image_urls.append(ROCKAUTO_IMG_URL_BASE.format(image["ImageData"]["Full"]))
		await asyncio.sleep(0)
		return image_urls
	
	@check_part_number("listing_container_id_num")
	async def get_oem_numbers(self):
		logging.info(f"Checking OEM numbers for ... ({self.part_number})")
		check_oem_span_tag: bs4.element.Tag = self.part_tbody_tag.select_one(
			".listing-text-row-moreinfo-truck > span:nth-child(3)")
		if not (check_oem_span_tag is not None and check_oem_span_tag.get(
				"title") == "Replaces these Alternate/ OE Part Numbers"):
			return f"No OEM Number found for => ({self.part_number})"
		oem_numbers = check_oem_span_tag.text
		oem_numbers = oem_numbers.replace('{', '')
		oem_numbers = oem_numbers.replace('}', '')
		oem_numbers = oem_numbers.replace('#', '')
		oem_numbers = oem_numbers.replace(',', '|')
		await asyncio.sleep(0)
		return oem_numbers
	
	def toJSON(self):
		return {
			self.part_number: {
				"images": self.images,
				"make_model_year": self.make_model_year_table,
				"oem_numbers": self.oem_numbers
			}
		}
	
	async def get_all_info(self, session) -> "AutoPart":
		try:
			listing_container_id_num = await self.get_part_number(session)
			self.images = await self.get_images()
			self.make_model_year_table = await self.get_make_model_year(session)
			self.oem_numbers = await self.get_oem_numbers()
			return self
		except Exception as e:
			raise PartNumberNotFound(self.part_number)


class FormData:
	def __init__(self, **kwargs):
		for k, v in kwargs.items():
			setattr(self, k, v)
	
	def update_attr(self, **kwargs):
		self.__dict__.update(kwargs)
	
	def to_dict(self) -> dict:
		return self.__dict__


async def bound_fetch(sem, f, *args, **kwargs):
	# Getter function with semaphore.
	async with sem:
		return await f(*args, **kwargs)


if __name__ == "__main__":
	import time
	import csv
	
	start_time = time.time()
	# part_numbers = ["NCV51018", "NCV49509", "GES800305"]
	# part_numbers = ["GES800305", "14102007", "14102008", "14102013", "14102013asdasdasd", "asdasdasdasdasdasdasd"]
	# part_numbers=["14120006"]
	part_numbers = []
	with open("Butun_Bilgiler.csv") as csvfile:
		logging.info(f"Reading part numbers...")
		data = csv.DictReader(csvfile)
		for row in data:
			part_numbers.append(row["Part Noi "].strip())
	# part_numbers = part_numbers[0: 50]
	logging.info(f"{len(part_numbers)} part numbers found...")
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	
	
	async def main():
		tasks = []
		# conn = TCPConnector(limit=10, limit_per_host=10, use_dns_cache=False)
		
		conn = TCPConnector(limit=10, limit_per_host=10, ssl=False, use_dns_cache=False)
		headers = {
			'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
		}
		sem = asyncio.Semaphore(10)
		
		async with ClientSession(connector=conn, headers=headers, trust_env=True) as session:
			for part_number in part_numbers:
				auto_part = AutoPart(part_number)
				
				task = asyncio.ensure_future(bound_fetch(sem, auto_part.get_all_info, session=session))
				tasks.append(task)
			responses = await asyncio.gather(*tasks, return_exceptions=True)
			pprint.pprint(responses)
			to_Json = []
			for response in responses:
				to_Json.append(response.toJSON())
			with open("Butun_Bilgiler.json", "w", encoding="utf-8") as outfile:
				logging.info(f"Writing to json file...")
				json.dump(to_Json, outfile, ensure_ascii=False, indent=4)
	
	
	loop = asyncio.get_event_loop()
	future = asyncio.ensure_future(main())
	loop.run_until_complete(future)
	logging.info("--- %s seconds ---" % (time.time() - start_time))
