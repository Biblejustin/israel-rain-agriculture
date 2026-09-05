Release notes for the CRU CY dataset (all versions)

---
Introduction

The CRU CY dataset consists of country averages at a monthly, seasonal
and annual frequency, for ten variables. Spatial averages are calculated
using area-weighted means.

The CRU CY dataset is an update of the TYN CY dataset, which may be
found on the CRU website:

http://www.cru.uea.ac.uk/cru/data/hrg/

---
Relationship to Other Datasets

CRU CY is derived directly from the CRU TS dataset, and version
numbering is matched between the two datasets. Thus, the first official
version of CRU CY is v3.21, as it is based on CRU TS v3.21.

---
Format

Each country file contains all the spatial means for a particular
country and variable. The files are ASCII text, and should be readable
with almost any application including a text editor (they import into
Excel readily, start the import at line 4 or 5).

Each file begins with three information lines:

Line 1: Includes the date and time of produciton, and the date string
uniquely identifying the CRU TS run on which the dataset is based.

Line 2: Identifies the country, parameter (variable) and units (eg, mm).

Line 3: Contains the time period, the missing value code, and the data
format (as a Fortran-style string).

There is then a data header, describing the following columns:

YEAR
JAN-DEC (12 columns, monthly means)
MAM, JJA, SON, DJF (4 columns, seasonal means)
ANN (annual mean)

After these lines come the data, one line per year. For version 3.21,
this covers 1901 to 2012.

This data format is almost identical to that of the TYN CY dataset,
although the reference to the CRU TS version and run (on line 1) is new.

---
Notes on usage

To understand this dataset, it is important to understand the
construction and limitations of the underlying dataset, CRU TS. It is
therefore recommended that all users read the relevant paper:

Harris, I., Osborn, T.J., Jones, P. et al. Version 4 of the CRU TS
monthly high-resolution gridded multivariate climate dataset.
Sci Data 7, 109 (2020). https://doi.org/10.1038/s41597-020-0453-3

In brief: the CRU TS dataset prioritises completeness, and has no
missing data over land. Where observations are unavailable, the 1961-90
monthly climatic mean is used as a substitute. In data sparse regions
of the world, this can lead to repeated values, and this can show up in
derived products such as CRU CY.

Unlike the previous TYN CY dataset, CRU CY consists solely of country
averages.

Finally, note that the 'DJF' (winter) value for the last year will
be missing; this is because the season straddles two years, and cannot
be calculated without the January and February values.

