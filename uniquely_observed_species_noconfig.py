# coding: utf-8

import argparse
import pandas as pd
import numpy as np
import requests
import time
import urllib.parse

"""
Find which species in an iNaturalist export only have observations from a single observer.

Get an export from here: https://www.inaturalist.org/observations/export with a query such
as quality_grade=research&identifications=any&rank=species&projects[]=92926 and at least the
following columns: taxon_id, scientific_name, common_name, user_login

Download it, extract the CSV, then run this script with the file name as its argument. It will
output basic stats formatted as HTML.

The only external module required is pandas.

Example usage:

		py uniquely_observed_species.py wien_cnc_2021.csv > wien_cnc_2021_results.html

If you provide the --project-id (-p) argument, the taxa links in the output list will link to 
a list of observations of that taxa within that project. Otherwise, they default to linking
to the taxa page.

If a quality_grade column is included, non-research-grade observations will be included in the
analysis. Uniquely observed species with no research-grade observations will be marked. Species
which were observed by multiple people, only one of which has research-grade observation(s) will
also be marked.

By Barnaby Walters waterpigs.co.uk
"""

def fetch_all_results(api_url, delay=1.0, ttl=(60 * 60 * 24)):
	total_results = None
	results = []
	page = 1
	while (total_results is None) or len(results) < total_results:
		api_url = f"{api_url}&page={page}&ttl={ttl}"
		jresp = requests.get(api_url).json()
		if total_results is None:
			total_results = jresp['total_results']
		results.extend(jresp['results'])
		page += 1
		time.sleep(delay)
	return results

def species_name(t):
	if not pd.isnull(t['common_name']):
		return f"<i>{t['scientific_name']}</i> ({t['common_name']})"
	else:
		return f"<i>{t['scientific_name']}</i>"

