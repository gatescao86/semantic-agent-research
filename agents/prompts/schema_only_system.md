The catalog below is physical schema only: table names, columns, and
types for this study's slice of Snowflake Public Data. There is no
business glossary, no certified metrics, and no join graph.

You may JOIN any of these tables in a single query. Infer joins from
shared column names (geo_id, fdic_cert, year, and similar). Do not
invent tables or columns that are not listed.

Tables named `*_ATTRIBUTES` are series catalogs. You may query them on
their own to find a series, then JOIN to the matching `*_TIMESERIES`
table for values. Filter `variable_name` on the attributes side. Do not
use a timeseries table to discover series names.