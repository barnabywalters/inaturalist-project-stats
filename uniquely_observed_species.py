# coding: utf-8

import argparse
import os
import os.path
import pandas as pd
import numpy as np
import requests
import time
import urllib.parse
import yaml
import IPython
import hashlib
import json

"""


By Barnaby Walters waterpigs.co.uk
"""

def fetch_all_results(api_url, delay=1.0, ttl=(60 * 60 * 24), cache_location=None):
	total_results = None
	results = []
	page = 1
	cache_path = None
	fetched_from_cache = False
	while (total_results is None) or len(results) < total_results:
		req_url = f"{api_url}&page={page}&ttl={ttl}"
		
		try:
			if cache_location is None:
				raise Exception()
			cache_path = os.path.join(cache_location, f"{hashlib.md5(req_url.encode('utf-8')).hexdigest()}.json")
			with open(cache_path) as fp:
				jresp = json.load(fp)
				fetched_from_cache = True
				print('c', end='', flush=True)
		except:
			resp = requests.get(req_url)
			resp.raise_for_status()
			fetched_from_cache = False
			jresp = resp.json()
			#print(req_url)
			print('.', end='', flush=True)
			
			if cache_path is not None:
				with open(cache_path, 'w') as fp:
					json.dump(jresp, fp)
			
		if total_results is None:
			total_results = jresp['total_results']
		results.extend(jresp['results'])
		page += 1
		if not fetched_from_cache:
			time.sleep(delay)
	return results

def species_name(t, locale='en'):
	if not pd.isnull(t[f'common_name_{locale}']) and t['scientific_name'] != t[f'common_name_{locale}']:
		return f"<i>{t['scientific_name']}</i> ({t[f'common_name_{locale}']})"
	elif not pd.isnull(t['common_name']) and t['scientific_name'] != t['common_name']:
		return f"<i>{t['scientific_name']}</i> ({t['common_name']})"
	else:
		return f"<i>{t['scientific_name']}</i>"

