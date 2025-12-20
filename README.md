# find_bad_toast.py

This is a script for scanning the extended and external attributes of a PostgreSQL database,
looking for corrupt rows. The most common and obvious types of TOAST table corruption
result in an error when the TOAST value is read in, and this script goes through each
table, reading in each such attribute, to see if an error results.

It requires **Python 3.11** or higher. The dependencies are in the `pyproject.toml` and `requirements.txt`
files.

## Usage

```bash
./find_bad_toast.py [options]
```

### Options are:

**DB connection options.** These are the same as `pg_dump` and other PostgreSQL
tools:

* `-d` / `--dbname` -- The database name, or a [standard PostgreSQL connection string](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING).
* `-h` / `--host` -- The host to connet to.
* `-p` / `--port` -- The port to connect to.
* `-U` / `--username` -- The username to use for connection.

The script will not prompt for a password if one is required. The password
can be specified in a `.pgpass` file, or the account being used can
bet set up with `peer` authentication if it is local. (Never use `trust`
authentication!)

**Table and schema filtering options.** These are the same as `pg_dump`:

* `-t` / `include-table`
* `-T` / `exclude-table`
* `-n` / `include-schema`
* `-N` / `exclude-schema`

Each option may be specified more than once, and they may be combined.

All of the patterns used to match table and schema names are case-insensitive.
The patterns are glob-like:

* `*` matches any number of characters at its position, including 0.
* `?` matches exactly one character at its position.

For a table to be processed, it must match *any* of the include patterns, and must
*not* match *any* of the exclude patterns. The script does not check to see if the
patterns make sense together, so:

```bash
--include-table=food* --exclude-table=foo*
```

... will not match any tables, and the script will not warn you about this.

The order the patterns are specified in is not important. All matching is
case-sensitive.

**Operation mode.** The script can run in either "attribute" or "table" mode. The
default is "table" mode. "Attribute" mode can be selected with the `--attribute-mode`
switch.

In **table** mode, all of the attributes (columns) that are of either extended or 
external storage mode are copied out to `/dev/null` at once. This is fast, but
the error that comes back (if there's a problem) does not identify the particular
column or row that triggered the error.

In **attribute** mode, the table is scanned one row at a time, one attribute at
a time. This is much slower than table mode, but it allows pinpointing the row(s)
and attribute(s) that are having problems.

The suggested approach (if you don't already know which table is the problem) is
to scan the database using table mode, and then re-scan any problematic tables
with attribute mode.

To scan in attribute mode requires that the table have a primary key; a primary
key is not required for table mode.

**Miscellaneous**

* `-v` / `--verbosity` -- Increases the amount of output. Right now, there's no
extra output from specifying it more than twice, although that's allowed.
* `-q` / `--quiet` -- Silence all non-error output. This takes precedence
over `verbosity`.

**Status Code**

The script returns status code 0 if no problems are found, status code 1 if
a data error is found, and status code 2 for other situations (such as
parameter errors).

## Credits

Written by Christophe Pettus <christophe.pettus@pgexperts.com>. Thanks
to Josh Berkus for the original blog post that inspired the first
version of the script, and Quinn Weaver and Lukas Fittl for their
work on the first version.