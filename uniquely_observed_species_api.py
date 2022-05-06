# coding: utf-8

import argparse
import json
import time
import requests

MAX_OBSERVATION_COUNT = 3
API_DELAY = 1.0
API_TTL = 60 * 60 * 24

def fetch_all_results(api_url, delay=1.0, ttl=(60 * 60 * 24)):
	total_results = None
	results = []
	page = 1
	while (total_results is None) or len(results) < total_results:
		curr_url = f"{api_url}&page={page}&ttl={ttl}"
		jresp = requests.get(curr_url).json()
		if total_results is None:
			total_results = jresp['total_results']
		results.extend(jresp['results'])
		page += 1
		time.sleep(delay)
	return results

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Given a project ID, find species which were only observed by a single person.')
	parser.add_argument('project_id')

	args = parser.parse_args()

	pid = args.project_id

	total_results = None
	species = []
	page = 1
	while (total_results is None) or len(species) < total_results:
		api_url = f"https://api.inaturalist.org/v1/observations/species_counts?project_id={pid}&hrank=species&quality_grade=research&page={page}&ttl={API_TTL}"
		print(f"GET {api_url}")
		jresp = requests.get(api_url).json()
		if total_results is None:
			total_results = jresp['total_results']
		species.extend(jresp['results'])
		page += 1
		time.sleep(API_DELAY)
	
	least_observed_species = [sp for sp in species if sp['count'] <= MAX_OBSERVATION_COUNT]
	uniquely_observed_species = {}

	for los in least_observed_species:
		taxon_id = los['taxon']['id']
		first_observer = None
		page = 1
		total_results = None
		downloaded_results = 0
		could_be_uniquiely_observed = True

		while could_be_uniquiely_observed and ((total_results is None) or downloaded_results < total_results):
			api_url = f"https://api.inaturalist.org/v1/observations?project_id={pid}&taxon_id={taxon_id}&hrank=species&quality_grade=research&order=desc&order_by=created_at&page={page}&ttl={API_TTL}"
			print(f"GET {api_url}")
			jresp = requests.get(api_url).json()
			if total_results is None:
				total_results = jresp['total_results']
			
			for obs in jresp['results']:
				if first_observer is None:
					first_observer = obs['user']['login']
				elif obs['user']['login'] != first_observer:
					could_be_uniquiely_observed = False
					break
				downloaded_results += 1
			
			time.sleep(API_DELAY)
			page += 1

		if could_be_uniquiely_observed:
			if first_observer not in uniquely_observed_species:
				uniquely_observed_species[first_observer] = []
			uniquely_observed_species[first_observer].append({
				'id': los['taxon']['id'],
				'name': los['taxon']['name'],
				'common_name': los['taxon'].get('preferred_common_name', '')
			})
	
	for observer, taxon in uniquely_observed_species.items():
		print(f"<p>@{observer}:</p><ul>")
		for t in taxon:
			print(f"""<li><a href="https://www.inaturalist.org/taxa/{t['id']}"><i>{t['name']}</i> ({t['common_name']})</a></li>""")
		print("</ul>")