def chunks(l, chunk_size):
	chunk_size = max(1, chunk_size)
	return (l[i:i+chunk_size] for i in range(0, len(l), chunk_size))

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Given an iNaturalist observation export, find species which were only observed by a single person.')
	parser.add_argument('analysis')
	args = parser.parse_args()

	config = yaml.safe_load(open(os.path.join('data', args.analysis, 'config.yaml')))
	df = pd.read_csv(os.path.join('data', args.analysis, config['file']))
	root_h_lvl = int(config.get('root_header_level', 1))
	try:
		os.mkdir(os.path.join('data', args.analysis, 'output'))
	except:
		pass
	try:
		os.mkdir(os.path.join('data', args.analysis, 'output', 'current'))
	except:
		pass
	
	# Ensure a context query string exists.
	if 'context_query' not in config:
		if 'project' in config:
			config['context_query'] = f"project_id={config['project']}"
		else:
			config['context_query'] = ''
	
	# Flesh-out places config.
	for p_config in config.get('places', []):
		p_config['col'] = p_config.get('col', p_config['id'])
		p_config['quoted_pids'] = urllib.parse.quote_plus(p_config['id'])

		# Find the most appropriate display name.
		if 'name' not in p_config:
			try:
				p_result = requests.get(f"https://api.inaturalist.org/v1/places/{p_config['quoted_pids']}").json()['results'][0]
			except:
				p_result = {}
			p_config['name'] = p_result.get('display_name', str(p_config['id']))
	places = config['places']
	
	locale = config.get('locale', 'en')

	f_unique = open(os.path.join('data', args.analysis, 'output', 'current', 'unique.html'), 'w')
	f_notable = open(os.path.join('data', args.analysis, 'output', 'current', 'notable.html'), 'w')

	unique_observations = {}

	# If quality_grade isn???t given, assume that the export contains only RG observations.
	if 'quality_grade' not in df.columns:
		df.loc[:, 'quality_grade'] = 'research'

	# Filter out casual observations.
	df = df.query('quality_grade != "casual"')
	
	# Only include observations with a species-level identification.
	df = df.dropna(subset=['taxon_species_name'])

	# Create a local species reference from the dataframe.
	species = df.loc[:, ('taxon_id', 'scientific_name', 'common_name', 'species_guess')].drop_duplicates(subset=['taxon_id'])
	# iNat export common_name is in english, at least for me.
	species.loc[:, 'common_name_en'] = species.loc[:, 'common_name']
	# species_guess is usually in the locale we want for some reason, so use that instead of common name.
	species.loc[:, 'common_name'] = species.loc[:, 'species_guess']
	species = species.set_index(species.loc[:, 'taxon_id'])
	species.loc[:, 'uniquely_observed'] = False
	species.loc[:, 'global_observation_count'] = np.nan
	species.loc[:, 'project_observation_count'] = np.nan
	# Other place observation counts follow pattern {place_id}_observation_count
	species.loc[:, 'notable_sort_order'] = np.nan
	species.loc[:, 'notable'] = False
	if config.get('locale') and config['locale'] != 'en':
		species.loc[:, f"common_name_{config['locale']}"] = np.nan
	
	notable_species = []

	# Perform unique observation analysis.
	for tid in species.index:
		observers = df.query('taxon_id == @tid').loc[:, 'user_login'].drop_duplicates()
		research_grade_observers = df.query('taxon_id == @tid and quality_grade == "research"').loc[:, 'user_login'].drop_duplicates()

		species.loc[tid, 'project_observation_count'] = observers.shape[0]

		if observers.shape[0] == 1:
			# Only one person made any observations of this species.
			observer = observers.squeeze()
			if observer not in unique_observations:
				unique_observations[observer] = []

			species.loc[tid, 'uniquely_observed'] = True

			unique_observations[observer].append({
				'id': tid,
				'has_research_grade': (not research_grade_observers.empty),
				'num_other_observers': 0,
			})
		elif research_grade_observers.shape[0] == 1:
			# Multiple people observed the species, but only one person has research-grade observation(s).
			rg_observer = research_grade_observers.squeeze()
			if rg_observer not in unique_observations:
				unique_observations[rg_observer] = []
			
			species.loc[tid, 'uniquely_observed'] = True

			unique_observations[rg_observer].append({
				'id': tid,
				'has_research_grade': True,
				'num_other_observers': observers.shape[0] - 1,
			})

	# If we???re looking up notability by place, fetch notability data.
	if len(places) > 0:
		# Fetch place-dependent notability results for all defined places.
		try:
			global_p_config = [p for p in config['places'] if p['id'] == 'global'][0]
		except IndexError:
			global_p_config = {}
		
		potentially_notable_taxon_ids = list(species.loc[species.loc[:, 'project_observation_count'] <= global_p_config.get('observation_threshold', 5), 'taxon_id'].dropna())
		
		print(f"Found {len(potentially_notable_taxon_ids)} potentially notable taxa")
		
		# Output notability report.
		f_notable.write(f"""<h{root_h_lvl} id="notable-species">Notable Species</h{root_h_lvl}>\n""")
		
		notability_results = {}
		for p_config in places:
			p_col = p_config['col']
			pids = p_config['quoted_pids']
			notability_results[p_config['col']] = []
			species.loc[:, f"{p_col}_first"] = False
			species.loc[:, f"{p_col}_notable"] = False

			# Create place-specific first and notability columns.
			if p_config['id'] != 'global':
				# TODO: use each stage to whittle down the list of potentially notable taxon, to reduce the
				# number of queries required for the larger places.
				for tids in chunks(potentially_notable_taxon_ids, 100):
					ctids = urllib.parse.quote_plus(','.join([str(int(t)) for t in tids]))
					notability_results[p_col].extend(fetch_all_results(f"https://api.inaturalist.org/v1/observations/species_counts?place_id={pids}&taxon_id={ctids}&rank=species&locale={config.get('locale', 'en')}", cache_location='data/_cache'))
				
				for nr in notability_results[p_col]:
					species.loc[nr['taxon']['id'], [f"{p_col}_observation_count", 'global_observation_count', f"common_name_{config.get('locale', 'en')}"]] = [
						nr['count'],
						nr['taxon']['observations_count'],
						nr['taxon'].get('preferred_common_name')
					]
				notable_ix = ~pd.isnull(species.loc[:, f"{p_col}_observation_count"])
				species.loc[notable_ix, f"{p_col}_first"] = species.loc[notable_ix, 'project_observation_count'] == species.loc[notable_ix, f"{p_col}_observation_count"]
				species.loc[notable_ix, f"{p_col}_notable"] = species.loc[notable_ix, f"{p_col}_observation_count"] <= p_config.get('observation_threshold', 5)
			else:
				# No additional data is required for global results, provided they???re processed last.
				notable_ix = ~pd.isnull(species.loc[:, 'global_observation_count'])
				species.loc[notable_ix, 'global_first'] = species.loc[notable_ix, 'project_observation_count'] == species.loc[notable_ix, 'global_observation_count']
				species.loc[notable_ix, 'global_notable'] = species.loc[notable_ix, 'global_observation_count'] <= global_p_config.get('observation_threshold', 5)

			# Update general notability
			species.loc[notable_ix, 'notable'] = species.loc[notable_ix, 'notable'] | species.loc[notable_ix, f"{p_col}_notable"]
			
			# Clean up the species dataframe.
			species = species.loc[~pd.isnull(species.loc[:, 'taxon_id']), :]
			species.loc[:, 'taxon_id'] = species.loc[:, 'taxon_id'].astype(int)

			f_notable.write(f"""<h{root_h_lvl+1} id="{p_col}"><a href="#{p_col}">{p_config['name']}</a></h{root_h_lvl+1}>\n""")

			# Report firsts first (NPI).
			f_notable.write(f"""<h{root_h_lvl+2} id="{p_col}-firsts"><a href="#{p_col}-firsts">First Observations</a> ({species.query(f"{p_col}_first").shape[0]})</h{root_h_lvl+2}>\n""")
			f_notable.write(f"<ul>\n")
			for i, tax_row in species.query(f"{p_col}_first").sort_values('scientific_name', ascending=True).iterrows():
				tid = tax_row['taxon_id']
				taxa_url = f"https://inaturalist.org/taxa/{tid}"
				
				try:
					# Look for an RG observation first, and prioritise that.
					first_obs = df.loc[(df.loc[:, 'taxon_id'] == tid) & df.loc[:, 'quality_grade'] == 'research', :].sort_values('time_observed_at', ascending=True).iloc[0, :]
				except IndexError:
					# Fall back to using the first non-RG observation if no RG observations are available.
					first_obs = df.loc[df.loc[:, 'taxon_id'] == tid, :].sort_values('time_observed_at', ascending=True).iloc[0, :]
				
				if first_obs['quality_grade'] == 'research':
					f_notable.write(f"""<li class="filterable"><a href="{taxa_url}"><b>{species_name(tax_row, locale=locale)}</b></a>: <a href="https://www.inaturalist.org/observations/{first_obs['id']}">first observation by @{first_obs['user_login']}</a></li>\n""")
				else:
					f_notable.write(f"""<li class="filterable"><a href="{taxa_url}">{species_name(tax_row, locale=locale)}</a>: <a href="https://www.inaturalist.org/observations/{first_obs['id']}">first observation by @{first_obs['user_login']}</a></li>\n""")
			f_notable.write(f"</ul>\n")
			
			# Then, report all other notable observations.
			f_notable.write(f"""<h{root_h_lvl+2} id="{p_col}-notable"><a href="#{p_col}-notable">Notable Observations</a> ({species.query(f'{p_col}_notable & not {p_col}_first').shape[0]})</h{root_h_lvl+2}>\n""")
			f_notable.write(f"<ul>\n")
			for i, row in species.query(f'{p_col}_notable & not {p_col}_first').sort_values(f'{p_col}_observation_count', ascending=True).iterrows():
				obs_url = f"https://www.inaturalist.org/observations?taxon_id={row['taxon_id']}"
				if p_config['id'] != 'global':
					obs_url = f"{obs_url}&amp;place_id={pids}"
				taxa_url = f"https://inaturalist.org/taxa/{row['taxon_id']}"
				
				rg_observers = list(df.loc[(df.loc[:, 'taxon_id'] == row['taxon_id']) & (df.loc[:, 'quality_grade'] == 'research'), 'user_login'].drop_duplicates())
				
				if len(rg_observers) > 0:
					f_notable.write(f'''<li class="filterable"><a href="{taxa_url}"><b>{species_name(row, locale=locale)}</b></a> observed by: ''')
				else:
					f_notable.write(f'''<li class="filterable"><a href="{taxa_url}">{species_name(row, locale=locale)}</a> observed by: ''')
				# Report a list of people who observed this species.
				observers = list(df.loc[df.loc[:, 'taxon_id'] == row['taxon_id'], :].sort_values('time_observed_at', ascending=True).loc[:, 'user_login'].drop_duplicates())
				for i, observer in enumerate(observers):
					if observer in rg_observers:
						f_notable.write(f''' <b><a href="https://www.inaturalist.org/observations?user_id={observer}&taxon_id={row['taxon_id']}&{config['context_query']}">@{observer}</a></b>''')
					else:
						f_notable.write(f''' <a href="https://www.inaturalist.org/observations?user_id={observer}&taxon_id={row['taxon_id']}&{config['context_query']}">@{observer}</a>''')
					if i+1 < len(observers):
						f_notable.write(',')  # No comma after the last observer in the list.
				f_notable.write(f''' (<a href="{obs_url}">{int(row[f'{p_col}_observation_count'])} total</a>)</li>\n''')
			f_notable.write(f"</ul>\n")
	f_notable.close()

	# Output unique observation report.
	sorted_observations = sorted(unique_observations.items(), key=lambda t: len(t[1]), reverse=True)

	f_unique.write(f"""<h{root_h_lvl} id="unique">Uniquely Observed Species</h{root_h_lvl}>\n""")
	f_unique.write(f"<p>{sum([len(t) for _, t in sorted_observations])} taxa uniquely observed by {len(sorted_observations)} observers.</p>\n")
	
	f_unique.write('<p>\n')
	for observer, _ in sorted_observations:
		f_unique.write(f"@{observer} \n")
	f_unique.write('</p>\n')

	f_unique.write('<p><b>bold</b> species are ones for which the given observer has one or more research-grade observations.</p>\n')
	f_unique.write('<p>If only one person has RG observations of a species, but other people have observations which need ID, the number of needs-ID observers are indicated in parentheses.\n')

	f_unique.write(f'<h{root_h_lvl+1} id="observers">Observers</h{root_h_lvl+1}>\n')

	for observer, taxa in sorted_observations:
		f_unique.write(f"""\n\n<div class="filterable"><h{root_h_lvl+2} id="{observer}"><a id="{observer}" href="https://www.inaturalist.org/people/{observer}">@{observer}</a> ({len(taxa)} taxa):</h{root_h_lvl+2}>\n""")
		f_unique.write('<ul>\n')

		for tobv in sorted(taxa, key=lambda t: species.loc[t['id']]['scientific_name']):
			tid = tobv['id']
			t = species.loc[tid]

			if config.get('project'):
				taxa_url = f"https://www.inaturalist.org/observations?taxon_id={tid}&amp;{config['context_query']}"
			else:
				taxa_url = f'https://www.inaturalist.org/taxa/{tid}'
			
			rgb, rge = ('<b>', '</b>') if tobv.get('has_research_grade') else ('', '')
			others = f" ({tobv.get('num_other_observers', 0)})" if tobv.get('num_other_observers', 0) > 0 else ''
			
			additional_text = ''

			classes = []
			if t['notable']:
				classes.append('notable')
			
			highest_ranked_first = None
			for p_config in places:
				if t[f"{p_config['col']}_notable"]:
					classes.append(f"{p_config['col']}-notable")
				if t[f"{p_config['col']}_first"]:
					highest_ranked_first = p_config.get('first_text', f"First {p_config['name']} observation!")

			if highest_ranked_first:
				additional_text = f"{additional_text} ??? {highest_ranked_first}"

			f_unique.write(f"""<li class="filterable {' '.join(classes)}"><a href="{taxa_url}">{rgb}{species_name(t, locale=locale)}{rge}</a>{others}{additional_text}</li>\n""")
		f_unique.write("</ul></div>\n")
	f_unique.close()

	species.to_csv(os.path.join('data', args.analysis, 'output', 'current', 'species.csv'), index=None)

	IPython.embed()
