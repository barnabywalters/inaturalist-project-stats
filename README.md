# iNaturalist Project Analyser

My python scripts for producing project reports from iNaturalist export files. Designed mostly for use with CNC or similar semi-competitive bioblitz projects.

Example output: [CNC Wien 2024 Firsts and Notable Report](https://waterpigs.co.uk/inat/cnc-wien-2024.html)

# Requirements

* A working [python 3.12](https://www.python.org/) installation
* The required libraries (`pip install -r requirements.txt`)

# Usage

See `python notable.py --help` for detailed instructions

# Limitations

* The script currently only works with obervations where the community taxon is at species-level. First and notable observations IDed to levels above species are not included
* If the first observation of a species is made during the project to be analysed, but more are added outside the project but before the analysis is carried out, the true first observation will not be recognised as such (though will likely still be considered notable). This could be fixed or improved at the cost of increased complexity and many additional API calls 