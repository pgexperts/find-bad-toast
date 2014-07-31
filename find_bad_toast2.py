#!/usr/bin/env python

import argparse
import psycopg2

"""

"""

"""
find_bad_toast_2 - *****************

Scan a PostgreSQL table for rows with corrupted TOAST records.

Arguments:

- conn is an open database handle

- table is the name of the table to scan

- pks is a sequence of column names. These are the columns that compose
the primary key of the column. Of course, there may be only one such column.

This is a translation, for performance reasons, from plpgsql to Python,
of the logic described at
*** http://www.databasesoup.com/2014/07/improved-toast-corruption-function.html.

The performance reasons are a) to avoid keeping a transaction open for the
initial whole-table scan, which is painful for large tables, and b) to improve
upon the performance of plpgsql as a language.


"""
def find_bad_toast_2(conn, table, pk_dict):

    ids_cur = conn.cursor()
    pk_columns = ', '.join(pk_dict.keys())
    ids_cur.execute('SELECT {pks} FROM {table}'.format(pks=pks, table=table))

    count = 0
    ids = None
    copy_cur = conn.cursor()
    while ids = cur.fetchone():
        count += 1
        if (count % 100000 = 0):
            print '{count} rows inspected'.format(count=count)

        try:
            copy_query = 'COPY (SELECT * FROM {table} WHERE'.format(table=table)

            where_clauses = []
            for col in pks.keys():
                where_clauses += '{col} = ?'.format(col=pk_col)

            copy_query += ' AND'.join(where_clauses)

            # copy_cur.execute(copy_query)
            print copy_query

def main():
    parser = argparse.ArgumentParser(description='Find corrupt rows in a table.')
    parse.add_Argument('-t', '--table', required=True)
    parser.addArgument('-p', '--pks', required=True)
    parser.addArgument('--connect-string', required=True)
    args = ArgParser.parse_arguments()
    
    conn = psycopg2.connect(args.connect_string)

    pk_dict = {}
    pk_pairs = args.pks.split()
    for pair in pk_pairs:
        if '=' not in pair:
            raise argparse.ArgumentError(
                '''Argument to -p or --pks must be one or more col=value pairs,
                separated by whitespace''')

        (col, value) = pair.split('=')
        if col in pk_dict:
            raise argparse.ArgumentError(
                'You passed a duplicate PK value for column "{c}"'.format(c=col)

        pk_dict{col} = value

    find_bad_toast2(conn, args.table, pk_dict)

if __name__ = '__main__':
    main()