def chunks(l, chunk_size):
	chunk_size = max(1, chunk_size)
	return (l[i:i+chunk_size] for i in range(0, len(l), chunk_size))

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Given an iNaturalist observation export, find species which were only observed by a single person.')
	parser.add_argument('export_file')
	parser.add_argument('-p', '--project-id', dest='project_id', default=None)
	parser.add_argument('--place', dest='place_ids', default=None)
	parser.add_argument('--observer-element', dest='observer_element', default='<h3>', help='The element to wrap observer names in e.g. `<h3 class="observer">`. Defaults to <h2>.')
	parser.add_argument('--notable-class', dest='notable_class', default='notable')

	args = parser.parse_args()
	observer_element_open = args.observer_element
	observer_element_close = f"</{args.observer_element.split(' ')[0][1:].strip('<>')}>"

	place_ids = args.place_ids

	unique_observations = {}

	df = pd.read_csv(args.export_file)

	# If quality_grade isn’t given, assume that the export contains only RG observations.
	if 'quality_grade' not in df.columns:
		df.loc[:, 'quality_grade'] = 'research'

	# Filter out casual observations.
	df = df.query('quality_grade != "casual"')

	# Create a local species reference from the dataframe.
	species = df.loc[:, ('taxon_id', 'scientific_name', 'common_name')].drop_duplicates()
	species = species.set_index(species.loc[:, 'taxon_id'])
	species.loc[:, 'place_observations'] = 0
	species.loc[:, 'global_observations'] = 0
	species.loc[:, 'notable_sort_order'] = np.nan
	species.loc[:, 'notable'] = False
	
	notable_species = []

	for tid in species.index:
		observers = df.query('taxon_id == @tid').loc[:, 'user_login'].drop_duplicates()
		research_grade_observers = df.query('taxon_id == @tid and quality_grade == "research"').loc[:, 'user_login'].drop_duplicates()

		if observers.shape[0] == 1:
			# Only one person made any observations of this species.
			observer = observers.squeeze()
			if observer not in unique_observations:
				unique_observations[observer] = []

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
			
			unique_observations[rg_observer].append({
				'id': tid,
				'has_research_grade': True,
				'num_other_observers': observers.shape[0] - 1,
			})

	# If we’re looking up notability by place, fetch notability data.
	if place_ids:
		unique_species = []
		[unique_species.extend(l) for l in unique_observations.values()]
		all_taxon_ids = [str(int(s['id'])) for s in unique_species]
		notability_results = []
		pids = urllib.parse.quote_plus(place_ids)
		for tids in chunks(all_taxon_ids, 100):
			ctids = urllib.parse.quote_plus(','.join([str(int(t)) for t in tids]))
			notability_results.extend(fetch_all_results(f"https://api.inaturalist.org/v1/observations/species_counts?place_id={pids}&taxon_id={ctids}&rank=species"))
		
		for nr in notability_results:
			species.loc[nr['taxon']['id'], ['place_observations', 'global_observations', 'notable', 'notable_sort_order']] = [
				nr['count'],
				nr['taxon']['observations_count'],
				(nr['count'] <= 5) or (nr['taxon']['observations_count'] <= 10),
				(nr['count']+10) if nr['taxon']['observations_count'] > 10 else nr['taxon']['observations_count']
			]
		
		if species.loc[:, 'notable'].any():
			print(f"""<h2 id="notable-species">Notable Species</h2>""")
			print(f"<p>These species have either been observed ≤ 5 times within the project’s Place, or ≤ 10 times on iNaturalist globally.</p>")
			print(f"<ul>")

			for i, row in species.query('notable == True').sort_values('notable_sort_order', ascending=True).iterrows():
				global_obs_url = f"https://www.inaturalist.org/observations?taxon_id={row['taxon_id']}"
				local_obs_url = f"{global_obs_url}&amp;place_id={pids}"
				taxa_url = f"https://inaturalist.org/taxa/{row['taxon_id']}"
				print(f'''<li><a href="{taxa_url}"><b>{species_name(row)}</b></a>: <a href="{local_obs_url}">{row['place_observations']} local</a>, <a href="{global_obs_url}">{row['global_observations']} global</a></li>''')
			print(f"</ul>")

	# Sort observers by number of unique species.
	sorted_observations = sorted(unique_observations.items(), key=lambda t: len(t[1]), reverse=True)

	print(f"<p>{sum([len(t) for _, t in sorted_observations])} taxa uniquely observed by {len(sorted_observations)} observers.</p>")

	print('<p>')
	for observer, _ in sorted_observations:
		print(f"@{observer} ", end='')
	print('</p>')

	print('<p><b>bold</b> species are ones for which the given observer has one or more research-grade observations.</p>')
	print('<p>If only one person has RG observations of a species, but other people have observations which need ID, the number of needs-ID observers are indicated in parentheses.')

	print('<h2 id="observers">Observers</h2>')

	for observer, taxa in sorted_observations:
		print(f"""\n\n{observer_element_open}<a id="{observer}" href="https://www.inaturalist.org/people/{observer}">@{observer}</a> ({len(taxa)} taxa):{observer_element_close}<ul>""")
		for tobv in sorted(taxa, key=lambda t: species.loc[t['id']]['scientific_name']):
			tid = tobv['id']
			t = species.loc[tid]

			if args.project_id:
				taxa_url = f"https://www.inaturalist.org/observations?taxon_id={tid}&amp;project_id={args.project_id}"
			else:
				taxa_url = f'https://www.inaturalist.org/taxa/{tid}'
			
			rgb, rge = ('<b>', '</b>') if tobv.get('has_research_grade') else ('', '')
			others = f" ({tobv.get('num_other_observers', 0)})" if tobv.get('num_other_observers', 0) > 0 else ''
			
			additional_text = ''

			classes = []
			if t['notable']:
				classes.append('notable')
			if t['place_observations'] == 1:
				classes.append('first-local-observation')
				additional_text = f"{additional_text} • First local observation!"
			if t['global_observations'] == 1:
				classes.append('first-global-observation')
				additional_text = f"{additional_text} • First iNaturalist observation!"

			print(f"""<li class="{' '.join(classes)}"><a href="{taxa_url}">{rgb}{species_name(t)}{rge}</a>{others}{additional_text}</li>""")
		print("</ul>")
