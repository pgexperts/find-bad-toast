# find_bad_toast.py

This is a script for scanning the extended and external attributes of a PostgreSQL database,
looking for corrupt rows. The most common and obvious types of TOAST table corruption
result in an error when the TOAST value is read in, and this script goes through each
table, reading in each such attribute, to see if an error results.

It requires **Python 3.11** or higher. The dependencies are listed in the `pyproject.toml` 
and `requirements.txt` files.

It has been tested with PostgreSQL 18. It should run on any version of PostgreSQL
supported by [asyncpg](https://github.com/MagicStack/asyncpg), 
which is currently version 9.5 and later.

It has only been tested on Linux.

## Usage

```sh
./find_bad_toast.py [options] [tables...]
```

### Command-Line Options

The positional arguments are a list of tables to scan. They can be either
table names without a schema (in which case `public` is assumed), or they
can be qualified: `myschema.mytable`. If the table cannot be found, a
warning message is emitted and the table is ignored.

Specific tables mentioned here *are* filtered by the filtering options
below.

#### DB connection options.

These are the same as `pg_dump` and other PostgreSQL
tools:

* `-d` / `--dbname` -- The database name, or a 
[standard PostgreSQL connection string](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING).
* `-h` / `--host` -- The host to connet to.
* `-p` / `--port` -- The port to connect to.
* `-U` / `--username` -- The username to use for connection.

The script will not prompt for a password if one is required. The password
can be specified in a `.pgpass` file, or the account being used is
set up with `peer` authentication if it is local. (Never use `trust`
authentication!)

#### Table and schema filtering options.

These are the same as `pg_dump`:

* `-t` / `include-table`
* `-T` / `exclude-table`
* `-n` / `include-schema`
* `-N` / `exclude-schema`

Each option may be specified more than once, and they may be combined.

All of the patterns used to match table and schema names are case-insensitive.
The patterns are glob-like:

* `*` matches any number of characters at its position, including none.
* `?` matches exactly one character at its position.

For a table to be processed, it must match *any* of the `include` patterns, and must
match *none* of the `exclude` patterns. The script does not check to see if the
patterns make sense together, so:

```bash
--include-table=food* --exclude-table=foo*
```

... will not match any tables, and the script will not warn you about this.

The order the patterns are specified in is not important. All matching is
case-sensitive.

The script currently does not support escaping `*` and `?`,
but if you have an `*` or a `?` in your table name, what are you even doing?

#### Operation mode.

The script can run in either "attribute" or "table" mode. The
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
with attribute mode. The script will run through the entire set of tables in 
attribute mode if desired; this will take a long time.

In attribute model, the table primary key will be used to identify records if
the table has one. Otherwise, the `ctid` is used.

#### Miscellaneous options.

* `-x` / `--read-only` -- If set, the session will be set to a default
transaction mopde of `READ ONLY`. The script does not do any writing, so
this does not change its behavior, but it is useful in two ways:
  * It is a reassuring extra check that the script will not modify the database.
  * If the default transaction mode in the system is `SERIALIZABLE`, it can
  help prevent the queries this script is running from causing false-positive
  serialization failures.
  * **Note:** If turned on, the script will need a persistent connection to the
  database server. This prevents it from  being used with a pooler such
  as [PgBouncer](https://www.pgbouncer.org) in transaction mode.
* `-v` / `--verbosity` -- Increases the amount of output. Right now, there's no
extra output from specifying it more than twice, although that's allowed.
* `-q` / `--quiet` -- Silence all non-error output. This takes precedence
over `verbosity`.

### Status Code

The script returns status code 0 if no problems are found, status code 1 if
a database error is found, and status code 2 for other situations (such as
parameter errors).

## Warnings

The script currently does not distinguish between data corruption and other
types of problems, such as disconnections. It does report the error message
returned by the server, so that false positives can be diagnosed.

Be judicious about running this script against a production server. It generates
a lot of I/O, and will run a large number of pages through shared buffers,
potentially evicting more important data.

It does no writes to the database, so it is safe to run it as a read-only
user. It does not create any transactions except for those on
the single queries it runs.

## Credits

Written by Christophe Pettus <christophe.pettus@pgexperts.com>. Thanks
to Josh Berkus for the original blog post that inspired the first
version of the script, and Quinn Weaver and Lukas Fittl for their
work on the first version.