find_bad_toast
==============

Scenario
--------

You know you have a table with (at least one) corrupted TOAST entry.
You want to scan the table and find which row(s) have the corruption.

Background
----------

See (Josh Berkus's blog post on TOAST corruption)[http://www.databasesoup.com/2014/07/improved-toast-corruption-function.html]. This program is a translation of the plpgsql version, generalizing it to arbitrary multicolumn PKs. Rewriting this in Python also eliminates the need for transactions, which was a crucial performance problem when running the plpgsql version on large tables.

Solution
--------

    find_bad_toast --table MY_TABLE --pk PK_COL_1 [ --pk PK_COL_2 ... ] --connect-string 'user=MY_USERNAME host=MY_HOST dbname=MY_DB'

or, if you prefer,

    find_bad_toast -t MY_TABLE -p PK_COL_1 [ -p PK_COL_2 ... ] --connect-string 'user=MY_USERNAME host=MY_HOST dbname=MY_DB'

Installing
----------

- Create a virtualenv, enter it, then 'pip install -r requirements.txt'

Author
------

Quinn Weaver <quinn@pgexperts.com>


