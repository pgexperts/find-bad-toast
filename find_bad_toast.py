#!/usr/bin/env python
from typing import Dict, List, Tuple

import re
import sys
import argparse

import asyncio
import asyncpg
import humanize

#

EXCLUDE_SCHEMAS = ['information_schema', 'pg_catalog']

def glob_to_regex(glob) -> str | None:
    if not glob:
        return None

    regex = glob
    regex = regex.replace('.', r'\.')
    regex = regex.replace('*', r'.*')
    regex = regex.replace('?', '.')

    return regex

def globs_to_regex(globs: List[str] | None) -> str | None:
    if not globs:
        return None

    return '^' + '|'.join([f"({glob_to_regex(glob)})" for glob in globs if glob]) + '$'

def match_regex(name, yes_regex: str | None, no_regex: str | None) -> bool:
    if yes_regex:
        yes = bool(re.match(yes_regex, name))
    else:
        yes = True

    if no_regex:
        no = bool(re.match(no_regex, name))
    else:
        no = False

    return yes and not no

async def find_all_tables(conn: 'asyncpg.connection.Connection',
                          include_schemas: List[str] | None=None,
                          exclude_schemas: List[str] | None=None,
                          include_tables: List[str] | None=None,
                          exclude_tables: List[str] | None=None,
                          ):
    # Finds all user tables in the database we're connected to, filtering by the provided
    # globs (which are converted to regexes).

    # Returns them as an iteration of (schema_name, table_name) tuples.

    schema_yes_regex = globs_to_regex(include_schemas)
    schema_no_regex = globs_to_regex(exclude_schemas)
    table_yes_regex = globs_to_regex(include_tables)
    table_no_regex = globs_to_regex(exclude_tables)

    for row in await conn.fetch("""
        SELECT table_schema, table_name
          FROM information_schema.tables
         WHERE NOT(table_schema = ANY($1::varchar[]))
          ORDER BY table_schema, table_name
        """, EXCLUDE_SCHEMAS):

        schema_name, table_name = row['table_schema'], row['table_name']

        if match_regex(schema_name, schema_yes_regex, schema_no_regex) and \
           match_regex(table_name, table_yes_regex, table_no_regex):
            yield schema_name, table_name


async def find_pk_and_extended(conn: 'asyncpg.connection.Connection',
                               schemaname:str,
                               tablename:str,
                               verbosity:int = 1) -> Dict[str, List[str]] | None:
    # For a given table, find its primary key columns, and any columns with
    # storage mode 'extended' (potentially TOASTed).

    row = await conn.fetchrow("""
        SELECT array_agg(a.attname) as primary_key_columns
            FROM   pg_index i
            JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                 AND a.attnum = ANY(i.indkey)
            WHERE  i.indrelid = $1::regclass
            AND    i.indisprimary;
        """, f"{schemaname}.{tablename}")

    if row['primary_key_columns']:
        result = {'primary_key_columns': row['primary_key_columns']}
    else:
        result = {'primary_key_columns': []}

    row = await conn.fetchrow("""
        SELECT array_agg(a.attname) as extended_attributes
            FROM   pg_class t
            JOIN   pg_attribute a ON a.attrelid = t.oid
            WHERE  t.oid = $1::regclass
              AND  (a.attstorage = 'e' OR a.attstorage = 'x')
        """, f"{schemaname}.{tablename}")

    if not row['extended_attributes']:
        if verbosity > 1:
            print(f"{schemaname}.{tablename} does not any extended or external attributes, skipping")
        return None

    result['extended_attributes'] = row['extended_attributes']

    return result

async def check_table(conn: 'asyncpg.connection.Connection', schemaname:str,
                      tablename:str,
                      pk_and_extended: Dict[str, List[str]],
                      verbosity:int = 1,
                      attribute_mode:bool=False) -> bool:


    if not attribute_mode:
        if verbosity > 0:
            print(f"{schemaname}.{tablename}: checking {', '.join(pk_and_extended['extended_attributes'])}")

        query = f"""COPY ( SELECT {', '.join(['"' + attr + '"' for attr in pk_and_extended['extended_attributes']])} 
                           FROM "{schemaname}"."{tablename}"
                         ) TO '/dev/null'
                    """
        try:
            await conn.execute(query)
        except Exception as e:
            print(f"{schemaname}.{tablename}: {e}", file=sys.stderr)
        return False

    pks = pk_and_extended['primary_key_columns']
    if not pks:
        print(f"{schemaname}.{tablename} does not have a primary key column, skipping in attribute mode", file=sys.stderr)
        return True

    attributes = pk_and_extended['extended_attributes']

    where_predicate = ' AND '.join(f'"{pk}"=${ordinal+1}' for ordinal, pk in enumerate(pks))
    if where_predicate:
        where_clause = f"WHERE {where_predicate}"
    else:
        where_clause = ''

    select_list = ', '.join(pks)

    for attribute in attributes:
        max_size_for_attr = 0

        query = f"""SELECT md5("{attribute}"::text) as hash, pg_column_size("{attribute}") as len
                           FROM "{schemaname}"."{tablename}"
                           {where_clause}
                    """

        row_count = 0

        for row in await conn.fetch(f"""
            SELECT {select_list} FROM "{schemaname}"."{tablename}"
            """):

            pk_values = [ v for v in row.values() ]

            try:
                row = await conn.fetchrow(query, *pk_values)
                if row and row['len']:
                    max_size_for_attr = max(max_size_for_attr, row['len'])
            except Exception as e:
                print(f"{schemaname}.{tablename}.{attribute} @ {', '.join([pk + '=' + str(pkv) for pk, pkv in zip(pks, pk_values)])}: {e}", file=sys.stderr)
                return False

            row_count += 1
            if (row_count % 10000) == 0:
                if verbosity > 1:
                    print(f"{schemaname}.{tablename}.{attribute} {row_count} rows checked")

        if verbosity > 0:
            print(f"{schemaname}.{tablename}.{attribute} {row_count} rows checked, max size={humanize.intword(max_size_for_attr)}")

    return True

