from typing import Dict, List, Tuple

import re
import sys

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


async def find_pk_and_extended(conn: 'asyncpg.connection.Connection', schemaname:str, tablename:str) -> Dict[str, List[str]] | None:
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
        print(f"{schemaname}.{tablename} does not any extended or external attributes, skipping")
        return None

    result['extended_attributes'] = row['extended_attributes']

    return result

async def check_table(conn: 'asyncpg.connection.Connection', schemaname:str, tablename:str, pk_and_extended: Dict[str, List[str]], full_table:bool=False) -> None:
    if full_table:
        print(f"{schemaname}.{tablename}: checking {', '.join(pk_and_extended['extended_attributes'])}")

        query = f"""COPY ( SELECT {', '.join(pk_and_extended['extended_attributes'])} 
                           FROM {schemaname}.{tablename}
                         ) TO '/dev/null'
                    """
        try:
            await conn.execute(query)
        except Exception as e:
            print(f"{schemaname}.{tablename}: {e}", file=sys.stderr)
        return

    pks = pk_and_extended['primary_key_columns']
    if not pks:
        print(f"{schemaname}.{tablename} does not have a primary key column, skipping in attribute mode")
        return

    attributes = pk_and_extended['extended_attributes']

    where_predicate = ' AND '.join(f'{pk}=${ordinal+1}' for ordinal, pk in enumerate(pks))
    if where_predicate:
        where_clause = f"WHERE {where_predicate}"
    else:
        where_clause = ''

    select_list = ', '.join(pks)


    for attribute in attributes:
        max_size_for_attr = 0

        query = f"""SELECT md5({attribute}::text) as hash, pg_column_size({attribute}) as len
                           FROM {schemaname}.{tablename}
                           {where_clause}
                    """

        row_count = 0

        for row in await conn.fetch(f"""
            SELECT {select_list} FROM {schemaname}.{tablename}
            """):

            pk_values = [ v for v in row.values() ]

            try:
                row = await conn.fetchrow(query, *pk_values)
                if row and row['len']:
                    max_size_for_attr = max(max_size_for_attr, row['len'])
            except Exception as e:
                print(f"{schemaname}.{tablename}.{attribute} @ {', '.join([pk + '=' + str(pkv) for pk, pkv in zip(pks, pk_values)])}: {e}", file=sys.stderr)

            row_count += 1
            if (row_count % 10000) == 0:
                print(f"{schemaname}.{tablename}.{attribute} {row_count} rows checked")

        print(f"{schemaname}.{tablename}.{attribute} {row_count} rows checked, max size={humanize.intword(max_size_for_attr)}")

async def main(full_table=False, **db_conn_parameters) -> None:
    conn = await asyncpg.connect(**db_conn_parameters)

    tables = [(schemaname, tablename) async for (schemaname, tablename) in find_all_tables(conn)]

    for schemaname, tablename in tables:
        pk_and_extended = await find_pk_and_extended(conn, schemaname, tablename)
        if not pk_and_extended:
            continue

        await check_table(conn, schemaname, tablename, pk_and_extended, full_table=full_table)

if __name__ == '__main__':

    asyncio.run(main(database='df'))