#!/usr/bin/env python

import argparse
import psycopg2

"""

"""

"""
find_bad_toast_2 - *****************

Scan a PostgreSQL table for rows with corrupted TOAST records.

Arguments:

- connect_string is psycopg2 connection string.

- table is the name of the table to scan.

- pks is a sequence of column names. These are the columns that compose
the primary key of the column. Of course, there may be only one such column.

This is a translation, for performance reasons, from plpgsql to Python,
of the logic described at
*** http://www.databasesoup.com/2014/07/improved-toast-corruption-function.html

The performance reasons are a) to avoid keeping a transaction open for the
initial whole-table scan, which is painful for large tables, and b) to improve
upon the performance of plpgsql as a language.

"""
def find_bad_toast_2(connect_string, table, pks):
    conn = psycopg2.connect(connect_string)
    
    ids_cur = conn.cursor()
    pk_cols = ', '.join(pks)
    ids_cur.execute('SELECT {p} FROM {table}'.format(p=pk_cols, table=table))

    count = 0
    copy_cur = conn.cursor()
    while True:
        ids = cur.fetchone()
        if not ids:
            break

        count += 1
        if count % 100000 == 0:
            print '{count} rows inspected'.format(count=count)

        try:
            copy_query = 'COPY (SELECT * FROM {table} WHERE'.format(table=table)

            where_clauses = []
            for col in pks(): where_clauses += '{col} = ?'.format(col=col)
            copy_query += ' AND'.join(where_clauses)

            # copy_cur.execute(copy_query, ids)
            print copy_query

        except Exception as e:
            print str(e)


def main():
    parser = argparse.ArgumentParser(
        description='Find rows in a table that have corrupted TOAST values.'
    )
    parse.add_Argument('-t', '--table', required=True)
    parser.addArgument('-p', '--pks', required=True, action='append')
    parser.addArgument('--connect-string', required=True)
    args = ArgParser.parse_arguments()
    
    find_bad_toast2(args.connect_string, args.table, args.pks)


if __name__ = '__main__':
    main()