async def main(specific_tables: List[str],
               include_schemas: List[str] | None=None,
               exclude_schemas: List[str] | None=None,
               include_tables: List[str] | None=None,
               exclude_tables: List[str] | None=None,
               verbosity:int = 1,
               attribute_mode:bool = False,
               read_only:bool = False,
                **db_conn_parameters: Dict[str, str],
               ) -> bool:

    conn = await asyncpg.connect(**db_conn_parameters)

    if read_only:
        await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")

    something_bad = False

    try:
        tables = [(schema_name, table_name)
                  async for (schema_name, table_name) in find_all_tables(conn,
                                                                         include_schemas,
                                                                         exclude_schemas,
                                                                         include_tables,
                                                                         exclude_tables,
                                                                         )]

        if specific_tables:
            chosen_tables = []
            for stable in specific_tables:
                if '.' in stable:
                    specific_schema_table = tuple(stable.split('.', 1))
                else:
                    specific_schema_table = ('public', stable)

                if specific_schema_table not in tables:
                    print(f"{stable} not found in database, or filtered out", file=sys.stderr)
                    continue

                chosen_tables.append(specific_schema_table)

            tables = chosen_tables
        else:
            if not tables:
                print("no tables found (did the exclude criteria filter them all out?", file=sys.stderr)
                return True

        for schema_name, table_name in tables:
            pk_and_extended = await find_pk_and_extended(conn, schema_name, table_name, verbosity=verbosity)
            if not pk_and_extended:
                continue

            something_bad |= await check_table(conn, schema_name, table_name, pk_and_extended, verbosity=verbosity, attribute_mode=attribute_mode)

    finally:
        await conn.close()

    return something_bad

def entrypoint():
    parser = argparse.ArgumentParser(prog="find_bad_toast",
                                     description="Scan a PostgreSQL database to find corrupted TOAST records",
                                     epilog="password must be supplied by a .pgpass file, or peer/trust authentication",
                                     add_help=False,
                                     )

    parser.add_argument('tables', nargs='*', action='extend', default=list())

    parser.add_argument("--attribute-mode", help="read each attribute individually (slower, more precise)",
                        action='store_true', default=False)

    parser.add_argument("-t", "--table", help="pattern of table names to include", nargs='*', action='extend',
                        default=list())
    parser.add_argument("-T", "--exclude-table", help="pattern of table names to exclude", nargs='*', action='extend',
                        default=list())
    parser.add_argument("-n", "--schema", help="pattern of schema names to include", nargs='*', action='extend',
                        default=list())
    parser.add_argument("-N", "--exclude-schema", help="pattern of schema names to include", nargs='*', action='extend',
                        default=list())

    parser.add_argument("-d", "--dbname", help="database name or connection string", default='')
    parser.add_argument("-h", "--host", help="database server host address", default='')
    parser.add_argument("-p", "--port", help="database server port address", default='')
    parser.add_argument("-U", "--username", help="database username", default='')

    parser.add_argument("-x", "--read-only", help="set the session default to read-only", action='store_true', default=False)
    parser.add_argument("-v", "--verbosity", help="increase the output detail, up to -vvv", action='count', default=1)
    parser.add_argument("-q", "--quiet", help="silence all non-error output", action='store_true', default=False)

    args = parser.parse_args()

    specific_tables = args.tables

    attribute_mode = args.attribute_mode

    include_schemas = args.schema
    exclude_schemas = args.exclude_schema
    include_tables = args.table
    exclude_tables = args.exclude_table

    verbosity = args.verbosity
    if args.quiet:
        verbosity = 0

    read_only = args.read_only

    db_conn_parameters = dict()

    if args.dbname:
        db_conn_parameters['database'] = args.dbname

    if args.host:
        db_conn_parameters['host'] = args.host

    if args.port:
        db_conn_parameters['port'] = args.port

    if args.username:
        db_conn_parameters['username'] = args.username

    something_bad = asyncio.run(
        main(specific_tables,
             include_schemas=include_schemas,
             exclude_schemas=exclude_schemas,
             include_tables=include_tables,
             exclude_tables=exclude_tables,
             verbosity=verbosity,
             attribute_mode=attribute_mode,
             read_only=read_only,
             **db_conn_parameters))

    if something_bad:
        exit(1)

if __name__ == '__main__':
    entrypoint()

