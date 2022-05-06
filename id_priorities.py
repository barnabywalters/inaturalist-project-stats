# coding: utf-8

import argparse
import pandas as pd
import os.path
import yaml

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Find observations IDed to genus level for which there are no species-level IDs, i.e. observations which, if they were IDed to species level, are guaranteed to be species not yet present in the set.')
	parser.add_argument('analysis')
	args = parser.parse_args()
	
	config = yaml.safe_load(open(os.path.join('data', args.analysis, 'config.yaml')))
	root_h_lvl = int(config.get('root_header_level', 1))
	df = pd.read_csv(os.path.join('data', args.analysis, config['file']))
	
	try:
		os.mkdir(os.path.join('data', args.analysis, 'output'))
	except:
		pass
	try:
		os.mkdir(os.path.join('data', args.analysis, 'output', 'current'))
	except:
		pass
	
	# Genuses of any observation not IDed to species level has potential.
	potential_genuses = list(df.loc[pd.isnull(df.taxon_species_name), 'taxon_genus_name'].value_counts().index)
	
	# Whittle that list down to those for which no observations are IDed to species
	speciesless_genuses = [g for g in potential_genuses if not df.loc[df.taxon_genus_name == g, 'taxon_species_name'].any()]
	
	# List all observations in those genuses which have not been marked as impossible to improve
	priority_obs = df.loc[df.taxon_genus_name.isin(speciesless_genuses) & (df.quality_grade != 'research')]
	
	# Order by taxonomy
	priority_obs = priority_obs.sort_values(['taxon_kingdom_name', 'taxon_class_name', 'taxon_order_name', 'taxon_family_name', 'taxon_genus_name'])
	
	# Create thumbnail image URL column
	priority_obs.loc[:, 'image_url_smol'] = priority_obs.image_url.str.replace('medium.jpeg', 'thumb.jpeg')
	
	# Create basic list for review
	fp = open(os.path.join('data', args.analysis, 'output', 'current', 'priority.html'), 'w')
	
	fp.write(f"<h{root_h_lvl}>Priority Observations</h{root_h_lvl}>")
	fp.write('<p>The following observations are in genera for which the project currently has no species-level observations, and are therefore likely to be able to increase the species count.</p>')
	
	# Clumsy inline CSS for now.
	fp.write('''
<style>
body {
	font-family: Whitney, "Trebuchet MS", Arial, sans-serif;
}

.family-container {
	display: flex;
	flex-wrap: wrap;
}

.priority-observation {
	margin: 0 0.5em 0.5em 0;
	padding: 0.5em;
	background-color: #f1f1f1;
}

.priority-observation .genus {
	display: block;
	margin-bottom: 0.5em;
	text-align: center;
}

.priority-observation img {
	display: block;
	height: 10em;
}
</style>
''')
	
	current_kingdom = None
	current_class = None
	current_order = None
	current_family = None
	in_family_container = False
	current_genus = None
	
	for i, row in priority_obs.iterrows():
		if row['taxon_kingdom_name'] != current_kingdom:
			if in_family_container:
				fp.write('</div>')
				in_family_container = False
			fp.write(f'''<h{root_h_lvl+1}>{row['taxon_kingdom_name']}</h{root_h_lvl+1}>''')
		
		if row['taxon_family_name'] != current_family:
			if in_family_container:
				fp.write('</div>')
				in_family_container = False
			fp.write(f'''<h{root_h_lvl+2}>{row['taxon_class_name']} → {row['taxon_order_name']} → {row['taxon_family_name']}</h{root_h_lvl+2}>
<div class="family-container">''')
			in_family_container = True
		
		fp.write(f'''<div class="priority-observation">
<a class="genus" href="{row['url']}">{row['taxon_genus_name']}</a>
<a href="{row['url']}"><img src="{row['image_url']}" /></a>
</div>
''')
		
		current_kingdom = row['taxon_kingdom_name']
		current_class = row['taxon_class_name']
		current_order = row['taxon_order_name']
		current_family = row['taxon_family_name']
		current_genus = row['taxon_genus_name']
	
	fp.close()